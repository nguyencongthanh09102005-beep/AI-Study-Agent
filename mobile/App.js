import React, { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  SafeAreaView,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { api } from './src/api';

function Pill({ children }) {
  return <View style={styles.pill}><Text style={styles.pillText}>{children}</Text></View>;
}

function Progress({ value = 0 }) {
  const safe = Math.max(0, Math.min(100, Number(value || 0)));
  return (
    <View style={styles.progressTrack}>
      <View style={[styles.progressFill, { width: `${safe}%` }]} />
    </View>
  );
}

function Header({ title, subtitle, userName = '' }) {
  const initial = (userName || 'T').trim().charAt(0).toUpperCase() || 'T';
  return (
    <View style={styles.header}>
      <View style={{ flex: 1, paddingRight: 12 }}>
        <Text style={styles.title}>{title}</Text>
        {!!subtitle && <Text style={styles.subtitle}>{subtitle}</Text>}
      </View>
      <View style={styles.avatar}><Text style={styles.avatarText}>{initial}</Text></View>
    </View>
  );
}

function ErrorCard({ message }) {
  if (!message) return null;
  return (
    <View style={[styles.card, { borderColor: '#F1C6C6', backgroundColor: '#FFF7F7' }]}>
      <Text style={{ color: '#A33A3A', fontWeight: '700' }}>{message}</Text>
    </View>
  );
}

function HomeScreen({ dashboard, setTab, loading }) {
  const user = dashboard?.user || {};
  const subjects = dashboard?.subjects || [];
  const tasks = dashboard?.tasks || [];

  return (
    <ScrollView contentContainerStyle={styles.page}>
      <Header
        title={`Chào ${user.name || 'bạn'} 👋`}
        subtitle="Study Agent đang dùng dữ liệu học tập thật từ Flask"
        userName={user.name}
      />

      <TouchableOpacity style={styles.heroCard} onPress={() => setTab('agent')}>
        <View style={{ flex: 1 }}>
          <Text style={styles.heroEyebrow}>TRỢ LÝ CÁ NHÂN</Text>
          <Text style={styles.heroTitle}>Bạn đang cần hiểu lại phần nào?</Text>
          <Text style={styles.heroText}>Agent kết hợp tài liệu, kiến thức chung, điểm yếu và tiến độ riêng của bạn.</Text>
          <View style={styles.heroButton}><Text style={styles.heroButtonText}>Hỏi Study Agent →</Text></View>
        </View>
        <View style={styles.robot}><Text style={{ fontSize: 38 }}>🤖</Text></View>
      </TouchableOpacity>

      {loading && <ActivityIndicator />}

      <Text style={styles.sectionTitle}>Sắp tới</Text>
      {tasks.length ? tasks.slice(0, 5).map((task) => (
        <View key={task.id} style={styles.card}>
          <View style={styles.rowBetween}>
            <Text style={[styles.cardTitle, { flex: 1 }]}>{task.title}</Text>
            <Text style={styles.time}>{String(task.study_at || '').slice(11, 16)}</Text>
          </View>
          <Text style={styles.muted}>{task.subject_name || 'Tự học'} · {task.duration} phút</Text>
        </View>
      )) : <View style={styles.card}><Text style={styles.muted}>Chưa có buổi học sắp tới.</Text></View>}

      <Text style={styles.sectionTitle}>Tiến độ môn học</Text>
      {subjects.map((item) => (
        <TouchableOpacity key={item.id} style={styles.card} onPress={() => setTab('subjects')}>
          <View style={styles.rowBetween}>
            <View style={{ flex: 1, paddingRight: 14 }}>
              <Text style={styles.cardTitle}>{item.name}</Text>
              <Text style={styles.muted}>{item.code || 'Chưa có mã môn'}</Text>
            </View>
            <Text style={styles.percent}>{item.progress || 0}%</Text>
          </View>
          <Progress value={item.progress} />
          <Text style={styles.weakText}>
            {item.weakness
              ? `Cần củng cố: ${item.weakness.topic}`
              : 'Chưa phát hiện điểm yếu nổi bật'}
          </Text>
        </TouchableOpacity>
      ))}
    </ScrollView>
  );
}

function SubjectsScreen({ subjects, userName }) {
  return (
    <ScrollView contentContainerStyle={styles.page}>
      <Header title="Môn học" subtitle="Tri thức chung + dữ liệu học tập riêng" userName={userName} />
      {subjects.map((item) => (
        <View key={item.id} style={styles.subjectCard}>
          <View style={styles.subjectIcon}><Text style={{ fontSize: 24 }}>📘</Text></View>
          <View style={{ flex: 1 }}>
            <Text style={styles.cardTitle}>{item.name}</Text>
            <Text style={styles.muted}>{item.code || 'Chưa có mã môn'}</Text>
            <View style={styles.pillRow}>
              <Pill>{item.credits || 0} tín chỉ</Pill>
              <Pill>Mục tiêu {item.target_score || 0}</Pill>
              <Pill>{item.progress || 0}%</Pill>
            </View>
            <Progress value={item.progress} />
            <Text style={styles.weakText}>
              {item.weaknesses?.length
                ? `Điểm yếu: ${item.weaknesses.map((w) => w.topic).join(', ')}`
                : 'Chưa có điểm yếu cần ôn'}
            </Text>
          </View>
        </View>
      ))}
    </ScrollView>
  );
}

function SubjectSelector({ subjects, selectedId, onSelect }) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ maxHeight: 46, marginBottom: 10 }}>
      <View style={{ flexDirection: 'row', gap: 8 }}>
        {subjects.map((subject) => (
          <TouchableOpacity
            key={subject.id}
            onPress={() => onSelect(subject.id)}
            style={[
              styles.pill,
              selectedId === subject.id && { backgroundColor: '#6567E8' },
            ]}
          >
            <Text style={[
              styles.pillText,
              selectedId === subject.id && { color: 'white' },
            ]}>{subject.name}</Text>
          </TouchableOpacity>
        ))}
      </View>
    </ScrollView>
  );
}

