// Android Emulator có thể dùng mặc định 10.0.2.2.
// iPhone/Expo Go cần EXPO_PUBLIC_API_URL trỏ tới IP LAN của máy chạy Flask,
// ví dụ http://192.168.1.15:5000.
const configuredBaseUrl = String(
  process.env.EXPO_PUBLIC_API_URL || ''
).trim();

export const API_BASE_URL = (
  configuredBaseUrl || 'http://10.0.2.2:5000'
).replace(/\/$/, '');

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: 'include',
    ...options,
    headers: options.body instanceof FormData
      ? { ...(options.headers || {}) }
      : { 'Content-Type': 'application/json', ...(options.headers || {}) },
  });

  const text = await response.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { message: text };
  }

  if (!response.ok) {
    throw new Error(data?.error || data?.message || `HTTP ${response.status}`);
  }

  return data;
}

export const api = {
  login: (email, password) =>
    request('/api/mobile/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  logout: () =>
    request('/api/mobile/logout', {
      method: 'POST',
      body: JSON.stringify({}),
    }),

  subjects: () => request('/api/mobile/subjects'),

  dashboard: () => request('/api/mobile/dashboard'),

  subjectDetail: (subjectId) =>
    request(`/api/mobile/subjects/${subjectId}`),

  createSubject: (payload) =>
    request('/api/mobile/subjects', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  updateSubject: (subjectId, payload) =>
    request(`/api/mobile/subjects/${subjectId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  deleteSubject: (subjectId) =>
    request(`/api/mobile/subjects/${subjectId}`, { method: 'DELETE' }),

  documents: () => request('/api/mobile/documents'),

  uploadDocument: async (subjectId, file) => {
    const form = new FormData();
    form.append('subject_id', String(subjectId));
    form.append('file', {
      uri: file.uri,
      name: file.name || 'tai-lieu.pdf',
      type: file.mimeType || 'application/pdf',
    });
    return request('/api/mobile/documents', {
      method: 'POST',
      body: form,
    });
  },

  moveDocument: (docId, subjectId) =>
    request(`/api/mobile/documents/${docId}`, {
      method: 'PUT',
      body: JSON.stringify({ subject_id: subjectId }),
    }),

  deleteDocument: (docId) =>
    request(`/api/mobile/documents/${docId}`, { method: 'DELETE' }),

  setPersonalSyllabus: (subjectId, docId) =>
    request(`/api/mobile/subjects/${subjectId}/personal-syllabus`, {
      method: 'PUT',
      body: JSON.stringify({ document_id: docId }),
    }),

  chat: (subjectId, message) =>
    request('/api/mobile/chat', {
      method: 'POST',
      body: JSON.stringify({ subject_id: subjectId, message }),
    }),

  chatHistory: (subjectId) =>
    request(`/api/mobile/chat/${subjectId}`),

  quizGenerate: (subjectId, count = 10, mode = 'subject') =>
    request('/api/mobile/quiz/generate', {
      method: 'POST',
      body: JSON.stringify({
        subject_id: subjectId,
        count,
        mode,
      }),
    }),

  quizSubmit: (quizId, answers) =>
    request('/api/mobile/quiz/submit', {
      method: 'POST',
      body: JSON.stringify({
        quiz_id: quizId,
        answers,
      }),
    }),

  studyPlan: () => request('/api/mobile/study-plan'),

  generateStudyPlan: (payload) =>
    request('/api/mobile/study-plan', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
};
