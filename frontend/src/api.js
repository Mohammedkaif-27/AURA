const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

export async function sendMessage(message, sessionId, token) {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify({ message, session_id: sessionId }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Request failed (${res.status})`);
  }

  return res.json();
}

export async function fetchSessions(token) {
  const res = await fetch(`${API_BASE}/chat/sessions`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  if (!res.ok) throw new Error('Failed to fetch sessions');
  return res.json();
}

export async function fetchSessionMessages(sessionId, token) {
  const res = await fetch(`${API_BASE}/chat/sessions/${sessionId}`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  if (!res.ok) throw new Error('Failed to fetch messages');
  return res.json();
}

export async function deleteSession(sessionId, token) {
  const res = await fetch(`${API_BASE}/chat/sessions/${sessionId}`, {
    method: 'DELETE',
    headers: { 'Authorization': `Bearer ${token}` }
  });
  if (!res.ok) throw new Error('Failed to delete session');
  return res.json();
}
