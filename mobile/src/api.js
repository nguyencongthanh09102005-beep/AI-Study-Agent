// Android Emulator truy cập Flask trên máy Windows qua 10.0.2.2.
// Khi deploy backend thật, đổi URL này thành domain HTTPS của server.
export const API_BASE_URL = 'http://10.0.2.2:5000';

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
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

  subjects: () => request('/api/mobile/subjects'),

  dashboard: () => request('/api/mobile/dashboard'),

  subjectDetail: (subjectId) => request(`/api/mobile/subjects/${subjectId}`),

  chat: (subjectId, message) =>
    request('/api/mobile/chat', {
      method: 'POST',
      body: JSON.stringify({ subject_id: subjectId, message }),
    }),

  quizGenerate: (documentId, count = 10) =>
    request('/api/mobile/quiz/generate', {
      method: 'POST',
      body: JSON.stringify({ document_id: documentId, count }),
    }),

  studyPlan: (payload) =>
    request('/api/mobile/study-plan', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
};
