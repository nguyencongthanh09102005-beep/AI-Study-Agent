import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
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
import * as DocumentPicker from 'expo-document-picker';
import FloatingStudyChat from './src/FloatingStudyChat';
import StudyRoom from './src/StudyRoom';
import ConnectionSettings from './src/ConnectionSettings';
import { restoreServerAddress } from './src/serverAddressStorage';
import StudyDateTimePicker from './src/StudyDateTimePicker';
const {
  localDateKey, addDays, getWeekDates, getPlanOverview,
  getVisiblePlanTasks, splitReminders, findTaskConflicts,
} = require('./src/plan-utils');

function localInputDate(days = 0, hour = 19, minute = 0) {
  const date = new Date();
  date.setDate(date.getDate() + days);
  date.setHours(hour, minute, 0, 0);
  const pad = value => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

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

function HomeScreen({ dashboard, setTab, loading, onOpenStudy, onAskAI, onOpenQuiz, onOpenSubjectJourney }) {
  const user = dashboard?.user || {};
  const subjects = dashboard?.subjects || [];
  const tasks = dashboard?.tasks || [];

  return (
    <ScrollView contentContainerStyle={styles.page}>
      <Header
        title={`Xin chào, ${(user.name || 'bạn').split(' ').slice(-1)[0]} 👋`}
        subtitle="Hôm nay bạn muốn học gì?"
        userName={user.name}
      />

      <View style={styles.homeMetricsRow}>
        <View style={styles.homeMetric}><Text style={styles.homeMetricValue}>{dashboard?.stats?.subject_count || 0}</Text><Text style={styles.homeMetricLabel}>Môn học</Text></View>
        <View style={styles.homeMetric}><Text style={styles.homeMetricValue}>{dashboard?.stats?.document_count || 0}</Text><Text style={styles.homeMetricLabel}>Tài liệu</Text></View>
        <View style={styles.homeMetric}><Text style={styles.homeMetricValue}>{dashboard?.stats?.quiz_attempt_count || 0}</Text><Text style={styles.homeMetricLabel}>Bài làm</Text></View>
      </View>

      {dashboard?.next_best_action && (
        <TouchableOpacity style={styles.recommendCard}
          onPress={() => {
            const item = dashboard.next_best_action;
            if (item.kind === 'weakness' || item.kind === 'check') {
              onOpenQuiz(item.subject_id || null);
            } else if (item.kind === 'setup') {
              onOpenSubjectJourney(null, 'create');
            } else if (item.kind === 'plan') {
              onOpenSubjectJourney(item.subject_id || null, 'roadmap');
            } else if (item.kind === 'task' || item.kind === 'deadline') {
              setTab('plan');
            } else {
              onAskAI();
            }
          }}>
          <Text style={styles.eyebrow}>✦ STUDY AGENT ĐỀ XUẤT</Text>
          <Text style={styles.cardTitle}>{dashboard.next_best_action.title}</Text>
          <Text style={styles.muted}>{dashboard.next_best_action.reason}</Text>
          <Text style={styles.smallActionText}>Xem việc nên làm tiếp →</Text>
        </TouchableOpacity>
      )}

      {loading && <ActivityIndicator />}

      <Text style={styles.sectionTitle}>Lịch học hôm nay & sắp tới</Text>
      {tasks.length ? tasks.slice(0, 5).map((task) => (
        <TouchableOpacity key={task.id} style={styles.card}
          disabled={task.source !== 'roadmap' || !task.roadmap_session_id}
          onPress={() => onOpenStudy(task.id)}>
          <View style={styles.rowBetween}>
            <Text style={[styles.cardTitle, { flex: 1 }]}>{task.title}</Text>
            <Text style={styles.time}>{String(task.study_at || '').slice(11, 16)}</Text>
          </View>
          <Text style={styles.muted}>
            {task.subject_name || 'Tự học'} · {task.duration} phút
            {task.source === 'adaptive' ? ' · Adaptive' : ''}
          </Text>
          {task.source === 'roadmap' && !!task.roadmap_session_id &&
            <Text style={styles.smallActionText}>Vào không gian học tập →</Text>}
        </TouchableOpacity>
      )) : <View style={styles.card}><Text style={styles.muted}>Chưa có nhiệm vụ học nào.</Text></View>}

      <Text style={styles.sectionTitle}>Tiến độ môn học</Text>
      {subjects.slice(0, 3).map((item) => (
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

function SubjectForm({ initial, onSave, onCancel, busy }) {
  const [name, setName] = useState(initial?.name || '');
  const [code, setCode] = useState(initial?.code || '');
  const [credits, setCredits] = useState(String(initial?.credits || 0));
  const [target, setTarget] = useState(String(initial?.target_score || 0));
  const [description, setDescription] = useState(initial?.description || '');

  return (
    <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
      <Header title={initial ? 'Sửa môn học' : 'Tạo môn học'} subtitle="Thiết lập không gian học tập của bạn" />
      <Text style={styles.fieldLabel}>Tên môn học *</Text>
      <TextInput style={styles.fieldInput} value={name} onChangeText={setName} placeholder="Ví dụ: Điện toán đám mây" />
      <Text style={styles.fieldLabel}>Mã môn học</Text>
      <TextInput style={styles.fieldInput} value={code} onChangeText={setCode} placeholder="0104123039" />
      <Text style={styles.fieldLabel}>Số tín chỉ</Text>
      <TextInput style={styles.fieldInput} value={credits} onChangeText={setCredits} keyboardType="number-pad" />
      <Text style={styles.fieldLabel}>Mục tiêu điểm (0–10)</Text>
      <TextInput style={styles.fieldInput} value={target} onChangeText={setTarget} keyboardType="decimal-pad" />
      <Text style={styles.fieldLabel}>Mô tả môn học</Text>
      <TextInput style={[styles.fieldInput, { minHeight: 110, textAlignVertical: 'top' }]} multiline value={description} onChangeText={setDescription} />
      <TouchableOpacity style={styles.primaryButton} disabled={busy} onPress={() => onSave({
        name: name.trim(), code: code.trim(), credits: credits.trim(),
        target_score: target.replace(',', '.'), description: description.trim(),
      })}>
        <Text style={styles.primaryButtonText}>{busy ? 'Đang lưu…' : initial ? 'Lưu thay đổi' : 'Tạo môn học'}</Text>
      </TouchableOpacity>
      <TouchableOpacity style={styles.secondaryAction} onPress={onCancel}>
        <Text style={styles.secondaryActionText}>Quay lại</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

function SubjectsScreen({ subjects, userName, refreshData, onOpenStudy, onOpenQuiz, entryIntent }) {
  const [mode, setMode] = useState('list');
  const [selectedId, setSelectedId] = useState(null);
  const [editing, setEditing] = useState(null);
  const [detail, setDetail] = useState(null);
  const [roadmap, setRoadmap] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [docPreview, setDocPreview] = useState(null);
  const [sharedDocPreview, setSharedDocPreview] = useState(null);
  const [docSummary, setDocSummary] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [courseFilter, setCourseFilter] = useState('all');
  const [expanded, setExpanded] = useState({
    roadmap:false, personal:false, shared:false, weaknesses:false
  });
  const toggleSection = key => setExpanded(old => ({...old,[key]:!old[key]}));

  const loadDetail = async (id, revealRoadmap = false) => {
    setBusy(true);
    setError('');
    try {
      const [subjectData, documentData, roadmapData] = await Promise.all([
        api.subjectDetail(id), api.documents(),
        api.roadmap(id).catch(err => ({ready:false,notice:err.message,
          chapters:[],sessions:[]})),
      ]);
      setRoadmap(roadmapData);
      setExpanded({roadmap:revealRoadmap,personal:false,shared:false,weaknesses:false});
      setSelectedId(id);
      setDetail(subjectData);
      setDocuments(documentData.documents || []);
      setMode('detail');
    } catch (err) {
      setError(err.message || 'Không tải được môn học.');
    } finally {
      setBusy(false);
    }
  };

  // Mobile keeps four bottom tabs. A recommendation may deep-link to the
  // verified roadmap inside Môn học without creating a duplicate plan flow.
  useEffect(() => {
    if (!entryIntent) return;
    if (entryIntent.mode === 'create') {
      setEditing(null);
      setError('');
      setMode('form');
    } else if (entryIntent.subjectId) {
      loadDetail(entryIntent.subjectId, true);
    } else {
      setMode('list');
    }
  }, [entryIntent?.token]);

  const confirmScheduleRoadmap = () => {
    if (!selectedId || !roadmap?.ready || busy) return;
    const missing = (roadmap.sessions || []).filter(item => !item.scheduled_task_id).length;
    if (!missing) {
      Alert.alert('Đã có lịch', 'Các buổi trong lộ trình đã có lịch học hợp lệ.');
      return;
    }
    Alert.alert(
      'Đưa lộ trình vào Kế hoạch học?',
      'Hệ thống sẽ xếp các buổi chưa có lịch vào khung giờ trống (thứ Hai–thứ Bảy). Các buổi đã có lịch sẽ được giữ nguyên.',
      [
        {text:'Hủy',style:'cancel'},
        {text:'Xác nhận xếp lịch',onPress:async () => {
          setBusy(true); setError('');
          try {
            const result = await api.scheduleRoadmap(selectedId);
            await loadDetail(selectedId, true);
            await refreshData();
            Alert.alert('Đã cập nhật lịch', result.message || 'Các buổi mới đã được xếp lịch.');
          } catch (err) {
            setError(err.message || 'Không thể đưa lộ trình vào lịch.');
          } finally { setBusy(false); }
        }},
      ]
    );
  };

  const saveSubject = async (payload) => {
    if (!payload.name) {
      setError('Bạn chưa nhập tên môn học.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const saved = editing
        ? await api.updateSubject(editing.id, payload)
        : await api.createSubject(payload);
      await refreshData();
      setEditing(null);
      await loadDetail(saved.subject.id);
    } catch (err) {
      setError(err.message || 'Không thể lưu môn học.');
    } finally {
      setBusy(false);
    }
  };

  const confirmDeleteSubject = () => {
    Alert.alert('Xóa môn học?', 'Tài liệu, Quiz và task sẽ được giữ lại ở trạng thái chưa phân loại. Lịch sử Chat của môn sẽ bị xóa.', [
      { text: 'Hủy', style: 'cancel' },
      { text: 'Xóa môn', style: 'destructive', onPress: async () => {
        setBusy(true);
        try {
          await api.deleteSubject(selectedId);
          await refreshData();
          setMode('list');
          setSelectedId(null);
          setDetail(null);
        } catch (err) {
          setError(err.message || 'Xóa môn thất bại.');
        } finally { setBusy(false); }
      } },
    ]);
  };

  const pickFile = async () => {
    try {
      const picked = await DocumentPicker.getDocumentAsync({
        type: ['application/pdf', 'text/plain', 'text/markdown'],
        copyToCacheDirectory: true,
        multiple: false,
      });
      if (picked.canceled || !picked.assets?.length) return;
      setBusy(true);
      setError('');
      await api.uploadDocument(selectedId, picked.assets[0]);
      await loadDetail(selectedId);
      await refreshData();
    } catch (err) {
      setError(err.message || 'Không tải được tài liệu.');
    } finally { setBusy(false); }
  };

  const previewDocument = async (doc) => {
    setBusy(true);
    setError('');
    setDocSummary('');
    try {
      const data = await api.documentDetail(doc.id);
      setDocPreview(data.document);
    } catch (err) {
      setError(err.message || 'Không thể đọc tài liệu.');
    } finally { setBusy(false); }
  };

  const previewSharedDocument = async (doc) => {
    setBusy(true);
    setError('');
    try {
      const data = await api.sharedDocumentDetail(doc.id);
      setSharedDocPreview(data.document);
      setMode('shared-preview');
    } catch (err) {
      setError(err.message || 'Không xem được tài liệu dùng chung.');
    } finally { setBusy(false); }
  };

  const summarizeDocument = async () => {
    if (!docPreview) return;
    setBusy(true);
    setError('');
    try {
      const data = await api.summarizeDocument(docPreview.id);
      setDocSummary(data.summary || '');
    } catch (err) {
      setError(err.message || 'Không thể tóm tắt.');
    } finally { setBusy(false); }
  };

  const confirmDeleteDocument = (doc) => {
    Alert.alert('Xóa tài liệu?', doc.original_name, [
      { text: 'Hủy', style: 'cancel' },
      { text: 'Xóa', style: 'destructive', onPress: async () => {
        try {
          setBusy(true);
          await api.deleteDocument(doc.id);
          await loadDetail(selectedId);
          await refreshData();
        } catch (err) {
          setError(err.message || 'Xóa tài liệu thất bại.');
        } finally { setBusy(false); }
      } },
    ]);
  };

  const selectSyllabus = async (docId) => {
    setBusy(true);
    setError('');
    try {
      await api.setPersonalSyllabus(selectedId, docId);
      await loadDetail(selectedId);
    } catch (err) {
      setError(err.message || 'Không lưu được đề cương.');
    } finally { setBusy(false); }
  };

  const moveDocument = (doc) => {
    const otherSubjects = subjects.filter((item) => item.id !== selectedId);
    if (!otherSubjects.length) {
      Alert.alert('Chưa có môn khác', 'Tạo thêm một môn để chuyển tài liệu.');
      return;
    }
    Alert.alert('Chuyển tài liệu sang môn', doc.original_name, [
      ...otherSubjects.map((item) => ({
        text: item.name,
        onPress: async () => {
          try {
            setBusy(true);
            await api.moveDocument(doc.id, item.id);
            await loadDetail(selectedId);
            await refreshData();
          } catch (err) {
            setError(err.message || 'Không thể chuyển tài liệu.');
          } finally { setBusy(false); }
        },
      })),
      { text: 'Hủy', style: 'cancel' },
    ]);
  };

  if (mode === 'preview' && docPreview) return (
    <ScrollView contentContainerStyle={styles.page}>
      <TouchableOpacity onPress={() => setMode('detail')}>
        <Text style={styles.backLink}>← Chi tiết môn học</Text>
      </TouchableOpacity>
      <Header title="Nội dung tài liệu" subtitle={docPreview.original_name} userName={userName} />
      <ErrorCard message={error} />
      {busy && <ActivityIndicator />}
      <TouchableOpacity style={styles.primaryButton} onPress={summarizeDocument} disabled={busy}>
        <Text style={styles.primaryButtonText}>✦ Tóm tắt bằng AI</Text>
      </TouchableOpacity>
      {!!docSummary && <View style={styles.card}>
        <Text style={styles.cardTitle}>Tóm tắt tài liệu</Text>
        <ChatFormattedText value={docSummary} style={[styles.muted, { fontSize: 14, lineHeight: 23 }]} />
      </View>}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Văn bản đã trích xuất</Text>
        <Text style={[styles.muted, { fontSize: 13, lineHeight: 22 }]}>
          {docPreview.extracted_text || 'Không đọc được văn bản. PDF scan ảnh chưa hỗ trợ OCR.'}
        </Text>
      </View>
    </ScrollView>
  );

  if (mode === 'shared-preview' && sharedDocPreview) return (
    <ScrollView contentContainerStyle={styles.page}>
      <TouchableOpacity onPress={() => setMode('detail')}>
        <Text style={styles.backLink}>← Chi tiết môn học</Text>
      </TouchableOpacity>
      <Header title="Tài liệu dùng chung" subtitle={sharedDocPreview.original_name} userName={userName} />
      <View style={styles.card}>
        <Text style={styles.cardTitle}>{sharedDocPreview.subject_name} · Đã xử lý</Text>
        <Text style={styles.muted}>Tài liệu do quản trị viên cung cấp, chỉ đọc.</Text>
      </View>
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Nội dung trích xuất</Text>
        <Text style={[styles.muted, { fontSize: 13, lineHeight: 22 }]}>
          {sharedDocPreview.extracted_text || 'Chưa có nội dung văn bản.'}
        </Text>
      </View>
    </ScrollView>
  );

  if (mode === 'form') return (
    <View style={styles.safe}>
      <ErrorCard message={error} />
      <SubjectForm key={editing?.id || 'new'} initial={editing} busy={busy} onSave={saveSubject}
        onCancel={() => { setError(''); setMode(editing ? 'detail' : 'list'); }} />
    </View>
  );

  if (mode === 'detail' && detail) {
    const sub = detail.subject || {};
    const syllabus = detail.shared || {};
    const docs = documents.filter((doc) => doc.subject_id === selectedId);
    return (
      <ScrollView contentContainerStyle={styles.page}>
        <TouchableOpacity onPress={() => { setMode('list'); setError(''); }}>
          <Text style={styles.backLink}>← Danh sách môn học</Text>
        </TouchableOpacity>
        <Header title={sub.name} subtitle={sub.code || 'Chưa có mã môn'} userName={userName} />
        <ErrorCard message={error} />
        {busy && <ActivityIndicator />}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Tổng quan môn học</Text>
          <Text style={styles.muted}>{sub.credits} tín chỉ · Mục tiêu {sub.target_score} · Tiến độ {sub.progress}%</Text>
          <Progress value={sub.progress} />
          {!!sub.description && <Text style={styles.muted}>{sub.description}</Text>}
          <Text style={styles.muted}>Đề cương đang dùng: {
            syllabus.syllabus_source === 'shared' ? 'Đề cương chuẩn dùng chung' :
            syllabus.syllabus_source === 'personal' ? 'Đề cương cá nhân' : 'Chưa chọn'
          }</Text>
          {!!syllabus.syllabus_source_name && <Text style={styles.muted}>{syllabus.syllabus_source_name}</Text>}
        </View>
        <TouchableOpacity style={styles.settingsEntry} onPress={() => toggleSection('roadmap')}
          accessibilityRole="button" accessibilityState={{expanded:expanded.roadmap}}>
          <Text style={styles.settingsEntryText}>📖 Đề cương & lộ trình</Text>
          <Text style={styles.settingsChevron}>{expanded.roadmap ? '⌃' : '›'}</Text>
        </TouchableOpacity>
        {expanded.roadmap && <View style={styles.card}>
          <Text style={styles.cardTitle}>Đề cương, CLO & lộ trình chính thức</Text>
          <Text style={styles.muted}>{roadmap?.ready
            ? 'Lộ trình đã được xác nhận từ đề cương.'
            : roadmap?.notice || 'Chưa có lộ trình được xác nhận. Hãy tạo từ Web.'}</Text>
          {(roadmap?.chapters || []).map((chapter, index) => (
            <View key={'chapter-'+index} style={{marginTop:9}}>
              <Text style={styles.cardTitle}>{chapter.title}</Text>
              {!!chapter.topics?.length && <Text style={styles.muted}>
                {chapter.topics.map(t=>typeof t==='string'?t:t?.title||'').filter(Boolean).join(' · ').slice(0,240)}
              </Text>}
            </View>
          ))}
          {!!roadmap?.sessions?.length && <Text style={[styles.cardTitle,{marginTop:13}]}>
            Lộ trình theo buổi ({roadmap.sessions.length})
          </Text>}
          {!!roadmap?.ready && (roadmap.sessions || []).some(item => !item.scheduled_task_id) && (
            <TouchableOpacity style={styles.primaryButton} disabled={busy}
              accessibilityRole="button" onPress={confirmScheduleRoadmap}>
              <Text style={styles.primaryButtonText}>▦ Đưa buổi chưa có lịch vào Kế hoạch</Text>
            </TouchableOpacity>
          )}
          {!!roadmap?.ready && <Text style={styles.muted}>
            {(roadmap.sessions || []).filter(item => !!item.scheduled_task_id).length}/{roadmap.sessions.length} buổi đã có lịch. Những buổi cũ sẽ không bị tự dời.
          </Text>}
          {(roadmap?.sessions || []).map((lesson,index)=>(
            <TouchableOpacity key={'lesson-'+index}
              style={{paddingVertical:11,borderTopWidth:1,borderTopColor:'#E6EAF5'}}
              disabled={!lesson.scheduled_task_id}
              onPress={()=>onOpenStudy(lesson.scheduled_task_id)}>
              <Text style={styles.cardTitle}>{lesson.title}</Text>
              <Text style={styles.muted}>
                Chương {lesson.unit_id} · {lesson.study_at
                  ? lesson.study_at.replace('T',' ').slice(0,16)
                  : 'Chưa đưa vào thời khóa biểu'}
              </Text>
              <Text style={styles.smallActionText}>
                {lesson.scheduled_task_id ? 'Vào học →' : 'Chưa có lịch · Chọn xếp lịch ở trên'}
              </Text>
            </TouchableOpacity>
          ))}
        </View>}
        <TouchableOpacity style={styles.primaryButton} onPress={() => onOpenQuiz(sub.id)}
          accessibilityRole="button">
          <Text style={styles.primaryButtonText}>✓ Làm Quiz & Ôn điểm yếu</Text>
        </TouchableOpacity>
        <View style={styles.actionRow}>
          <TouchableOpacity style={styles.smallAction} onPress={() => { setEditing(sub); setMode('form'); }}><Text style={styles.smallActionText}>✎ Sửa môn</Text></TouchableOpacity>
          <TouchableOpacity style={[styles.smallAction, styles.deleteAction]} onPress={confirmDeleteSubject}><Text style={styles.deleteActionText}>Xóa môn</Text></TouchableOpacity>
        </View>
        <TouchableOpacity style={styles.settingsEntry} onPress={() => toggleSection('personal')}
          accessibilityRole="button" accessibilityState={{expanded:expanded.personal}}>
          <Text style={styles.settingsEntryText}>📄 Tài liệu cá nhân ({docs.length})</Text>
          <Text style={styles.settingsChevron}>{expanded.personal ? '⌃' : '›'}</Text>
        </TouchableOpacity>
        {expanded.personal && <>
        <Text style={styles.sectionTitle}>Tài liệu cá nhân</Text>
        <TouchableOpacity style={styles.primaryButton} disabled={busy} onPress={pickFile}>
          <Text style={styles.primaryButtonText}>＋ Tải lên PDF / TXT / MD</Text>
        </TouchableOpacity>
        <Text style={styles.muted}>Mọi tệp bạn tải lên chỉ thuộc tài khoản này, không được công khai vào kiến thức chung.</Text>
        {!docs.length && <View style={styles.card}><Text style={styles.muted}>Chưa có tài liệu. Hãy tải lên đề cương hoặc chương học.</Text></View>}
        {docs.map((doc) => (
          <View key={doc.id} style={styles.card}>
            <Text style={styles.cardTitle}>📄 {doc.original_name}</Text>
            <Text style={styles.muted}>{doc.extracted_chars ? `${doc.extracted_chars} ký tự đã trích xuất` : 'Chưa có nội dung văn bản trích xuất'}</Text>
            <View style={styles.actionRow}>
              <TouchableOpacity style={styles.smallAction} onPress={async () => {
                await previewDocument(doc);
                setMode('preview');
              }}>
                <Text style={styles.smallActionText}>Xem nội dung</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.smallAction} onPress={() => selectSyllabus(doc.id)}>
                <Text style={styles.smallActionText}>{sub.personal_syllabus_document_id === doc.id ? '✓ Đề cương' : 'Chọn đề cương'}</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.smallAction} onPress={() => moveDocument(doc)}>
                <Text style={styles.smallActionText}>Chuyển môn</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[styles.smallAction, styles.deleteAction]} onPress={() => confirmDeleteDocument(doc)}>
                <Text style={styles.deleteActionText}>Xóa</Text>
              </TouchableOpacity>
            </View>
          </View>
        ))}
        {sub.personal_syllabus_document_id ? (
          <TouchableOpacity style={styles.secondaryAction} onPress={() => selectSyllabus(null)}>
            <Text style={styles.secondaryActionText}>Bỏ chọn đề cương cá nhân</Text>
          </TouchableOpacity>
        ) : null}
        </>}
        <TouchableOpacity style={styles.settingsEntry} onPress={() => toggleSection('shared')}
          accessibilityRole="button" accessibilityState={{expanded:expanded.shared}}>
          <Text style={styles.settingsEntryText}>📚 Tài liệu chung ({(detail.shared_documents || []).length})</Text>
          <Text style={styles.settingsChevron}>{expanded.shared ? '⌃' : '›'}</Text>
        </TouchableOpacity>
        {expanded.shared && <>
        <Text style={styles.sectionTitle}>Tài liệu dùng chung</Text>
        <Text style={styles.muted}>Được quản trị viên tải và xử lý sẵn theo mã môn; bạn có quyền xem nhưng không thể sửa.</Text>
        {(detail.shared_documents || []).length ? detail.shared_documents.map((doc) => (
          <View key={'shared-' + doc.id} style={styles.card}>
            <Text style={styles.cardTitle}>📚 {doc.original_name}</Text>
            <Text style={styles.muted}>{doc.is_syllabus ? 'Đề cương chuẩn · ' : ''}✓ {doc.extracted_chars || 0} ký tự đã trích xuất</Text>
            <TouchableOpacity style={styles.secondaryAction} disabled={busy} onPress={() => previewSharedDocument(doc)}>
              <Text style={styles.secondaryActionText}>◉ Xem tài liệu chung</Text>
            </TouchableOpacity>
          </View>
        )) : <Text style={styles.muted}>Chưa có tài liệu chung cho mã môn này.</Text>}
        </>}
        <TouchableOpacity style={styles.settingsEntry} onPress={() => toggleSection('weaknesses')}
          accessibilityRole="button" accessibilityState={{expanded:expanded.weaknesses}}>
          <Text style={styles.settingsEntryText}>🎯 Điểm yếu cần ôn</Text>
          <Text style={styles.settingsChevron}>{expanded.weaknesses ? '⌃' : '›'}</Text>
        </TouchableOpacity>
        {expanded.weaknesses && <>
        <Text style={styles.sectionTitle}>Điểm yếu đang cần ôn</Text>
        {(detail.weaknesses || []).length ? detail.weaknesses.map((w, i) => (
          <View key={i} style={styles.card}><Text style={styles.cardTitle}>{w.topic}</Text><Text style={styles.muted}>{w.chapter || 'Chưa phân chương'}</Text></View>
        )) : <Text style={styles.muted}>Chưa có điểm yếu cần ôn.</Text>}
        </>}
      </ScrollView>
    );
  }

  return (
    <ScrollView contentContainerStyle={styles.page}>
      <Header title="Môn học" subtitle="Lộ trình và tài liệu học tập" userName={userName} />
      <TextInput value={search} onChangeText={setSearch} style={styles.loginInput}
        placeholder="⌕ Tìm môn học..." placeholderTextColor="#7B8DAC" />
      <View style={styles.actionRow}>
        {[['all','Tất cả'],['ongoing','Đang học'],['completed','Đã hoàn thành']].map(([key,label])=>(
          <TouchableOpacity key={key} onPress={()=>setCourseFilter(key)}
            style={[styles.smallAction,courseFilter===key&&{backgroundColor:'#6567E8'}]}>
            <Text style={[styles.smallActionText,courseFilter===key&&{color:'#FFFFFF'}]}>{label}</Text>
          </TouchableOpacity>
        ))}
      </View>
      <ErrorCard message={error} />
      <TouchableOpacity style={styles.primaryButton} onPress={() => { setEditing(null); setError(''); setMode('form'); }}>
        <Text style={styles.primaryButtonText}>＋ Tạo môn học</Text>
      </TouchableOpacity>
      {busy && <ActivityIndicator />}
      {subjects.filter(item => {
        const matchesName = String(item.name||'').toLowerCase().includes(search.trim().toLowerCase());
        const progress = Number(item.progress || 0);
        return matchesName && (courseFilter==='all' ||
          (courseFilter==='completed'?progress>=100:progress<100));
      }).map((item) => (
        <TouchableOpacity key={item.id} style={styles.subjectCard} onPress={() => loadDetail(item.id)}>
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
            <Text style={styles.weakText}>{item.weaknesses?.length
              ? `Điểm yếu: ${item.weaknesses.map((w) => w.topic).join(', ')}`
              : 'Chưa có điểm yếu cần ôn'}</Text>
          </View>
        </TouchableOpacity>
      ))}
      {!subjects.length && <View style={styles.card}><Text style={styles.muted}>Bạn chưa có môn học. Bấm “Tạo môn học” để bắt đầu.</Text></View>}
    </ScrollView>
  );
}

function SubjectSelector({ subjects, selectedId, onSelect, disabled = false }) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ maxHeight: 46, marginBottom: 10 }}>
      <View style={{ flexDirection: 'row', gap: 8 }}>
        {subjects.map((subject) => (
          <TouchableOpacity
            key={subject.id}
            disabled={disabled}
            accessibilityRole="button"
            accessibilityState={{selected:selectedId===subject.id,disabled}}
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

// Hiển thị Markdown cơ bản trong phản hồi AI mà không cần thư viện ngoài.
// React Native Text không tự định dạng dấu **in đậm** từ câu trả lời AI.
function ChatFormattedText({ value, style }) {
  const rows = String(value ?? '').split(/\r?\n/);
  return (
    <Text style={style}>
      {rows.map((row, rowIndex) => {
        const heading = row.match(/^\s{0,3}#{1,6}\s+(.*)$/);
        const bullet = !heading && row.match(/^\s*[-*+•]\s+(.+)$/);
        const numbered = !heading && !bullet && row.match(/^\s*(\d+[.)])\s+(.+)$/);
        const content = heading ? heading[1] : bullet ? '• ' + bullet[1]
          : numbered ? numbered[1] + ' ' + numbered[2] : row;
        const segments = content.split(/(\*\*[^*\n]+\*\*)/g);
        return (
          <Text key={rowIndex} style={heading ? { fontWeight: '700' } : undefined}>
            {segments.map((part, partIndex) => (
              part.startsWith('**') && part.endsWith('**') && part.length > 4
                ? <Text key={partIndex} style={{ fontWeight: '700' }}>{part.slice(2, -2)}</Text>
                : <Text key={partIndex}>{part}</Text>
            ))}
            {rowIndex < rows.length - 1 ? '\n' : ''}
          </Text>
        );
      })}
    </Text>
  );
}

function AgentScreen({ subjects, userName }) {
  const [subjectId, setSubjectId] = useState(subjects[0]?.id || null);
  const [message, setMessage] = useState('');
  const [messages, setMessages] = useState([]);
  const [sending, setSending] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!subjectId && subjects[0]?.id) setSubjectId(subjects[0].id);
  }, [subjects, subjectId]);

  useEffect(() => {
    if (!subjectId) {
      setMessages([
        { role: 'assistant', text: 'Chọn môn học rồi hỏi bất kỳ phần nào bạn đang chưa rõ.' },
      ]);
      return undefined;
    }

    let cancelled = false;
    setLoadingHistory(true);
    setError('');

    api.chatHistory(subjectId)
      .then((data) => {
        if (cancelled) return;
        const history = (data?.messages || []).map((item) => ({
          role: item.role,
          text: item.content,
        }));
        setMessages(
          history.length
            ? history
            : [{ role: 'assistant', text: `Bắt đầu hỏi Study Agent về ${data?.subject_name || 'môn học này'}.` }]
        );
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err.message || 'Không tải được lịch sử Chat.');
        setMessages([
          { role: 'assistant', text: 'Không tải được lịch sử cũ, nhưng bạn vẫn có thể thử lại sau.' },
        ]);
      })
      .finally(() => {
        if (!cancelled) setLoadingHistory(false);
      });

    return () => {
      cancelled = true;
    };
  }, [subjectId]);

  const selectSubject = (id) => {
    if (sending) {
      setError('Đợi câu trả lời hoàn tất rồi hãy đổi môn học.');
      return;
    }
    setSubjectId(id);
    setMessage('');
    setMessages([]);
    setError('');
  };

  const send = async () => {
    const value = message.trim();
    if (!value || !subjectId || sending || loadingHistory) return;

    setError('');
    const pendingItem = { role: 'user', text: value };
    setMessages((old) => [...old, pendingItem]);
    setMessage('');
    setSending(true);

    try {
      const result = await api.chat(subjectId, value);
      setMessages((old) => [...old, { role: 'assistant', text: result.answer }]);
    } catch (err) {
      // Không giả vờ tin nhắn đã lưu khi API gặp lỗi.
      setMessages((old) => old.filter((item) => item !== pendingItem));
      setMessage((current) => current || value);
      setError(err.message || 'Không thể gửi câu hỏi. Bạn có thể gửi lại.');
    } finally {
      setSending(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.chatPage}>
        <Header title="Study Agent" subtitle="Chat đồng bộ với lịch sử trên Web" userName={userName} />
        <SubjectSelector subjects={subjects} selectedId={subjectId} onSelect={selectSubject} />
        <ErrorCard message={error} />
        <ScrollView style={styles.chatList} contentContainerStyle={{ paddingBottom: 16 }}>
          {messages.map((item, index) => (
            <View key={index} style={[styles.message, item.role === 'user' ? styles.userMessage : styles.aiMessage]}>
              <ChatFormattedText value={item.text} style={item.role === 'user' ? styles.userMessageText : styles.aiMessageText} />
            </View>
          ))}
          {(sending || loadingHistory) && <ActivityIndicator />}
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

function QuizScreen({ subjects, userName, refreshData, initialSubjectId, initialQuizId, onBack }) {
  const [subjectId, setSubjectId] = useState(initialSubjectId || subjects[0]?.id || null);
  const [quiz, setQuiz] = useState(null);
  const [answers, setAnswers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState([]);
  const [personalDocs, setPersonalDocs] = useState([]);
  const [mode, setMode] = useState('subject');
  const [count, setCount] = useState(10);
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [tab, setTab] = useState('create');
  const [currentQuestion,setCurrentQuestion] = useState(0);
  const submitKey=useRef('');

  useEffect(() => {
    if (initialSubjectId) setSubjectId(initialSubjectId);
    else if (!subjectId && subjects[0]?.id) setSubjectId(subjects[0].id);
  }, [subjects, initialSubjectId, subjectId]);

  useEffect(()=>{
    if(!Number.isSafeInteger(initialQuizId)||initialQuizId<=0) return;
    let active=true;
    setLoading(true);setError('');
    api.quizDetail(initialQuizId).then(body=>{
      if(!active)return;
      setQuiz(body);
      setAnswers(Array(body.questions?.length||0).fill(null));
      setCurrentQuestion(0);
      submitKey.current='';
      setResult(null);
      setTab('take');
    }).catch(err=>{if(active)setError(err.message||'Quiz đang khóa.');})
      .finally(()=>{if(active)setLoading(false);});
    return()=>{active=false;};
  },[initialQuizId]);

  const refreshQuizList = async () => {
    const [data, docsData] = await Promise.all([
      api.quizzes(),
      api.documents(),
    ]);
    setSaved(data.quizzes || []);
    setPersonalDocs(docsData.documents || []);
  };

  useEffect(() => {
    let active = true;
    Promise.all([api.quizzes(), api.documents()]).then(([data, docsData]) => {
      if (!active) return;
      setSaved(data.quizzes || []);
      setPersonalDocs(docsData.documents || []);
    }).catch(() => {});
    return () => { active = false; };
  }, [subjectId]);

  const generate = async () => {
    if (!subjectId || loading) return;
    if (mode === 'document' && !selectedDoc) {
      setError('Hãy chọn tài liệu cá nhân để tạo Quiz.');
      return;
    }
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const data = await api.quizGenerate(subjectId, count, mode, selectedDoc);
      setQuiz(data);
      setAnswers(Array(data.questions?.length || 0).fill(null));
      setCurrentQuestion(0);
      submitKey.current='';
      setTab('take');
      await refreshQuizList();
    } catch (err) {
      setError(err.message || 'Không thể tạo Quiz.');
    } finally {
      setLoading(false);
    }
  };

  const openQuiz = async (id) => {
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const data = await api.quizDetail(id);
      setQuiz(data);
      setAnswers(Array(data.questions?.length || 0).fill(null));
      setCurrentQuestion(0);
      submitKey.current='';
      setTab('take');
    } catch (err) {
      setError(err.message || 'Không đọc được Quiz.');
    } finally {
      setLoading(false);
    }
  };

  const submit=()=>{
    if(!quiz?.quiz_id || loading)return;
    const firstUnanswered=answers.findIndex(value=>value===null||value===undefined);
    if(firstUnanswered>=0){
      setCurrentQuestion(firstUnanswered);
      setError('Vui lòng trả lời đủ '+answers.length+' câu trước khi nộp.');
      return;
    }
    Alert.alert('Xác nhận nộp Quiz',
      'Bạn đã trả lời đủ '+answers.length+' câu. Nộp bài để chấm và cập nhật điểm yếu?',
      [{text:'Kiểm tra lại',style:'cancel'},
       {text:'Nộp bài',onPress:async()=>{
         if(loading)return;
         setLoading(true);setError('');
         if(!submitKey.current) submitKey.current='mobile_'
           +Date.now().toString(36)+'_'+Math.random().toString(36).slice(2,14);
         try{
           const data=await api.quizSubmit(quiz.quiz_id,answers,submitKey.current);
           setResult(data);
           setCurrentQuestion(0);
           setTab('result');
           submitKey.current='';
           try{
             await Promise.all([refreshQuizList(),refreshData()]);
           }catch(_refreshError){
             setError('Bài đã nộp thành công. Chưa làm mới được danh sách Quiz; bạn có thể mở lại sau.');
           }
         }catch(err){setError(err.message||'Không nộp được Quiz. Có thể thử lại.');}
         finally{setLoading(false);}
       }}]);
  };
  const viewReview=async (id)=>{
    setLoading(true);setError('');
    try{
      const [q,review]=await Promise.all([api.quizDetail(id),api.quizReview(id)]);
      setQuiz(q);
      setResult({...review.attempt,
        correct_answers:review.correct_answers,
        explanations:review.explanations});
      const previous=JSON.parse(review.attempt.answers_json||'[]');
      setAnswers(Array.isArray(previous)?previous:[]);
      setCurrentQuestion(0);
      setTab('result');
    }catch(err){setError(err.message||'Chưa xem được bài đã nộp.');}
    finally{setLoading(false);}
  };

  const changeSubject = (id) => {
    setSubjectId(id);
    setQuiz(null);
    setAnswers([]);
    setCurrentQuestion(0);
    submitKey.current='';
    setResult(null);
    setSelectedDoc(null);
    setError('');
    setTab('create');
  };

  const Choice = ({ label, active, onPress }) => (
    <TouchableOpacity style={[styles.smallAction, active && { backgroundColor: '#6567E8' }]} onPress={onPress}>
      <Text style={[styles.smallActionText, active && { color: 'white' }]}>{label}</Text>
    </TouchableOpacity>
  );

  return (
    <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
      <TouchableOpacity onPress={onBack} accessibilityRole="button">
        <Text style={styles.backLink}>← Quay về môn học</Text>
      </TouchableOpacity>
      <Header title="Quiz & điểm yếu" subtitle="Luyện tập theo đề cương và năng lực" userName={userName} />
      <SubjectSelector subjects={subjects} selectedId={subjectId} onSelect={changeSubject} />
      <ErrorCard message={error} />
      {loading && <ActivityIndicator />}
      {!!subjects.find(s=>s.id===subjectId)?.weaknesses?.length && (
        <View style={[styles.card,{backgroundColor:'#F1F4FF'}]}>
          <Text style={styles.cardTitle}>🎯 Điểm yếu cần củng cố</Text>
          {subjects.find(s=>s.id===subjectId).weaknesses.slice(0,4).map((weak,i)=>(
            <Text key={i} style={styles.muted}>• {weak.topic}{weak.chapter?' · '+weak.chapter:''}</Text>
          ))}
          <TouchableOpacity style={styles.secondaryAction}
            onPress={()=>{setMode('weakness');setCount(10);setTab('create');}}>
            <Text style={styles.secondaryActionText}>✦ Tạo Quiz ôn điểm yếu →</Text>
          </TouchableOpacity>
        </View>
      )}
      <View style={styles.actionRow}>
        <Choice label="Tạo Quiz" active={tab === 'create'} onPress={() => { setTab('create'); setQuiz(null); setResult(null); }} />
        <Choice label={`Quiz đã lưu (${saved.length})`} active={tab === 'saved'} onPress={() => setTab('saved')} />
      </View>
      {tab === 'create' && (
        <>
          <Text style={styles.sectionTitle}>Chọn nguồn tạo Quiz</Text>
          <View style={styles.actionRow}>
            <Choice label="Theo môn" active={mode === 'subject'} onPress={() => setMode('subject')} />
            <Choice label="Tài liệu cá nhân" active={mode === 'document'} onPress={() => setMode('document')} />
            <Choice label="Ôn điểm yếu" active={mode === 'weakness'} onPress={() => setMode('weakness')} />
          </View>
          {mode === 'document' && (
            <>
              <Text style={styles.fieldLabel}>Chọn tài liệu</Text>
              {personalDocs.filter(d => d.subject_id === subjectId).map(doc => (
                <Choice key={doc.id} label={doc.original_name} active={selectedDoc === doc.id} onPress={() => setSelectedDoc(doc.id)} />
              ))}
            </>
          )}
          <Text style={styles.sectionTitle}>Số câu hỏi</Text>
          <View style={styles.actionRow}>
            {[10, 20, 30].map(number => (
              <Choice key={number} label={String(number)} active={count === number} onPress={() => setCount(number)} />
            ))}
          </View>
          <TouchableOpacity style={styles.primaryButton} onPress={generate} disabled={loading || !subjectId}>
            <Text style={styles.primaryButtonText}>✦ Tạo Quiz</Text>
          </TouchableOpacity>
        </>
      )}
      {tab === 'saved' && (
        <>
          <Text style={styles.sectionTitle}>Lịch sử Quiz</Text>
          {!saved.length && <Text style={styles.muted}>Chưa có Quiz. Tạo Quiz để bắt đầu luyện tập.</Text>}
          {saved.filter(q => !subjectId || q.subject_id === subjectId).map(item => (
            <View key={item.id} style={styles.card}>
              <Text style={styles.cardTitle}>{item.title}</Text>
              <Text style={styles.muted}>Đã làm {item.attempt_count || 0} lần · Điểm cao nhất {item.best_score ?? '—'}%</Text>
              <View style={styles.actionRow}>
                <TouchableOpacity style={styles.smallAction} onPress={() => openQuiz(item.id)}>
                  <Text style={styles.smallActionText}>Làm Quiz →</Text>
                </TouchableOpacity>
                {item.attempt_count>0 &&
                  <TouchableOpacity style={styles.smallAction} onPress={()=>viewReview(item.id)}>
                    <Text style={styles.smallActionText}>Xem bài đã nộp</Text>
                  </TouchableOpacity>}
              </View>
            </View>
          ))}
        </>
      )}
      {(tab === 'take' || tab === 'result') && quiz && (
        <>
          <TouchableOpacity onPress={() => setTab('saved')}>
            <Text style={styles.backLink}>← Danh sách Quiz</Text>
          </TouchableOpacity>
          <Text style={styles.sectionTitle}>{quiz.title}</Text>
          {!!quiz.questions?.length && <Text style={styles.muted}>
            Câu {currentQuestion+1}/{quiz.questions.length}
            {'  '}·{'  '}Đã trả lời {answers.filter(a=>a!==null&&a!==undefined).length}/{answers.length}
          </Text>}
          <Progress value={quiz.questions?.length?(
            answers.filter(a=>a!==null&&a!==undefined).length*100/quiz.questions.length):0}/>
          {quiz.questions?.slice(currentQuestion,currentQuestion+1).map((question) => {
            const qIndex=currentQuestion;
            const chosen = answers[qIndex];
            const correct = tab === 'result' && result?.correct_answers
              ? Number(result.correct_answers[qIndex])
              : -1;
            return (
              <View key={qIndex} style={styles.card}>
                <Text style={styles.eyebrow}>CÂU {qIndex + 1} / {quiz.questions.length}</Text>
                <Text style={styles.quizQuestion}>{question.question}</Text>
                {!!question.topic && <Text style={styles.muted}>{question.chapter || ''} · {question.topic}</Text>}
                {(question.options || []).map((option, index) => (
                  <TouchableOpacity key={index} disabled={tab === 'result'}
                    style={[styles.option, chosen === index && styles.optionSelected,
                      tab === 'result' && index === correct && { borderColor: '#31A879', backgroundColor: '#EAFAF2' }]}
                    onPress={() => {
                      submitKey.current='';
                      setAnswers(old => old.map((v, n) => n === qIndex ? index : v));
                      setError('');
                    }}>
                    <Text style={[styles.optionLetter, chosen === index && styles.optionLetterSelected]}>
                      {String.fromCharCode(65 + index)}
                    </Text>
                    <Text style={styles.optionText}>{option}</Text>
                  </TouchableOpacity>
                ))}
                {tab === 'result' && (
                  <Text style={styles.muted}>
                    Đáp án đúng: {String.fromCharCode(65 + correct)}
                    {result?.explanations?.[qIndex] ? ` · ${result.explanations[qIndex]}` : ''}
                  </Text>
                )}
              </View>
            );
          })}
          <View style={[styles.actionRow,{justifyContent:'space-between'}]}>
            <TouchableOpacity disabled={currentQuestion===0}
              style={[styles.smallAction,currentQuestion===0&&{opacity:0.35}]}
              onPress={()=>setCurrentQuestion(i=>Math.max(0,i-1))}>
              <Text style={styles.smallActionText}>← Câu trước</Text>
            </TouchableOpacity>
            <TouchableOpacity disabled={currentQuestion+1>=(quiz.questions?.length||0)}
              style={[styles.smallAction,currentQuestion+1>=(quiz.questions?.length||0)&&{opacity:0.35}]}
              onPress={()=>setCurrentQuestion(i=>Math.min(quiz.questions.length-1,i+1))}>
              <Text style={styles.smallActionText}>Câu tiếp →</Text>
            </TouchableOpacity>
          </View>
          {tab === 'take' && (
            <TouchableOpacity style={styles.primaryButton} disabled={loading} onPress={submit}>
              <Text style={styles.primaryButtonText}>Nộp bài ({answers.filter(a => a !== null).length}/{answers.length})</Text>
            </TouchableOpacity>
          )}
          {tab === 'result' && result && (
            <View style={styles.insightCard}>
              <Text style={styles.insightTitle}>Kết quả: {result.correct_count}/{result.total_questions} · {result.score}%</Text>
              <Text style={styles.muted}>Điểm yếu cần ôn: {result.weakness_count ?? '—'}.
                {result.learning_updated ? ' Tiến độ đã đồng bộ với Web.' : ''}</Text>
              {!!result.resolved_topics?.length &&
                <Text style={[styles.muted,{color:'#18805C'}]}>
                  Tiến bộ: {result.resolved_topics.slice(0,4).join(' · ')}
                </Text>}
              {!!result.new_weakness_topics?.length &&
                <Text style={styles.muted}>
                  Cần ôn thêm: {result.new_weakness_topics.slice(0,4).join(' · ')}
                </Text>}
              <TouchableOpacity style={styles.secondaryAction} onPress={() => {
                setAnswers(Array(quiz.questions?.length || 0).fill(null));
                setCurrentQuestion(0);
                submitKey.current='';
                setResult(null);
                setTab('take');
              }}>
                <Text style={styles.secondaryActionText}>↻ Làm lại Quiz</Text>
              </TouchableOpacity>
            </View>
          )}
        </>
      )}
    </ScrollView>
  );
}

function PlanScreen({ plan, subjects, userName, refreshData, onOpenStudy, onOpenRoadmap }) {
  const [local, setLocal] = useState(plan || {});
  const [mode, setMode] = useState('list');
  const [planView, setPlanView] = useState('week');
  const [selectedDate, setSelectedDate] = useState(localDateKey(new Date()));
  const [showCompletedReminders, setShowCompletedReminders] = useState(false);
  const [showAllPending, setShowAllPending] = useState(false);
  const [selectedSubject, setSelectedSubject] = useState(subjects[0]?.id || null);
  const [goal, setGoal] = useState('Nắm vững kiến thức và luyện tập trước kỳ thi');
  const [deadline, setDeadline] = useState(localInputDate(14, 23, 0));
  const [preferredTime, setPreferredTime] = useState('19:00');
  const [dailyMinutes, setDailyMinutes] = useState('45');
  const [taskEdit, setTaskEdit] = useState(null);
  const [taskTitle, setTaskTitle] = useState('');
  const [taskAt, setTaskAt] = useState('');
  const [taskDuration, setTaskDuration] = useState('45');
  const [taskNote, setTaskNote] = useState('');
  const [taskDocumentId, setTaskDocumentId] = useState(null);
  const [taskDocuments, setTaskDocuments] = useState([]);
  const [uploadingTaskDoc, setUploadingTaskDoc] = useState(false);
  const [reminders, setReminders] = useState([]);
  const [reminderEdit, setReminderEdit] = useState(null);
  const [reminderTitle, setReminderTitle] = useState('');
  const [reminderAt, setReminderAt] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setLocal(plan || {});
  }, [plan]);

  const refresh = async () => {
    const [updated, deadlineData] = await Promise.all([api.studyPlan(), api.reminders()]);
    setLocal(updated);
    setReminders(deadlineData.reminders || []);
    await refreshData();
  };

  useEffect(() => {
    let active = true;
    api.reminders()
      .then((data) => { if (active) setReminders(data.reminders || []); })
      .catch(() => {});
    return () => { active = false; };
  }, []);

  const run = async (action, successMode = 'list') => {
    setBusy(true);
    setError('');
    try {
      await action();
      await refresh();
      setMode(successMode);
    } catch (err) {
      setError(err.message || 'Không thực hiện được thao tác.');
    } finally {
      setBusy(false);
    }
  };

  const openTask = (task = null) => {
    setTaskEdit(task);
    setTaskDocumentId(task?.document_id || null);
    setTaskTitle(task?.title || '');
    setTaskAt(task?.study_at || localInputDate(1, 19, 0));
    setTaskDuration(String(task?.duration || 45));
    setTaskNote(task?.note || '');
    setSelectedSubject(task?.subject_id || subjects[0]?.id || null);
    setMode('task');
  };

  useEffect(() => {
    if (mode !== 'task') return;
    let active = true;
    api.documents()
      .then(data => { if (active) setTaskDocuments(data.documents || []); })
      .catch(err => { if (active) setError(err.message || 'Chưa đọc được tài liệu cá nhân.'); });
    return () => { active = false; };
  }, [mode]);

  const uploadTaskDocument = async () => {
    if (!selectedSubject || uploadingTaskDoc) {
      if (!selectedSubject) setError('Hãy chọn môn học trước khi tải tài liệu.');
      return;
    }
    try {
      const picked = await DocumentPicker.getDocumentAsync({
        type:['application/pdf','text/plain','text/markdown'],
        copyToCacheDirectory:true,multiple:false,
      });
      if (picked.canceled || !picked.assets?.length) return;
      setUploadingTaskDoc(true);
      setError('');
      const uploaded = await api.uploadDocument(selectedSubject,picked.assets[0]);
      setTaskDocumentId(uploaded.document.id);
      const docs = await api.documents();
      setTaskDocuments(docs.documents || []);
    } catch (err) {
      setError(err.message || 'Không tải được tài liệu cá nhân.');
    } finally { setUploadingTaskDoc(false); }
  };

  const openReminder = (reminder = null) => {
    setReminderEdit(reminder);
    setReminderTitle(reminder?.title || '');
    setReminderAt(reminder?.due_at || localInputDate(7, 23, 59));
    setSelectedSubject(reminder?.subject_id || subjects[0]?.id || null);
    setMode('reminder');
  };

  const confirmDelete = (label, action) => {
    Alert.alert('Xác nhận xóa', label, [
      { text: 'Hủy', style: 'cancel' },
      { text: 'Xóa', style: 'destructive', onPress: () => run(action) },
    ]);
  };

  const entryField = (label, value, update, placeholder, multiline = false) => (
    <View>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput style={[styles.fieldInput, multiline && { minHeight: 85, textAlignVertical: 'top' }]}
        value={value} onChangeText={update} placeholder={placeholder}
        multiline={multiline} />
    </View>
  );

  if (mode !== 'list') return (
    <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
      <TouchableOpacity onPress={() => setMode('list')}><Text style={styles.backLink}>← Kế hoạch học</Text></TouchableOpacity>
      <Header title={mode === 'generate' ? 'Tạo kế hoạch AI' : mode === 'task' ? 'Buổi học' : 'Nhắc nhở'} userName={userName} />
      <ErrorCard message={error} />
      {busy && <ActivityIndicator />}
      <Text style={styles.fieldLabel}>Môn học</Text>
      <SubjectSelector subjects={subjects} selectedId={selectedSubject}
        disabled={mode === 'task' && !!taskEdit?.document_id}
        onSelect={id => { setSelectedSubject(id); if (mode === 'task' && !taskEdit?.document_id) setTaskDocumentId(null); }} />
      {mode === 'generate' ? (
        <>
          {entryField('Mục tiêu học tập', goal, setGoal, 'Ví dụ: Đạt 8 điểm cuối kỳ')}
          <Text style={styles.fieldLabel}>Thời hạn nhanh</Text>
          <View style={styles.actionRow}>
            {[7, 14, 30].map(days => (
              <TouchableOpacity key={days} style={styles.smallAction}
                onPress={() => setDeadline(localInputDate(days, 23, 0))}>
                <Text style={styles.smallActionText}>{days} ngày</Text>
              </TouchableOpacity>
            ))}
          </View>
          {entryField('Deadline (YYYY-MM-DDTHH:MM)', deadline, setDeadline, '2026-11-20T23:00')}
          {entryField('Giờ học ưu tiên (HH:MM)', preferredTime, setPreferredTime, '19:00')}
          {entryField('Số phút mỗi buổi', dailyMinutes, setDailyMinutes, '45')}
          <Text style={styles.muted}>AI ưu tiên đề cương môn học, tài liệu, điểm yếu và mục tiêu riêng.</Text>
          <TouchableOpacity style={styles.primaryButton} disabled={busy} onPress={() =>
            run(() => api.generateStudyPlan({
              subject_id: selectedSubject, goal, deadline,
              preferred_time: preferredTime, daily_minutes: Number(dailyMinutes),
            }))}>
            <Text style={styles.primaryButtonText}>✦ Tạo lộ trình AI</Text>
          </TouchableOpacity>
        </>
      ) : mode === 'task' ? (
        <>
          {entryField('Tên buổi học', taskTitle, setTaskTitle, 'Đọc chương 1')}
          <Text style={styles.fieldLabel}>Chọn nhanh ngày học</Text>
          <View style={styles.actionRow}>
            <TouchableOpacity style={styles.smallAction} onPress={() => setTaskAt(localInputDate(0,19,0))}>
              <Text style={styles.smallActionText}>Hôm nay 19:00</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.smallAction} onPress={() => setTaskAt(localInputDate(1,19,0))}>
              <Text style={styles.smallActionText}>Ngày mai 19:00</Text>
            </TouchableOpacity>
          </View>
          <StudyDateTimePicker label="Ngày và giờ học" value={taskAt} onChange={setTaskAt} disabled={busy} />
          {entryField('Thời lượng (phút)', taskDuration, setTaskDuration, '45')}
          {entryField('Ghi chú', taskNote, setTaskNote, 'Nội dung cần ôn tập', true)}
          {(!taskEdit || taskEdit.source === 'manual') && <>
            <Text style={styles.fieldLabel}>Tài liệu cá nhân cho buổi tự học (không bắt buộc)</Text>
            {taskEdit?.document_id ? (
              <Text style={styles.muted}>📄 {taskEdit.personal_document_name || 'Tài liệu đã gắn'} · Để bảo toàn lịch sử học, không đổi tài liệu của buổi này.</Text>
            ) : <>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{maxHeight:52,marginBottom:9}}>
                <TouchableOpacity style={[styles.smallAction,{marginRight:8},
                  !taskDocumentId && styles.docSelected]}
                  onPress={()=>setTaskDocumentId(null)}>
                  <Text style={[styles.smallActionText,!taskDocumentId && styles.docSelectedText]}>Không gắn tài liệu</Text>
                </TouchableOpacity>
                {taskDocuments.filter(doc=>Number(doc.subject_id)===Number(selectedSubject)
                  && Number(doc.extracted_chars)>0).map(doc=>(
                  <TouchableOpacity key={doc.id} style={[styles.smallAction,{marginRight:8},
                    taskDocumentId===doc.id && styles.docSelected]}
                    accessibilityRole="button"
                    accessibilityState={{selected:taskDocumentId===doc.id}}
                    onPress={()=>setTaskDocumentId(doc.id)}>
                    <Text numberOfLines={1} style={[styles.smallActionText,
                      taskDocumentId===doc.id && styles.docSelectedText]}>📄 {doc.original_name}</Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>
              <TouchableOpacity disabled={busy||uploadingTaskDoc} accessibilityRole="button"
                onPress={uploadTaskDocument} style={styles.docUpload}>
                <Text style={styles.docUploadText}>{uploadingTaskDoc?'Đang tải tài liệu…':'＋ Tải tài liệu mới và chọn cho buổi này'}</Text>
              </TouchableOpacity>
              <Text style={styles.helperNote}>File mới được lưu vào kho cá nhân của môn ngay sau khi tải lên, kể cả khi bạn hủy tạo buổi.</Text>
            </>}
          </>}
          {findTaskConflicts(local?.tasks || [],{
            study_at:taskAt,duration:Number(taskDuration)
          },taskEdit?.id).length>0 && (
            <View style={[styles.card,{backgroundColor:'#FFF9E9',borderColor:'#EFCB85'}]}>
              <Text style={[styles.cardTitle,{color:'#95611E'}]}>⚠ Phát hiện trùng giờ học</Text>
              <Text style={styles.muted}>
                {findTaskConflicts(local?.tasks || [],{
                  study_at:taskAt,duration:Number(taskDuration)
                },taskEdit?.id).slice(0,3).map(c=>c.title).join(', ')}
              </Text>
            </View>
          )}
          <TouchableOpacity style={styles.primaryButton} disabled={busy||uploadingTaskDoc} onPress={() => {
            if (uploadingTaskDoc) return;
            const payload={subject_id:selectedSubject,title:taskTitle,
              study_at:taskAt,duration:Number(taskDuration),note:taskNote,
              ...(!taskEdit || taskEdit.source === 'manual'
                ? {document_id:taskDocumentId} : {})};
            const save=()=>run(()=>taskEdit
              ?api.updateTask(taskEdit.id,payload):api.createTask(payload));
            const conflicts=findTaskConflicts(local?.tasks||[],payload,taskEdit?.id);
            if(!conflicts.length)return save();
            Alert.alert('Lịch học trùng giờ',
              'Có '+conflicts.length+' buổi trùng khung giờ đã chọn. Bạn vẫn muốn lưu?',
              [{text:'Hủy',style:'cancel'},{text:'Giữ khung giờ',onPress:save}]);
          }}>
            <Text style={styles.primaryButtonText}>{taskEdit ? 'Lưu buổi học' : 'Thêm buổi học'}</Text>
          </TouchableOpacity>
        </>
      ) : (
        <>
          {entryField('Nội dung nhắc nhở', reminderTitle, setReminderTitle, 'Ôn tập cuối kỳ')}
          <Text style={styles.fieldLabel}>Thời hạn nhanh</Text>
          <View style={styles.actionRow}>
            {[1, 7, 14].map(days => (
              <TouchableOpacity key={days} style={styles.smallAction}
                onPress={() => setReminderAt(localInputDate(days, 23, 59))}>
                <Text style={styles.smallActionText}>{days} ngày nữa</Text>
              </TouchableOpacity>
            ))}
          </View>
          <StudyDateTimePicker label="Hạn cần hoàn thành" value={reminderAt} onChange={setReminderAt} disabled={busy} />
          <TouchableOpacity style={styles.primaryButton} disabled={busy} onPress={() => run(() => (
            reminderEdit
              ? api.updateReminder(reminderEdit.id, {
                subject_id: selectedSubject, title: reminderTitle, due_at: reminderAt, done: reminderEdit.done,
              })
              : api.createReminder({
                subject_id: selectedSubject, title: reminderTitle, due_at: reminderAt,
              })
          ))}>
            <Text style={styles.primaryButtonText}>{reminderEdit ? 'Lưu deadline' : 'Thêm deadline'}</Text>
          </TouchableOpacity>
        </>
      )}
    </ScrollView>
  );


  const tasks = local?.tasks || [];
  const weekDays = getWeekDates(selectedDate);
  const todayTasks = tasks.filter(item =>
    String(item.study_at || '').slice(0,10) === localDateKey(new Date()));
  const completedToday = todayTasks.filter(item => !!item.done).length;
  const conflictingTasks = tasks.filter(task =>
    findTaskConflicts(tasks,task,task.id).length > 0);
  const displayedTasks = getVisiblePlanTasks(tasks, selectedDate, planView === 'list');
  const { pending, completed } = splitReminders(reminders);
  const pendingVisible = showAllPending ? pending : pending.slice(0, 5);
  const dayLabels = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'];
  const dateLabel = key => key?.slice(8, 10) + '/' + key?.slice(5, 7);

  const renderReminder = item => (
    <View key={item.id} style={[styles.planReminderRow, item.done && styles.planReminderDone]}>
      <TouchableOpacity
        accessibilityRole="button"
        accessibilityLabel={item.done ? 'Đánh dấu chưa xong: ' + item.title : 'Hoàn thành: ' + item.title}
        style={[styles.planCheck, item.done && styles.planCheckDone]}
        disabled={busy}
        onPress={() => run(() => api.updateReminder(item.id, {
          title: item.title, due_at: item.due_at, subject_id: item.subject_id,
          done: !item.done,
        }))}
      >
        <Text style={[styles.planCheckText, item.done && styles.planCheckTextDone]}>{item.done ? '✓' : ''}</Text>
      </TouchableOpacity>
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={[styles.planReminderTitle, item.done && styles.planDoneTitle]}>{item.title}</Text>
        <Text style={styles.planReminderMeta}>
          {String(item.due_at || '').replace('T', ' ').slice(0, 16)} · {item.subject_name || 'Cá nhân'}
        </Text>
      </View>
      <TouchableOpacity
        accessibilityRole="button" accessibilityLabel={'Sửa deadline: ' + item.title}
        style={styles.planIconAction} onPress={() => openReminder(item)} disabled={busy}>
        <Text style={styles.planIconText}>✎</Text>
      </TouchableOpacity>
      <TouchableOpacity
        accessibilityRole="button" accessibilityLabel={'Xóa deadline: ' + item.title}
        style={styles.planIconAction}
        onPress={() => confirmDelete(item.title, () => api.deleteReminder(item.id))} disabled={busy}>
        <Text style={[styles.planIconText, { color: '#B83D52' }]}>×</Text>
      </TouchableOpacity>
    </View>
  );

  return (
    <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
      <Header title="Kế hoạch học tập" subtitle="Xếp lịch học và theo dõi deadline" userName={userName} />
      <ErrorCard message={error} />
      {busy && <ActivityIndicator />}
      <View style={styles.planTodaySummary}>
        <Text style={styles.planTodaySummaryLabel}>Hôm nay</Text>
        <Text style={styles.planTodaySummaryValue}>{completedToday}/{todayTasks.length} buổi đã hoàn thành</Text>
      </View>
      <View style={styles.planToolbar}>
        <TouchableOpacity style={styles.smallAction} disabled={busy} onPress={() => openTask()}>
          <Text style={styles.smallActionText}>＋ Buổi học</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.smallAction} disabled={busy} onPress={() => openReminder()}>
          <Text style={styles.smallActionText}>＋ Deadline</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.smallAction} disabled={busy} onPress={onOpenRoadmap}>
          <Text style={styles.smallActionText}>⇢ Lộ trình học</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.planCalendarCard}>
        <View style={styles.planSectionRow}>
          <Text style={styles.planSectionTitle}>◷ Lịch học</Text>
          <View style={styles.planViewTabs}>
            {['week', 'list'].map(key => (
              <TouchableOpacity key={key} accessibilityRole="button"
                accessibilityState={{ selected: planView === key }}
                style={[styles.planViewTab, planView === key && styles.planViewTabSelected]}
                onPress={() => setPlanView(key)}>
                <Text style={[styles.planViewLabel, planView === key && styles.planViewLabelSelected]}>
                  {key === 'week' ? 'Tuần' : 'Danh sách'}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
        {planView === 'week' && (
          <>
            <View style={styles.planCalendarNav}>
              <TouchableOpacity style={styles.planArrow} accessibilityLabel="Tuần trước"
                onPress={() => setSelectedDate(addDays(selectedDate, -7))}>
                <Text style={styles.planArrowText}>‹</Text>
              </TouchableOpacity>
              <View style={{ flex: 1, alignItems: 'center' }}>
                <Text style={styles.planWeekRange}>
                  {dateLabel(weekDays[0])} – {dateLabel(weekDays[6])}
                </Text>
              </View>
              <TouchableOpacity style={styles.planArrow} accessibilityLabel="Tuần sau"
                onPress={() => setSelectedDate(addDays(selectedDate, 7))}>
                <Text style={styles.planArrowText}>›</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.planTodayButton}
                onPress={() => setSelectedDate(localDateKey(new Date()))}>
                <Text style={styles.planTodayText}>Hôm nay</Text>
              </TouchableOpacity>
            </View>
            <View style={styles.planWeekRow}>
              {weekDays.map((date, i) => {
                const active = date === selectedDate;
                const count = tasks.filter(t => String(t.study_at || '').slice(0, 10) === date).length;
                return (
                  <TouchableOpacity key={date} style={[styles.planDayCell, active && styles.planDayCellActive]}
                    accessibilityRole="button"
                    accessibilityLabel={dayLabels[i] + ' ' + date + ': ' + count + ' buổi học'}
                    accessibilityState={{ selected: active }}
                    onPress={() => setSelectedDate(date)}>
                    <Text style={[styles.planDayName, active && styles.planDayActiveText]}>{dayLabels[i]}</Text>
                    <Text style={[styles.planDayDate, active && styles.planDayActiveText]}>{date.slice(8, 10)}</Text>
                    <Text style={[styles.planDayCount, active && styles.planDayActiveText]}>{count} buổi</Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          </>
        )}
      </View>

      <View style={styles.card}>
        <View style={styles.planSectionRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.planSectionTitle}>
              {planView === 'week' ? 'Lịch ngày ' + dateLabel(selectedDate) : 'Danh sách nhiệm vụ'}
            </Text>
            <Text style={styles.planSectionSubtitle}>
              {displayedTasks.length} buổi học · Nhấn dấu ✓ để đánh dấu hoàn thành
            </Text>
          </View>
          <TouchableOpacity style={styles.planEditButton} disabled={busy} onPress={() => openTask()}>
            <Text style={styles.planEditButtonText}>＋ Thêm</Text>
          </TouchableOpacity>
        </View>
        {!!local?.truncated && (
          <Text style={styles.planSectionSubtitle}>Đang hiển thị 200 nhiệm vụ gần nhất. Danh sách đầy đủ có thể xem trên Web.</Text>
        )}
        {!displayedTasks.length && (
          <Text style={styles.planEmptyText}>
            {planView === 'week' ? 'Ngày này chưa có lịch. Chọn ngày khác hoặc thêm buổi học.' : 'Chưa có buổi học nào. Mở Lộ trình học để xếp lịch, hoặc thêm buổi tự học.'}
          </Text>
        )}
        {displayedTasks.map(task => (
          <View key={task.id} style={[styles.planTaskRow, task.done && styles.planTaskDone]}>
            <TouchableOpacity
              accessibilityRole="button"
              accessibilityLabel={task.source === 'roadmap'
                ? (task.done ? 'Đã học: ' : 'Mở không gian học tập: ') + task.title
                : (task.done ? 'Đánh dấu chưa xong: ' : 'Hoàn thành: ') + task.title}
              style={[styles.planCheck, task.done && styles.planCheckDone]}
              disabled={busy || (task.source === 'roadmap' && !task.roadmap_label)}
              onPress={() => task.source === 'roadmap'
                ? onOpenStudy(task.id) : run(() => api.toggleTask(task.id))}>
              <Text style={[styles.planCheckText, task.done && styles.planCheckTextDone]}>
                {task.done ? '✓' : task.source === 'roadmap' ? '▶' : ''}
              </Text>
            </TouchableOpacity>
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={[styles.planTaskTitle, task.done && styles.planDoneTitle]} numberOfLines={2}>
                {task.subject_name || 'Tự học'}
              </Text>
              <Text style={styles.planTaskMeta}>
                {String(task.study_at || '').slice(11,16)} · {task.duration} phút
              </Text>
              <Text style={styles.planTaskNote} numberOfLines={1}>
                {task.roadmap_label || task.title}
              </Text>
              {!!task.personal_document_name && <Text style={styles.planTaskDoc} numberOfLines={1}>
                📄 {task.personal_document_name}
              </Text>}
              {task.source === 'roadmap' && !!task.roadmap_session_id && (
                task.roadmap_label ? <TouchableOpacity onPress={() => onOpenStudy(task.id)}
                  accessibilityRole="button" accessibilityLabel={'Bắt đầu học: '+task.title}
                  style={{paddingVertical:7}}>
                  <Text style={styles.smallActionText}>▶ Bắt đầu học →</Text>
                </TouchableOpacity> :
                <Text style={styles.planAdaptiveTag}>⚠ Buổi cần rà soát lộ trình</Text>
              )}
              {task.source === 'adaptive' && <Text style={styles.planAdaptiveTag}>✦ Ôn tập điểm yếu</Text>}
            </View>
            <View style={styles.planTaskActions}>
              <TouchableOpacity style={styles.planIconAction} disabled={busy}
                accessibilityLabel={'Sửa buổi học: ' + task.title}
                onPress={() => openTask(task)}>
                <Text style={styles.planIconText}>✎</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.planIconAction} disabled={busy}
                accessibilityLabel={'Xóa buổi học: ' + task.title}
                onPress={() => confirmDelete(task.title, () => api.deleteTask(task.id))}>
                <Text style={[styles.planIconText, { color: '#B83D52' }]}>×</Text>
              </TouchableOpacity>
            </View>
          </View>
        ))}
      </View>

      <View style={styles.card}>
        <View style={styles.planSectionRow}>
          <Text style={styles.planSectionTitle}>⚑ Deadline & cảnh báo</Text>
          <Text style={styles.planSectionSubtitle}>{pending.length} cần làm</Text>
        </View>
        {!pending.length && (
          <Text style={styles.planEmptyText}>
            {completed.length ? '✓ Không còn deadline chưa hoàn thành.' : 'Chưa có deadline. Bạn có thể thêm mới.'}
          </Text>
        )}
        {!!conflictingTasks.length && <View style={styles.planConflictNote}>
          <Text style={styles.planConflictText}>⚠ {conflictingTasks.length} buổi học đang trùng giờ</Text>
          <TouchableOpacity accessibilityRole="button" onPress={()=>setPlanView('list')}>
            <Text style={styles.smallActionText}>Xem danh sách buổi →</Text>
          </TouchableOpacity>
        </View>}
        {pendingVisible.map(renderReminder)}
        {pending.length > 5 && (
          <TouchableOpacity style={styles.planCollapseButton}
            onPress={() => setShowAllPending(value => !value)}>
            <Text style={styles.planCollapseText}>
              {showAllPending ? 'Thu gọn deadline cần làm' : 'Xem thêm ' + (pending.length - 5) + ' deadline'}
            </Text>
            <Text style={styles.planCollapseText}>{showAllPending ? '⌃' : '⌄'}</Text>
          </TouchableOpacity>
        )}
        {!!completed.length && (
          <>
            <TouchableOpacity style={styles.planCollapseButton} accessibilityRole="button"
              accessibilityState={{ expanded: showCompletedReminders }}
              onPress={() => setShowCompletedReminders(value => !value)}>
              <Text style={styles.planCollapseText}>✓ Đã hoàn thành ({completed.length})</Text>
              <Text style={styles.planCollapseText}>{showCompletedReminders ? '⌃' : '⌄'}</Text>
            </TouchableOpacity>
            {showCompletedReminders && completed.map(renderReminder)}
          </>
        )}
      </View>
    </ScrollView>
  );
}

function ProfileScreen({ userName, email, refreshData, onOpenQuiz, onOpenConnection, onLogout }) {
  const [profile, setProfile] = useState({});
  const [style, setStyle] = useState('balanced');
  const [time, setTime] = useState('19:00');
  const [minutes, setMinutes] = useState('45');
  const [goals, setGoals] = useState('');
  const [notes, setNotes] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [showLearningSettings, setShowLearningSettings] = useState(false);

  useEffect(() => {
    let active = true;
    api.profile().then(data => {
      if (!active) return;
      const p = data.profile || {};
      setProfile(p);
      setStyle(p.learning_style || 'balanced');
      setTime(p.preferred_study_time || '19:00');
      setMinutes(String(p.daily_minutes || 45));
      setGoals(p.goals || '');
      setNotes(p.notes || '');
    }).catch(err => { if (active) setError(err.message); });
    return () => { active = false; };
  }, []);

  const save = async () => {
    setBusy(true);
    setError('');
    try {
      await api.updateProfile({
        learning_style: style,
        preferred_study_time: time,
        daily_minutes: Number(minutes),
        goals,
        notes,
      });
      await refreshData();
      Alert.alert('Đã lưu', 'Hồ sơ học tập đã được đồng bộ với website.');
    } catch (err) {
      setError(err.message || 'Lưu thất bại.');
    } finally { setBusy(false); }
  };

  return (
    <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
      <Header title="Cá nhân" subtitle="Hồ sơ & cài đặt" userName={userName} />
      <View style={styles.card}>
        <Text style={styles.cardTitle}>👤 {userName || 'Sinh viên'}</Text>
        {!!email && <Text style={styles.muted}>{email}</Text>}
        <Text style={styles.muted}>Tài khoản sinh viên · Đồng bộ với Web</Text>
      </View>
      <Text style={styles.sectionTitle}>Học tập</Text>
      <TouchableOpacity style={styles.settingsEntry} onPress={onOpenQuiz}>
        <Text style={styles.settingsEntryText}>✓ Kết quả Quiz & điểm yếu</Text>
        <Text style={styles.settingsChevron}>›</Text>
      </TouchableOpacity>
      <TouchableOpacity style={styles.settingsEntry}
        onPress={() => setShowLearningSettings(v => !v)}>
        <Text style={styles.settingsEntryText}>⚙ Tùy chỉnh học tập</Text>
        <Text style={styles.settingsChevron}>{showLearningSettings ? '⌃' : '›'}</Text>
      </TouchableOpacity>
      {showLearningSettings && <View style={styles.card}>
      <ErrorCard message={error} />
      <Text style={styles.fieldLabel}>Phong cách học</Text>
      <View style={styles.actionRow}>
        {['balanced','visual','reading','practice'].map(value => (
          <TouchableOpacity key={value} style={[styles.smallAction, style === value && { backgroundColor: '#6567E8' }]}
            onPress={() => setStyle(value)}>
            <Text style={[styles.smallActionText, style === value && { color: 'white' }]}>
              {({ balanced:'Cân bằng', visual:'Trực quan', reading:'Đọc hiểu', practice:'Thực hành' })[value]}
            </Text>
          </TouchableOpacity>
        ))}
      </View>
      <Text style={styles.fieldLabel}>Giờ học ưu tiên (HH:MM)</Text>
      <TextInput style={styles.fieldInput} value={time} onChangeText={setTime} placeholder="19:00" />
      <Text style={styles.fieldLabel}>Số phút mỗi buổi</Text>
      <TextInput style={styles.fieldInput} value={minutes} onChangeText={setMinutes} keyboardType="number-pad" />
      <Text style={styles.fieldLabel}>Mục tiêu học tập</Text>
      <TextInput style={[styles.fieldInput, { minHeight: 82, textAlignVertical: 'top' }]} multiline value={goals} onChangeText={setGoals} placeholder="Ví dụ: điểm 8 môn Điện toán đám mây" />
      <Text style={styles.fieldLabel}>Ghi chú cá nhân</Text>
      <TextInput style={[styles.fieldInput, { minHeight: 82, textAlignVertical: 'top' }]} multiline value={notes} onChangeText={setNotes} />
      <TouchableOpacity disabled={busy} style={styles.primaryButton} onPress={save}>
        <Text style={styles.primaryButtonText}>{busy ? 'Đang lưu...' : 'Lưu hồ sơ học tập'}</Text>
      </TouchableOpacity>
      </View>}
      <Text style={styles.sectionTitle}>Ứng dụng</Text>
      <TouchableOpacity style={styles.settingsEntry} onPress={onOpenConnection}>
        <Text style={styles.settingsEntryText}>⌁ Cài đặt kết nối</Text>
        <Text style={styles.settingsChevron}>›</Text>
      </TouchableOpacity>
      <TouchableOpacity style={styles.settingsEntry} onPress={onLogout}>
        <Text style={[styles.settingsEntryText,{color:'#B83F51'}]}>↪ Đăng xuất</Text>
        <Text style={styles.settingsChevron}>›</Text>
      </TouchableOpacity>

    </ScrollView>
  );
}

function LoginScreen({ onLogin, onRegister, onOpenConnection }) {
  const [signup, setSignup] = useState(false);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const submit = async () => {
    if (signup && password !== confirm) {
      setError('Xác nhận mật khẩu không trùng khớp.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      if (signup) await onRegister(name.trim(), email.trim(), password);
      else await onLogin(email.trim(), password);
    } catch (err) {
      setError(err.message || 'Không thể xác thực.');
    } finally { setLoading(false); }
  };

  return (
    <ScrollView contentContainerStyle={styles.loginScroll} keyboardShouldPersistTaps="handled">
      <View style={styles.loginWrap}>
        <View style={styles.logo}><Text style={{ fontSize: 34 }}>🎓</Text></View>
        <Text style={styles.loginTitle}>AI Study Agent</Text>
        <Text style={styles.loginSubtitle}>Học theo đề cương · AI cá nhân hóa</Text>
        <Text style={styles.loginModeTitle}>{signup ? 'Đăng ký sinh viên' : 'Đăng nhập'}</Text>
        {signup && <TextInput value={name} onChangeText={setName} style={styles.loginInput} placeholder="Họ và tên" />}
        <TextInput value={email} onChangeText={setEmail} autoCapitalize="none"
          keyboardType="email-address" autoComplete="email" style={styles.loginInput}
          placeholder="Email" placeholderTextColor="#7484A2" />
        <View style={styles.loginPasswordRow}>
          <TextInput value={password} onChangeText={setPassword} secureTextEntry={!showPassword}
            autoComplete={signup ? 'new-password' : 'current-password'}
            style={[styles.loginInput, styles.loginPasswordInput]}
            placeholder="Mật khẩu" placeholderTextColor="#7484A2" />
          <TouchableOpacity accessibilityLabel={showPassword ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
            style={styles.loginEyeButton} onPress={() => setShowPassword(v => !v)}>
            <Text style={styles.loginEyeText}>{showPassword ? 'Ẩn' : 'Hiện'}</Text>
          </TouchableOpacity>
        </View>
        {signup && (
          <View style={styles.loginPasswordRow}>
            <TextInput value={confirm} onChangeText={setConfirm} secureTextEntry={!showConfirm}
              autoComplete="new-password" style={[styles.loginInput, styles.loginPasswordInput]}
              placeholder="Nhập lại mật khẩu" placeholderTextColor="#7484A2" />
            <TouchableOpacity accessibilityLabel={showConfirm ? 'Ẩn mật khẩu xác nhận' : 'Hiện mật khẩu xác nhận'}
              style={styles.loginEyeButton} onPress={() => setShowConfirm(v => !v)}>
              <Text style={styles.loginEyeText}>{showConfirm ? 'Ẩn' : 'Hiện'}</Text>
            </TouchableOpacity>
          </View>
        )}
        <ErrorCard message={error} />
        <TouchableOpacity style={styles.primaryButton} onPress={submit} disabled={loading}>
          <Text style={styles.primaryButtonText}>{loading ? 'Đang xử lý...' : signup ? 'Tạo tài khoản' : 'Đăng nhập'}</Text>
        </TouchableOpacity>
        <TouchableOpacity
          onPress={() => { setSignup(v => !v); setError(''); }}
          accessibilityRole="button" style={styles.loginLinkButton}>
          <Text style={styles.loginLink}>
            {signup ? 'Đã có tài khoản? Đăng nhập' : 'Chưa có tài khoản? Đăng ký sinh viên'}
          </Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={onOpenConnection}
          accessibilityRole="button" style={styles.loginLinkButton}>
          <Text style={styles.loginConnectionLink}>⚙ Cài đặt kết nối máy chủ</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}

export default function App() {
  const [loggedIn, setLoggedIn] = useState(false);
  const [checkingSession, setCheckingSession] = useState(true);
  const [tab, setTab] = useState('home');
  const [dashboard, setDashboard] = useState(null);
  const [subjects, setSubjects] = useState([]);
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeStudyTask, setActiveStudyTask] = useState(null);
  const [activeLesson, setActiveLesson] = useState(null);
  const [quizSubjectId, setQuizSubjectId] = useState(null);
  const [quizToOpenId,setQuizToOpenId]=useState(null);
  const [showConnectionSettings, setShowConnectionSettings] = useState(false);
  const [chatOpenSignal, setChatOpenSignal] = useState(0);
  const [subjectsEntry, setSubjectsEntry] = useState(null);
  const openSubjectJourney = (subjectId, mode = 'roadmap') => {
    setActiveStudyTask(null);
    setActiveLesson(null);
    setSubjectsEntry({subjectId, mode, token: Date.now()});
    setTab('subjects');
  };
  const openQuiz = (subjectId, quizId=null) => {
    setQuizSubjectId(subjectId || null);
    setQuizToOpenId(quizId || null);
    setActiveStudyTask(null);
    setActiveLesson(null);
    setTab('quiz');
  };

  const openStudyRoom = taskId => {
    setActiveLesson(null);
    setActiveStudyTask(taskId);
  };
  const closeStudyRoom = () => {
    setActiveLesson(null);
    setActiveStudyTask(null);
    refreshData().catch(() => {});
  };

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

  // Khôi phục địa chỉ API trước khi hỏi phiên đăng nhập. Địa chỉ đã lưu
  // không được dùng để khôi phục mật khẩu hoặc tự đăng nhập tài khoản cũ.
  useEffect(() => {
    let active = true;
    restoreServerAddress()
      .catch(() => null) // Missing local storage should still allow manual setup.
      .then(() => api.session())
      .then(() => refreshData())
      .then(() => { if (active) setLoggedIn(true); })
      .catch(() => { if (active) setLoggedIn(false); })
      .finally(() => { if (active) setCheckingSession(false); });
    return () => { active = false; };
  }, []);

  const handleLogin = async (email, password) => {
    await api.login(email, password);
    await refreshData();
    setLoggedIn(true);
  };

  const handleRegister = async (name, email, password) => {
    await api.register(name, email, password);
    await refreshData();
    setLoggedIn(true);
  };

  const handleLogout = async () => {
    try {
      await api.logout();
    } finally {
      setLoggedIn(false);
      setTab('home');
      setQuizSubjectId(null);
      setQuizToOpenId(null);
      setActiveStudyTask(null);
      setActiveLesson(null);
      setDashboard(null);
      setSubjects([]);
      setPlan(null);
    }
  };

  useEffect(() => {
    if (loggedIn) {
      refreshData().catch(() => {});
    }
  }, [loggedIn]);

  const userName = dashboard?.user?.name || '';

  const screen = useMemo(() => {
    if (activeStudyTask) return (
      <StudyRoom key={activeStudyTask} taskId={activeStudyTask}
        onBack={closeStudyRoom} onContext={setActiveLesson}
        onOpenQuiz={info => openQuiz(
          info?.subjectId || activeLesson?.subjectId,
          info?.quizId || null
        )} />
    );
    if (tab === 'profile') return (
      <ProfileScreen userName={userName} email={dashboard?.user?.email}
        refreshData={refreshData} onOpenQuiz={() => openQuiz(null)}
        onOpenConnection={() => setShowConnectionSettings(true)}
        onLogout={handleLogout}/>
    );
    if (tab === 'subjects') return <SubjectsScreen subjects={subjects}
      userName={userName} refreshData={refreshData}
      entryIntent={subjectsEntry}
      onOpenStudy={openStudyRoom} onOpenQuiz={openQuiz} />;
    if (tab === 'agent') return <AgentScreen subjects={subjects} userName={userName} />;
    if (tab === 'quiz') return <QuizScreen subjects={subjects}
      initialSubjectId={quizSubjectId} initialQuizId={quizToOpenId}
      onBack={() => {setQuizToOpenId(null);setTab('subjects');}}
      userName={userName} refreshData={refreshData} />;
    if (tab === 'plan') return <PlanScreen plan={plan} subjects={subjects} userName={userName}
      refreshData={refreshData} onOpenStudy={openStudyRoom}
      onOpenRoadmap={() => openSubjectJourney(null, 'roadmap')} />;
    return (
      <HomeScreen
        dashboard={dashboard}
        setTab={setTab}
        loading={loading}
        onOpenStudy={openStudyRoom}
        onAskAI={() => setChatOpenSignal(value => value+1)}
        onOpenSubjectJourney={openSubjectJourney}
        onOpenQuiz={openQuiz}
      />
    );
  }, [tab, subjects, dashboard, plan, loading, userName, loggedIn,
      activeStudyTask, activeLesson?.subjectId, quizSubjectId, quizToOpenId, subjectsEntry]);

  if (checkingSession) {
    return (
      <SafeAreaView style={[styles.safe, { justifyContent: 'center', alignItems: 'center' }]}>
        <ActivityIndicator size="large" />
        <Text style={{ marginTop: 12, color: '#667085' }}>Đang kiểm tra phiên đăng nhập...</Text>
      </SafeAreaView>
    );
  }
  if (showConnectionSettings) return (
    <ConnectionSettings onBack={() => setShowConnectionSettings(false)}
      onSaved={() => {
        // New host requires a new login; never preserve old identity.
        setLoggedIn(false);
        setDashboard(null);
        setSubjects([]);
        setPlan(null);
        setActiveStudyTask(null);
        setActiveLesson(null);
        setTab('home');
        setShowConnectionSettings(false);
      }}/>
  );
  if (!loggedIn) return <LoginScreen onLogin={handleLogin}
    onRegister={handleRegister}
    onOpenConnection={() => setShowConnectionSettings(true)} />;

  const tabs = [
    ['home', '⌂', 'Tổng quan'],
    ['subjects', '▤', 'Môn học'],
    ['plan', '▦', 'Lịch học'],
    ['profile', '♙', 'Cá nhân'],
  ];

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar barStyle="dark-content" />
      <View style={styles.app}>{screen}</View>
      <View style={styles.bottomNav}>
        {tabs.map(([key, icon, label]) => (
          <TouchableOpacity
            key={key}
            style={styles.navItem}
            onPress={() => {
              setActiveStudyTask(null);
              setActiveLesson(null);
              setSubjectsEntry(null);
              setTab(key);
              refreshData().catch(() => {});
            }}
          >
            <Text style={[styles.navIcon, (tab === key || (tab === 'quiz' && key === 'subjects')) && styles.navActive]}>{icon}</Text>
            <Text style={[styles.navLabel, (tab === key || (tab === 'quiz' && key === 'subjects')) && styles.navActive]}>{label}</Text>
          </TouchableOpacity>
        ))}
      </View>
      <FloatingStudyChat subjects={subjects} lesson={activeLesson}
        openSignal={chatOpenSignal}/>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#F6F8FC' },
  app: { flex: 1 },
  page: { padding: 16, paddingBottom: 110, backgroundColor: '#F6F8FC' },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 22 },
  title: { fontSize: 24, fontWeight: '800', color: '#17203A' },
  subtitle: { marginTop: 5, fontSize: 13, color: '#536689', lineHeight: 19 },
  avatar: { width: 42, height: 42, borderRadius: 21, backgroundColor: '#E8EAFE', alignItems: 'center', justifyContent: 'center' },
  avatarText: { color: '#5965D8', fontWeight: '800' },
  heroCard: { backgroundColor: '#6567E8', borderRadius: 24, padding: 22, flexDirection: 'row', marginBottom: 24 },
  heroEyebrow: { color: '#D8DBFF', fontSize: 11, fontWeight: '800', letterSpacing: 1.1 },
  heroTitle: { color: 'white', fontSize: 20, lineHeight: 29, fontWeight: '800', marginTop: 8 },
  heroText: { color: '#EEF0FF', fontSize: 13, lineHeight: 19, marginTop: 8 },
  heroButton: { alignSelf: 'flex-start', backgroundColor: 'white', paddingHorizontal: 14, paddingVertical: 10, borderRadius: 12, marginTop: 16 },
  heroButtonText: { color: '#555DD0', fontWeight: '800' },
  robot: { width: 72, justifyContent: 'center', alignItems: 'center' },
  mobileStatusRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginTop: -8, marginBottom: 14 },
  mobileStatusText: { flex: 1, color: '#53668B', fontSize: 11 },
  logoutButton: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: '#EEF0FF' },
  logoutButtonText: { color: '#5965D8', fontSize: 11, fontWeight: '800' },
  fieldLabel: { fontSize: 13, fontWeight: '700', color: '#29324D', marginBottom: 8 },
  fieldInput: { backgroundColor: 'white', borderWidth: 1, borderColor: '#DFE3F0', borderRadius: 12, paddingHorizontal: 14, paddingVertical: 13, fontSize: 15, color: '#17203A', marginBottom: 16 },
  backLink: { color: '#6567E8', fontWeight: '700', marginBottom: 16, fontSize: 13 },
  actionRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 },
  smallAction: { paddingHorizontal: 12, minHeight: 43, justifyContent: 'center', borderRadius: 10, backgroundColor: '#EEF0FF' },
  smallActionText: { color: '#505AD0', fontSize: 12, fontWeight: '700' },
  deleteAction: { backgroundColor: '#FFF0F1' },
  deleteActionText: { color: '#B83647', fontSize: 12, fontWeight: '700' },
  secondaryAction: { paddingVertical: 16, alignItems: 'center' },
  secondaryActionText: { fontSize: 14, fontWeight: '700', color: '#5965D8' },
  homeMetricsRow: { flexDirection: 'row', gap: 9, marginBottom: 16 },
  homeMetric: { flex: 1, backgroundColor: 'white', borderRadius: 15, padding: 13, borderWidth: 1, borderColor: '#E9ECF7' },
  homeMetricValue: { color: '#5965D8', fontSize: 21, fontWeight: '900' },
  homeMetricLabel: { color: '#526588', fontSize: 12, marginTop: 4, fontWeight: '600' },
  recommendCard: { padding: 17, borderRadius: 18, marginBottom: 15, backgroundColor: '#EDF0FF', borderWidth: 1, borderColor: '#CDD5FF', gap: 5 },
  loginScroll: { flex: 1, backgroundColor: '#F6F8FC' },
  sectionTitle: { fontSize: 17, fontWeight: '800', color: '#202943', marginBottom: 10, marginTop: 4 },
  card: { backgroundColor: 'white', borderRadius: 18, padding: 17, marginBottom: 12, borderWidth: 1, borderColor: '#EBEEF5' },
  subjectCard: { backgroundColor: 'white', borderRadius: 20, padding: 17, marginBottom: 14, borderWidth: 1, borderColor: '#EBEEF5', flexDirection: 'row', gap: 14 },
  subjectIcon: { width: 50, height: 50, borderRadius: 16, backgroundColor: '#F0F1FF', alignItems: 'center', justifyContent: 'center' },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  cardTitle: { fontSize: 15, fontWeight: '800', color: '#27304B' },
  muted: { color: '#53678B', fontSize: 13, lineHeight: 20, marginTop: 5 },
  time: { color: '#5965D8', fontWeight: '800', fontSize: 12 },
  percent: { color: '#5965D8', fontWeight: '800', fontSize: 15 },
  progressTrack: { height: 8, backgroundColor: '#EDEEFA', borderRadius: 999, marginTop: 13, overflow: 'hidden' },
  progressFill: { height: '100%', backgroundColor: '#6567E8', borderRadius: 999 },
  weakText: { color: '#855D28', fontSize: 12, lineHeight: 18, marginTop: 10 },
  pillRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 10 },
  pill: { backgroundColor: '#EEF0FF', borderRadius: 999, paddingHorizontal: 9, paddingVertical: 6 },
  pillText: { color: '#4B55B3', fontSize: 11, fontWeight: '700' },
  chatPage: { flex: 1, padding: 20, backgroundColor: '#F6F8FC' },
  contextStrip: { flexDirection: 'row', flexWrap: 'wrap', gap: 7, marginBottom: 12 },
  chatList: { flex: 1 },
  message: { maxWidth: '84%', borderRadius: 18, paddingHorizontal: 14, paddingVertical: 12, marginBottom: 10 },
  aiMessage: { alignSelf: 'flex-start', backgroundColor: 'white', borderWidth: 1, borderColor: '#EBEEF5' },
  userMessage: { alignSelf: 'flex-end', backgroundColor: '#6567E8' },
  aiMessageText: { color: '#283954', lineHeight: 21, fontSize: 14 },
  userMessageText: { color: 'white', lineHeight: 20, fontSize: 13 },
  composer: { flexDirection: 'row', gap: 9, paddingTop: 10 },
  input: { flex: 1, backgroundColor: 'white', borderWidth: 1, borderColor: '#E5E8F1', borderRadius: 16, paddingHorizontal: 14, height: 48, color: '#222A40' },
  sendButton: { width: 48, height: 48, borderRadius: 16, backgroundColor: '#6567E8', alignItems: 'center', justifyContent: 'center' },
  sendText: { color: 'white', fontSize: 18, fontWeight: '900' },
  eyebrow: { color: '#6972D4', fontSize: 11, fontWeight: '900', letterSpacing: 1 },
  quizQuestion: { fontSize: 19, lineHeight: 27, fontWeight: '800', color: '#202943', marginVertical: 14 },
  option: { borderWidth: 1, borderColor: '#E5E8F1', borderRadius: 14, padding: 13, marginBottom: 9, flexDirection: 'row', alignItems: 'center', gap: 10 },
  optionSelected: { borderColor: '#6567E8', backgroundColor: '#F1F2FF' },
  optionLetter: { width: 26, height: 26, borderRadius: 13, backgroundColor: '#F0F2F7', textAlign: 'center', lineHeight: 26, color: '#526487', fontWeight: '800' },
  optionLetterSelected: { backgroundColor: '#6567E8', color: 'white' },
  optionText: { color: '#293B5B', fontSize: 14, fontWeight: '600', flexShrink: 1, lineHeight: 21 },
  insightCard: { backgroundColor: '#FFF8E8', borderRadius: 18, padding: 16 },
  insightTitle: { color: '#8E632E', fontWeight: '800', marginBottom: 5 },
  profileCard: { backgroundColor: '#222C4D', borderRadius: 22, padding: 20, marginBottom: 20 },
  profileGrid: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 18 },
  metric: { color: 'white', fontSize: 21, fontWeight: '900' },
  metricLabel: { color: '#E2E5F6', fontSize: 12, marginTop: 4 },
  timelineRow: { flexDirection: 'row', alignItems: 'stretch', marginBottom: 12, gap: 12 },
  timelineDot: { width: 34, height: 34, borderRadius: 17, backgroundColor: '#6567E8', alignItems: 'center', justifyContent: 'center', marginTop: 9 },
  timelineIndex: { color: 'white', fontWeight: '900' },
  timelineCard: { flex: 1, backgroundColor: 'white', borderRadius: 17, padding: 15, borderWidth: 1, borderColor: '#EBEEF5' },
  timelineDay: { color: '#6972D4', fontSize: 10, fontWeight: '900', marginBottom: 4, textTransform: 'uppercase' },
  bottomNav: { height: 78, backgroundColor: 'white', flexDirection: 'row', borderTopWidth: 1, borderTopColor: '#E9ECF3', paddingTop: 10, paddingBottom: 8 },
  navItem: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  navIcon: { fontSize: 19, color: '#637493' },
  navLabel: { fontSize: 11, color: '#637493', marginTop: 4, fontWeight: '700' },
  navActive: { color: '#5E66D8' },
  loginSafe: { flex: 1, backgroundColor: '#F6F8FC', justifyContent: 'center' },
  loginWrap: { flexGrow: 1, paddingHorizontal: 26, paddingTop: 32, paddingBottom: 32, justifyContent: 'center', alignItems: 'stretch' },
  logo: { alignSelf: 'center', width: 64, height: 64, borderRadius: 22, backgroundColor: '#EBEDFF', alignItems: 'center', justifyContent: 'center', marginBottom: 14 },
  loginTitle: { textAlign: 'center', color: '#202943', fontSize: 28, fontWeight: '900' },
  loginSubtitle: { textAlign: 'center', color: '#53678B', fontSize: 14, marginTop: 7, marginBottom: 18 },
  loginInput: { height: 52, borderRadius: 15, backgroundColor: 'white', borderWidth: 1, borderColor: '#E4E7F0', paddingHorizontal: 15, marginBottom: 11, color: '#202943' },
  primaryButton: { height: 52, borderRadius: 15, backgroundColor: '#6567E8', alignItems: 'center', justifyContent: 'center', marginTop: 4 },
  primaryButtonText: { color: 'white', fontSize: 15, fontWeight: '900' },
  loginHint: { color: '#516585', textAlign: 'center', fontSize: 12, marginTop: 18 },
  loginAdminNote: { color: '#4D6290', textAlign: 'center', fontSize: 11.5, lineHeight: 18, marginTop: 11 },
  loginBackendHint: { color: '#677899', textAlign: 'center', fontSize: 10, marginTop: 10 },
  loginModeTitle:{fontSize:17,fontWeight:'800',color:'#27304B',marginBottom:14},
  loginLinkButton:{alignItems:'center',paddingVertical:11},
  loginLink:{fontSize:13,fontWeight:'800',color:'#5C60D5'},
  loginConnectionLink:{fontSize:12,color:'#687B9B',fontWeight:'700'},
  settingsEntry:{minHeight:54,paddingHorizontal:16,paddingVertical:14,
    borderRadius:14,backgroundColor:'#FFFFFF',borderWidth:1,borderColor:'#E8ECF6',
    flexDirection:'row',alignItems:'center',marginBottom:9},
  settingsEntryText:{color:'#2F436C',fontSize:14,fontWeight:'700',flex:1},
  settingsChevron:{fontSize:22,color:'#8493AF',paddingHorizontal:4},
  authSegment: { flexDirection: 'row', padding: 5, borderRadius: 15, backgroundColor: '#E9EEFA', marginBottom: 20, gap: 5 },
  authSegmentButton: { flex: 1, paddingVertical: 13, borderRadius: 11, alignItems: 'center' },
  authSegmentSelected: { backgroundColor: '#6567E8' },
  authSegmentText: { color: '#405582', fontSize: 13, fontWeight: '700' },
  authSegmentTextSelected: { color: 'white', fontWeight: '800' },
  loginPasswordRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: 'white', borderWidth: 1, borderColor: '#D7DFF0', borderRadius: 15, marginBottom: 11 },
  loginPasswordInput: { flex: 1, borderWidth: 0, marginBottom: 0, paddingRight: 3 },
  loginEyeButton: { paddingHorizontal: 14, height: 51, justifyContent: 'center', alignItems: 'center' },
  loginEyeText: { color: '#4B5ED0', fontWeight: '800', fontSize: 12 },
  planToolbar: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16, marginTop: 12 },
  planCalendarCard: { backgroundColor: 'white', padding: 15, borderRadius: 19, marginBottom: 13, borderColor: '#E0E7F5', borderWidth: 1 },
  planSectionRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginBottom: 10 },
  planSectionTitle: { color: '#273B65', fontWeight: '800', fontSize: 15, flexShrink: 1 },
  planSectionSubtitle: { color: '#53698E', fontSize: 11.5, lineHeight: 17, marginTop: 4 },
  planViewTabs: { flexDirection: 'row', padding: 3, backgroundColor: '#E9EEFB', borderRadius: 11, gap: 3 },
  planViewTab: { paddingVertical: 8, paddingHorizontal: 10, borderRadius: 9 },
  planViewTabSelected: { backgroundColor: '#6265E8' },
  planViewLabel: { fontSize: 11, fontWeight: '800', color: '#496087' },
  planViewLabelSelected: { color: 'white' },
  planCalendarNav: { flexDirection: 'row', gap: 8, alignItems: 'center', marginBottom: 11 },
  planArrow: { backgroundColor: '#E9EFFB', width: 32, height: 32, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  planArrowText: { color: '#4E62B9', fontWeight: '800', fontSize: 21 },
  planWeekRange: { fontSize: 13, fontWeight: '800', color: '#31446C' },
  planTodayButton: { backgroundColor: '#E7EDFF', paddingHorizontal: 11, paddingVertical: 9, borderRadius: 10 },
  planTodayText: { color: '#4E5ED4', fontSize: 11, fontWeight: '800' },
  planWeekRow: { flexDirection: 'row', gap: 3 },
  planDayCell: { flex: 1, minWidth: 0, alignItems: 'center', justifyContent: 'center', borderRadius: 10, backgroundColor: '#ECF2FB', paddingVertical: 10, gap: 4 },
  planDayCellActive: { backgroundColor: '#6567E8' },
  planDayName: { fontWeight: '800', color: '#566A91', fontSize: 10 },
  planDayDate: { color: '#354B73', fontSize: 12, fontWeight: '800' },
  planDayCount: { color: '#65789B', fontSize: 10 },
  planDayActiveText: { color: 'white' },
  planEditButton: { borderRadius: 10, paddingVertical: 9, paddingHorizontal: 12, backgroundColor: '#E8ECFF' },
  planEditButtonText: { color: '#4F5BC6', fontSize: 12, fontWeight: '800' },
  planEmptyText: { color: '#53668A', fontSize: 13, lineHeight: 20, padding: 12, backgroundColor: '#F0F4FC', borderRadius: 12 },
  planTaskRow: { flexDirection: 'row', gap: 10, alignItems: 'flex-start', backgroundColor: '#F1F5FC', padding: 12, borderRadius: 13, marginTop: 8 },
  planTaskDone: { backgroundColor: '#F0F3FA' },
  planTaskActions: { flexDirection: 'column', gap: 8 },
  planCheck: { width: 44, height: 44, borderWidth: 1.5, borderColor: '#8A98C4', borderRadius: 11, alignItems: 'center', justifyContent: 'center', backgroundColor: 'white' },
  planCheckDone: { borderColor: '#6567E8', backgroundColor: '#6567E8' },
  planCheckText: { color: '#45578C', fontSize: 14, fontWeight: '900' },
  planCheckTextDone: { color: 'white' },
  planTaskTitle: { color: '#2B3F67', fontWeight: '800', fontSize: 13.5, lineHeight: 20 },
  planDoneTitle: { color: '#526689', textDecorationLine: 'line-through' },
  planTaskMeta: { color: '#51668A', fontSize: 11.5, lineHeight: 18, marginTop: 4 },
  planTaskNote: { color: '#566C91', fontSize: 11.5, lineHeight: 17, marginTop: 5 },
  planAdaptiveTag: { color: '#6C589A', fontWeight: '800', fontSize: 10.5, marginTop: 5 },
  planIconAction: { backgroundColor: '#E6ECFA', width: 44, height: 44, borderRadius: 11, justifyContent: 'center', alignItems: 'center' },
  planIconText: { color: '#5869BC', fontSize: 16, fontWeight: '800' },
  planTodaySummary: { backgroundColor: '#EEF0FF', borderColor: '#D6DEFD', borderWidth: 1, borderRadius: 15,
    paddingVertical: 13, paddingHorizontal: 15, flexDirection: 'row', alignItems: 'center',
    justifyContent: 'space-between', gap: 9 },
  planTodaySummaryLabel: {fontSize: 13, color: '#5364A3', fontWeight: '800'},
  planTodaySummaryValue: {fontSize: 13, color: '#3E4C9F', fontWeight: '800', flexShrink: 1, textAlign: 'right'},
  planConflictNote: {padding:12, backgroundColor:'#FFF7E9', borderColor:'#EED3A8',
    borderWidth:1,borderRadius:12,gap:7,marginBottom:9},
  planConflictText: {color:'#956021',fontSize:12,fontWeight:'800'},
  planTaskDoc: {fontSize:11,color:'#536AA1',marginTop:4},
  docSelected: {backgroundColor:'#6265E8'},
  docSelectedText: {color:'white'},
  docUpload: {borderWidth:1,borderColor:'#CDD4F6',backgroundColor:'#F0F2FF',
    borderRadius:12,minHeight:45,alignItems:'center',justifyContent:'center',paddingHorizontal:12},
  docUploadText: {fontSize:12,color:'#4A5EBD',fontWeight:'800'},
  helperNote: {fontSize:11,color:'#63769A',lineHeight:18,marginTop:7,marginBottom:13},
  planProgressPercent: { color: '#5C5DDC', fontSize: 24, fontWeight: '900' },
  planProgressHours: { color: '#53668A', fontSize: 12, lineHeight: 17, marginTop: 11 },
  planReminderRow: { flexDirection: 'row', alignItems: 'center', gap: 9, borderBottomWidth: 1, borderBottomColor: '#E8EDF8', paddingVertical: 12 },
  planReminderDone: { backgroundColor: '#F7F9FE' },
  planReminderTitle: { color: '#2D4269', fontSize: 12.5, fontWeight: '800', lineHeight: 18 },
  planReminderMeta: { color: '#54678A', fontSize: 10.5, lineHeight: 17, marginTop: 4 },
  planCollapseButton: { flexDirection: 'row', justifyContent: 'space-between', paddingHorizontal: 12, paddingVertical: 12, marginTop: 10, backgroundColor: '#E8EEFC', borderRadius: 12 },
  planCollapseText: { color: '#4A5FA4', fontSize: 12, fontWeight: '800' },
});
