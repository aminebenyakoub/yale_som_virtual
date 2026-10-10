import { useEffect, useRef, useState } from 'react'

// Talks to the FastAPI backend (backend/main.py). Override with VITE_API_URL when it runs elsewhere.
export const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

const MUTE_KEY = 'som-chat-muted'
const loadMuted = () => {
  try {
    return localStorage.getItem(MUTE_KEY) === '1'
  } catch {
    return false
  }
}

// Read a reply aloud and flag talkRef.speaking so the avatar's mouth moves. When muted (or the
// browser has no speech), the mouth still moves for about as long as reading it would take.
function useVoice(talkRef, muted) {
  const timer = useRef()
  const stop = () => {
    clearTimeout(timer.current)
    if ('speechSynthesis' in window) speechSynthesis.cancel()
    talkRef.current.speaking = false
  }
  const say = (text) => {
    stop()
    const done = () => (talkRef.current.speaking = false)
    talkRef.current.speaking = true
    if (muted || !('speechSynthesis' in window)) {
      timer.current = setTimeout(done, Math.min(12000, 400 + text.length * 45))
      return
    }
    const u = new SpeechSynthesisUtterance(text)
    const voices = speechSynthesis.getVoices().filter((v) => v.lang.startsWith('en'))
    u.voice = voices.find((v) => /Rishi|Aaron|Daniel|Alex/.test(v.name)) || voices[0] || null
    u.rate = 1.05
    u.onend = done
    u.onerror = done
    speechSynthesis.speak(u)
  }
  useEffect(() => stop, []) // eslint-disable-line react-hooks/exhaustive-deps
  return { say, stop }
}

export default function ChatPanel({ prof, talkRef, onClose }) {
  const [messages, setMessages] = useState([])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [muted, setMuted] = useState(loadMuted)
  const { say, stop } = useVoice(talkRef, muted)
  const listRef = useRef()
  const inputRef = useRef()

  // greeting comes from the backend, so a missing server shows up right away
  useEffect(() => {
    let live = true
    fetch(`${API}/api/professors/${prof.slug}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((p) => {
        if (!live) return
        setMessages([{ role: 'assistant', content: p.greeting }])
        say(p.greeting)
      })
      .catch(() => live && setError(`Can't reach the professor backend at ${API}. Is uvicorn running?`))
    return () => {
      live = false
    }
  }, [prof.slug]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, busy])

  useEffect(() => {
    inputRef.current?.focus()
    const esc = (e) => e.code === 'Escape' && onClose()
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [onClose])

  const send = async (e) => {
    e.preventDefault()
    const text = draft.trim()
    if (!text || busy) return
    const next = [...messages, { role: 'user', content: text }]
    setMessages(next)
    setDraft('')
    setBusy(true)
    setError('')
    stop()
    try {
      const r = await fetch(`${API}/api/professors/${prof.slug}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: next.slice(-30).map(({ role, content }) => ({ role, content })) }),
      })
      const data = await r.json()
      if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`)
      setMessages((m) => [...m, { role: 'assistant', content: data.reply, tools: data.tools_used }])
      say(data.reply)
    } catch (err) {
      setError(err.message === 'Failed to fetch' ? `Can't reach the professor backend at ${API}.` : err.message)
    } finally {
      setBusy(false)
      inputRef.current?.focus()
    }
  }

  const toggleMute = () => {
    const v = !muted
    setMuted(v)
    if (v) stop()
    try {
      localStorage.setItem(MUTE_KEY, v ? '1' : '0')
    } catch {
      // private window: the setting just won't stick
    }
  }

  const last = prof.name.split(' ').slice(-1)[0]
  return (
    <div className="chat" onClick={(e) => e.stopPropagation()}>
      <header>
        <div>
          <div className="kicker">AI professor</div>
          <b>Prof. {prof.name}</b>
        </div>
        <button className="icon" onClick={toggleMute} title={muted ? 'Turn voice on' : 'Mute voice'}>
          {muted ? 'voice off' : 'voice on'}
        </button>
        <button className="icon" onClick={onClose} title="Back to walking (Esc)">
          ✕
        </button>
      </header>
      <div className="msgs" ref={listRef}>
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            {m.content}
            {m.tools?.length > 0 && <div className="tools">looked it up in the course catalog</div>}
          </div>
        ))}
        {busy && <div className="msg assistant typing">Prof. {last} is thinking…</div>}
        {error && <div className="msg error">{error}</div>}
      </div>
      <form onSubmit={send}>
        <input
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={`Ask Prof. ${last} anything…`}
          maxLength={2000}
        />
        <button className="send" disabled={busy || !draft.trim()}>
          Send
        </button>
      </form>
    </div>
  )
}
