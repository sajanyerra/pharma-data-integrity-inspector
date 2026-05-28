const API_BASE = import.meta.env.VITE_API_BASE || 'https://pharma-data-integrity-inspector.onrender.com'

function getSessionId() {
  if (typeof window === 'undefined') return 'default'
  let sid = localStorage.getItem('session_id')
  if (!sid) {
    sid = crypto.randomUUID()
    localStorage.setItem('session_id', sid)
  }
  return sid
}

const sessionId = getSessionId()

export default API_BASE
export { sessionId }