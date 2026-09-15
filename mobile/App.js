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

const COLORS = {
  bg: '#F8FBFF',
  card: '#FFFFFF',
  navy: '#15336B',
  blue: '#2388FF',
  blue2: '#4BA8FF',
  teal: '#2EB9AA',
  purple: '#8059E9',
  orange: '#F6A63B',
  red: '#FF6868',
  muted: '#7185AA',
  line: '#E3ECF7',
  softBlue: '#EAF5FF',
  softTeal: '#E8F8F5',
  softPurple: '#F0ECFF',
  softOrange: '#FFF4E4',
};

const subjects = [
  { id: 1, name: 'Trí tuệ nhân tạo', code: 'CS317', credits: 3, target: 8.5, progress: 70, icon: '✦', color: COLORS.blue, soft: COLORS.softBlue },
  { id: 2, name: 'Lịch sử Đảng', code: 'LLCT101', credits: 2, target: 9.0, progress: 45, icon: '▣', color: COLORS.red, soft: '#FFF0F0' },
  { id: 3, name: 'Điện toán đám mây', code: 'CS302', credits: 3, target: 8.0, progress: 20, icon: '☁', color: COLORS.blue, soft: COLORS.softBlue },
  { id: 4, name: 'Xử lý ảnh', code: 'CS303', credits: 3, target: 8.5, progress: 60, icon: '▧', color: COLORS.purple, soft: COLORS.softPurple },
];

const reminders = [
  { title: 'Làm quiz Chương 3 - Vật lý', due: 'Hạn: Hôm nay, 20:00', badge: 'Sắp đến', color: COLORS.red, icon: '▣' },
  { title: 'Ôn tập từ vựng Unit 5 - Tiếng Anh', due: 'Hạn: Ngày mai, 19:00', badge: 'Ngày mai', color: COLORS.blue, icon: '▤' },
  { title: 'Hoàn thành bài tập Toán', due: 'Hạn: 12 Thg 1, 2025', badge: 'Còn 2 ngày', color: COLORS.navy, icon: '▦' },
];

const plans = [
  { time: '08:00', end: '09:00', subject: 'Toán học', detail: 'Ôn tập hàm số bậc hai', status: 'Đã hoàn thành', color: COLORS.teal, icon: '⊞' },
  { time: '14:00', end: '15:00', subject: 'Tiếng Anh', detail: 'Luyện đề đọc hiểu', status: 'Sắp học', color: COLORS.blue, icon: '▤' },
  { time: '19:00', end: '20:00', subject: 'Hóa học', detail: 'Làm bài tập chương 3', status: 'Chưa bắt đầu', color: '#65789B', icon: '⚗' },
];

function Robot({ small = false }) {
  const scale = small ? 0.72 : 1;
  return (
    <View style={[styles.robotWrap, { transform: [{ scale }] }]}>
      <View style={styles.antennaLine} />
      <View style={styles.antennaBall} />
      <View style={styles.robotHead}>
        <View style={styles.robotFace}>
          <Text style={styles.robotEyes}>⌒  ⌒</Text>
          <Text style={styles.robotSmile}>﹀</Text>
        </View>
      </View>
      <View style={styles.robotBody}>
        <Text style={styles.robotAI}>AI</Text>
      </View>
      <View style={styles.robotBook}><Text style={styles.robotBookText}>AI</Text></View>
    </View>
  );
}

function Brand() {
  return (
    <View style={styles.brandRow}>
      <View style={styles.brandIcon}><Robot small /></View>
      <Text style={styles.brandText}>AI Study <Text style={styles.brandAccent}>Agent</Text></Text>
    </View>
  );
}

function StatCard({ icon, label, value, note, soft, color }) {
  return (
    <View style={[styles.statCard, { backgroundColor: soft }]}>
      <Text style={[styles.statIcon, { color }]}>{icon}</Text>
      <Text style={styles.statLabel}>{label}</Text>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statNote}>{note}</Text>
    </View>
  );
}

function ProgressBar({ value, color = COLORS.blue }) {
  return (
    <View style={styles.progressTrack}>
      <View style={[styles.progressFill, { width: `${value}%`, backgroundColor: color }]} />
    </View>
  );
}

