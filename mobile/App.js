import React, { useMemo, useState } from 'react';
import {
  SafeAreaView,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';

const subjects = [
  { id: 1, name: 'Điện toán đám mây', code: '0104123039', progress: 72, weak: 'Bảo mật cloud' },
  { id: 2, name: 'Khai thác dữ liệu', code: '0104122041', progress: 58, weak: 'Phân cụm' },
  { id: 3, name: 'Trí tuệ nhân tạo', code: '0104121033', progress: 81, weak: 'Heuristic search' },
];

const tasks = [
  { title: 'Ôn Chương 4 - Bảo mật đám mây', time: '19:30', subject: 'Điện toán đám mây' },
  { title: 'Làm Quiz Chương 3', time: '21:00', subject: 'Khai thác dữ liệu' },
];

function Pill({ children }) {
  return <View style={styles.pill}><Text style={styles.pillText}>{children}</Text></View>;
}

function Progress({ value }) {
  return (
    <View style={styles.progressTrack}>
      <View style={[styles.progressFill, { width: `${value}%` }]} />
    </View>
  );
}

function Header({ title, subtitle }) {
  return (
    <View style={styles.header}>
      <View>
        <Text style={styles.title}>{title}</Text>
        {!!subtitle && <Text style={styles.subtitle}>{subtitle}</Text>}
      </View>
      <View style={styles.avatar}><Text style={styles.avatarText}>T</Text></View>
    </View>
  );
}

function HomeScreen({ setTab }) {
  return (
    <ScrollView contentContainerStyle={styles.page}>
      <Header title="Chào Thành 👋" subtitle="Study Agent đã sẵn sàng đồng hành hôm nay" />

      <TouchableOpacity style={styles.heroCard} onPress={() => setTab('agent')}>
        <View style={{ flex: 1 }}>
          <Text style={styles.heroEyebrow}>TRỢ LÝ CÁ NHÂN</Text>
          <Text style={styles.heroTitle}>Bạn đang cần hiểu lại phần nào?</Text>
          <Text style={styles.heroText}>Agent sẽ kết hợp tài liệu chung của môn và tiến độ riêng của bạn để trả lời phù hợp.</Text>
          <View style={styles.heroButton}><Text style={styles.heroButtonText}>Hỏi Study Agent →</Text></View>
        </View>
        <View style={styles.robot}><Text style={{ fontSize: 38 }}>🤖</Text></View>
      </TouchableOpacity>

      <Text style={styles.sectionTitle}>Hôm nay</Text>
      {tasks.map((task) => (
        <View key={task.title} style={styles.card}>
          <View style={styles.rowBetween}>
            <Text style={styles.cardTitle}>{task.title}</Text>
            <Text style={styles.time}>{task.time}</Text>
          </View>
          <Text style={styles.muted}>{task.subject}</Text>
        </View>
      ))}

      <Text style={styles.sectionTitle}>Tiến độ môn học</Text>
      {subjects.map((item) => (
        <TouchableOpacity key={item.id} style={styles.card} onPress={() => setTab('subjects')}>
          <View style={styles.rowBetween}>
            <View style={{ flex: 1, paddingRight: 14 }}>
              <Text style={styles.cardTitle}>{item.name}</Text>
              <Text style={styles.muted}>{item.code}</Text>
            </View>
            <Text style={styles.percent}>{item.progress}%</Text>
          </View>
          <Progress value={item.progress} />
          <Text style={styles.weakText}>Cần củng cố: {item.weak}</Text>
        </TouchableOpacity>
      ))}
    </ScrollView>
  );
}

function SubjectsScreen() {
  return (
    <ScrollView contentContainerStyle={styles.page}>
      <Header title="Môn học" subtitle="Tri thức chung + dữ liệu học tập riêng" />
      {subjects.map((item) => (
        <View key={item.id} style={styles.subjectCard}>
          <View style={styles.subjectIcon}><Text style={{ fontSize: 24 }}>📘</Text></View>
          <View style={{ flex: 1 }}>
            <Text style={styles.cardTitle}>{item.name}</Text>
            <Text style={styles.muted}>{item.code}</Text>
            <View style={styles.pillRow}>
              <Pill>Đề cương chung</Pill>
              <Pill>Tài liệu chung</Pill>
              <Pill>Hồ sơ cá nhân</Pill>
            </View>
            <Progress value={item.progress} />
            <Text style={styles.weakText}>Điểm yếu hiện tại: {item.weak}</Text>
          </View>
        </View>
      ))}
    </ScrollView>
  );
}

function AgentScreen() {
  const [message, setMessage] = useState('');
  const [messages, setMessages] = useState([
    { role: 'assistant', text: 'Mình đang theo dõi môn Điện toán đám mây. Bạn đang yếu phần Bảo mật cloud. Hôm nay muốn hỏi gì?' },
  ]);

  const send = () => {
    const value = message.trim();
    if (!value) return;
    setMessages((old) => [
      ...old,
      { role: 'user', text: value },
      { role: 'assistant', text: 'Mình sẽ đối chiếu đề cương, tài liệu môn học và lịch sử học của bạn để trả lời theo đúng mức độ hiện tại.' },
    ]);
    setMessage('');
  };

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.chatPage}>
        <Header title="Study Agent" subtitle="Điện toán đám mây • Agent cá nhân" />
        <View style={styles.contextStrip}>
          <Pill>📚 Tri thức chung</Pill>
          <Pill>🧠 Memory riêng</Pill>
          <Pill>🎯 Mục tiêu 8.0</Pill>
        </View>
        <ScrollView style={styles.chatList} contentContainerStyle={{ paddingBottom: 16 }}>
          {messages.map((item, index) => (
            <View key={index} style={[styles.message, item.role === 'user' ? styles.userMessage : styles.aiMessage]}>
              <Text style={item.role === 'user' ? styles.userMessageText : styles.aiMessageText}>{item.text}</Text>
            </View>
          ))}
        </ScrollView>
        <View style={styles.composer}>
          <TextInput
            value={message}
            onChangeText={setMessage}
            placeholder="Hỏi nhanh trong lúc học..."
            placeholderTextColor="#8B93A7"
            style={styles.input}
          />
          <TouchableOpacity style={styles.sendButton} onPress={send}><Text style={styles.sendText}>➤</Text></TouchableOpacity>
        </View>
      </View>
    </SafeAreaView>
  );
}

