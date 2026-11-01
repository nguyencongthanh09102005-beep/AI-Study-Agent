/* A real study room, not a demo: all content comes from the saved,
   syllabus-verified roadmap, and timer transitions are committed by Flask.
*/
import React,{useEffect,useRef,useState} from 'react';
import {
  ActivityIndicator, Alert, AppState, ScrollView, StyleSheet, Text,
  TouchableOpacity, View,
} from 'react-native';
import { api } from './api';

const pad = n => String(n).padStart(2,'0');
function elapsedLabel(n) {
  const sec = Math.max(0,Math.floor(Number(n)||0));
  return pad(Math.floor(sec/3600))+':'+pad(Math.floor(sec/60)%60)+':'+pad(sec%60);
}
function ListBlock({title,values,empty}) {
  const arr = Array.isArray(values) ? values : [];
  return <View style={styles.card}>
    <Text style={styles.heading}>{title}</Text>
    {arr.length ? arr.map((item,i) => (
      <View key={i} style={styles.bulletRow}>
        <Text style={styles.bullet}>✓</Text>
        <Text style={styles.detail}>{typeof item === 'string' ? item :
          String(item?.title || item?.name || '')}</Text>
      </View>
    )) : <Text style={styles.faint}>{empty||'Chưa có nội dung.'}</Text>}
  </View>;
}