function BottomNav({ tab, setTab }) {
  const tabs = [
    ['home', '⌂', 'Trang chủ'],
    ['subjects', '▤', 'Môn học'],
    ['agent', '◉', 'Chat AI'],
    ['quiz', '▦', 'Quiz'],
    ['plan', '▣', 'Kế hoạch'],
  ];
  return (
    <View style={styles.bottomNav}>
      {tabs.map(([key, icon, label]) => {
        const active = tab === key;
        return (
          <TouchableOpacity key={key} style={[styles.navItem, active && styles.navItemActive]} onPress={() => setTab(key)}>
            <Text style={[styles.navIcon, active && styles.navActive]}>{icon}</Text>
            <Text style={[styles.navLabel, active && styles.navActive]}>{label}</Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

function HomeScreen({ setTab }) {
  return (
    <ScrollView contentContainerStyle={styles.page} showsVerticalScrollIndicator={false}>
      <View style={styles.topRow}>
        <Brand />
        <View style={styles.bell}><Text style={styles.bellText}>♧</Text><View style={styles.bellDot} /></View>
      </View>

      <View style={styles.heroHome}>
        <View style={styles.heroHomeText}>
          <Text style={styles.hello}>Xin chào,</Text>
          <Text style={styles.userName}>Nguyễn Công Thành 👋</Text>
          <Text style={styles.motto}>Mỗi nỗ lực nhỏ hôm nay{`\n`}sẽ tạo nên thay đổi lớn ngày mai!</Text>
        </View>
        <View style={styles.heroRobot}><Robot /></View>
      </View>

      <View style={styles.statsRow}>
        <StatCard icon="⌁" label="Môn học" value="5" note="Đang theo học" soft={COLORS.softBlue} color={COLORS.blue} />
        <StatCard icon="▤" label="Tài liệu" value="24" note="Đã lưu" soft={COLORS.softTeal} color={COLORS.teal} />
        <StatCard icon="▦" label="Quiz" value="12" note="Đã làm" soft={COLORS.softPurple} color={COLORS.purple} />
        <StatCard icon="▥" label="Tiến độ" value="68%" note="Hoàn thành" soft={COLORS.softOrange} color={COLORS.orange} />
      </View>

      <View style={styles.panel}>
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>▥  Tiến độ tuần này</Text>
          <Text style={styles.sectionHint}>06 - 12 Thg 1, 2025</Text>
        </View>
        <View style={styles.chartArea}>
          {[18, 35, 30, 44, 42, 58, 69].map((n, i) => (
            <View key={i} style={styles.chartCol}>
              <View style={styles.chartGuide} />
              <View style={[styles.chartPoint, { bottom: n * 1.25 }]} />
              <Text style={styles.chartDay}>{['T2','T3','T4','T5','T6','T7','CN'][i]}</Text>
            </View>
          ))}
          <View style={styles.chartBadge}><Text style={styles.chartBadgeText}>68%</Text></View>
        </View>
      </View>

      <View style={styles.panel}>
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>🔔  Nhắc việc gần nhất</Text>
          <Text style={styles.linkText}>Xem tất cả ›</Text>
        </View>
        {reminders.map((item, index) => (
          <View key={item.title} style={[styles.reminderRow, index > 0 && styles.rowDivider]}>
            <View style={[styles.reminderIcon, { backgroundColor: index === 0 ? COLORS.softBlue : index === 1 ? COLORS.softTeal : COLORS.softPurple }]}>
              <Text style={{ color: item.color, fontSize: 19 }}>{item.icon}</Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.reminderTitle}>{item.title}</Text>
              <Text style={styles.reminderDue}>{item.due}</Text>
            </View>
            <View style={[styles.badge, { backgroundColor: index === 0 ? '#FFEDEC' : index === 1 ? '#EAF5FF' : '#EEF2F7' }]}>
              <Text style={[styles.badgeText, { color: item.color }]}>{item.badge}</Text>
            </View>
          </View>
        ))}
      </View>

      <TouchableOpacity style={styles.ctaBanner} onPress={() => setTab('subjects')}>
        <Text style={styles.ctaSketch}>✈   Kiến thức hôm nay{`\n`}     Kiến tạo tương lai ♡</Text>
        <View style={styles.ctaButton}><Text style={styles.ctaButtonText}>Tiếp tục học  ›</Text></View>
      </TouchableOpacity>
    </ScrollView>
  );
}

function SubjectsScreen() {
  const [query, setQuery] = useState('');
  const visible = subjects.filter((s) => s.name.toLowerCase().includes(query.toLowerCase()));
  return (
    <ScrollView contentContainerStyle={styles.page} showsVerticalScrollIndicator={false}>
      <View style={styles.subjectHero}>
        <View style={{ flex: 1 }}>
          <Text style={styles.screenTitle}>Môn <Text style={styles.gradientWord}>học</Text></Text>
          <Text style={styles.screenSubtitle}>Quản lý môn học, theo dõi tiến độ{`\n`}và chinh phục mục tiêu của bạn!</Text>
        </View>
        <Robot />
      </View>

      <View style={styles.searchRow}>
        <View style={styles.searchBox}>
          <Text style={styles.searchIcon}>⌕</Text>
          <TextInput value={query} onChangeText={setQuery} placeholder="Tìm kiếm môn học..." placeholderTextColor="#99A8BF" style={styles.searchInput} />
        </View>
        <TouchableOpacity style={styles.addButton}><Text style={styles.addButtonText}>＋  Thêm môn</Text></TouchableOpacity>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filterRow}>
        {['Tất cả (4)', 'Đang học (4)', 'Đã hoàn thành (0)', 'Chưa bắt đầu (0)'].map((x, i) => (
          <View key={x} style={[styles.filterPill, i === 0 && styles.filterPillActive]}><Text style={[styles.filterText, i === 0 && styles.filterTextActive]}>{x}</Text></View>
        ))}
      </ScrollView>

      <View style={styles.subjectGrid}>
        {visible.map((item) => (
          <View key={item.id} style={styles.subjectCard}>
            <View style={styles.subjectTop}>
              <View style={[styles.subjectIconBox, { backgroundColor: item.soft }]}><Text style={[styles.subjectIconText, { color: item.color }]}>{item.icon}</Text></View>
              <View style={{ flex: 1 }}>
                <Text style={styles.subjectName}>{item.name}</Text>
                <Text style={styles.subjectCode}>{item.code}</Text>
              </View>
              <Text style={styles.more}>⋮</Text>
            </View>
            <View style={styles.subjectMetaRow}>
              <Text style={styles.subjectMeta}>🎓  {item.credits} tín chỉ</Text>
              <View style={styles.metaDivider} />
              <Text style={[styles.subjectMeta, { color: item.color }]}>◎  Mục tiêu {item.target}</Text>
            </View>
            <View style={styles.progressLabelRow}><Text style={styles.progressLabel}>Tiến độ học tập</Text><Text style={[styles.progressPercent, { color: item.color }]}>{item.progress}%</Text></View>
            <ProgressBar value={item.progress} color={item.color} />
            <TouchableOpacity style={[styles.continueBtn, { backgroundColor: item.soft }]}><Text style={[styles.continueText, { color: item.color }]}>Tiếp tục học  →</Text></TouchableOpacity>
          </View>
        ))}
      </View>

      <Text style={styles.footerQuote}>🌱  Mỗi môn học là một bước tiến đến phiên bản tốt hơn của bạn! ♡</Text>
    </ScrollView>
  );
}

function PlanScreen() {
  return (
    <ScrollView contentContainerStyle={styles.page} showsVerticalScrollIndicator={false}>
      <View style={styles.planHeader}>
        <View style={{ flex: 1 }}>
          <Text style={styles.screenTitle}>Kế hoạch <Text style={styles.gradientWord}>học tập</Text></Text>
          <Text style={styles.screenSubtitle}>Học thông minh hơn mỗi ngày{`\n`}với lộ trình dành riêng cho bạn</Text>
        </View>
      </View>

      <View style={styles.personalPlanCard}>
        <View style={{ flex: 1 }}>
          <Text style={styles.personalTitle}>Lộ trình cá nhân hóa{`\n`}dành riêng cho bạn</Text>
          <Text style={styles.personalBullet}>◎  Phù hợp năng lực</Text>
          <Text style={styles.personalBullet}>▥  Tối ưu thời gian</Text>
          <Text style={styles.personalBullet}>★  Giúp bạn đạt mục tiêu</Text>
          <Text style={styles.handwrite}>Học đúng – Học đủ – Tiến xa hơn! →</Text>
        </View>
        <Robot />
      </View>

      <View style={styles.sectionHeader}>
        <Text style={styles.sectionTitle}>Lịch học tuần này</Text>
        <Text style={styles.sectionHint}>‹   6 – 12 Tháng 10, 2024   ›</Text>
      </View>

      <View style={styles.daysRow}>
        {['T2\n6','T3\n7','T4\n8','T5\n9','T6\n10','T7\n11','CN\n12'].map((d, i) => (
          <View key={d} style={[styles.dayBox, i === 0 && styles.dayBoxActive]}><Text style={[styles.dayText, i === 0 && styles.dayTextActive]}>{d}</Text></View>
        ))}
      </View>

      {plans.map((item) => (
        <View key={item.subject} style={styles.scheduleCard}>
          <View style={styles.timeCol}><Text style={styles.timeMain}>{item.time}</Text><Text style={styles.timeEnd}>– {item.end}</Text></View>
          <View style={styles.scheduleIcon}><Text style={{ fontSize: 20, color: item.color }}>{item.icon}</Text></View>
          <View style={{ flex: 1 }}><Text style={styles.scheduleSubject}>{item.subject}</Text><Text style={styles.scheduleDetail}>{item.detail}</Text></View>
          <View><Text style={styles.duration}>◷ 60 phút</Text><View style={[styles.badge, { backgroundColor: item.color === COLORS.teal ? '#E7F8F3' : item.color === COLORS.blue ? '#E9F4FF' : '#F1F3F7' }]}><Text style={[styles.badgeText, { color: item.color }]}>{item.status}</Text></View></View>
        </View>
      ))}

      <View style={styles.panel}>
        <View style={styles.sectionHeader}><Text style={styles.sectionTitle}>🔔  Nhắc nhở & hạn nộp</Text><Text style={styles.linkText}>Xem tất cả ›</Text></View>
        {reminders.map((r, i) => <View key={r.title} style={[styles.reminderRow, i > 0 && styles.rowDivider]}><View style={[styles.reminderIcon, { backgroundColor: i === 0 ? COLORS.softTeal : i === 1 ? COLORS.softPurple : COLORS.softBlue }]}><Text>{r.icon}</Text></View><View style={{ flex: 1 }}><Text style={styles.reminderTitle}>{r.title.replace('Làm quiz Chương 3 - Vật lý','Ôn tập chương 3')}</Text><Text style={styles.reminderDue}>{i === 0 ? 'Hóa học' : i === 1 ? 'Tiếng Anh' : 'Văn học'}</Text></View><Text style={[styles.reminderDue, i === 0 && { color: COLORS.red }]}>{i === 0 ? 'Ngày mai\n10 Tháng 10' : i === 1 ? '12 Tháng 10' : '15 Tháng 10'}</Text></View>)}
      </View>

      <View style={styles.reviewPanel}>
        <Text style={styles.sectionTitle}>▥  Chủ đề cần ôn thêm</Text>
        <Text style={styles.sectionHint}>Dựa trên kết quả học tập gần đây</Text>
        <View style={styles.reviewRow}>
          {[
            ['◎', 'Hàm số và đồ thị', 'Toán học', '#FFECEC', COLORS.red],
            ['⚗', 'Cân bằng hóa học', 'Hóa học', '#FFF2E7', '#EF7B23'],
            ['▤', 'Đọc hiểu', 'Tiếng Anh', '#F2ECFF', COLORS.purple],
          ].map(([icon,title,sub,bg,c]) => <View key={title} style={[styles.reviewChip,{backgroundColor:bg}]}><Text style={{color:c,fontSize:18}}>{icon}</Text><View><Text style={[styles.reviewTitle,{color:c}]}>{title}</Text><Text style={styles.reviewSub}>{sub}</Text></View></View>)}
        </View>
      </View>
    </ScrollView>
  );
}

function AgentScreen() {
  const [message, setMessage] = useState('');
  const [messages, setMessages] = useState([
    { role: 'assistant', text: 'Chào Thành 👋 Mình là Study Agent cá nhân của bạn. Hôm nay bạn muốn ôn lại kiến thức nào?' },
  ]);
  const send = () => {
    const value = message.trim();
    if (!value) return;
    setMessages((old) => [...old, { role: 'user', text: value }, { role: 'assistant', text: 'Mình sẽ đối chiếu đề cương, tài liệu chung và lịch sử học tập riêng của bạn để trả lời phù hợp.' }]);
    setMessage('');
  };
  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.chatPage}>
        <View style={styles.topRow}><Brand /><Text style={styles.chatContext}>Trợ lý cá nhân</Text></View>
        <View style={styles.agentSummary}><Robot small /><View style={{ flex: 1 }}><Text style={styles.agentTitle}>Study Agent của Thành</Text><Text style={styles.agentSub}>Tri thức chung + memory cá nhân + mục tiêu học tập</Text></View></View>
        <ScrollView style={styles.chatList} contentContainerStyle={{ paddingBottom: 20 }}>
          {messages.map((m, i) => <View key={i} style={[styles.message, m.role === 'user' ? styles.userMessage : styles.aiMessage]}><Text style={[styles.messageText, m.role === 'user' && { color: 'white' }]}>{m.text}</Text></View>)}
        </ScrollView>
        <View style={styles.composer}><TextInput value={message} onChangeText={setMessage} placeholder="Hỏi Study Agent..." placeholderTextColor="#9AA9BF" style={styles.composerInput} /><TouchableOpacity style={styles.sendBtn} onPress={send}><Text style={styles.sendBtnText}>➤</Text></TouchableOpacity></View>
      </View>
    </SafeAreaView>
  );
}

function QuizScreen() {
  const [selected, setSelected] = useState(0);
  const options = ['Mô hình IaaS', 'Mô hình SaaS', 'Mô hình PaaS', 'Mạng riêng ảo'];
  return (
    <ScrollView contentContainerStyle={styles.page}>
      <View style={styles.quizHeader}><Text style={styles.screenTitle}>Quiz <Text style={styles.gradientWord}>thông minh</Text></Text><Text style={styles.screenSubtitle}>Học từ mỗi câu trả lời để cá nhân hóa lộ trình của bạn</Text></View>
      <View style={styles.quizCard}><Text style={styles.quizStep}>CÂU 3 / 10</Text><Text style={styles.quizQuestion}>Dịch vụ nào cung cấp hạ tầng máy chủ ảo hóa cho người dùng?</Text>{options.map((o,i)=><TouchableOpacity key={o} style={[styles.option, selected===i && styles.optionActive]} onPress={()=>setSelected(i)}><View style={[styles.optionLetter, selected===i && styles.optionLetterActive]}><Text style={[styles.optionLetterText, selected===i && {color:'white'}]}>{String.fromCharCode(65+i)}</Text></View><Text style={styles.optionText}>{o}</Text></TouchableOpacity>)}<TouchableOpacity style={styles.quizNext}><Text style={styles.quizNextText}>Câu tiếp theo  →</Text></TouchableOpacity></View>
      <View style={styles.aiInsight}><Text style={styles.aiInsightTitle}>🧠 Agent đang học về bạn</Text><Text style={styles.aiInsightText}>Các câu sai sẽ tự động cập nhật chủ đề cần ôn và điều chỉnh kế hoạch học tiếp theo.</Text></View>
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
        <Robot />
        <Text style={styles.loginTitle}>AI Study <Text style={styles.brandAccent}>Agent</Text></Text>
        <Text style={styles.loginSubtitle}>Trợ lý học tập đồng hành cùng bạn mỗi ngày</Text>
        <TextInput value={email} onChangeText={setEmail} autoCapitalize="none" style={styles.loginInput} placeholder="Email" />
        <TextInput value={password} onChangeText={setPassword} secureTextEntry style={styles.loginInput} placeholder="Mật khẩu" />
        <TouchableOpacity style={styles.loginButton} onPress={onLogin}><Text style={styles.loginButtonText}>Đăng nhập</Text></TouchableOpacity>
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

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar barStyle="dark-content" />
      <View style={styles.app}>{screen}</View>
      <BottomNav tab={tab} setTab={setTab} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.bg }, app: { flex: 1 }, page: { paddingHorizontal: 18, paddingTop: 12, paddingBottom: 115, backgroundColor: COLORS.bg },
  topRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }, brandRow: { flexDirection: 'row', alignItems: 'center', gap: 8 }, brandIcon: { width: 34, height: 34, overflow: 'hidden', alignItems: 'center', justifyContent: 'center' }, brandText: { fontSize: 20, fontWeight: '800', color: COLORS.navy }, brandAccent: { color: COLORS.teal },
  bell: { width: 40, height: 40, borderRadius: 20, backgroundColor: 'white', alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: COLORS.line }, bellText: { fontSize: 20, color: COLORS.navy }, bellDot: { position: 'absolute', right: 5, top: 5, width: 8, height: 8, borderRadius: 4, backgroundColor: COLORS.red },
  heroHome: { minHeight: 225, borderRadius: 30, backgroundColor: '#EDF7FF', overflow: 'hidden', flexDirection: 'row', padding: 18, marginBottom: 14 }, heroHomeText: { flex: 1, zIndex: 2 }, hello: { fontSize: 18, color: COLORS.muted, marginTop: 14 }, userName: { fontSize: 29, lineHeight: 35, fontWeight: '900', color: COLORS.navy, marginTop: 4 }, motto: { fontSize: 15, lineHeight: 22, color: COLORS.muted, marginTop: 8 }, heroRobot: { position: 'absolute', right: -5, bottom: -2 },
  statsRow: { flexDirection: 'row', gap: 8, marginBottom: 14 }, statCard: { flex: 1, minHeight: 120, borderRadius: 20, padding: 12 }, statIcon: { fontSize: 22, marginBottom: 4 }, statLabel: { fontSize: 12, color: COLORS.navy }, statValue: { fontSize: 27, fontWeight: '900', color: COLORS.navy, marginTop: 2 }, statNote: { fontSize: 10, color: COLORS.muted, marginTop: 2 },
  panel: { backgroundColor: 'white', borderRadius: 22, padding: 15, borderWidth: 1, borderColor: COLORS.line, marginBottom: 14 }, sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }, sectionTitle: { fontSize: 18, fontWeight: '800', color: COLORS.navy }, sectionHint: { fontSize: 11, color: COLORS.muted }, linkText: { fontSize: 12, color: COLORS.blue, fontWeight: '700' },
  chartArea: { height: 155, flexDirection: 'row', paddingTop: 18, paddingHorizontal: 6, alignItems: 'flex-end', position: 'relative' }, chartCol: { flex: 1, height: 125, alignItems: 'center', justifyContent: 'flex-end' }, chartGuide: { position: 'absolute', top: 0, bottom: 20, width: 1, backgroundColor: '#ECF1F7' }, chartPoint: { position: 'absolute', width: 10, height: 10, borderRadius: 5, backgroundColor: COLORS.blue, borderWidth: 2, borderColor: 'white' }, chartDay: { fontSize: 11, color: COLORS.muted, marginBottom: 3 }, chartBadge: { position: 'absolute', right: 45, top: 12, backgroundColor: COLORS.blue, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 9 }, chartBadgeText: { color: 'white', fontWeight: '800' },
  reminderRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10 }, rowDivider: { borderTopWidth: 1, borderTopColor: '#EDF1F6' }, reminderIcon: { width: 38, height: 38, borderRadius: 12, alignItems: 'center', justifyContent: 'center' }, reminderTitle: { fontSize: 13, fontWeight: '700', color: COLORS.navy }, reminderDue: { fontSize: 10.5, color: COLORS.muted, marginTop: 3 }, badge: { borderRadius: 14, paddingHorizontal: 10, paddingVertical: 6 }, badgeText: { fontSize: 10.5, fontWeight: '700' },
  ctaBanner: { backgroundColor: '#E9FAF7', borderRadius: 20, padding: 15, marginBottom: 10, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }, ctaSketch: { color: '#1576E8', fontSize: 13, fontStyle: 'italic', lineHeight: 18 }, ctaButton: { backgroundColor: COLORS.blue, borderRadius: 18, paddingHorizontal: 18, paddingVertical: 12 }, ctaButtonText: { color: 'white', fontWeight: '800' },
  bottomNav: { position: 'absolute', left: 0, right: 0, bottom: 0, height: 82, backgroundColor: 'white', borderTopWidth: 1, borderTopColor: COLORS.line, flexDirection: 'row', paddingHorizontal: 10, paddingTop: 8 }, navItem: { flex: 1, alignItems: 'center', justifyContent: 'center', borderRadius: 18, marginHorizontal: 2 }, navItemActive: { backgroundColor: '#EEF6FF' }, navIcon: { fontSize: 22, color: '#5F7191', lineHeight: 26 }, navLabel: { fontSize: 10.5, color: '#5F7191', marginTop: 2 }, navActive: { color: COLORS.blue, fontWeight: '800' },
  subjectHero: { flexDirection: 'row', minHeight: 190, alignItems: 'center' }, screenTitle: { fontSize: 36, fontWeight: '900', color: COLORS.navy, lineHeight: 41 }, gradientWord: { color: COLORS.teal }, screenSubtitle: { color: COLORS.muted, fontSize: 15, lineHeight: 22, marginTop: 6 }, searchRow: { flexDirection: 'row', gap: 10, marginBottom: 14 }, searchBox: { flex: 1, height: 54, borderRadius: 18, borderWidth: 1.2, borderColor: '#CDDBEC', backgroundColor: 'white', flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14 }, searchIcon: { fontSize: 25, color: '#5574A5', marginRight: 8 }, searchInput: { flex: 1, fontSize: 14, color: COLORS.navy }, addButton: { backgroundColor: COLORS.blue, borderRadius: 18, paddingHorizontal: 14, justifyContent: 'center' }, addButtonText: { color: 'white', fontWeight: '800' },
  filterRow: { gap: 8, paddingBottom: 12 }, filterPill: { borderRadius: 18, paddingHorizontal: 14, paddingVertical: 9, borderWidth: 1, borderColor: COLORS.line, backgroundColor: 'white' }, filterPillActive: { backgroundColor: '#EAF5FF', borderColor: '#D8ECFF' }, filterText: { fontSize: 11.5, color: COLORS.muted }, filterTextActive: { color: COLORS.blue, fontWeight: '800' }, subjectGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 }, subjectCard: { width: '48.5%', backgroundColor: 'white', borderRadius: 20, padding: 13, borderWidth: 1, borderColor: COLORS.line }, subjectTop: { flexDirection: 'row', gap: 8, alignItems: 'flex-start' }, subjectIconBox: { width: 43, height: 43, borderRadius: 14, alignItems: 'center', justifyContent: 'center' }, subjectIconText: { fontSize: 22, fontWeight: '800' }, subjectName: { fontSize: 14, fontWeight: '800', color: COLORS.navy }, subjectCode: { fontSize: 11, color: COLORS.muted, marginTop: 2 }, more: { color: '#7690B3', fontSize: 18 },
  subjectMetaRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 14 }, subjectMeta: { fontSize: 10, color: COLORS.navy, fontWeight: '600' }, metaDivider: { width: 1, height: 21, backgroundColor: COLORS.line }, progressLabelRow: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 13 }, progressLabel: { fontSize: 10.5, color: COLORS.muted }, progressPercent: { fontSize: 11, fontWeight: '800' }, progressTrack: { height: 8, borderRadius: 6, backgroundColor: '#E8EFF7', overflow: 'hidden', marginTop: 6 }, progressFill: { height: '100%', borderRadius: 6 }, continueBtn: { marginTop: 12, borderRadius: 13, alignItems: 'center', paddingVertical: 10 }, continueText: { fontSize: 11, fontWeight: '800' }, footerQuote: { textAlign: 'center', color: '#3D83C8', fontStyle: 'italic', fontSize: 12, marginVertical: 24 },
  planHeader: { minHeight: 115, paddingTop: 24 }, personalPlanCard: { backgroundColor: '#EAF6FF', borderRadius: 24, minHeight: 210, flexDirection: 'row', padding: 18, marginBottom: 18, overflow: 'hidden' }, personalTitle: { fontSize: 20, lineHeight: 25, color: COLORS.navy, fontWeight: '900', marginBottom: 10 }, personalBullet: { fontSize: 12, color: '#61779A', marginTop: 7 }, handwrite: { marginTop: 13, color: '#2A83E4', fontSize: 11.5, fontStyle: 'italic' }, daysRow: { flexDirection: 'row', gap: 7, marginBottom: 12 }, dayBox: { flex: 1, backgroundColor: '#F1F6FB', borderRadius: 15, paddingVertical: 10, alignItems: 'center' }, dayBoxActive: { backgroundColor: COLORS.blue }, dayText: { fontSize: 12, color: COLORS.navy, textAlign: 'center', lineHeight: 18 }, dayTextActive: { color: 'white', fontWeight: '800' },
  scheduleCard: { backgroundColor: 'white', borderRadius: 16, borderWidth: 1, borderColor: COLORS.line, padding: 12, marginBottom: 9, flexDirection: 'row', alignItems: 'center', gap: 10 }, timeCol: { width: 54 }, timeMain: { fontSize: 13, fontWeight: '800', color: COLORS.navy }, timeEnd: { fontSize: 11, color: COLORS.muted, marginTop: 2 }, scheduleIcon: { width: 37, height: 37, borderRadius: 11, backgroundColor: '#EEF6FF', alignItems: 'center', justifyContent: 'center' }, scheduleSubject: { fontSize: 13, color: COLORS.navy, fontWeight: '800' }, scheduleDetail: { fontSize: 10.5, color: COLORS.muted, marginTop: 3 }, duration: { fontSize: 10, color: COLORS.muted, marginBottom: 5 }, reviewPanel: { backgroundColor: 'white', borderRadius: 20, borderWidth: 1, borderColor: COLORS.line, padding: 14, marginBottom: 12 }, reviewRow: { flexDirection: 'row', gap: 7, marginTop: 10 }, reviewChip: { flex: 1, borderRadius: 15, padding: 9, flexDirection: 'row', alignItems: 'center', gap: 6 }, reviewTitle: { fontSize: 9.5, fontWeight: '800' }, reviewSub: { fontSize: 8.5, color: COLORS.muted },
  chatPage: { flex: 1, paddingHorizontal: 18, paddingTop: 12, paddingBottom: 95, backgroundColor: COLORS.bg }, chatContext: { fontSize: 12, color: COLORS.muted }, agentSummary: { backgroundColor: '#EDF7FF', borderRadius: 22, padding: 12, flexDirection: 'row', alignItems: 'center', marginBottom: 12 }, agentTitle: { fontSize: 16, color: COLORS.navy, fontWeight: '800' }, agentSub: { fontSize: 11, color: COLORS.muted, marginTop: 3 }, chatList: { flex: 1 }, message: { maxWidth: '83%', borderRadius: 18, paddingHorizontal: 14, paddingVertical: 11, marginBottom: 9 }, aiMessage: { alignSelf: 'flex-start', backgroundColor: 'white', borderWidth: 1, borderColor: COLORS.line }, userMessage: { alignSelf: 'flex-end', backgroundColor: COLORS.blue }, messageText: { color: COLORS.navy, fontSize: 13.5, lineHeight: 19 }, composer: { height: 56, borderRadius: 19, borderWidth: 1, borderColor: COLORS.line, backgroundColor: 'white', flexDirection: 'row', alignItems: 'center', paddingLeft: 14, paddingRight: 6 }, composerInput: { flex: 1, color: COLORS.navy }, sendBtn: { width: 42, height: 42, borderRadius: 14, backgroundColor: COLORS.blue, alignItems: 'center', justifyContent: 'center' }, sendBtnText: { color: 'white', fontSize: 18 },
  quizHeader: { paddingTop: 30, marginBottom: 20 }, quizCard: { backgroundColor: 'white', borderRadius: 22, borderWidth: 1, borderColor: COLORS.line, padding: 18 }, quizStep: { color: COLORS.blue, fontSize: 11, fontWeight: '800', letterSpacing: 1 }, quizQuestion: { fontSize: 20, lineHeight: 28, fontWeight: '900', color: COLORS.navy, marginTop: 10, marginBottom: 16 }, option: { borderRadius: 15, borderWidth: 1, borderColor: COLORS.line, padding: 12, flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 9 }, optionActive: { borderColor: COLORS.blue, backgroundColor: '#F0F7FF' }, optionLetter: { width: 30, height: 30, borderRadius: 10, backgroundColor: '#EDF2F8', alignItems: 'center', justifyContent: 'center' }, optionLetterActive: { backgroundColor: COLORS.blue }, optionLetterText: { color: COLORS.navy, fontWeight: '800' }, optionText: { fontSize: 13, color: COLORS.navy, fontWeight: '600' }, quizNext: { backgroundColor: COLORS.blue, borderRadius: 15, alignItems: 'center', paddingVertical: 13, marginTop: 8 }, quizNextText: { color: 'white', fontWeight: '800' }, aiInsight: { backgroundColor: '#EAF8F5', borderRadius: 20, padding: 16, marginTop: 14 }, aiInsightTitle: { fontSize: 15, color: COLORS.navy, fontWeight: '800' }, aiInsightText: { fontSize: 12, color: COLORS.muted, lineHeight: 18, marginTop: 5 },
  loginSafe: { flex: 1, backgroundColor: '#EFF8FF' }, loginWrap: { flex: 1, paddingHorizontal: 28, justifyContent: 'center', alignItems: 'center' }, loginTitle: { fontSize: 30, fontWeight: '900', color: COLORS.navy, marginTop: 10 }, loginSubtitle: { fontSize: 13, color: COLORS.muted, marginTop: 5, marginBottom: 22 }, loginInput: { width: '100%', height: 54, backgroundColor: 'white', borderRadius: 17, borderWidth: 1, borderColor: COLORS.line, paddingHorizontal: 15, marginBottom: 10, color: COLORS.navy }, loginButton: { width: '100%', height: 54, backgroundColor: COLORS.blue, borderRadius: 17, alignItems: 'center', justifyContent: 'center', marginTop: 6 }, loginButtonText: { color: 'white', fontSize: 15, fontWeight: '800' },
  robotWrap: { width: 150, height: 150, alignItems: 'center', justifyContent: 'center' }, antennaLine: { position: 'absolute', top: 10, width: 4, height: 18, borderRadius: 2, backgroundColor: COLORS.blue }, antennaBall: { position: 'absolute', top: 2, width: 13, height: 13, borderRadius: 7, backgroundColor: COLORS.blue2 }, robotHead: { position: 'absolute', top: 28, width: 92, height: 66, borderRadius: 28, backgroundColor: '#E9F3FA', borderWidth: 3, borderColor: '#94C6F5', alignItems: 'center', justifyContent: 'center' }, robotFace: { width: 69, height: 42, borderRadius: 18, backgroundColor: '#102E57', alignItems: 'center', justifyContent: 'center' }, robotEyes: { color: 'white', fontSize: 14, lineHeight: 15 }, robotSmile: { color: 'white', fontSize: 15, marginTop: -3 }, robotBody: { position: 'absolute', top: 86, width: 65, height: 47, borderRadius: 22, backgroundColor: '#DCEFFF', borderWidth: 2, borderColor: '#7BB6EE', alignItems: 'center', justifyContent: 'center' }, robotAI: { color: COLORS.blue, fontSize: 20, fontWeight: '900' }, robotBook: { position: 'absolute', bottom: 7, left: 18, width: 54, height: 38, borderRadius: 6, backgroundColor: COLORS.teal, transform: [{ rotate: '-8deg' }], alignItems: 'center', justifyContent: 'center' }, robotBookText: { color: 'white', fontSize: 16, fontWeight: '900' },
});