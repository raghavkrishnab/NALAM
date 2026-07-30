// Vite proxies /api to the FastAPI backend, so everything stays same-origin.
const BASE = '/api';

async function request(path, options = {}) {
  const response = await fetch(`${BASE}${path}`, options);
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (body.detail) detail = body.detail;
    } catch {
      // Non-JSON error body; the status line is all we have.
    }
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

const json = (body) => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

export const getHealth = () => request('/health');

export const getOptions = (language) => request(`/options?language=${language}`);

export const getSchemes = (language, category) =>
  request(`/schemes?language=${language}${category ? `&category=${category}` : ''}`);

export const matchProfile = (profile) => request('/match', json(profile));

export const sendChat = (payload) => request('/chat', json(payload));

export const getChatStarters = (language) => request(`/chat/starters?language=${language}`);

export async function transcribeAudio(blob, language) {
  const form = new FormData();
  form.append('audio', blob, 'recording.webm');
  form.append('language', language || 'auto');
  return request('/transcribe', { method: 'POST', body: form });
}

export async function readDocument(file) {
  const form = new FormData();
  form.append('document', file);
  return request('/ocr', { method: 'POST', body: form });
}