function QuizScreen() {
  const [selected, setSelected] = useState(1);
  const options = ['Mô hình IaaS', 'Mô hình SaaS', 'Mô hình PaaS', 'Mạng riêng ảo'];
  return (
    <ScrollView contentContainerStyle={styles.page}>
      <Header title="Quiz thông minh" subtitle="Kết quả sẽ cập nhật phần kiến thức yếu" />
      <View style={styles.card}>
        <Text style={styles.eyebrow}>CÂU 3 / 10</Text>
        <Text style={styles.quizQuestion}>Dịch vụ nào cung cấp hạ tầng máy chủ ảo hóa cho người dùng?</Text>
        {options.map((item, index) => (
          <TouchableOpacity key={item} style={[styles.option, selected === index && styles.optionSelected]} onPress={() => setSelected(index)}>
            <Text style={[styles.optionLetter, selected === index && styles.optionLetterSelected]}>{String.fromCharCode(65 + index)}</Text>
            <Text style={styles.optionText}>{item}</Text>
          </TouchableOpacity>
        ))}
      </View>
      <View style={styles.insightCard}>
        <Text style={styles.insightTitle}>Agent đang học về bạn</Text>
        <Text style={styles.muted}>Sau mỗi quiz, các câu sai sẽ được dùng để cập nhật “phần yếu” và điều chỉnh kế hoạch học tiếp theo.</Text>
      </View>
    </ScrollView>
  );
}

function PlanScreen() {
  return (
    <ScrollView contentContainerStyle={styles.page}>
      <Header title="Lộ trình của bạn" subtitle="Cá nhân hóa theo mục tiêu, năng lực và deadline" />
      <View style={styles.profileCard}>
        <Text style={styles.eyebrow}>HỒ SƠ HỌC TẬP</Text>
        <View style={styles.profileGrid}>
          <View><Text style={styles.metric}>8.0</Text><Text style={styles.metricLabel}>Mục tiêu</Text></View>
          <View><Text style={styles.metric}>72%</Text><Text style={styles.metricLabel}>Tiến độ</Text></View>
          <View><Text style={styles.metric}>19:30</Text><Text style={styles.metricLabel}>Giờ ưu tiên</Text></View>
        </View>
      </View>
      {[
        ['Hôm nay', 'Ôn Bảo mật cloud', '45 phút'],
        ['Ngày mai', 'Làm Quiz chương 4', '30 phút'],
        ['Thứ 5', 'Hỏi Agent các câu sai', '25 phút'],
        ['Cuối tuần', 'Ôn tổng hợp + Quiz lại', '60 phút'],
      ].map(([day, title, duration], index) => (
        <View key={title} style={styles.timelineRow}>
          <View style={styles.timelineDot}><Text style={styles.timelineIndex}>{index + 1}</Text></View>
          <View style={styles.timelineCard}>
            <Text style={styles.timelineDay}>{day}</Text>
            <Text style={styles.cardTitle}>{title}</Text>
            <Text style={styles.muted}>{duration}</Text>
          </View>
        </View>
      ))}
    </ScrollView>
  );
}

function LoginScreen({ onLogin }) {
  const [email, setEmail] = useState('demo@study.local');
  const [password, setPassword] = useState('123456');
  return (
    <SafeAreaView style={styles.loginSafe}>
      <StatusBar barStyle="dark-content" />
      <View style={styles.loginWrap}>
        <View style={styles.logo}><Text style={{ fontSize: 34 }}>🎓</Text></View>
        <Text style={styles.loginTitle}>AI Study Agent</Text>
        <Text style={styles.loginSubtitle}>Trợ lý học tập đồng hành cùng bạn</Text>
        <TextInput value={email} onChangeText={setEmail} autoCapitalize="none" style={styles.loginInput} placeholder="Email" />
        <TextInput value={password} onChangeText={setPassword} secureTextEntry style={styles.loginInput} placeholder="Mật khẩu" />
        <TouchableOpacity style={styles.primaryButton} onPress={onLogin}>
          <Text style={styles.primaryButtonText}>Đăng nhập</Text>
        </TouchableOpacity>
        <Text style={styles.loginHint}>Bản mobile đang được phát triển từ backend Flask hiện tại.</Text>
      </View>
    </SafeAreaView>
  );
}

export default function App() {
  const [loggedIn, setLoggedIn] = useState(false);
  const [tab, setTab] = useState('home');

  const screen = useMemo(() => {
    if (tab === 'subjects') return <SubjectsScreen />;
    if (tab === 'agent') return <AgentScreen />;
    if (tab === 'quiz') return <QuizScreen />;
    if (tab === 'plan') return <PlanScreen />;
    return <HomeScreen setTab={setTab} />;
  }, [tab]);

  if (!loggedIn) return <LoginScreen onLogin={() => setLoggedIn(true)} />;

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