function AgentScreen({ subjects, userName }) {
  const [subjectId, setSubjectId] = useState(subjects[0]?.id || null);
  const [message, setMessage] = useState('');
  const [messages, setMessages] = useState([
    { role: 'assistant', text: 'Chọn môn học rồi hỏi bất kỳ phần nào bạn đang chưa rõ.' },
  ]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!subjectId && subjects[0]?.id) setSubjectId(subjects[0].id);
  }, [subjects, subjectId]);

  const send = async () => {
    const value = message.trim();
    if (!value || !subjectId || sending) return;

    setError('');
    setMessages((old) => [...old, { role: 'user', text: value }]);
    setMessage('');
    setSending(true);

    try {
      const result = await api.chat(subjectId, value);
      setMessages((old) => [...old, { role: 'assistant', text: result.answer }]);
    } catch (err) {
      setError(err.message || 'Không thể gửi câu hỏi.');
    } finally {
      setSending(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.chatPage}>
        <Header title="Study Agent" subtitle="Chat thật với backend Flask" userName={userName} />
        <SubjectSelector subjects={subjects} selectedId={subjectId} onSelect={setSubjectId} />
        <ErrorCard message={error} />
        <ScrollView style={styles.chatList} contentContainerStyle={{ paddingBottom: 16 }}>
          {messages.map((item, index) => (
            <View key={index} style={[styles.message, item.role === 'user' ? styles.userMessage : styles.aiMessage]}>
              <Text style={item.role === 'user' ? styles.userMessageText : styles.aiMessageText}>{item.text}</Text>
            </View>
          ))}
          {sending && <ActivityIndicator />}
        </ScrollView>
        <View style={styles.composer}>
          <TextInput
            value={message}
            onChangeText={setMessage}
            placeholder="Hỏi nhanh trong lúc học..."
            placeholderTextColor="#8B93A7"
            style={styles.input}
          />
          <TouchableOpacity style={styles.sendButton} onPress={send}>
            <Text style={styles.sendText}>➤</Text>
          </TouchableOpacity>
        </View>
      </View>
    </SafeAreaView>
  );
}

