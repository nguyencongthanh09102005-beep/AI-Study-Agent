/* Personal study room: private file, independent source-grounded Q&A,
   optional ten-question quiz, and the same server-authoritative timer as Web.
   Never mix private file text into shared/course Chat AI history. */
import React, {useEffect, useRef, useState} from 'react';
import {
  ActivityIndicator, Alert, AppState, ScrollView, StyleSheet,
  Text, TextInput, TouchableOpacity, View,
} from 'react-native';
import {File, Paths} from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import {api} from './api';

const pad=value=>String(value).padStart(2,'0');
function formatTime(seconds) {
  const n=Math.max(0,Math.floor(Number(seconds)||0));
  return [Math.floor(n/3600),Math.floor(n/60)%60,n%60].map(pad).join(':');
}

export default function ManualStudyRoom({taskId,onBack,onOpenQuiz}) {
  const [data,setData]=useState(null);
  const [busy,setBusy]=useState(false);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState('');
  const [clock,setClock]=useState(Date.now());
  const [question,setQuestion]=useState('');
  const [answer,setAnswer]=useState(null);
  const [chatBusy,setChatBusy]=useState(false);
  const [quizBusy,setQuizBusy]=useState(false);
  const [previewBusy,setPreviewBusy]=useState(false);
  const csrf=useRef('');
  const lastSync=useRef(Date.now());
  const flight=useRef(false);

  const reload=async()=>{
    const result=await api.manualRoom(taskId);
    csrf.current=result.csrf||'';
    lastSync.current=Date.now();
    setData(result);
    return result;
  };

  useEffect(()=>{
    let active=true;
    setLoading(true);setError('');setData(null);setAnswer(null);
    api.manualRoom(taskId).then(result=>{
      if(!active)return;
      csrf.current=result.csrf||'';
      lastSync.current=Date.now();
      setData(result);
    }).catch(err=>{
      if(active)setError(err.message||'Không mở được Không gian tự học.');
    }).finally(()=>{if(active)setLoading(false);});
    return()=>{active=false;};
  },[taskId]);

  useEffect(()=>{
    const timer=setInterval(()=>setClock(Date.now()),1000);
    return()=>clearInterval(timer);
  },[]);

  useEffect(()=>{
    if(data?.timer?.status!=='running')return;
    const timer=setInterval(()=>{
      if(AppState.currentState!=='active'||flight.current)return;
      sendTimerAction('heartbeat');
    },15000);
    return()=>clearInterval(timer);
  },[data?.timer?.status,taskId]);

  useEffect(()=>{
    const listener=AppState.addEventListener('change',state=>{
      if(state==='active'&&data) {
        reload().catch(err=>setError(err.message||'Chưa đồng bộ được đồng hồ.'));
      }
    });
    return()=>listener.remove();
  },[taskId,!!data]);

  const sendTimerAction=async action=>{
    if(flight.current||!csrf.current)return false;
    flight.current=true;setBusy(true);
    setError('');
    try {
      const result=await api.manualTimer(taskId,action,csrf.current);
      setData(old=>old?{...old,timer:result,task:{...old.task,done:!!result.done}}:old);
      lastSync.current=Date.now();
      return true;
    } catch(err) {
      setError(err.message||'Không lưu được thời gian học.');
      try {await reload();}catch(_ignore){}
      return false;
    } finally {
      flight.current=false;setBusy(false);
    }
  };

  const confirmFinish=()=>Alert.alert(
    'Hoàn thành buổi tự học?',
    'Đồng hồ và trạng thái hoàn thành sẽ được lưu trên cùng tài khoản Web và Mobile.',
    [
      {text:'Hủy',style:'cancel'},
      {text:'Hoàn thành',onPress:()=>sendTimerAction('finish')},
    ],
  );

  const askDocument=async()=>{
    if(chatBusy||!question.trim()||!csrf.current)return;
    setChatBusy(true);setError('');setAnswer(null);
    try {
      const result=await api.manualAsk(taskId,question.trim(),csrf.current);
      setAnswer(result);
    } catch(err) {
      setError(err.message||'AI chưa trả lời được theo tài liệu.');
    } finally {setChatBusy(false);}
  };

  const prepareQuiz=()=>{
    if(quizBusy||!csrf.current)return;
    Alert.alert(
      'Chuẩn bị Quiz 10 câu?',
      'Quiz chỉ dùng tài liệu cá nhân của buổi này. Chỉ tạo khi bạn xác nhận; có thể mất phí gọi AI.',
      [
        {text:'Hủy',style:'cancel'},
        {text:'Tạo Quiz',onPress:async()=>{
          setQuizBusy(true);setError('');
          try {
            const result=await api.manualPrepareQuiz(taskId,csrf.current);
            await reload();
            Alert.alert('Quiz đã sẵn sàng','Đã tạo bài Quiz 10 câu từ tài liệu này.',[
              {text:'Để sau'},
              {text:'Mở Quiz',onPress:()=>onOpenQuiz({
                subjectId:result.subject_id,quizId:result.quiz_id,
              })},
            ]);
          } catch(err) {
            setError(err.message||'Không chuẩn bị được Quiz từ tài liệu.');
          } finally {setQuizBusy(false);}
        }},
      ],
    );
  };

  const previewOriginal=async()=>{
    if(previewBusy)return;
    setPreviewBusy(true);setError('');
    try {
      const payload=await api.manualFile(taskId);
      const ext=(String(payload.name||'').match(/\.(pdf|docx|txt|md)$/i)||[])[0]||'.txt';
      // Filename is generated here, not taken from source content.
      const file=new File(Paths.cache,`aistudy-private-${taskId}-${Date.now()}${ext.toLowerCase()}`);
      file.create();
      await file.write(payload.base64,{encoding:'base64'});
      try {
        await file.preview({title:payload.name,mimeType:payload.type});
      } catch (err) {
        if(await Sharing.isAvailableAsync()) {
          await Sharing.shareAsync(file.uri,{
            mimeType:payload.type,dialogTitle:'Mở tài liệu học cá nhân',
          });
        } else {
          throw err;
        }
      }
      // The OS viewer may keep the file open. It lives only in this app's
      // temporary cache; avoid deleting it before the external viewer finishes.
    } catch(err) {
      setError(err.message||'Không mở được file gốc. Bạn vẫn có thể đọc nội dung đã trích xuất bên dưới.');
    } finally {setPreviewBusy(false);}
  };

  const timer=data?.timer||{};
  const elapsed=(timer.elapsed_seconds||0)+(timer.status==='running'
    ?Math.min(45,Math.floor((clock-lastSync.current)/1000)):0);

  const leave=()=>{
    if(timer.status!=='running')return onBack();
    Alert.alert('Đồng hồ đang chạy','Bạn nên tạm dừng trước khi rời Không gian tự học.',[
      {text:'Ở lại',style:'cancel'},
      {text:'Tạm dừng và thoát',onPress:async()=>{
        if (await sendTimerAction('pause')) onBack();
      }},
    ]);
  };
  if(loading) return <View style={styles.center}>
    <ActivityIndicator size="large" color="#5A69D9"/>
    <Text style={styles.faint}>Đang mở tài liệu tự học...</Text>
  </View>;

  return <ScrollView style={styles.root} contentContainerStyle={styles.page}
    keyboardShouldPersistTaps="handled">
    <TouchableOpacity accessibilityRole="button" onPress={leave} style={styles.back}>
      <Text style={styles.link}>← Về Kế hoạch học</Text>
    </TouchableOpacity>
    {!!error&&<Text style={styles.error}>{error}</Text>}
    {!data?<View style={styles.card}>
      <Text style={styles.faint}>Buổi học hoặc tài liệu đã thay đổi. Hãy kiểm tra lại trên Web.</Text>
    </View>:<>
      <Text style={styles.kicker}>KHÔNG GIAN TỰ HỌC · TÀI LIỆU CÁ NHÂN</Text>
      <Text style={styles.title}>{data.task.title}</Text>
      <Text style={styles.subtitle}>{data.subject.name} · {data.task.duration} phút</Text>

      <View style={styles.timerCard}>
        <Text style={styles.heading}>◷ Đồng hồ học tập</Text>
        <Text style={styles.timer}>{formatTime(elapsed)}</Text>
        <Text style={styles.faint}>
          {timer.status==='running'?'Đang học · đã đồng bộ với máy chủ':
           timer.status==='paused'?'Đã tạm dừng':
           timer.status==='completed'?'✓ Đã hoàn thành':'Chưa bắt đầu'}
        </Text>
        <View style={styles.actions}>
          {timer.status==='idle'&&<TouchableOpacity disabled={busy}
            accessibilityRole="button" style={styles.primary}
            onPress={()=>sendTimerAction('start')}>
            <Text style={styles.primaryText}>▶ Bắt đầu học</Text>
          </TouchableOpacity>}
          {timer.status==='paused'&&<TouchableOpacity disabled={busy}
            accessibilityRole="button" style={styles.primary}
            onPress={()=>sendTimerAction('resume')}>
            <Text style={styles.primaryText}>▶ Tiếp tục</Text>
          </TouchableOpacity>}
          {timer.status==='running'&&<TouchableOpacity disabled={busy}
            accessibilityRole="button" style={styles.outline}
            onPress={()=>sendTimerAction('pause')}>
            <Text style={styles.outlineText}>Ⅱ Tạm dừng</Text>
          </TouchableOpacity>}
          {['running','paused'].includes(timer.status)&&<TouchableOpacity
            accessibilityRole="button" disabled={busy} style={styles.outline}
            onPress={confirmFinish}><Text style={styles.outlineText}>✓ Hoàn thành</Text>
          </TouchableOpacity>}
        </View>
        {busy&&<ActivityIndicator color="#5869E0"/>}
      </View>

      <View style={styles.card}>
        <Text style={styles.heading}>📄 Tài liệu đã gắn</Text>
        <Text style={styles.fileName}>{data.document.name}</Text>
        <Text style={styles.faint}>Nội dung chỉ thuộc buổi tự học và tài khoản này.</Text>
        <TouchableOpacity accessibilityRole="button" style={styles.outline}
          disabled={previewBusy} onPress={previewOriginal}>
          {previewBusy?<ActivityIndicator color="#5364C9"/>:
          <Text style={styles.outlineText}>↗ Xem file gốc (PDF / Word / văn bản)</Text>}
        </TouchableOpacity>
        <Text style={styles.subhead}>Nội dung tài liệu</Text>
        {data.document.text ?
          <Text style={styles.extractedText} selectable>{data.document.text}</Text>:
          <Text style={styles.faint}>Không đọc được chữ từ tài liệu này. Nếu là PDF scan/ảnh, hãy mở file gốc; AI và Quiz cần văn bản đã trích xuất.</Text>}
        {data.document.preview_truncated&&
          <Text style={styles.faint}>Đang xem 18.000 ký tự đầu. File gốc chứa nhiều nội dung hơn.</Text>}
      </View>

      {!!data.task.note&&<View style={styles.card}>
        <Text style={styles.heading}>🎯 Ghi chú tự học</Text>
        <Text style={styles.extractedText}>{data.task.note}</Text>
      </View>}

      <View style={styles.card}>
        <Text style={styles.heading}>💬 Chat AI theo tài liệu</Text>
        <Text style={styles.faint}>Chỉ dựa trên file cá nhân này, không dùng nguồn không được xác minh.</Text>
        <TextInput multiline maxLength={700} value={question} onChangeText={setQuestion}
          placeholder="Ví dụ: Giải thích phần 1.1 trong file..."
          placeholderTextColor="#7D8BA9" style={styles.question}/>
        <TouchableOpacity disabled={chatBusy||!question.trim()||!data.document.text}
          accessibilityRole="button" style={styles.primary} onPress={askDocument}>
          {chatBusy?<ActivityIndicator color="white"/>:
          <Text style={styles.primaryText}>✦ Hỏi Study Agent</Text>}
        </TouchableOpacity>
        {!!answer?.response&&<View style={styles.answerBox}>
          <Text style={styles.answerSource}>Theo tài liệu: {answer.source}</Text>
          <Text selectable style={styles.extractedText}>{answer.response}</Text>
        </View>}
        {!!answer?.error&&<Text style={styles.error}>{answer.error}</Text>}
      </View>

      <View style={styles.card}>
        <Text style={styles.heading}>📝 Quiz 10 câu theo tài liệu</Text>
        {data.quiz.id?<TouchableOpacity style={styles.primary} accessibilityRole="button"
          onPress={async()=>{
            if(timer.status==='running' && !(await sendTimerAction('pause'))) return;
            onOpenQuiz({subjectId:data.task.subject_id,quizId:data.quiz.id});
          }}>
          <Text style={styles.primaryText}>▶ Mở Quiz đã chuẩn bị</Text>
        </TouchableOpacity>:<>
          <Text style={styles.faint}>Chỉ tạo bài khi bạn yêu cầu; không tự sinh Quiz mỗi lần mở buổi.</Text>
          <TouchableOpacity disabled={quizBusy||!data.document.text} style={styles.outline}
            accessibilityRole="button" onPress={prepareQuiz}>
            {quizBusy?<ActivityIndicator color="#5364C9"/>:
              <Text style={styles.outlineText}>✦ Chuẩn bị Quiz 10 câu</Text>}
          </TouchableOpacity>
        </>}
        {!!data.quiz.error&&<Text style={styles.error}>{data.quiz.error}</Text>}
      </View>
    </>}
  </ScrollView>;
}
const styles=StyleSheet.create({
  root:{flex:1,backgroundColor:'#F7F9FD'},
  page:{padding:17,paddingBottom:130,gap:15},
  center:{flex:1,justifyContent:'center',alignItems:'center',gap:16},
  back:{minHeight:45,justifyContent:'center',alignSelf:'flex-start'},
  link:{fontSize:14,fontWeight:'800',color:'#5968D4'},
  kicker:{fontSize:10,letterSpacing:1.1,fontWeight:'800',color:'#626FC4'},
  title:{fontSize:24,fontWeight:'800',color:'#1E2A4F',lineHeight:32},
  subtitle:{fontSize:13,color:'#6B7D9E'},
  card:{backgroundColor:'white',borderColor:'#E0E7F5',borderWidth:1,
    borderRadius:18,padding:17,gap:11},
  heading:{fontSize:16,color:'#2B3B67',fontWeight:'800'},
  subhead:{fontSize:13,color:'#4D63A4',fontWeight:'800',marginTop:6},
  fileName:{fontSize:14,color:'#293D6E',fontWeight:'800'},
  faint:{fontSize:12,lineHeight:19,color:'#667B9D'},
  extractedText:{fontSize:13,lineHeight:22,color:'#3C506F'},
  timerCard:{backgroundColor:'white',borderColor:'#CEDCF8',borderWidth:1,
    borderRadius:18,padding:20,gap:13,alignItems:'center'},
  timer:{fontSize:40,fontVariant:['tabular-nums'],fontWeight:'800',color:'#5366D5'},
  actions:{flexDirection:'row',flexWrap:'wrap',gap:10,justifyContent:'center'},
  primary:{minHeight:47,backgroundColor:'#5B68DF',borderRadius:12,
    paddingHorizontal:15,paddingVertical:12,alignItems:'center',justifyContent:'center'},
  primaryText:{fontSize:13,color:'white',fontWeight:'800'},
  outline:{minHeight:47,backgroundColor:'#EFF2FF',borderRadius:12,
    borderWidth:1,borderColor:'#CAD5F8',paddingHorizontal:13,paddingVertical:12,
    alignItems:'center',justifyContent:'center'},
  outlineText:{fontSize:13,color:'#4D5FB7',fontWeight:'800'},
  question:{minHeight:88,borderWidth:1,borderColor:'#D8E1F4',borderRadius:12,
    backgroundColor:'#FBFCFF',paddingHorizontal:12,paddingVertical:11,
    fontSize:14,textAlignVertical:'top',color:'#25385D'},
  answerBox:{padding:13,backgroundColor:'#F1F5FF',borderRadius:12,gap:9},
  answerSource:{fontSize:12,color:'#495E9E',fontWeight:'800'},
  error:{padding:11,borderRadius:10,fontSize:12,color:'#AC3647',
    backgroundColor:'#FFF0F1',lineHeight:19},
});
