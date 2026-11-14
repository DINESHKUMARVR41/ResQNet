import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { Link, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { Activity, ArrowRight, Bell, HeartHandshake, LayoutDashboard, LogOut, ShieldCheck, Users, PawPrint, Plus, MapPin, RefreshCw, Clock3, AlertTriangle, Mic, MicOff, BarChart2, CheckCircle, XCircle } from 'lucide-react'
import {
  api, ApiError, caseApi, responderApi, type User, type UserRole, type RescueCase, type AssignmentOffer, progressApi,
  aiApi, notifApi, evidenceApi, analyticsApi, progressExtApi, adminApi,
  type IncidentExtraction, type Notification, type Evidence, type AnalyticsSummary, handoffApi, type Handoff, type Organization
} from './lib/api'

type Session = { token: string; user: User }
const demoAccounts: { label: string; email: string; role: UserRole }[] = [
  { label: 'Citizen', email: 'citizen@resqnet.demo', role: 'citizen' },
  { label: 'Rescuer', email: 'rescuer@resqnet.demo', role: 'rescuer' },
  { label: 'NGO', email: 'ngo@resqnet.demo', role: 'coordinator' },
  { label: 'Coordinator', email: 'coordinator@resqnet.demo', role: 'coordinator' },
  { label: 'Administrator', email: 'admin@resqnet.demo', role: 'admin' },
]
const DEMO_PASSWORD = 'ResQNetDemo!2026'
function App() {
  const [session, setSession] = useState<Session | null>(() => { const raw = localStorage.getItem('resqnet-session'); return raw ? JSON.parse(raw) : null })
  const [checking, setChecking] = useState(Boolean(session))
  useEffect(() => { if (!session) return; api.me(session.token).then(user => setSession({ ...session, user })).catch(() => { localStorage.removeItem('resqnet-session'); setSession(null) }).finally(() => setChecking(false)) }, [])
  const save = (next: Session) => { localStorage.setItem('resqnet-session', JSON.stringify(next)); setSession(next) }
  const logout = () => { localStorage.removeItem('resqnet-session'); setSession(null) }
  if (checking) return <div className="loading-screen">Loading your secure workspace…</div>
  return <Routes><Route path="/" element={session ? <Dashboard session={session} logout={logout} /> : <Landing />} /><Route path="/login" element={session ? <Navigate to="/" /> : <AuthPage onAuth={save} />} /><Route path="/register" element={session ? <Navigate to="/" /> : <AuthPage onAuth={save} register />} /><Route path="*" element={<Navigate to="/" />} /></Routes>
}
function Landing() { return <main className="landing"><nav className="topbar"><div className="brand"><span className="brand-mark"><PawPrint size={21}/></span>ResQNet</div><div className="nav-actions"><Link className="link-button" to="/login">Sign in</Link><Link className="button button-dark" to="/register">Get started <ArrowRight size={16}/></Link></div></nav><section className="hero"><div className="hero-copy"><div className="eyebrow"><span className="pulse-dot"/> ANIMAL EMERGENCY COORDINATION</div><h1>Every report deserves<br/><em>a response.</em></h1><p className="hero-text">A coordinated rescue network that connects citizens, responders and animal welfare organizations — with accountability at every step.</p><div className="hero-actions"><Link className="button button-primary" to="/register">Report an emergency <ArrowRight size={17}/></Link><Link className="button button-light" to="/login">Open dashboard</Link></div><div className="hero-proof"><ShieldCheck size={17}/> Human-reviewed. Accountable. Built for action.</div></div><div className="hero-visual"><div className="orbit orbit-one"/><div className="orbit orbit-two"/><div className="rescue-card"><div className="rescue-card-top"><span className="live-tag"><i/> LIVE WORKFLOW</span><span className="case-number">RQ- DEMO</span></div><div className="animal-icon"><PawPrint size={34}/></div><h3>Rescue starts with a report.</h3><p>One accountable case. One clear next step.</p><div className="mini-steps"><span className="step-done">Report</span><span className="step-active">Assign</span><span>Verify</span></div><div className="card-foot"><span><span className="avatar-dot"/> Response network</span><b>Connected</b></div></div><div className="floating-note"><span className="note-icon"><Activity size={17}/></span><span><b>Reliability first</b><small>Deadlines. Escalations. Proof.</small></span></div></div></section><section className="feature-strip"><div><b>01</b><span><strong>Report</strong><small>Simple, accessible intake</small></span></div><div><b>02</b><span><strong>Prioritize</strong><small>Explainable emergency triage</small></span></div><div><b>03</b><span><strong>Assign</strong><small>Eligible responder matching</small></span></div><div><b>04</b><span><strong>Verify</strong><small>Evidence-backed outcomes</small></span></div></section><footer>ResQNet · Report. Prioritize. Assign. Rescue. Verify. <span>Development demonstration · No live rescue network connected</span></footer></main> }
function AuthPage({ onAuth, register = false }: { onAuth: (session: Session) => void; register?: boolean }) {
  const [name, setName] = useState(''); const [email, setEmail] = useState(''); const [password, setPassword] = useState(''); const [role, setRole] = useState<'citizen'|'rescuer'>('citizen'); const [error, setError] = useState(''); const [busy, setBusy] = useState(false); const navigate = useNavigate()
  const submit = async (event: FormEvent) => { event.preventDefault(); setBusy(true); setError(''); try { const result = register ? await api.register({ full_name: name, email, password, role }) : await api.login(email, password); onAuth({ token: result.access_token, user: result.user }); navigate('/') } catch (e) { setError(e instanceof Error ? e.message : 'Unable to authenticate') } finally { setBusy(false) } }
  const demoLogin = async (account: typeof demoAccounts[number]) => { setEmail(account.email); setPassword(DEMO_PASSWORD); setBusy(true); setError(''); try { const result = await api.login(account.email, DEMO_PASSWORD); if (result.user.role !== account.role) throw new Error('The demo account has an unexpected role. Please reseed the demo accounts.'); onAuth({ token: result.access_token, user: result.user }); navigate('/') } catch (e) { setError(e instanceof ApiError && e.status === 401 ? 'Demo login failed. Please verify the demo account.' : e instanceof Error ? e.message : 'Unable to authenticate') } finally { setBusy(false) } }
  return <main className="auth-layout"><section className="auth-aside"><Link to="/" className="brand brand-light"><span className="brand-mark"><PawPrint size={21}/></span>ResQNet</Link><div><div className="eyebrow eyebrow-light">A MORE ACCOUNTABLE WAY TO RESCUE</div><h1>From first report<br/>to verified care.</h1><p>One shared picture of every emergency, with clear ownership and no silent handoffs.</p></div><small>DEVELOPMENT ENVIRONMENT · SYNTHETIC DEMO ACCOUNTS</small></section><section className="auth-main"><div className="auth-box"><Link to="/" className="back-link">← Back to home</Link><h2>{register ? 'Create your account' : 'Welcome back'}</h2><p className="muted">{register ? 'Join the ResQNet response community.' : 'Sign in to your ResQNet workspace.'}</p><form onSubmit={submit}>{register && <label>Full name<input required minLength={2} value={name} onChange={e=>setName(e.target.value)} placeholder="Your name"/></label>}<label>Email address<input required type="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="you@example.com"/></label><label>Password<input required minLength={10} type="password" value={password} onChange={e=>setPassword(e.target.value)} placeholder="At least 10 characters"/></label>{register && <label>Account type<select value={role} onChange={e=>setRole(e.target.value as 'citizen'|'rescuer')}><option value="citizen">Citizen</option><option value="rescuer">Rescuer</option></select></label>}{error && <div className="error-box">{error}</div>}<button className="button button-primary full-width" disabled={busy}>{busy ? 'Please wait…' : register ? 'Create account' : 'Sign in'} <ArrowRight size={16}/></button></form>{!register && <div className="demo-panel"><div className="demo-title"><span>DEMO ACCESS</span><small>All passwords: {DEMO_PASSWORD}</small></div><div className="demo-grid">{demoAccounts.map(account=><button key={`${account.role}-${account.email}`} disabled={busy} onClick={()=>demoLogin(account)}>{account.label}<ArrowRight size={14}/></button>)}</div></div>}<p className="switch-auth">{register ? 'Already have an account?' : 'New to ResQNet?'} <Link to={register ? '/login' : '/register'}>{register ? 'Sign in' : 'Create account'}</Link></p></div></section></main>
}

// ── Notifications Bell ─────────────────────────────────────────────────────
function NotificationBell({ token }: { token: string }) {
  const [unread, setUnread] = useState(0)
  const [open, setOpen] = useState(false)
  const [notifs, setNotifs] = useState<Notification[]>([])
  const [loading, setLoading] = useState(false)

  const fetchCount = () => {
    notifApi.count(token).then(r => setUnread(r.unread)).catch(() => {})
  }

  useEffect(() => {
    fetchCount()
    const id = setInterval(fetchCount, 30000)
    return () => clearInterval(id)
  }, [token])

  const openPanel = async () => {
    setOpen(o => !o)
    if (!open) {
      setLoading(true)
      try { const list = await notifApi.list(token); setNotifs(list) }
      catch { /* ignore */ }
      finally { setLoading(false) }
    }
  }

  const markRead = async (id: string) => {
    try {
      await notifApi.markRead(token, id)
      setNotifs(n => n.map(x => x.id === id ? { ...x, is_read: true } : x))
      setUnread(u => Math.max(0, u - 1))
    } catch { /* ignore */ }
  }

  const markAllRead = async () => {
    const unreadItems = notifs.filter(n => !n.is_read)
    for (const n of unreadItems) await markRead(n.id)
  }

  return (
    <div className="notif-wrapper">
      <button className="notif-bell" onClick={openPanel} title="Notifications">
        <Bell size={18}/>
        {unread > 0 && <span className="notif-badge">{unread > 99 ? '99+' : unread}</span>}
      </button>
      {open && (
        <div className="notif-panel">
          <div className="notif-panel-header">
            <b>Notifications</b>
            {notifs.some(n => !n.is_read) && <button className="link-btn" onClick={markAllRead}>Mark all read</button>}
          </div>
          {loading ? (
            <div className="notif-loading">Loading…</div>
          ) : notifs.length === 0 ? (
            <div className="notif-empty"><Bell size={22}/><span>No notifications</span></div>
          ) : (
            <div className="notif-list">
              {notifs.map(n => (
                <div key={n.id} className={`notif-item${n.is_read ? '' : ' notif-unread'}`}>
                  <div className="notif-item-content">
                    <b>{n.title}</b>
                    <span>{n.body}</span>
                    <small>{new Date(n.created_at).toLocaleString()}{n.case_id ? ` · ${n.case_id}` : ''}</small>
                  </div>
                  {!n.is_read && <button className="notif-read-btn" onClick={() => markRead(n.id)}>✓</button>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── AI Extraction Panel ────────────────────────────────────────────────────
function AiPanel({
  token, description, onApply, onDismiss
}: {
  token: string; description: string;
  onApply: (ex: IncidentExtraction) => void; onDismiss: () => void
}) {
  const [result, setResult] = useState<IncidentExtraction | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const analyze = async () => {
    if (!description.trim()) { setError('Enter a description first.'); return }
    setLoading(true); setError(''); setResult(null)
    try { const r = await aiApi.extract(token, description); setResult(r) }
    catch (e) { setError(e instanceof Error ? e.message : 'AI extraction failed') }
    finally { setLoading(false) }
  }

  useEffect(() => { analyze() }, [])

  if (error) return <div className="ai-panel ai-panel-error"><AlertTriangle size={15}/> {error} <button className="link-btn" onClick={onDismiss}>Dismiss</button></div>
  if (loading) return <div className="ai-panel ai-panel-loading">✨ Analyzing description…</div>
  if (!result) return null

  const pct = Math.round(result.confidence_score * 100)
  return (
    <div className="ai-panel">
      <div className="ai-panel-header">
        <span className="ai-badge">✨ {result.source === 'gemini' ? 'AI-powered' : 'Smart detection'}</span>
        <button className="link-btn" onClick={onDismiss}>Dismiss</button>
      </div>
      <div className="ai-fields">
        <div><small>Animal detected</small><b>{result.animal_category}</b></div>
        <div><small>Suggested priority</small><b className={`priority priority-${result.suggested_priority.toLowerCase()}`}>{result.suggested_priority}</b></div>
        <div><small>Urgency</small><b>{result.urgency_level}</b></div>
        {result.num_animals !== null && <div><small>Count</small><b>{result.num_animals}</b></div>}
      </div>
      <div className="confidence-bar-wrap">
        <small>Confidence: {pct}%</small>
        <div className="confidence-bar"><div className="confidence-fill" style={{ width: `${pct}%` }}/></div>
      </div>
      {result.explanation && <p className="ai-explanation">{result.explanation}</p>}
      {result.missing_info.length > 0 && (
        <div className="ai-missing">
          <small>Missing info:</small>
          <ul>{result.missing_info.map((m, i) => <li key={i}>{m}</li>)}</ul>
        </div>
      )}
      {result.needs_human_review && <div className="ai-review-warn"><AlertTriangle size={12}/> Needs human review</div>}
      <button className="button button-light" style={{ marginTop: 10, fontSize: 11 }} onClick={() => onApply(result)}>Apply suggestion</button>
    </div>
  )
}

// ── Voice Recording Panel ──────────────────────────────────────────────────
function VoicePanel({ token, casePublicId }: { token: string; casePublicId?: string }) {
  const [supported] = useState(() => typeof MediaRecorder !== 'undefined')
  const [recording, setRecording] = useState(false)
  const [chunks, setChunks] = useState<Blob[]>([])
  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const [duration, setDuration] = useState(0)
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState(''); const [transcript,setTranscript]=useState(''); const [savingTranscript,setSavingTranscript]=useState(false)
  const recRef = useRef<MediaRecorder | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  if (!supported) return <div className="voice-panel voice-unsupported"><Mic size={16}/> Voice recording requires a modern browser</div>

  const start = async () => {
    setChunks([]); setAudioUrl(null); setUploadMsg(''); setTranscript('')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mr = new MediaRecorder(stream)
      const buf: Blob[] = []
      mr.ondataavailable = e => { if (e.data.size > 0) buf.push(e.data) }
      mr.onstop = () => {
        const blob = new Blob(buf, { type: 'audio/webm' })
        setChunks(buf)
        setAudioUrl(URL.createObjectURL(blob))
        stream.getTracks().forEach(t => t.stop())
      }
      mr.start()
      recRef.current = mr
      setRecording(true)
      setDuration(0)
      timerRef.current = setInterval(() => setDuration(d => d + 1), 1000)
    } catch { setUploadMsg('Microphone access denied.') }
  }

  const stop = () => {
    recRef.current?.stop()
    if (timerRef.current) clearInterval(timerRef.current)
    setRecording(false)
  }

  const upload = async () => {
    if (!chunks.length || !casePublicId) { setUploadMsg('Submit the case first to get a case ID.'); return }
    setUploading(true); setUploadMsg('')
    try {
      const blob = new Blob(chunks, { type: 'audio/webm' })
      const fd = new FormData(); fd.append('audio', blob, 'voice-report.webm')
      const result = await api.uploadAudioReport(token, casePublicId, fd)
      if(result.transcription)setTranscript(result.transcription); setUploadMsg(result.transcription ? 'Transcription is ready for your review.' : (result.note || 'Audio saved. Transcription is not configured; please enter the report description manually.'))
    } catch (e) { setUploadMsg(e instanceof Error ? e.message : 'Upload failed') }
    finally { setUploading(false) }
  }

  const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

  return (
    <div className="voice-panel">
      <div className="voice-panel-header"><Mic size={15}/> Voice report (optional enhancement)</div>
      <div className="voice-controls">
        {!recording ? (
          <button type="button" className="button button-light" onClick={start}><Mic size={14}/> Start recording</button>
        ) : (
          <button type="button" className="button button-primary" onClick={stop}><MicOff size={14}/> Stop ({fmt(duration)})</button>
        )}
        {recording && <span className="voice-rec-dot">● REC {fmt(duration)}</span>}
      </div>
      {audioUrl && (
        <div className="voice-preview">
          <audio controls src={audioUrl}/>
          <button type="button" className="button button-light" disabled={uploading} onClick={upload}>
            {uploading ? 'Uploading…' : 'Upload voice report'}
          </button>
        </div>
      )}
      {uploadMsg && <div className="success-box" style={{ marginTop: 8 }}>{uploadMsg}</div>}
      {transcript && <div style={{marginTop:10}}><label>Review transcription before adding it to your report<textarea value={transcript} onChange={e=>setTranscript(e.target.value)} rows={4}/></label><button type="button" className="button button-primary" disabled={savingTranscript||transcript.trim().length<5} onClick={async()=>{if(!casePublicId)return;setSavingTranscript(true);try{await aiApi.saveVoiceTranscript(token,casePublicId,transcript);setUploadMsg('Reporter-confirmed transcript added to the case.');setTranscript('')}catch(e){setUploadMsg(e instanceof Error?e.message:'Could not save transcript')}finally{setSavingTranscript(false)}}}>{savingTranscript?'Saving…':'Add confirmed transcript to case'}</button></div>}
    </div>
  )
}

// ── Evidence Submission Panel ──────────────────────────────────────────────
function EvidencePanel({ token, publicId, onDone }: { token: string; publicId: string; onDone: () => void }) {
  const [list, setList] = useState<Evidence[]>([])
  const [open, setOpen] = useState(false)
  const [evType, setEvType] = useState('after_photo')
  const [file, setFile] = useState<File | null>(null)
  const [notes, setNotes] = useState('')
  const [condition, setCondition] = useState('')
  const [dest, setDest] = useState('')
  const [handover, setHandover] = useState('')
  const [gpsLat, setGpsLat] = useState('')
  const [gpsLon, setGpsLon] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const loadList = () => evidenceApi.list(token, publicId).then(setList).catch(() => {})
  useEffect(() => { loadList() }, [publicId])

  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setErr(''); setMsg('')
    try {
      const fd = new FormData()
      fd.append('evidence_type', evType)
      if (file) fd.append('file', file)
      if (notes) fd.append('rescue_notes', notes)
      if (condition) fd.append('animal_condition', condition)
      if (dest) fd.append('destination', dest)
      if (handover) fd.append('handover_details', handover)
      if (gpsLat) fd.append('gps_lat', gpsLat)
      if (gpsLon) fd.append('gps_lon', gpsLon)
      await evidenceApi.submit(token, publicId, fd)
      setMsg('Evidence submitted!'); setOpen(false); setFile(null); setNotes(''); setCondition(''); setDest(''); setHandover('')
      await loadList(); onDone()
    } catch (e) { setErr(e instanceof Error ? e.message : 'Submission failed') }
    finally { setBusy(false) }
  }

  return (
    <div className="evidence-panel">
      <div className="evidence-panel-header">
        <h3>Evidence</h3>
        <button className="button button-light" style={{ fontSize: 10, padding: '6px 10px' }} onClick={() => { setOpen(o => !o); setMsg(''); setErr('') }}>
          {open ? 'Cancel' : 'Submit Evidence'}
        </button>
      </div>
      {msg && <div className="success-box" style={{ marginBottom: 10 }}>{msg}</div>}
      {err && <div className="error-box" style={{ marginBottom: 10 }}>{err}</div>}
      {open && (
        <form className="evidence-form" onSubmit={submit}>
          <label>Evidence type<select value={evType} onChange={e => setEvType(e.target.value)}>
            <option value="before_photo">Before photo</option>
            <option value="after_photo">After photo</option>
            <option value="note">Note</option>
            <option value="video">Video</option>
          </select></label>
          <label>File (images, max 10 MB)<input type="file" accept="image/*,video/*" onChange={e => setFile(e.target.files?.[0] ?? null)}/></label>
          <label>Rescue notes<textarea value={notes} onChange={e => setNotes(e.target.value)} placeholder="What happened during rescue…"/></label>
          <label>Animal condition<textarea value={condition} onChange={e => setCondition(e.target.value)} placeholder="Injuries, behaviour, treatment given…"/></label>
          <label>Destination / shelter<input value={dest} onChange={e => setDest(e.target.value)} placeholder="Where the animal was taken"/></label>
          <label>Handover details<input value={handover} onChange={e => setHandover(e.target.value)} placeholder="Who received the animal"/></label>
          <div className="form-grid" style={{ marginTop: 0 }}>
            <label>GPS latitude (optional)<input type="number" step="any" value={gpsLat} onChange={e => setGpsLat(e.target.value)}/></label>
            <label>GPS longitude (optional)<input type="number" step="any" value={gpsLon} onChange={e => setGpsLon(e.target.value)}/></label>
          </div>
          <button className="button button-primary" disabled={busy}>{busy ? 'Submitting…' : 'Submit evidence'}</button>
        </form>
      )}
      {list.length > 0 && (
        <div className="evidence-list">
          {list.map(ev => (
            <div key={ev.id} className="evidence-item">
              <div className="evidence-type">{ev.evidence_type.replace('_', ' ')}</div>
              {ev.rescue_notes && <p><b>Notes:</b> {ev.rescue_notes}</p>}
              {ev.animal_condition && <p><b>Condition:</b> {ev.animal_condition}</p>}
              {ev.destination && <p><b>Destination:</b> {ev.destination}</p>}
              {ev.has_file && <div><small>File: {ev.mime_type ?? 'attached'} · {ev.file_size ? `${Math.round(ev.file_size / 1024)} KB` : ''}</small> <button type="button" className="button button-light" style={{fontSize:10,padding:'5px 9px'}} onClick={async()=>{try{const blob=await evidenceApi.download(token,publicId,ev.id);const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=ev.id;a.click();URL.revokeObjectURL(url)}catch(e){setErr(e instanceof Error?e.message:'Download failed')}}}>Download file</button></div>}
              <small>{new Date(ev.created_at).toLocaleString()}</small>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Progress Controls ──────────────────────────────────────────────────────
function ProgressControls({ token, item, onProgress }: { token: string; item: RescueCase; onProgress: () => void }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const advance = async (status: string) => {
    setBusy(true); setErr('')
    try {
      // Try new progressExtApi first, fall back to old progressApi
      if (status === 'IN_PROGRESS' || status === 'ON_SCENE') {
        await progressApi.update(token, item.public_id, status as 'IN_PROGRESS' | 'ON_SCENE')
      } else {
        await progressExtApi.update(token, item.public_id, status)
      }
      onProgress()
    } catch (e) { setErr(e instanceof Error ? e.message : 'Update failed') }
    finally { setBusy(false) }
  }

  const statusButtons: Record<string, { label: string; next: string }> = {
    ASSIGNED: { label: '🚗 Mark En Route', next: 'EN_ROUTE' },
    EN_ROUTE: { label: '📍 Mark Arrived', next: 'ARRIVED' },
    ARRIVED: { label: '🚑 Start Rescue', next: 'RESCUE_IN_PROGRESS' },
    RESCUE_IN_PROGRESS: { label: '✅ Mark Rescued', next: 'RESCUED' },
    IN_PROGRESS: { label: '📍 Mark Arrival at Scene', next: 'ON_SCENE' },
    ON_SCENE: { label: '✅ Mark Rescued', next: 'RESCUED' },
  }

  const btn = statusButtons[item.status]
  if (!btn) return null

  return (
    <div className="progress-controls">
      <div className="progress-status">Status: <b>{item.status.replaceAll('_', ' ')}</b></div>
      {err && <div className="error-box" style={{ marginBottom: 8 }}>{err}</div>}
      <button className="button button-primary" disabled={busy} onClick={() => advance(btn.next)}>
        {busy ? 'Updating…' : btn.label}
      </button>
    </div>
  )
}

// ── Coordinator Verification Panel ────────────────────────────────────────
function VerifyPanel({ token, publicId, evidence, onDone }: { token: string; publicId: string; evidence: Evidence[]; onDone: () => void }) {
  const [open, setOpen] = useState(false)
  const [decision, setDecision] = useState<'approve' | 'reject' | 'request_more'>('approve')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (reason.trim().length < 5) { setErr('Reason must be at least 5 characters.'); return }
    setBusy(true); setErr(''); setMsg('')
    try {
      await evidenceApi.verify(token, publicId, decision, reason)
      setMsg(`Decision recorded: ${decision}`); setOpen(false); onDone()
    } catch (e) { setErr(e instanceof Error ? e.message : 'Verification failed') }
    finally { setBusy(false) }
  }

  return (
    <div className="verify-panel">
      {!open ? (
        <button className="button button-primary" onClick={() => { setOpen(true); setMsg(''); setErr('') }}>
          <CheckCircle size={14}/> Verify Rescue
        </button>
      ) : (
        <form onSubmit={submit}>
          <b style={{ fontSize: 11 }}>Evidence ({evidence.length} items)</b>
          {evidence.length > 0 && (
            <div className="evidence-list" style={{ marginBottom: 10 }}>
              {evidence.map(ev => (
                <div key={ev.id} className="evidence-item">
                  <div className="evidence-type">{ev.evidence_type.replace('_', ' ')}</div>
                  {ev.rescue_notes && <p>{ev.rescue_notes}</p>}
                  {ev.animal_condition && <small>Condition: {ev.animal_condition}</small>}
                  {ev.has_file && <small>File attached · {ev.mime_type}</small>}
                </div>
              ))}
            </div>
          )}
          <div className="verify-decisions">
            {(['approve', 'reject', 'request_more'] as const).map(d => (
              <button key={d} type="button"
                className={`verify-decision-btn${decision === d ? ' selected' : ''}`}
                onClick={() => setDecision(d)}>
                {d === 'approve' && <><CheckCircle size={13}/> Approve</>}
                {d === 'reject' && <><XCircle size={13}/> Reject</>}
                {d === 'request_more' && <>📋 Request More</>}
              </button>
            ))}
          </div>
          <label style={{ display: 'grid', gap: 5, fontSize: 10, fontWeight: 700, color: '#52675a', marginTop: 10 }}>
            Reason (required)
            <textarea minLength={5} required value={reason} onChange={e => setReason(e.target.value)}
              placeholder="Explain your decision…"
              style={{ border: '1px solid #dfe7df', borderRadius: 8, padding: 10, fontFamily: 'inherit', minHeight: 80, resize: 'vertical' }}
            />
          </label>
          {err && <div className="error-box" style={{ marginTop: 8 }}>{err}</div>}
          <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
            <button className="button button-primary" disabled={busy || reason.trim().length < 5}>
              {busy ? 'Saving…' : 'Confirm'}
            </button>
            <button type="button" className="button button-light" onClick={() => setOpen(false)}>Cancel</button>
          </div>
        </form>
      )}
      {msg && <div className="success-box" style={{ marginTop: 8 }}>{msg}<button onClick={() => setMsg('')}>Dismiss</button></div>}
    </div>
  )
}

// ── Close Case Panel ───────────────────────────────────────────────────────
function CloseCase({ token, publicId, onDone }: { token: string; publicId: string; onDone: () => void }) {
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setErr('')
    try { await evidenceApi.close(token, publicId, reason); setOpen(false); onDone() }
    catch (e) { setErr(e instanceof Error ? e.message : 'Close failed') }
    finally { setBusy(false) }
  }

  if (!open) return <button className="button button-light" style={{ fontSize: 11, marginTop: 8 }} onClick={() => setOpen(true)}>Close Case</button>
  return (
    <form onSubmit={submit} style={{ marginTop: 10 }}>
      <label style={{ display: 'grid', gap: 5, fontSize: 10, fontWeight: 700, color: '#52675a' }}>
        Close reason
        <input required minLength={3} value={reason} onChange={e => setReason(e.target.value)} placeholder="Reason for closing…"
          style={{ border: '1px solid #dfe7df', borderRadius: 8, padding: '10px 12px', fontFamily: 'inherit' }}/>
      </label>
      {err && <div className="error-box" style={{ marginTop: 6 }}>{err}</div>}
      <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
        <button className="button button-primary" disabled={busy}>{busy ? 'Closing…' : 'Confirm close'}</button>
        <button type="button" className="button button-light" onClick={() => setOpen(false)}>Cancel</button>
      </div>
    </form>
  )
}

// ── Analytics Dashboard ────────────────────────────────────────────────────
function AnalyticsDashboard({ token }: { token: string }) {
  const [data, setData] = useState<AnalyticsSummary | null>(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')

  const load = async () => {
    setLoading(true); setErr('')
    try { setData(await analyticsApi.summary(token)) }
    catch (e) { setErr(e instanceof Error ? e.message : 'Failed to load analytics') }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [token])

  const priorityColors: Record<string, string> = { CRITICAL: '#b74332', HIGH: '#a65b18', MEDIUM: '#90721d', LOW: '#43805b', NEEDS_REVIEW: '#7165a0' }
  const statusColors: Record<string, string> = { OPEN: '#176344', TRIAGED: '#3d6fbe', ASSIGNED: '#a65b18', RESCUED: '#43805b', VERIFIED: '#286a49', CANCELLED: '#7c8980', CLOSED: '#567264' }

  const BarChart = ({ data: d, colors }: { data: Record<string, number>; colors: Record<string, string> }) => {
    const max = Math.max(...Object.values(d), 1)
    return (
      <div className="analytics-bar-chart">
        {Object.entries(d).map(([k, v]) => (
          <div key={k} className="analytics-bar">
            <div className="analytics-bar-label">{k.replace('_', ' ')}</div>
            <div className="analytics-bar-track">
              <div className="analytics-bar-fill" style={{ width: `${(v / max) * 100}%`, background: colors[k] ?? '#176344' }}/>
            </div>
            <div className="analytics-bar-count">{v}</div>
          </div>
        ))}
      </div>
    )
  }

  return (
    <section className="report-panel">
      <div className="section-heading">
        <div><h2><BarChart2 size={17}/> Analytics</h2><p>{data?.data_label ?? 'Live database records'}</p></div>
        <button className="refresh-button" onClick={load} disabled={loading}><RefreshCw size={14}/> Refresh</button>
      </div>
      {err && <div className="error-box">{err}</div>}
      {loading && <div style={{ color: '#567264', fontSize: 12 }}>Loading analytics…</div>}
      {data && (
        <>
          <div className="metric-grid" style={{ marginBottom: 20 }}>
            <div className="metric-card"><div className="metric-top"><span>Total cases</span><i><Activity/></i></div><strong>{data.total_cases}</strong><small>All time</small></div>
            <div className="metric-card"><div className="metric-top"><span>Verified rescues</span><i><CheckCircle/></i></div><strong>{data.verified_rescues}</strong><small>Confirmed outcomes</small></div>
            <div className="metric-card"><div className="metric-top"><span>Completion rate</span><i><ShieldCheck/></i></div><strong>{data.completion_rate_pct.toFixed(1)}%</strong><small>Verified / total</small></div>
          </div>
          <h3 style={{ font: '800 13px Manrope', color: '#385442', margin: '0 0 10px' }}>By priority</h3>
          <BarChart data={data.by_priority} colors={priorityColors}/>
          <h3 style={{ font: '800 13px Manrope', color: '#385442', margin: '16px 0 10px' }}>By status</h3>
          <BarChart data={data.by_status} colors={statusColors}/>
          <h3 style={{ font: '800 13px Manrope', color: '#385442', margin: '16px 0 10px' }}>By animal category</h3>
          <BarChart data={data.by_category} colors={{}}/>
        </>
      )}
    </section>
  )
}

function Dashboard({ session, logout }: { session: Session; logout: () => void }) {
  const [summary, setSummary] = useState<{total_cases:number;open_cases:number;available_responders:number;data_label:string}|null>(null)
  const [cases, setCases] = useState<RescueCase[]>([]); const [selected, setSelected] = useState<RescueCase|null>(null); const [offers,setOffers]=useState<AssignmentOffer[]>([])
  const [error,setError]=useState(''); const [notice,setNotice]=useState('')
  const [activeTab, setActiveTab] = useState<'overview' | 'analytics' | 'map' | 'handoffs' | 'admin'>('overview')
  const canManage = session.user.role === 'coordinator' || session.user.role === 'admin'
  const refresh = async () => { const s = await api.summary(session.token); setSummary(s); const c = await caseApi.list(session.token); setCases(c); if(session.user.role==='rescuer') setOffers(await responderApi.offers(session.token)); if(selected) setSelected(c.find(x=>x.public_id===selected.public_id) ?? selected) }
  useEffect(()=>{refresh().catch(e=>setError(e.message))},[session.token])
  const roleTitle: Record<UserRole,string> = { citizen:'Citizen workspace', rescuer:'Responder workspace', coordinator:'NGO operations', admin:'Administration' }
  const created = async (item: RescueCase) => { setNotice(`Report submitted. Your case ID is ${item.public_id}.`); await refresh(); const latest = await caseApi.get(session.token, item.public_id); setSelected(latest) }
  const triaged = async (item: RescueCase) => { setNotice(`Case ${item.public_id} moved to TRIAGED.`); await refresh(); setSelected(item) }
  return <div className="dashboard-shell"><aside className="sidebar"><Link to="/" className="brand"><span className="brand-mark"><PawPrint size={21}/></span>ResQNet</Link><div className="workspace-label">WORKSPACE</div><div className={`side-link${activeTab==='overview'?' active':''}`} onClick={()=>setActiveTab('overview')}><LayoutDashboard size={17}/> Overview</div><div className={`side-link${activeTab==='overview'?' active':''}`} onClick={()=>setActiveTab('overview')}><HeartHandshake size={17}/> Emergency cases</div><div className={`side-link${activeTab==='map'?' active':''}`} onClick={()=>setActiveTab('map')}><MapPin size={17}/> Incident map</div>{canManage&&<div className={`side-link${activeTab==='handoffs'?' active':''}`} onClick={()=>setActiveTab('handoffs')}><Users size={17}/> NGO handoffs</div>}{canManage&&<div className={`side-link${activeTab==='analytics'?' active':''}`} onClick={()=>setActiveTab('analytics')}><BarChart2 size={17}/> Analytics</div>}{session.user.role==='admin'&&<div className={`side-link${activeTab==='admin'?' active':''}`} onClick={()=>setActiveTab('admin')}><ShieldCheck size={17}/> Administration</div>}<div className="sidebar-bottom"><div className="user-avatar">{session.user.full_name.slice(0,1).toUpperCase()}</div><div className="user-meta"><b>{session.user.full_name}</b><small>{session.user.role}</small></div><button className="icon-button" onClick={logout} title="Sign out"><LogOut size={17}/></button></div></aside><main className="dashboard-main"><header className="dash-header"><div><div className="eyebrow">RESQNET OPERATIONS</div><h1>{roleTitle[session.user.role]}</h1><p>Good to see you, {session.user.full_name.split(' ')[0]}.</p></div><div style={{ display: 'flex', alignItems: 'center', gap: 12 }}><NotificationBell token={session.token}/><div className="profile-chip"><span className="status-dot"/> Development mode</div></div></header>{error && <div className="error-box">{error}</div>}{notice && <div className="success-box">{notice}<button onClick={()=>setNotice('')}>Dismiss</button></div>}

  {activeTab === 'analytics' && canManage ? (
    <AnalyticsDashboard token={session.token}/>
  ) : activeTab === 'map' ? (
    <IncidentMap cases={cases}/>
  ) : activeTab === 'handoffs' && canManage ? (
    <HandoffWorkspace token={session.token} cases={cases} onChanged={()=>refresh().catch(e=>setError(e.message))}/>
  ) : activeTab === 'admin' && session.user.role === 'admin' ? (
    <AdminWorkspace token={session.token}/>
  ) : (
    <>
      <div className="welcome-banner"><div><span className="banner-label">YOUR ROLE · {session.user.role.toUpperCase()}</span><h2>Every case has a next step.</h2><p>Reports are stored in the database. Priority suggestions are rule-based and require human review.</p></div><div className="banner-icon"><HeartHandshake size={42}/></div></div><div className="section-heading"><div><h2>Operational snapshot</h2><p>Counts are read from the connected database.</p></div><button className="refresh-button" onClick={()=>refresh().catch(e=>setError(e.message))}><RefreshCw size={14}/> Refresh</button></div><div className="metric-grid"><Metric label="Total cases" value={summary?.total_cases} icon={<Activity/>}/><Metric label="Open cases" value={summary?.open_cases} icon={<HeartHandshake/>}/><Metric label="Available responders" value={summary?.available_responders} icon={<Users/>}/></div>
      {session.user.role==='citizen' && <ReportForm token={session.token} onCreated={created}/>}
      {session.user.role==='rescuer' && <ResponderWorkspace token={session.token} offers={offers} onChanged={()=>refresh().catch(e=>setError(e.message))} />}
      <section className="case-section"><div className="section-heading"><div><h2>{canManage?'Incoming emergency reports':session.user.role==='rescuer'?'Your accepted rescue cases':'Your reported emergencies'}</h2><p>{canManage?'Review reports, check duplicate suggestions and record triage decisions.':session.user.role==='rescuer'?'Only cases offered to or accepted by you appear here.':'Track the status and updates of reports you submitted.'}</p></div><span className="live-label"><i/> DATABASE</span></div>{cases.length===0?<div className="empty-state"><PawPrint size={28}/><b>No cases yet</b><span>New emergency reports will appear here.</span></div>:<div className="case-list">{cases.map(item=><button key={item.id} className={`case-row ${selected?.id===item.id?'case-selected':''}`} onClick={()=>setSelected(item)}><div className="case-row-icon"><PawPrint size={18}/></div><div className="case-row-main"><b>{item.public_id} · {item.animal_category}</b><span>{item.description}</span><small><Clock3 size={12}/> {new Date(item.created_at).toLocaleString()} · {item.landmark || item.address_text || 'Location not provided'}</small></div><div className="case-row-meta"><span className={`priority priority-${item.priority.toLowerCase()}`}>{item.priority.replace('_',' ')}</span><small>{item.status.replaceAll('_',' ')}</small></div></button>)}</div>}</section>
      {selected && <CaseDetails item={selected} canManage={canManage} token={session.token} onTriage={triaged} canRespond={session.user.role==='rescuer'} onProgress={()=>refresh().catch(e=>setError(e.message))} onAssigned={()=>{setNotice('Assignment offer sent to the top eligible responder.');refresh().catch(e=>setError(e.message))}} onClose={()=>setSelected(null)}/>}
      <div className="demo-warning">Synthetic development environment · No live NGO, responder availability or rescue outcome is connected.</div>
    </>
  )}
  </main></div>
}
function IncidentMap({cases}:{cases:RescueCase[]}) {
  const host = useRef<HTMLDivElement|null>(null)
  const [ready,setReady] = useState(false)
  const [mapError,setMapError] = useState('')
  useEffect(()=>{
    let map:any; let disposed=false
    const load=()=>{
      if(disposed||!host.current||!window.L)return
      const L=window.L
      map=L.map(host.current).setView([11.6643,78.1460],11)
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap contributors'}).addTo(map)
      const points=cases.filter(c=>typeof c.latitude==='number'&&typeof c.longitude==='number')
      points.forEach(c=>{const popup=document.createElement('div');popup.textContent=`${c.public_id} · ${c.animal_category} · ${c.status.replaceAll('_',' ')} · ${c.priority}`;L.marker([c.latitude,c.longitude]).addTo(map).bindPopup(popup)})
      if(points.length){const bounds=L.latLngBounds(points.map(c=>[c.latitude,c.longitude]));map.fitBounds(bounds,{padding:[30,30],maxZoom:14})}
      setReady(true)
    }
    if(!document.querySelector('link[data-leaflet]')){const link=document.createElement('link');link.rel='stylesheet';link.href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';link.dataset.leaflet='true';document.head.appendChild(link)}
    if(window.L){load()}else{
      let script=document.querySelector<HTMLScriptElement>('script[data-leaflet]')
      if(!script){script=document.createElement('script');script.src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';script.dataset.leaflet='true';document.body.appendChild(script)}
      script.addEventListener('load',load);script.addEventListener('error',()=>setMapError('Map library could not be loaded. Check your internet connection.'))
    }
    return ()=>{disposed=true;if(map)map.remove()}
  },[cases])
  return <section className="case-section"><div className="section-heading"><div><h2>Incident map</h2><p>Only cases visible to your signed-in role are shown. Cases without coordinates appear in the list below.</p></div><span className="live-label">OPENSTREETMAP</span></div><div ref={host} style={{height:440,width:'100%',borderRadius:16,overflow:'hidden',background:'#e8eee8'}}/>{mapError&&<div className="error-box">{mapError}</div>}{!ready&&<p className="muted">Loading map…</p>}<div className="case-list" style={{marginTop:14}}>{cases.filter(c=>c.latitude===null||c.longitude===null).map(c=><div className="case-row" key={c.id}><MapPin size={16}/><div className="case-row-main"><b>{c.public_id}</b><span>{c.landmark||c.address_text||'No coordinates supplied'}</span></div></div>)}</div><p className="muted" style={{fontSize:11}}>Map tiles are provided by OpenStreetMap. Location visibility follows the cases returned by the API.</p></section>
}

function HandoffWorkspace({token,cases,onChanged}:{token:string;cases:RescueCase[];onChanged:()=>void}) {
  const [items,setItems]=useState<Handoff[]>([]);const [orgs,setOrgs]=useState<Organization[]>([]);const [caseId,setCaseId]=useState('');const [target,setTarget]=useState('');const [reason,setReason]=useState('');const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [message,setMessage]=useState('')
  const refresh=async()=>{const [h,o]=await Promise.all([handoffApi.list(token),handoffApi.organizations(token)]);setItems(h);setOrgs(o.filter(x=>x.verified))}
  useEffect(()=>{refresh().catch(e=>setError(e.message))},[token])
  const submit=async(e:FormEvent)=>{e.preventDefault();setBusy(true);setError('');setMessage('');try{await handoffApi.request(token,caseId,target,reason);setMessage('Handoff request sent. Ownership remains with the current organization until accepted.');setReason('');await refresh();onChanged()}catch(e){setError(e instanceof Error?e.message:'Unable to request handoff')}finally{setBusy(false)}}
  const respond=async(item:Handoff,accept:boolean)=>{setBusy(true);setError('');try{if(accept)await handoffApi.accept(token,item.id);else await handoffApi.decline(token,item.id,'The receiving organization cannot accept this case at this time.');await refresh();onChanged()}catch(e){setError(e instanceof Error?e.message:'Unable to update handoff')}finally{setBusy(false)}}
  const handoffCases=cases.filter(c=>['ASSIGNED','IN_PROGRESS','ON_SCENE','EN_ROUTE','ARRIVED','RESCUE_IN_PROGRESS','RESCUED','VERIFICATION_PENDING'].includes(c.status))
  return <section className="case-section"><div className="section-heading"><div><h2>NGO handoff management</h2><p>Requests transfer ownership only after the receiving organization explicitly accepts.</p></div><span className="live-label">DATABASE WORKFLOW</span></div>{message&&<div className="success-box">{message}</div>}{error&&<div className="error-box">{error}</div>}<form className="triage-form" onSubmit={submit}><b>Request a case handoff</b><label>Case<select required value={caseId} onChange={e=>setCaseId(e.target.value)}><option value="">Select a case</option>{handoffCases.map(c=><option key={c.public_id} value={c.public_id}>{c.public_id} · {c.animal_category} · {c.status}</option>)}</select></label><label>Receiving organization<select required value={target} onChange={e=>setTarget(e.target.value)}><option value="">Select verified organization</option>{orgs.map(o=><option key={o.id} value={o.id}>{o.name} · {o.city}</option>)}</select></label><label>Reason<textarea required minLength={8} value={reason} onChange={e=>setReason(e.target.value)} placeholder="Explain why the receiving NGO is better placed to continue this case"/></label><button className="button button-primary" disabled={busy||!caseId||!target||reason.trim().length<8}>{busy?'Sending…':'Send handoff request'}</button></form><h3 style={{marginTop:24}}>Handoff history and incoming requests</h3>{items.length===0?<div className="empty-state">No handoff requests yet.</div>:items.map(item=><div className="evidence-item" key={item.id}><b>{item.case_public_id||'Case'} · {item.status}</b><p>{item.from_organization} → {item.to_organization}</p><p>{item.reason}</p><small>Deadline: {new Date(item.deadline_at).toLocaleString()}</small>{item.incoming&&item.status==='PENDING'&&<div style={{display:'flex',gap:8,marginTop:10}}><button className="button button-primary" disabled={busy} onClick={()=>respond(item,true)}>Accept handoff</button><button className="button button-light" disabled={busy} onClick={()=>respond(item,false)}>Decline</button></div>}</div>)}</section>
}

declare global { interface Window { L?: any } }

function AdminWorkspace({token}:{token:string}) {
 const [users,setUsers]=useState<User[]>([]);const [orgs,setOrgs]=useState<Organization[]>([]);const [orgName,setOrgName]=useState('');const [fullName,setFullName]=useState('');const [city,setCity]=useState('Salem');const [newEmail,setNewEmail]=useState('');const [newPassword,setNewPassword]=useState('');const [newRole,setNewRole]=useState<'citizen'|'rescuer'|'coordinator'>('coordinator');const [newOrg,setNewOrg]=useState('');const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [message,setMessage]=useState('')
 const refresh=async()=>{const [u,o]=await Promise.all([adminApi.users(token),handoffApi.organizations(token)]);setUsers(u);setOrgs(o)}
 useEffect(()=>{refresh().catch(e=>setError(e.message))},[token])
 const toggle=async(user:User)=>{setBusy(true);setError('');try{await adminApi.setUserStatus(token,user.id,!user.is_active);await refresh()}catch(e){setError(e instanceof Error?e.message:'Could not update user')}finally{setBusy(false)}}
 const create=async(e:FormEvent)=>{e.preventDefault();setBusy(true);setError('');setMessage('');try{await adminApi.createOrganization(token,orgName,city);setOrgName('');setMessage('Organization created. It remains unverified until an administrator verifies it.');await refresh()}catch(e){setError(e instanceof Error?e.message:'Could not create organization')}finally{setBusy(false)}};const createUser=async(e:FormEvent)=>{e.preventDefault();setBusy(true);setError('');setMessage('');try{await adminApi.createUser(token,{full_name:fullName,email:newEmail,password:newPassword,role:newRole,organization_id:newRole==='coordinator'?newOrg:undefined});setFullName('');setNewEmail('');setNewPassword('');setMessage('Account created.');await refresh()}catch(e){setError(e instanceof Error?e.message:'Could not create account')}finally{setBusy(false)}}
 const verify=async(org:Organization)=>{setBusy(true);setError('');try{await adminApi.verifyOrganization(token,org.id,!org.verified);await refresh()}catch(e){setError(e instanceof Error?e.message:'Could not update organization')}finally{setBusy(false)}};const verifyResponder=async(user:User)=>{setBusy(true);setError('');try{await adminApi.setResponderVerification(token,user.id,!user.is_verified);await refresh()}catch(e){setError(e instanceof Error?e.message:'Could not update responder verification')}finally{setBusy(false)}}
 return <section className="case-section"><div className="section-heading"><div><h2>Administration</h2><p>Manage platform accounts and review organization verification.</p></div><span className="live-label">ADMIN ONLY</span></div>{error&&<div className="error-box">{error}</div>}{message&&<div className="success-box">{message}</div>}<h3>Users</h3>{users.map(u=><div className="evidence-item" key={u.id}><b>{u.full_name} · {u.role}</b><p>{u.email} · {u.is_active?'Active':'Disabled'} · {u.is_verified?'Verified':'Unverified'}</p><button className="button button-light" disabled={busy} onClick={()=>toggle(u)}>{u.is_active?'Deactivate':'Activate'}</button>{u.role==='rescuer'&&<button className="button button-light" disabled={busy} onClick={()=>verifyResponder(u)}>{u.is_verified?'Revoke responder verification':'Verify responder'}</button>}</div>)}<form className="triage-form" onSubmit={createUser}><b>Create platform account</b><label>Full name<input required minLength={2} value={fullName} onChange={e=>setFullName(e.target.value)}/></label><label>Email<input required type="email" value={newEmail} onChange={e=>setNewEmail(e.target.value)}/></label><label>Temporary password (10+ characters)<input required minLength={10} type="password" value={newPassword} onChange={e=>setNewPassword(e.target.value)}/></label><label>Role<select value={newRole} onChange={e=>setNewRole(e.target.value as 'citizen'|'rescuer'|'coordinator')}><option value="coordinator">NGO coordinator</option><option value="rescuer">Responder</option><option value="citizen">Citizen</option></select></label>{newRole==='coordinator'&&<label>Organization<select required value={newOrg} onChange={e=>setNewOrg(e.target.value)}><option value="">Select organization</option>{orgs.map(o=><option key={o.id} value={o.id}>{o.name}</option>)}</select></label>}<button className="button button-primary" disabled={busy||!newEmail||newPassword.length<10||(newRole==='coordinator'&&!newOrg)}>Create account</button></form><h3 style={{marginTop:24}}>Organizations</h3>{orgs.map(o=><div className="evidence-item" key={o.id}><b>{o.name}</b><p>{o.city}, {o.state} · {o.verified?'Verified':'Pending verification'}</p><button className="button button-light" disabled={busy} onClick={()=>verify(o)}>{o.verified?'Revoke verification':'Verify organization'}</button></div>)}<form className="triage-form" onSubmit={create}><b>Register organization</b><label>Organization name<input required minLength={3} value={orgName} onChange={e=>setOrgName(e.target.value)}/></label><label>City<input value={city} onChange={e=>setCity(e.target.value)}/></label><button className="button button-primary" disabled={busy||orgName.trim().length<3}>Create organization</button></form></section>
}

function ResponderWorkspace({token,offers,onChanged}:{token:string;offers:AssignmentOffer[];onChanged:()=>void}) {
 const [available,setAvailable]=useState<boolean|null>(null); const [verified,setVerified]=useState(false); const [species,setSpecies]=useState('dog, cat'); const [radius,setRadius]=useState('20'); const [latitude,setLatitude]=useState('11.6643'); const [longitude,setLongitude]=useState('78.1460'); const [capacity,setCapacity]=useState('2'); const [busy,setBusy]=useState(false); const [error,setError]=useState(''); const [reason,setReason]=useState('')
 useEffect(()=>{responderApi.profile(token).then(p=>{setAvailable(p.is_available);setVerified(p.verified);setSpecies(p.species.join(', '));setRadius(String(p.service_radius_km));setLatitude(p.latitude===null?'':String(p.latitude));setLongitude(p.longitude===null?'':String(p.longitude));setCapacity(String(p.capacity))}).catch(e=>setError(e.message))},[token])
 const toggle=async()=>{if(available===null)return;setBusy(true);setError('');try{const result=await responderApi.setAvailability(token,!available);setAvailable(result.is_available)}catch(e){setError(e instanceof Error?e.message:'Availability update failed')}finally{setBusy(false)}}
 const saveProfile=async(e:FormEvent)=>{e.preventDefault();setBusy(true);setError('');try{const p=await responderApi.updateProfile(token,{species:species.split(',').map(x=>x.trim().toLowerCase()).filter(Boolean),service_radius_km:Number(radius),latitude:Number(latitude),longitude:Number(longitude),capacity:Number(capacity)});setAvailable(p.is_available);setVerified(p.verified)}catch(e){setError(e instanceof Error?e.message:'Profile update failed')}finally{setBusy(false)}}
 const respond=async(offer:AssignmentOffer,accept:boolean)=>{setBusy(true);setError('');try{if(accept)await responderApi.accept(token,offer.offer_id);else await responderApi.decline(token,offer.offer_id,reason||'Unable to respond to this request.');setReason('');onChanged()}catch(e){setError(e instanceof Error?e.message:'Could not update offer')}finally{setBusy(false)}}
 return <><section className="report-panel"><div className="section-heading"><div><h2>Responder duty status</h2><p>Keep your skills, service area and availability accurate.</p></div><button className="button button-light" disabled={busy||available===null||!verified} onClick={toggle}>{available?'Go offline':'Go available'}</button></div>{error&&<div className="error-box">{error}</div>}<p><b>Verification:</b> {verified?'Verified':'Awaiting admin verification'} · <b>Availability:</b> {available===null?'Loading…':available?'Available':'Not available'}</p><form className="report-form" onSubmit={saveProfile}><div className="form-grid"><label>Animal skills (comma separated)<input value={species} onChange={e=>setSpecies(e.target.value)} placeholder="dog, cat, cattle, all"/></label><label>Service radius (km)<input type="number" min="1" max="100" value={radius} onChange={e=>setRadius(e.target.value)}/></label><label>Base latitude<input type="number" step="any" value={latitude} onChange={e=>setLatitude(e.target.value)}/></label><label>Base longitude<input type="number" step="any" value={longitude} onChange={e=>setLongitude(e.target.value)}/></label><label>Concurrent case capacity<input type="number" min="1" max="10" value={capacity} onChange={e=>setCapacity(e.target.value)}/></label></div><button className="button button-primary" disabled={busy||!species.trim()||!latitude||!longitude}>{busy?'Saving…':'Save responder profile'}</button></form><h3>Assignment offers</h3>{offers.length===0?<div className="empty-state"><HeartHandshake size={26}/><b>No assignment offers</b><span>New offers will appear here when a coordinator assigns a case.</span></div>:offers.map(offer=><div className="case-row" key={offer.offer_id}><div className="case-row-main"><b>{offer.case_id} · {offer.animal_category} · {offer.priority}</b><span>{offer.description}</span><small>Status: {offer.status} · Attempt #{offer.attempt_no} · {offer.distance_km===null?'Distance unavailable':`${offer.distance_km} km`} · Deadline {new Date(offer.deadline_at).toLocaleTimeString()}</small>{offer.status==='PENDING'&&<div className="offer-actions"><button className="button button-primary" disabled={busy} onClick={()=>respond(offer,true)}>Accept responsibility</button><button className="button button-light" disabled={busy} onClick={()=>respond(offer,false)}>Decline</button></div>}</div></div>)}{offers.some(o=>o.status==='PENDING')&&<label>Decline reason (optional)<input value={reason} onChange={e=>setReason(e.target.value)} placeholder="Explain why you cannot take this case"/></label>}</section></>
}

function ReportForm({token,onCreated}:{token:string;onCreated:(item:RescueCase)=>void}) {
 const [animal,setAnimal]=useState('Dog'); const [description,setDescription]=useState(''); const [landmark,setLandmark]=useState(''); const [address,setAddress]=useState(''); const [phone,setPhone]=useState(''); const [lat,setLat]=useState(''); const [lon,setLon]=useState(''); const [photo,setPhoto]=useState<File|null>(null); const [busy,setBusy]=useState(false); const [error,setError]=useState('')
 const [showAi, setShowAi] = useState(false); const [imageBusy,setImageBusy]=useState(false); const [imageResult,setImageResult]=useState('')
 const [createdCase, setCreatedCase] = useState<RescueCase | null>(null)

 const applyAi = (ex: IncidentExtraction) => {
   if (ex.animal_category) setAnimal(ex.animal_category.charAt(0).toUpperCase() + ex.animal_category.slice(1))
   if (ex.location_text && !address) setAddress(ex.location_text)
   if (ex.injury_description && !description.toLowerCase().includes(ex.injury_description.toLowerCase())) setDescription(`${description}\n\nAI-extracted detail (please verify): ${ex.injury_description}`)
   setShowAi(false)
 }
 const classifyPhoto=async()=>{if(!photo)return;setImageBusy(true);setImageResult('');try{const result=await aiApi.classifyImage(token,photo);if(result.available&&result.classification){setImageResult(`${result.classification} · ${Math.round((result.confidence??0)*100)}% confidence. Confirm manually before submitting.`);if((result.confidence??0)>=0.75)setAnimal(result.classification)}else setImageResult(result.message||'Image classification unavailable. Choose the animal manually.')}catch(e){setImageResult(e instanceof Error?e.message:'Image classification failed. Choose manually.')}finally{setImageBusy(false)}}

 const submit=async(e:FormEvent)=>{e.preventDefault();setBusy(true);setError('');try{const item=await caseApi.create(token,{animal_category:animal,description,landmark:landmark||undefined,address_text:address||undefined,reporter_phone:phone||undefined,latitude:lat?Number(lat):undefined,longitude:lon?Number(lon):undefined});setCreatedCase(item);onCreated(item);setDescription('');if(photo){try{await caseApi.uploadPhoto(token,item.public_id,photo)}catch(photoError){setError(`Case ${item.public_id} was created, but the photo could not be uploaded: ${photoError instanceof Error?photoError.message:'upload failed'}`)}}setPhoto(null)}catch(err){setError(err instanceof Error?err.message:'Could not submit report')}finally{setBusy(false)}}
 const locate=()=>{if(!navigator.geolocation){setError('Location is not available in this browser. Enter it manually.');return}navigator.geolocation.getCurrentPosition(p=>{setLat(p.coords.latitude.toFixed(6));setLon(p.coords.longitude.toFixed(6))},()=>setError('Location permission denied. You can enter the location manually.'),{enableHighAccuracy:true,timeout:10000})}
 return <section className="report-panel"><div className="section-heading"><div><h2><Plus size={17}/> Report an animal emergency</h2><p>Submit confirmed details. No report is sent until you press the button.</p></div></div><form className="report-form" onSubmit={submit}><div className="form-grid"><label>Animal category<select value={animal} onChange={e=>setAnimal(e.target.value)}><option>Dog</option><option>Cat</option><option>Cattle</option><option>Bird</option><option>Wildlife</option><option>Other</option></select></label><label>Contact phone (optional)<input value={phone} onChange={e=>setPhone(e.target.value)} placeholder="Your contact number"/></label><label className="wide-field">What happened?
   <div className="desc-row">
     <textarea required minLength={10} maxLength={5000} value={description} onChange={e=>setDescription(e.target.value)} placeholder="Describe what you observed. Avoid guessing about medical conditions."/>
     <button type="button" className="ai-analyze-btn" title="Analyze with AI" onClick={()=>setShowAi(s=>!s)} disabled={description.trim().length < 10}>✨ AI Analyze</button>
   </div>
 </label>
 {showAi && description.trim().length >= 10 && (
   <div className="wide-field">
     <AiPanel token={token} description={description} onApply={applyAi} onDismiss={() => setShowAi(false)}/>
   </div>
 )}
 <label>Landmark<input value={landmark} onChange={e=>setLandmark(e.target.value)} placeholder="Near bus stand, Salem"/></label><label>Address / area<input value={address} onChange={e=>setAddress(e.target.value)} placeholder="Street, area, city"/></label><label>Latitude (optional)<input type="number" step="any" value={lat} onChange={e=>setLat(e.target.value)} placeholder="11.6643"/></label><label>Longitude (optional)<input type="number" step="any" value={lon} onChange={e=>setLon(e.target.value)} placeholder="78.1460"/></label><div className="location-action"><button type="button" className="button button-light" onClick={locate}><MapPin size={15}/> Use my location</button><span>Location is shared only with authorized case staff.</span></div><label className="wide-field">Photograph (JPEG, PNG or WebP · max 5 MB)<input type="file" accept="image/jpeg,image/png,image/webp" onChange={e=>{setPhoto(e.target.files?.[0]??null);setImageResult('')}}/></label>{photo&&<div className="wide-field"><button type="button" className="button button-light" disabled={imageBusy} onClick={classifyPhoto}>{imageBusy?'Analyzing image…':'✨ Identify animal from image (optional)'}</button>{imageResult&&<p className="muted">{imageResult}</p>}</div>}
 </div>{error&&<div className="error-box">{error}</div>}<div className="report-consent"><ShieldCheck size={16}/> I confirm these details are accurate to the best of my knowledge. Priority is a non-medical suggestion and will be reviewed.</div><button className="button button-primary" disabled={busy||description.trim().length<10}>{busy?'Submitting…':'Submit emergency report'} <ArrowRight size={16}/></button></form>
 <VoicePanel token={token} casePublicId={createdCase?.public_id}/>
 </section>
}
function CaseDetails({item,canManage,canRespond,token,onTriage,onProgress,onAssigned,onClose}:{item:RescueCase;canManage:boolean;canRespond:boolean;token:string;onTriage:(item:RescueCase)=>void;onProgress:()=>void;onAssigned:()=>void;onClose:()=>void}) {
 const [priority,setPriority]=useState(item.priority); const [reason,setReason]=useState(''); const [busy,setBusy]=useState(false); const [error,setError]=useState(''); const [assigning,setAssigning]=useState(false)
 const [evidence, setEvidence] = useState<Evidence[]>([])
 const loadEvidence = () => evidenceApi.list(token, item.public_id).then(setEvidence).catch(() => {})
 useEffect(()=>{setPriority(item.priority);setReason('');if(canManage||canRespond)loadEvidence()},[item.id,item.priority])
 const updateProgress=async(next:'IN_PROGRESS'|'ON_SCENE')=>{setBusy(true);setError('');try{await progressApi.update(token,item.public_id,next);onProgress()}catch(err){setError(err instanceof Error?err.message:'Progress update failed')}finally{setBusy(false)}}
 const assign=async()=>{setAssigning(true);setError('');try{const result=await responderApi.assign(token,item.public_id);if(result.status==='NEEDS_COORDINATOR')setError(result.message||'No eligible responder found');else onAssigned()}catch(err){setError(err instanceof Error?err.message:'Assignment failed')}finally{setAssigning(false)}}
 const triage=async(e:FormEvent)=>{e.preventDefault();setBusy(true);setError('');try{const updated=await caseApi.triage(token,item.public_id,{priority,reason});onTriage(updated)}catch(err){setError(err instanceof Error?err.message:'Triage update failed')}finally{setBusy(false)}}

 const verificationStatuses = ['VERIFICATION_PENDING']
 const closableStatuses = ['VERIFIED', 'REJECTED', 'CANCELLED']

 return <section className="detail-panel"><div className="detail-header"><div><span className="eyebrow">CASE DETAILS</span><h2>{item.public_id}</h2><p>{item.animal_category} · {item.status.replaceAll('_',' ')}</p></div><button className="refresh-button" onClick={onClose}>Close</button></div><div className="detail-grid"><div><b>Incident description</b><p>{item.description}</p><b>Location</b><p>{item.landmark||item.address_text||'Not supplied'} {item.latitude!==null&&item.longitude!==null?`(${item.latitude}, ${item.longitude})`:''}</p><b>Priority explanation</b><p>{item.triage_reason||'Awaiting review'}</p>{item.needs_human_review&&<div className="review-note"><AlertTriangle size={15}/> Human review required</div>}{item.possible_duplicates.length>0&&<div className="duplicate-box"><b>Possible duplicate reports — coordinator review required</b>{item.possible_duplicates.map(d=><p key={d.public_id}>{d.public_id} · {d.distance_km} km away · {d.status}</p>)}</div>}</div><div><b>Report summary</b><p>Submitted {new Date(item.created_at).toLocaleString()}</p><p>Photograph: {item.has_photo?'Uploaded':'Not provided'}</p><p>Contact: {item.reporter_phone||'Not provided'}</p>{canManage&&<form className="triage-form" onSubmit={triage}><b>Coordinator triage decision</b><label>Priority<select value={priority} onChange={e=>setPriority(e.target.value)}><option>CRITICAL</option><option>HIGH</option><option>MEDIUM</option><option>LOW</option><option>NEEDS_REVIEW</option></select></label><label>Reason for decision<textarea required minLength={8} value={reason} onChange={e=>setReason(e.target.value)} placeholder="Explain why this priority is appropriate"/></label>{error&&<div className="error-box">{error}</div>}<button className="button button-primary" disabled={busy||reason.trim().length<8}>{busy?'Saving…':'Confirm triage'}</button></form>}

 {/* Responder: progress controls */}
 {canRespond && <ProgressControls token={token} item={item} onProgress={onProgress}/>}

 {/* Legacy progress (fallback for ASSIGNED/IN_PROGRESS) */}
 {canRespond&&(item.status==='ASSIGNED'||item.status==='IN_PROGRESS')&&!['EN_ROUTE','ARRIVED','RESCUE_IN_PROGRESS'].includes(item.status)&&<button className="button button-primary" disabled={busy} onClick={()=>updateProgress(item.status==='ASSIGNED'?'IN_PROGRESS':'ON_SCENE')}>{busy?'Updating…':item.status==='ASSIGNED'?'Start rescue response':'Mark arrival at scene'}</button>}

 {/* Coordinator: assign */}
 {canManage&&item.status==='TRIAGED'&&<button className="button button-primary" disabled={assigning} onClick={assign}>{assigning?'Finding responder…':'Offer to best eligible responder'}</button>}

 {/* Coordinator: verify */}
 {canManage && verificationStatuses.includes(item.status) && (
   <div style={{ marginTop: 12 }}>
     <VerifyPanel token={token} publicId={item.public_id} evidence={evidence} onDone={()=>{onProgress();loadEvidence()}}/>
   </div>
 )}

 {/* Coordinator: close */}
 {canManage && closableStatuses.includes(item.status) && (
   <CloseCase token={token} publicId={item.public_id} onDone={onProgress}/>
 )}

 </div></div><div className="timeline"><h3>Case activity timeline</h3>{item.events.length===0?<p>No activity events.</p>:item.events.map(ev=><div className="timeline-event" key={ev.id}><span className="timeline-dot"/><div><b>{ev.event_type.replaceAll('_',' ')}</b><p>{ev.message}</p><small>{ev.actor_name||'System'} · {new Date(ev.created_at).toLocaleString()}</small></div></div>)}</div>

 {/* Responder: evidence submission */}
 {canRespond && ['ASSIGNED','EN_ROUTE','ARRIVED','RESCUE_IN_PROGRESS','IN_PROGRESS','ON_SCENE','RESCUED'].includes(item.status) && (
   <EvidencePanel token={token} publicId={item.public_id} onDone={onProgress}/>
 )}

 </section>
}
function Metric({label,value,icon}:{label:string;value:number|undefined;icon:ReactNode}) { return <div className="metric-card"><div className="metric-top"><span>{label}</span><i>{icon}</i></div><strong>{value === undefined ? '—' : value}</strong><small>Current database count</small></div> }
export default App