function QuizScreen({ subjects, userName, refreshData }) {
  const [subjectId, setSubjectId] = useState(subjects[0]?.id || null);
  const [quiz, setQuiz] = useState(null);
  const [answers, setAnswers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!subjectId && subjects[0]?.id) setSubjectId(subjects[0].id);
  }, [subjects, subjectId]);

  const generate = async (mode = 'subject') => {
    if (!subjectId) return;
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const data = await api.quizGenerate(subjectId, 10, mode);
      setQuiz(data);
      setAnswers(Array(data.questions?.length || 0).fill(null));
    } catch (err) {
      setError(err.message || 'Không thể tạo quiz.');
    } finally {
      setLoading(false);
    }
  };

  const submit = async () => {
    if (!quiz?.quiz_id) return;
    setLoading(true);
    setError('');
    try {
      const data = await api.quizSubmit(quiz.quiz_id, answers);
      setResult(data);
      await refreshData();
    } catch (err) {
      setError(err.message || 'Không thể nộp quiz.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.page}>
      <Header title="Quiz thông minh" subtitle="Kết quả cập nhật điểm yếu thật" userName={userName} />
      <SubjectSelector subjects={subjects} selectedId={subjectId} onSelect={setSubjectId} />
      <View style={{ flexDirection: 'row', gap: 8, marginBottom: 14 }}>
        <TouchableOpacity style={[styles.primaryButton, { flex: 1 }]} onPress={() => generate('subject')}>
          <Text style={styles.primaryButtonText}>Tạo theo môn</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[styles.primaryButton, { flex: 1, backgroundColor: '#7A61C9' }]} onPress={() => generate('weakness')}>
          <Text style={styles.primaryButtonText}>Ôn điểm yếu</Text>
        </TouchableOpacity>
      </View>

      <ErrorCard message={error} />
      {loading && <ActivityIndicator />}

      {quiz?.questions?.map((question, qIndex) => (
        <View key={qIndex} style={styles.card}>
          <Text style={styles.eyebrow}>CÂU {qIndex + 1} / {quiz.questions.length}</Text>
          <Text style={styles.quizQuestion}>{question.question}</Text>
          {!!question.topic && <Text style={styles.muted}>{question.chapter || ''} · {question.topic}</Text>}
          {question.options.map((item, index) => (
            <TouchableOpacity
              key={index}
              style={[styles.option, answers[qIndex] === index && styles.optionSelected]}
              onPress={() => {
                const next = [...answers];
                next[qIndex] = index;
                setAnswers(next);
              }}
            >
              <Text style={[styles.optionLetter, answers[qIndex] === index && styles.optionLetterSelected]}>
                {String.fromCharCode(65 + index)}
              </Text>
              <Text style={styles.optionText}>{item}</Text>
            </TouchableOpacity>
          ))}
        </View>
      ))}

      {!!quiz?.questions?.length && (
        <TouchableOpacity style={styles.primaryButton} onPress={submit}>
          <Text style={styles.primaryButtonText}>Nộp bài</Text>
        </TouchableOpacity>
      )}

      {result && (
        <View style={styles.insightCard}>
          <Text style={styles.insightTitle}>Kết quả: {result.correct_count}/{result.total_questions}</Text>
          <Text style={styles.muted}>Điểm {result.score}%. Study Agent đã cập nhật tín hiệu học tập.</Text>
        </View>
      )}
    </ScrollView>
  );
}

function PlanScreen({ plan, userName }) {
  const profile = plan?.profile || {};
  const tasks = plan?.tasks || [];

  return (
    <ScrollView contentContainerStyle={styles.page}>
      <Header title="Lộ trình của bạn" subtitle="Kế hoạch thật từ backend" userName={userName} />
      <View style={styles.profileCard}>
        <Text style={styles.eyebrow}>HỒ SƠ HỌC TẬP</Text>
        <View style={styles.profileGrid}>
          <View><Text style={styles.metric}>{profile.learning_style || 'balanced'}</Text><Text style={styles.metricLabel}>Phong cách</Text></View>
          <View><Text style={styles.metric}>{profile.daily_minutes || 45}'</Text><Text style={styles.metricLabel}>Mỗi buổi</Text></View>
          <View><Text style={styles.metric}>{profile.preferred_study_time || '19:00'}</Text><Text style={styles.metricLabel}>Giờ ưu tiên</Text></View>
        </View>
      </View>

      {tasks.length ? tasks.map((task, index) => (
        <View key={task.id || index} style={styles.timelineRow}>
          <View style={styles.timelineDot}><Text style={styles.timelineIndex}>{index + 1}</Text></View>
          <View style={styles.timelineCard}>
            <Text style={styles.timelineDay}>{String(task.study_at || '').replace('T', ' ').slice(0, 16)}</Text>
            <Text style={styles.cardTitle}>{task.title}</Text>
            <Text style={styles.muted}>{task.subject_name || 'Tự học'} · {task.duration} phút</Text>
            {!!task.note && <Text style={styles.muted}>{task.note}</Text>}
          </View>
        </View>
      )) : <View style={styles.card}><Text style={styles.muted}>Chưa có kế hoạch học.</Text></View>}
    </ScrollView>
  );
}