export default function StudyRoom({taskId,onBack,onOpenQuiz,onContext}) {
  const [data,setData] = useState(null);
  const [error,setError] = useState('');
  const [busy,setBusy] = useState(false);
  const [loading,setLoading] = useState(true);
  const [tab,setTab] = useState('content');
  const [clock,setClock] = useState(Date.now());
  const [sessionQuiz,setSessionQuiz] = useState(null);
  const [quizPreparation,setQuizPreparation] = useState(null);
  const [quizBusy,setQuizBusy] = useState(false);
  const [quizError,setQuizError] = useState('');
  const quizCsrf=useRef('');
  const quizActionPending=useRef(false);
  const flight=useRef(false);
  const csrf=useRef('');
  const lastSync=useRef(Date.now());

  useEffect(()=>{
    let active=true;
    setLoading(true);
    setData(null);
    setError('');
    api.studyRoom(taskId).then(body=>{
      if(!active)return;
      setData(body);
      csrf.current=body.timer_csrf||'';
      lastSync.current=Date.now();
      onContext?.({
        taskId,subjectId:body.task.subject_id,
        chapterNumber:body.lesson.unit_id,sources:body.sources||[]
      });
    }).catch(err=>{if(active)setError(err.message||'Không mở được buổi học.');})
      .finally(()=>{if(active)setLoading(false);});
    return ()=>{active=false;onContext?.(null);};
  },[taskId]);

  const sendAction=async action=>{
    if (flight.current||!csrf.current)return;
    flight.current=true;
    setBusy(true);
    setError('');
    try {
      const result=await api.studyTimer(taskId,action,csrf.current);
      setData(previous=>previous?{...previous,timer:result}:previous);
      lastSync.current=Date.now();
    }catch(err){
      setError(err.message||'Không lưu được phiên học.');
      // Re-read authoritative state; never fake an optimistic completion.
      try {
        const fresh=await api.studyRoom(taskId);
        setData(fresh);
        csrf.current=fresh.timer_csrf;
      }catch(_error){}
    }finally{flight.current=false;setBusy(false);}
  };

  const refreshQuiz=async (subjectId=data?.task?.subject_id)=>{
    if (!subjectId) return;
    try {
      const [state,prep]=await Promise.all([
        api.sessionQuizStatus(taskId),
        api.quizPreparation(subjectId)
      ]);
      setSessionQuiz(state);
      setQuizPreparation(prep);
      quizCsrf.current=state.quiz_csrf||prep.quiz_csrf||'';
      setQuizError('');
    } catch(err) {
      setQuizError(err.message||'Không kiểm tra được tình trạng Quiz.');
    }
  };
  useEffect(()=>{
    if(!data?.task?.subject_id) return;
    let active=true;
    const id=data.task.subject_id;
    // Readiness always comes from Flask; no local guess about unlock time.
    const fetchStatus=async()=>{
      try{
        const [state,prep]=await Promise.all([
          api.sessionQuizStatus(taskId),api.quizPreparation(id)
        ]);
        if(!active)return;
        setSessionQuiz(state);
        setQuizPreparation(prep);
        quizCsrf.current=state.quiz_csrf||prep.quiz_csrf||'';
        setQuizError('');
      }catch(err){if(active)setQuizError(err.message||'Không đọc được Quiz.');}
    };
    fetchStatus();
    return()=>{active=false;};
  },[taskId,data?.task?.subject_id]);
  useEffect(()=>{
    if(!data?.task?.subject_id) return;
    const job=quizPreparation?.job?.state;
    const lesson= sessionQuiz?.state;
    // Both the timer and the unlock decision live on Flask. Poll modestly
    // while relevant, including a prepared Quiz approaching its start time.
    const intervalMs=['queued','running'].includes(job)?12000:
      ['locked','available','active'].includes(lesson)?30000:null;
    if(!intervalMs)return;
    const interval=setInterval(()=>{
      if(AppState.currentState==='active')refreshQuiz();
    },intervalMs);
    return()=>clearInterval(interval);
  },[taskId,data?.task?.subject_id,quizPreparation?.job?.state,sessionQuiz?.state]);

  useEffect(()=>{
    if(!data?.task?.subject_id)return;
    let active=true;
    const listener=AppState.addEventListener('change',state=>{
      if(state!=='active')return;
      // iOS pauses JS timers while the phone sleeps. Re-read real elapsed
      // seconds and Quiz unlock on foreground; never fabricate lost time.
      api.studyRoom(taskId).then(fresh=>{
        if(!active)return;
        setData(fresh);
        csrf.current=fresh.timer_csrf||'';
        lastSync.current=Date.now();
        onContext?.({
          taskId, subjectId:fresh.task.subject_id,
          chapterNumber:fresh.lesson.unit_id,sources:fresh.sources||[]
        });
      }).catch(err=>{
        if(!active)return;
        setData(null);
        onContext?.(null);
        setError(err.message||'Buổi học không còn hợp lệ. Hãy mở lại từ lịch.');
      });
      refreshQuiz();
    });
    return()=>{active=false;listener.remove();};
  },[taskId,data?.task?.subject_id]);

  const quizQueue=async action=>{
    if(!data?.task?.subject_id||quizActionPending.current||!quizCsrf.current)return;
    quizActionPending.current=true;
    setQuizBusy(true);
    setQuizError('');
    try{
      await api.quizPreparationAction(
        data.task.subject_id,action,quizCsrf.current
      );
      await refreshQuiz();
    }catch(err){
      setQuizError(err.message||'Không cập nhật được hàng đợi Quiz.');
    }finally{setQuizBusy(false);quizActionPending.current=false;}
  };
  const beginSessionQuiz=async()=>{
    if(quizActionPending.current||!quizCsrf.current||!sessionQuiz?.quiz_id)return;
    quizActionPending.current=true;
    setQuizBusy(true);
    setQuizError('');
    try{
      const result=await api.sessionQuizStart(taskId,quizCsrf.current);
      if(!result?.quiz_id)throw new Error('Quiz chưa có thể mở.');
      onOpenQuiz({quizId:result.quiz_id,subjectId:data.task.subject_id});
    }catch(err){
      setQuizError(err.message||'Quiz vẫn bị khóa hoặc học liệu đã thay đổi.');
      await refreshQuiz();
    }finally{setQuizBusy(false);quizActionPending.current=false;}
  };

  useEffect(()=>{
    const tick=setInterval(()=>setClock(Date.now()),1000);
    return()=>clearInterval(tick);
  },[]);
  useEffect(()=>{
    if(data?.timer?.status!=='running')return undefined;
    const heartbeat=setInterval(()=>{sendAction('heartbeat');},15000);
    return()=>clearInterval(heartbeat);
  },[data?.timer?.status,taskId]);

  const timer=data?.timer||{};
  const elapsed=(timer.elapsed_seconds||0)+(timer.status==='running'
    ? Math.min(45,Math.floor((clock-lastSync.current)/1000)):0);

  const done=()=>{
    Alert.alert('Hoàn thành buổi học?',
      'Thời gian học và tiến độ sẽ được lưu trên hệ thống.',
      [{text:'Hủy',style:'cancel'},{text:'Hoàn thành',onPress:()=>sendAction('finish')}]);
  };
  if(loading)return <View style={styles.center}><ActivityIndicator size="large" color="#5C69DE"/>
    <Text style={styles.faint}>Đang xác minh lộ trình và buổi học...</Text></View>;
  return <ScrollView style={styles.root} contentContainerStyle={styles.page}>
    <TouchableOpacity onPress={onBack} style={styles.back}>
      <Text style={styles.backText}>← Quay về lịch học</Text>
    </TouchableOpacity>
    {!!error && <Text style={styles.error}>{error}</Text>}
    {!data ? <View style={styles.card}><Text style={styles.faint}>Buổi học chưa thể mở. Kiểm tra đề cương và lộ trình trên Web.</Text></View> : <>
      <Text style={styles.title}>Không gian học tập</Text>
      <Text style={styles.subtitle}>{data.subject?.name} · Chương {data.lesson?.unit_id}</Text>
      <View style={styles.hero}>
        <Text style={styles.heroTop}>{data.task.study_at?.replace('T',' ').slice(0,16)}</Text>
        <Text style={styles.heroTitle}>{data.task.title}</Text>
        <Text style={styles.heroTop}>Dự kiến {data.task.duration} phút</Text>
      </View>
      <View style={styles.timerCard}>
        <Text style={styles.heading}>◷ Đồng hồ học tập</Text>
        <Text style={styles.timer}>{elapsedLabel(elapsed)}</Text>
        <Text style={styles.timerStatus}>{
          timer.status==='running'?'Đang học · đồng bộ máy chủ':
          timer.status==='paused'?'Đã tạm dừng':
          timer.status==='completed'?'✓ Đã hoàn thành':'Chưa bắt đầu'
        }</Text>
        <View style={styles.buttons}>
          {timer.status==='idle'&&<TouchableOpacity disabled={busy}
            style={styles.action} onPress={()=>sendAction('start')}>
            <Text style={styles.actionText}>▶ Bắt đầu học</Text>
          </TouchableOpacity>}
          {timer.status==='running'&&<TouchableOpacity disabled={busy}
            style={styles.action} onPress={()=>sendAction('pause')}>
            <Text style={styles.actionText}>Ⅱ Tạm dừng</Text>
          </TouchableOpacity>}
          {timer.status==='paused'&&<TouchableOpacity disabled={busy}
            style={styles.action} onPress={()=>sendAction('resume')}>
            <Text style={styles.actionText}>▶ Tiếp tục</Text>
          </TouchableOpacity>}
          {['running','paused'].includes(timer.status)&&
            <TouchableOpacity disabled={busy} style={styles.outline}
              onPress={done}><Text style={styles.outlineText}>✓ Hoàn thành</Text>
            </TouchableOpacity>}
        </View>
        {busy&&<ActivityIndicator color="#5969DB" style={{marginTop:12}}/>}
      </View>
      <View style={styles.tabs}>
        {[['content','Nội dung'],['documents','Tài liệu'],['activities','Hoạt động']].map(([key,label])=>
          <TouchableOpacity key={key} onPress={()=>setTab(key)}
            style={[styles.tab,tab===key&&styles.tabActive]}>
            <Text style={[styles.tabText,tab===key&&styles.tabTextActive]}>{label}</Text>
          </TouchableOpacity>
        )}
      </View>
      {tab==='content'&&<>
        <ListBlock title="Mục tiêu buổi học" values={data.lesson.objectives}/>
        <ListBlock title="Tiểu mục cần học" values={data.lesson.topics}/>
        {!!data.lesson.clo_refs?.length &&
          <ListBlock title="Chuẩn đầu ra (CLO)" values={data.lesson.clo_refs}/>}
      </>}
      {tab==='documents'&&<ListBlock title="Học liệu dùng chung đã duyệt"
        values={data.sources?.map(item=>item.name)}
        empty="Chưa có PDF chung được duyệt cho chương này. Không dùng tài liệu chưa duyệt làm dẫn chứng."/>}
      {tab==='activities'&&<ListBlock title="Hoạt động & thực hành" values={data.lesson.activities}/>}
      <View style={styles.quizCard}>
        <Text style={styles.heading}>✦ Quiz kiểm tra theo buổi</Text>
        <Text style={styles.faint}>
          {sessionQuiz?.is_final?'Buổi tổng hợp · 60 câu':'Buổi thường · 15 câu'}
          {sessionQuiz?.count ? ' · '+sessionQuiz.count+' câu' : ''}
        </Text>
        {!sessionQuiz && <ActivityIndicator color="#5969DB" />}
        {!!sessionQuiz && <>
          <Text style={styles.detail}>{
            sessionQuiz.state==='review'?'Đã nộp · có thể xem lại đáp án và ôn tập':
            sessionQuiz.state==='active'?'Quiz đang mở trong khung giờ học':
            sessionQuiz.state==='available'?'Đã đến giờ · có thể bắt đầu':
            sessionQuiz.state==='locked'?'Quiz đã chuẩn bị nhưng chưa đến giờ mở':
            sessionQuiz.state==='unprepared'?'Quiz chưa được chuẩn bị trên máy chủ':
            sessionQuiz.reason || 'Học liệu chung của chương chưa đủ điều kiện'
          }</Text>
          {!!sessionQuiz.study_at &&
            <Text style={styles.faint}>Khung giờ: {sessionQuiz.study_at.replace('T',' ')}
              {sessionQuiz.ends_at ? ' – '+sessionQuiz.ends_at.slice(11,16):''}
            </Text>}
          {!!sessionQuiz.reason && <Text style={styles.faint}>{sessionQuiz.reason}</Text>}
          {sessionQuiz.attempt_count>0&&
            <Text style={styles.faint}>Đã nộp {sessionQuiz.attempt_count} lần · Điểm cao nhất {sessionQuiz.best_score??'—'}</Text>}
          {['review','active','available'].includes(sessionQuiz.state) &&
            <TouchableOpacity disabled={quizBusy} style={styles.action}
              accessibilityRole="button" onPress={beginSessionQuiz}>
              <Text style={styles.actionText}>{sessionQuiz.state==='review'?'Xem lại / Làm lại Quiz →':'Bắt đầu Quiz theo buổi →'}</Text>
            </TouchableOpacity>}
        </>}
        {!!quizPreparation&&<Text style={styles.faint}>
          Đã chuẩn bị {quizPreparation.ready||0}/{quizPreparation.total||0} Quiz
          {quizPreparation.job?.state==='queued'?' · Đang xếp hàng':''}
          {quizPreparation.job?.state==='running'?' · Đang tạo bằng AI':''}
        </Text>}
        {['queued','running'].includes(quizPreparation?.job?.state)?
          <TouchableOpacity disabled={quizBusy} onPress={()=>quizQueue('pause')}
            style={styles.outline}><Text style={styles.outlineText}>Tạm dừng chuẩn bị</Text></TouchableOpacity>:
          sessionQuiz?.state==='unprepared'&&
            <TouchableOpacity disabled={quizBusy} onPress={()=>quizQueue('start')}
              style={styles.outline}><Text style={styles.outlineText}>Chuẩn bị Quiz bằng AI</Text></TouchableOpacity>}
        <TouchableOpacity disabled={quizBusy} style={styles.quizLink}
          onPress={()=>refreshQuiz()}>
          <Text style={styles.quizText}>↻ Cập nhật trạng thái Quiz</Text>
        </TouchableOpacity>
        {!!quizError && <Text style={styles.error}>{quizError}</Text>}
        {quizBusy&&<ActivityIndicator color="#5969DB"/>}
      </View>
      <TouchableOpacity style={styles.quizLink} onPress={()=>onOpenQuiz({subjectId:data.task.subject_id})}>
        <Text style={styles.quizText}>Quiz khác & ôn điểm yếu →</Text>
      </TouchableOpacity>
      <Text style={styles.hint}>Bong bóng AI phía dưới sẽ hỏi theo đúng buổi học này khi có học liệu đã duyệt.</Text>
    </>}
  </ScrollView>;
}
const styles=StyleSheet.create({
  root:{flex:1,backgroundColor:'#F7F9FD'},
  page:{padding:16,paddingBottom:120,gap:13},
  center:{flex:1,alignItems:'center',justifyContent:'center',gap:15},
  back:{paddingVertical:7},backText:{color:'#5567DA',fontWeight:'700'},
  title:{fontSize:24,fontWeight:'800',color:'#1C294A'},
  subtitle:{fontSize:13,color:'#697999'},
  card:{backgroundColor:'#FFFFFF',padding:17,borderRadius:18,borderWidth:1,
    borderColor:'#E8EBF6',gap:10},
  heading:{fontSize:16,color:'#27365C',fontWeight:'800'},
  faint:{fontSize:13,color:'#8190AB',lineHeight:20},
  detail:{flex:1,fontSize:13,color:'#465A7A',lineHeight:21},
  bullet:{fontSize:14,color:'#5972DF',marginRight:8},
  bulletRow:{flexDirection:'row',alignItems:'flex-start',gap:5},
  hero:{backgroundColor:'#EAF0FF',padding:18,borderRadius:18,gap:7},
  heroTop:{fontSize:12,color:'#677DAE'},heroTitle:{fontSize:18,fontWeight:'800',color:'#2B407E'},
  timerCard:{alignItems:'center',backgroundColor:'#FFFFFF',padding:19,borderRadius:18,
    borderWidth:1,borderColor:'#DCE5FA',gap:9},
  timer:{fontSize:43,fontWeight:'800',color:'#5265D6',fontVariant:['tabular-nums']},
  timerStatus:{fontSize:12,color:'#7180A2'},
  buttons:{flexDirection:'row',justifyContent:'center',flexWrap:'wrap',gap:9,marginTop:8},
  action:{backgroundColor:'#576BE0',paddingHorizontal:17,paddingVertical:12,borderRadius:12},
  actionText:{color:'#FFFFFF',fontWeight:'800'},
  outline:{paddingHorizontal:15,paddingVertical:11,borderWidth:1,
    borderColor:'#A8B9EC',borderRadius:12},
  outlineText:{color:'#485FAD',fontWeight:'800'},
  tabs:{flexDirection:'row',backgroundColor:'#EDF1FC',borderRadius:12,padding:4,gap:4},
  tab:{flex:1,padding:10,borderRadius:10,alignItems:'center'},
  tabActive:{backgroundColor:'#FFFFFF'},
  tabText:{fontSize:12,fontWeight:'700',color:'#7786A8'},
  tabTextActive:{color:'#485EC4'},
  quizCard:{backgroundColor:'#FFFFFF',borderRadius:18,padding:17,gap:11,
    borderColor:'#DFE5F6',borderWidth:1},
  quizLink:{alignItems:'center',padding:14,backgroundColor:'#EAEFFF',borderRadius:12},
  quizText:{color:'#5266CC',fontWeight:'800'},
  hint:{fontSize:12,textAlign:'center',color:'#7180A2',lineHeight:19},
  error:{fontSize:13,color:'#AD3B4E',backgroundColor:'#FFF4F4',padding:12,borderRadius:10},
});
