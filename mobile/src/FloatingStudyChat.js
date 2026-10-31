/* In-app floating AI, available in Expo Go on iOS and Android.
   The component does NOT draw over other apps. It reuses the existing
   per-subject conversation and Web's source-verified lesson chat when learning.
*/
import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator, Animated, Dimensions, KeyboardAvoidingView, Modal,
  PanResponder, Platform, ScrollView, StyleSheet, Text, TextInput,
  TouchableOpacity, View,
} from 'react-native';
import { api } from './api';

const BLUE = '#5969DB';
const bounded = (v, a, b) => Math.max(a, Math.min(v, b));

export default function FloatingStudyChat({ subjects = [], lesson = null }) {
  const [opened, setOpened] = useState(false);
  const [subjectId, setSubjectId] = useState(null);
  const [history, setHistory] = useState([]);
  const [value, setValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [windowSize, setWindowSize] = useState(Dimensions.get('window'));
  const position = useRef(new Animated.ValueXY({x:0,y:0})).current;
  const currentXY = useRef({x:0,y:0});
  const latestLoad = useRef(0);
  const scroll = useRef(null);

  const scopedId = lesson?.subjectId || subjectId || subjects[0]?.id;
  const currentSubject = subjects.find(s => Number(s.id) === Number(scopedId));
  const lessonHasSources = !lesson || lesson.sources?.length > 0;
  useEffect(() => {
    if (lesson?.subjectId) setSubjectId(lesson.subjectId);
    else if (!subjectId && subjects.length) setSubjectId(subjects[0].id);
  }, [lesson?.subjectId, subjects, subjectId]);

  useEffect(() => {
    const sub = Dimensions.addEventListener('change', event => {
      setWindowSize(event.window);
      currentXY.current = {x:0,y:0};
      position.setValue({x:0,y:0});
    });
    return () => sub.remove();
  }, [position]);

  const responder = useMemo(() => PanResponder.create({
    onStartShouldSetPanResponder: () => false,
    onMoveShouldSetPanResponder: (_, gesture) =>
      Math.abs(gesture.dx) > 6 || Math.abs(gesture.dy) > 6,
    onPanResponderGrant: () => {
      position.setOffset(currentXY.current);
      position.setValue({x:0,y:0});
    },
    onPanResponderMove: Animated.event([null, {dx:position.x,dy:position.y}],
      {useNativeDriver:false}),
    onPanResponderRelease: (_, gesture) => {
      position.flattenOffset();
      const width = windowSize.width;
      const height = windowSize.height;
      const next = {
        x:bounded(currentXY.current.x + gesture.dx,-width + 92, 12),
        y:bounded(currentXY.current.y + gesture.dy,-height + 240, 64),
      };
      currentXY.current = next;
      position.setValue(next);
    },
    onPanResponderTerminate: () => {
      position.flattenOffset();
      position.setValue(currentXY.current);
    },
  }), [position,windowSize.width,windowSize.height]);

  useEffect(() => {
    if (!opened || !scopedId) return undefined;
    const seq = ++latestLoad.current;
    let active = true;
    setLoading(true);
    setError('');
    api.chatHistory(scopedId).then(data => {
      if (!active || seq !== latestLoad.current) return;
      setHistory((data.messages || []).map(row => ({
        role:row.role, content:row.content, id:row.id
      })));
    }).catch(err => {
      if (active && seq === latestLoad.current) setError(err.message);
    }).finally(() => {
      if (active && seq === latestLoad.current) setLoading(false);
    });
    return () => { active = false; };
  }, [opened,scopedId]);

  const changeSubject = id => {
    if (sending || lesson) return;
    setSubjectId(id);
    setHistory([]);
    setError('');
  };

  const send = async () => {
    const question = value.trim();
    if (!question || !scopedId || sending || loading) return;
    if (!lessonHasSources) {
      setError('Chương chưa có học liệu đã duyệt. Hãy bổ sung trên Web trước khi hỏi theo buổi.');
      return;
    }
    setError('');
    setValue('');
    setSending(true);
    const draft = {role:'user',content:question,id:'draft-'+Date.now()};
    setHistory(rows => [...rows,draft]);
    try {
      const response = lesson?.taskId
        ? await api.studyChat(scopedId, question, lesson.taskId, lesson.chapterNumber)
        : await api.chat(scopedId, question);
      if (lesson?.taskId && (response.source_mode !== 'chapter' ||
        Number(response.lesson?.chapter_number) !== Number(lesson.chapterNumber))) {
        throw new Error('Nguồn trả lời không khớp buổi học được xác minh.');
      }
      setHistory(rows => [...rows,{role:'assistant',content:response.answer,id:'new-'+Date.now()}]);
    } catch (err) {
      setHistory(rows => rows.filter(row => row !== draft));
      setValue(text => text || question);
      setError(err.message || 'Chưa gửi được câu hỏi. Hãy thử lại.');
    } finally {
      setSending(false);
    }
  };

  if (!subjects.length) return null;
  return (
    <>
      <Animated.View style={[styles.floating, {transform:position.getTranslateTransform()}]}
        {...responder.panHandlers}>
        <TouchableOpacity onPress={() => setOpened(true)}
          accessibilityRole="button" accessibilityLabel="Mở bong bóng Chat AI"
          style={styles.bubble}>
          <Text style={styles.robot}>🤖</Text>
          <View style={styles.online} />
        </TouchableOpacity>
      </Animated.View>
      <Modal visible={opened} transparent animationType="slide"
        onRequestClose={() => setOpened(false)}>
        <KeyboardAvoidingView style={styles.overlay}
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <View style={[styles.panel,{maxHeight:Math.max(360,windowSize.height*0.88)}]}>
            <View style={styles.header}>
              <View style={styles.heading}>
                <Text style={styles.headingTitle}>🤖 AI Study Agent</Text>
                <Text style={styles.headingSub}>
                  {lesson ? 'Học theo chương · học liệu được xác minh' : 'Chat theo môn · đồng bộ Web'}
                </Text>
              </View>
              <TouchableOpacity onPress={() => setOpened(false)}
                accessibilityRole="button" accessibilityLabel="Thu nhỏ bong bóng Chat"
                style={styles.close}><Text style={styles.closeText}>−</Text></TouchableOpacity>
            </View>
            {lesson ? (
              <Text style={styles.context} numberOfLines={2}>
                📖 {currentSubject?.name || 'Buổi học'} · Chương {lesson.chapterNumber}
              </Text>
            ) : (
              <ScrollView horizontal showsHorizontalScrollIndicator={false}
                keyboardShouldPersistTaps="handled" style={styles.subjectList}
                contentContainerStyle={styles.subjectContent}>
                {subjects.map(s => (
                  <TouchableOpacity key={s.id} onPress={() => changeSubject(s.id)}
                    disabled={sending}
                    style={[styles.subjectChip,Number(s.id)===Number(scopedId)&&styles.activeChip]}>
                    <Text style={[styles.subjectText,Number(s.id)===Number(scopedId)&&styles.activeText]}
                      numberOfLines={1}>{s.name}</Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>
            )}
            <ScrollView ref={scroll} style={styles.messages}
              keyboardShouldPersistTaps="handled"
              onContentSizeChange={() => scroll.current?.scrollToEnd({animated:false})}>
              {!history.length && !loading && (
                <Text style={styles.empty}>Hỏi AI về môn học đang chọn. Câu trả lời có dẫn chứng khi tài liệu hỗ trợ.</Text>
              )}
              {history.map((item,index) => (
                <View key={item.id || index}
                  style={[styles.message,item.role==='user'?styles.userMessage:styles.aiMessage]}>
                  {item.role!=='user' && <Text style={styles.author}>AI Study Agent</Text>}
                  <Text style={[styles.messageText,item.role==='user'&&styles.userMessageText]}>
                    {String(item.content || '')}
                  </Text>
                </View>
              ))}
              {(loading || sending) && <ActivityIndicator color={BLUE} style={{marginVertical:10}} />}
            </ScrollView>
            {!!error && <Text style={styles.error} accessibilityRole="alert">{error}</Text>}
            <View style={styles.composer}>
              <TextInput style={styles.input} value={value}
                onChangeText={setValue} multiline maxLength={1200}
                placeholder={lesson?'Hỏi theo nội dung buổi học...':'Hỏi về môn học...'}
                placeholderTextColor="#8994B0" />
              <TouchableOpacity onPress={send} disabled={!value.trim()||sending||loading}
                accessibilityRole="button" accessibilityLabel="Gửi câu hỏi"
                style={[styles.send,(!value.trim()||sending||loading)&&{opacity:0.45}]}>
                <Text style={styles.sendText}>➤</Text>
              </TouchableOpacity>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </>
  );
}

const styles=StyleSheet.create({
  floating:{position:'absolute',right:20,bottom:78,zIndex:300,elevation:12},
  bubble:{height:60,width:60,borderRadius:30,backgroundColor:'#ECF0FF',
    borderWidth:2,borderColor:'#FFFFFF',justifyContent:'center',alignItems:'center',
    shadowColor:'#243C8A',shadowOpacity:0.22,shadowRadius:10,shadowOffset:{width:0,height:3}},
  robot:{fontSize:32},online:{position:'absolute',right:3,bottom:4,width:12,height:12,
    borderRadius:6,backgroundColor:'#28AF82',borderWidth:2,borderColor:'#FFFFFF'},
  overlay:{flex:1,justifyContent:'flex-end',backgroundColor:'rgba(15,25,49,.38)'},
  panel:{backgroundColor:'#FAFBFF',borderTopLeftRadius:24,borderTopRightRadius:24,
    minHeight:380,overflow:'hidden',paddingBottom:Platform.OS==='ios'?18:8},
  header:{padding:16,flexDirection:'row',alignItems:'center',backgroundColor:'#F1F4FF',
    borderBottomWidth:1,borderBottomColor:'#DFE6FD'},
  heading:{flex:1},headingTitle:{color:'#283871',fontSize:17,fontWeight:'800'},
  headingSub:{fontSize:11,color:'#6678A5',marginTop:3},
  close:{paddingHorizontal:12,paddingVertical:5,backgroundColor:'#E0E7FF',borderRadius:10},
  closeText:{fontSize:24,color:'#3754A4'},
  context:{fontSize:12,fontWeight:'700',color:'#4158A0',paddingHorizontal:15,paddingTop:10},
  subjectList:{maxHeight:54,flexGrow:0},
  subjectContent:{padding:10,gap:7,alignItems:'center'},
  subjectChip:{maxWidth:180,backgroundColor:'#FFFFFF',paddingVertical:8,paddingHorizontal:12,
    borderWidth:1,borderColor:'#DCE3F6',borderRadius:20},
  activeChip:{backgroundColor:'#5C70DC',borderColor:'#5C70DC'},
  subjectText:{fontSize:12,color:'#465B93',fontWeight:'700'},
  activeText:{color:'#FFFFFF'},
  messages:{flexGrow:1,flexShrink:1,paddingHorizontal:13,paddingVertical:12},
  empty:{color:'#8A96B3',fontSize:13,lineHeight:20,textAlign:'center',paddingTop:25},
  message:{maxWidth:'93%',padding:12,borderRadius:15,marginBottom:10},
  aiMessage:{alignSelf:'flex-start',backgroundColor:'#FFFFFF',borderWidth:1,borderColor:'#E0E8F9'},
  userMessage:{alignSelf:'flex-end',backgroundColor:'#E5ECFF'},
  author:{fontSize:10,fontWeight:'800',color:'#586FB2',marginBottom:6},
  messageText:{fontSize:13,color:'#283858',lineHeight:20},
  userMessageText:{color:'#304C91'},
  error:{paddingHorizontal:14,paddingVertical:7,color:'#AD334B',fontSize:12},
  composer:{flexDirection:'row',alignItems:'flex-end',gap:9,padding:12,
    borderTopColor:'#E3E9F7',borderTopWidth:1,backgroundColor:'#FFFFFF'},
  input:{flex:1,minHeight:42,maxHeight:106,backgroundColor:'#F5F7FC',borderColor:'#E0E5F4',
    borderWidth:1,borderRadius:15,paddingHorizontal:13,paddingVertical:9,
    fontSize:14,color:'#1D2C52'},
  send:{height:43,width:43,borderRadius:14,backgroundColor:BLUE,
    alignItems:'center',justifyContent:'center'},
  sendText:{fontSize:21,color:'#FFFFFF',fontWeight:'800'},
});