function LoginScreen({ onLogin }) {
  const [email, setEmail] = useState('demo@study.local');
  const [password, setPassword] = useState('123456');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const login = async () => {
    setLoading(true);
    setError('');
    try {
      await onLogin(email.trim(), password);
    } catch (err) {
      setError(err.message || 'Không thể đăng nhập.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.loginSafe}>
      <StatusBar barStyle="dark-content" />
      <View style={styles.loginWrap}>
        <View style={styles.logo}><Text style={{ fontSize: 34 }}>🎓</Text></View>
        <Text style={styles.loginTitle}>AI Study Agent</Text>
        <Text style={styles.loginSubtitle}>Mobile dùng chung dữ liệu với website Flask</Text>
        <TextInput value={email} onChangeText={setEmail} autoCapitalize="none" style={styles.loginInput} placeholder="Email" />
        <TextInput value={password} onChangeText={setPassword} secureTextEntry style={styles.loginInput} placeholder="Mật khẩu" />
        <TouchableOpacity style={styles.primaryButton} onPress={login} disabled={loading}>
          <Text style={styles.primaryButtonText}>{loading ? 'Đang đăng nhập...' : 'Đăng nhập'}</Text>
        </TouchableOpacity>
        <ErrorCard message={error} />
        <Text style={styles.loginHint}>Flask cần chạy với FLASK_HOST=0.0.0.0 trên máy Windows.</Text>
      </View>
    </SafeAreaView>
  );
}

export default function App() {
  const [loggedIn, setLoggedIn] = useState(false);
  const [tab, setTab] = useState('home');
  const [dashboard, setDashboard] = useState(null);
  const [subjects, setSubjects] = useState([]);
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(false);

  const refreshData = async () => {
    setLoading(true);
    try {
      const [dashboardData, subjectsData, planData] = await Promise.all([
        api.dashboard(),
        api.subjects(),
        api.studyPlan(),
      ]);
      setDashboard(dashboardData);
      setSubjects(subjectsData || []);
      setPlan(planData);
    } finally {
      setLoading(false);
    }
  };

  const handleLogin = async (email, password) => {
    await api.login(email, password);
    setLoggedIn(true);
    await refreshData();
  };

  useEffect(() => {
    if (loggedIn) {
      refreshData().catch(() => {});
    }
  }, [loggedIn]);

  const userName = dashboard?.user?.name || '';

  const screen = useMemo(() => {
    if (tab === 'subjects') return <SubjectsScreen subjects={subjects} userName={userName} />;
    if (tab === 'agent') return <AgentScreen subjects={subjects} userName={userName} />;
    if (tab === 'quiz') return <QuizScreen subjects={subjects} userName={userName} refreshData={refreshData} />;
    if (tab === 'plan') return <PlanScreen plan={plan} userName={userName} />;
    return <HomeScreen dashboard={dashboard} setTab={setTab} loading={loading} />;
  }, [tab, subjects, dashboard, plan, loading, userName]);

  if (!loggedIn) return <LoginScreen onLogin={handleLogin} />;

  const tabs = [
    ['home', '⌂', 'Trang chủ'],
    ['subjects', '📚', 'Môn học'],
    ['agent', '✦', 'Agent'],
    ['quiz', '✓', 'Quiz'],
    ['plan', '◷', 'Kế hoạch'],
  ];

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar barStyle="dark-content" />
      <View style={styles.app}>{screen}</View>
      <View style={styles.bottomNav}>
        {tabs.map(([key, icon, label]) => (
          <TouchableOpacity key={key} style={styles.navItem} onPress={() => setTab(key)}>
            <Text style={[styles.navIcon, tab === key && styles.navActive]}>{icon}</Text>
            <Text style={[styles.navLabel, tab === key && styles.navActive]}>{label}</Text>
          </TouchableOpacity>
        ))}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#F6F8FC' },
  app: { flex: 1 },
  page: { padding: 20, paddingBottom: 110, backgroundColor: '#F6F8FC' },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 22 },
  title: { fontSize: 28, fontWeight: '800', color: '#17203A' },
  subtitle: { marginTop: 5, fontSize: 13, color: '#7B849A' },
  avatar: { width: 42, height: 42, borderRadius: 21, backgroundColor: '#E8EAFE', alignItems: 'center', justifyContent: 'center' },
  avatarText: { color: '#5965D8', fontWeight: '800' },
  heroCard: { backgroundColor: '#6567E8', borderRadius: 24, padding: 22, flexDirection: 'row', marginBottom: 24 },
  heroEyebrow: { color: '#D8DBFF', fontSize: 11, fontWeight: '800', letterSpacing: 1.1 },
  heroTitle: { color: 'white', fontSize: 23, lineHeight: 29, fontWeight: '800', marginTop: 8 },
  heroText: { color: '#EEF0FF', fontSize: 13, lineHeight: 19, marginTop: 8 },
  heroButton: { alignSelf: 'flex-start', backgroundColor: 'white', paddingHorizontal: 14, paddingVertical: 10, borderRadius: 12, marginTop: 16 },
  heroButtonText: { color: '#555DD0', fontWeight: '800' },
  robot: { width: 72, justifyContent: 'center', alignItems: 'center' },
  sectionTitle: { fontSize: 17, fontWeight: '800', color: '#202943', marginBottom: 10, marginTop: 4 },
  card: { backgroundColor: 'white', borderRadius: 18, padding: 17, marginBottom: 12, borderWidth: 1, borderColor: '#EBEEF5' },
  subjectCard: { backgroundColor: 'white', borderRadius: 20, padding: 17, marginBottom: 14, borderWidth: 1, borderColor: '#EBEEF5', flexDirection: 'row', gap: 14 },
  subjectIcon: { width: 50, height: 50, borderRadius: 16, backgroundColor: '#F0F1FF', alignItems: 'center', justifyContent: 'center' },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  cardTitle: { fontSize: 15, fontWeight: '800', color: '#27304B' },
  muted: { color: '#81899B', fontSize: 12, lineHeight: 18, marginTop: 4 },
  time: { color: '#5965D8', fontWeight: '800', fontSize: 12 },
  percent: { color: '#5965D8', fontWeight: '800', fontSize: 15 },
  progressTrack: { height: 8, backgroundColor: '#EDEEFA', borderRadius: 999, marginTop: 13, overflow: 'hidden' },
  progressFill: { height: '100%', backgroundColor: '#6567E8', borderRadius: 999 },
  weakText: { color: '#9A6B34', fontSize: 11, marginTop: 10 },
  pillRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 10 },
  pill: { backgroundColor: '#EEF0FF', borderRadius: 999, paddingHorizontal: 9, paddingVertical: 6 },
  pillText: { color: '#6068C7', fontSize: 10, fontWeight: '700' },
  chatPage: { flex: 1, padding: 20, backgroundColor: '#F6F8FC' },
  contextStrip: { flexDirection: 'row', flexWrap: 'wrap', gap: 7, marginBottom: 12 },
  chatList: { flex: 1 },
  message: { maxWidth: '84%', borderRadius: 18, paddingHorizontal: 14, paddingVertical: 12, marginBottom: 10 },
  aiMessage: { alignSelf: 'flex-start', backgroundColor: 'white', borderWidth: 1, borderColor: '#EBEEF5' },
  userMessage: { alignSelf: 'flex-end', backgroundColor: '#6567E8' },
  aiMessageText: { color: '#28314B', lineHeight: 20, fontSize: 13 },
  userMessageText: { color: 'white', lineHeight: 20, fontSize: 13 },
  composer: { flexDirection: 'row', gap: 9, paddingTop: 10 },
  input: { flex: 1, backgroundColor: 'white', borderWidth: 1, borderColor: '#E5E8F1', borderRadius: 16, paddingHorizontal: 14, height: 48, color: '#222A40' },
  sendButton: { width: 48, height: 48, borderRadius: 16, backgroundColor: '#6567E8', alignItems: 'center', justifyContent: 'center' },
  sendText: { color: 'white', fontSize: 18, fontWeight: '900' },
  eyebrow: { color: '#6972D4', fontSize: 11, fontWeight: '900', letterSpacing: 1 },
  quizQuestion: { fontSize: 19, lineHeight: 27, fontWeight: '800', color: '#202943', marginVertical: 14 },
  option: { borderWidth: 1, borderColor: '#E5E8F1', borderRadius: 14, padding: 13, marginBottom: 9, flexDirection: 'row', alignItems: 'center', gap: 10 },
  optionSelected: { borderColor: '#6567E8', backgroundColor: '#F1F2FF' },
  optionLetter: { width: 26, height: 26, borderRadius: 13, backgroundColor: '#F0F2F7', textAlign: 'center', lineHeight: 26, color: '#747C90', fontWeight: '800' },
  optionLetterSelected: { backgroundColor: '#6567E8', color: 'white' },
  optionText: { color: '#2A334D', fontSize: 13, fontWeight: '600' },
  insightCard: { backgroundColor: '#FFF8E8', borderRadius: 18, padding: 16 },
  insightTitle: { color: '#8E632E', fontWeight: '800', marginBottom: 5 },
  profileCard: { backgroundColor: '#222C4D', borderRadius: 22, padding: 20, marginBottom: 20 },
  profileGrid: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 18 },
  metric: { color: 'white', fontSize: 21, fontWeight: '900' },
  metricLabel: { color: '#BAC1D9', fontSize: 11, marginTop: 4 },
  timelineRow: { flexDirection: 'row', alignItems: 'stretch', marginBottom: 12, gap: 12 },
  timelineDot: { width: 34, height: 34, borderRadius: 17, backgroundColor: '#6567E8', alignItems: 'center', justifyContent: 'center', marginTop: 9 },
  timelineIndex: { color: 'white', fontWeight: '900' },
  timelineCard: { flex: 1, backgroundColor: 'white', borderRadius: 17, padding: 15, borderWidth: 1, borderColor: '#EBEEF5' },
  timelineDay: { color: '#6972D4', fontSize: 10, fontWeight: '900', marginBottom: 4, textTransform: 'uppercase' },
  bottomNav: { height: 78, backgroundColor: 'white', flexDirection: 'row', borderTopWidth: 1, borderTopColor: '#E9ECF3', paddingTop: 10, paddingBottom: 8 },
  navItem: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  navIcon: { fontSize: 19, color: '#9AA1B2' },
  navLabel: { fontSize: 9, color: '#9AA1B2', marginTop: 4, fontWeight: '700' },
  navActive: { color: '#5E66D8' },
  loginSafe: { flex: 1, backgroundColor: '#F6F8FC', justifyContent: 'center' },
  loginWrap: { paddingHorizontal: 26, alignItems: 'stretch' },
  logo: { alignSelf: 'center', width: 72, height: 72, borderRadius: 24, backgroundColor: '#EBEDFF', alignItems: 'center', justifyContent: 'center', marginBottom: 16 },
  loginTitle: { textAlign: 'center', color: '#202943', fontSize: 28, fontWeight: '900' },
  loginSubtitle: { textAlign: 'center', color: '#838B9F', fontSize: 13, marginTop: 7, marginBottom: 28 },
  loginInput: { height: 52, borderRadius: 15, backgroundColor: 'white', borderWidth: 1, borderColor: '#E4E7F0', paddingHorizontal: 15, marginBottom: 11, color: '#202943' },
  primaryButton: { height: 52, borderRadius: 15, backgroundColor: '#6567E8', alignItems: 'center', justifyContent: 'center', marginTop: 4 },
  primaryButtonText: { color: 'white', fontSize: 15, fontWeight: '900' },
  loginHint: { color: '#989FAF', textAlign: 'center', fontSize: 11, marginTop: 18 },
});
