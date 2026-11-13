const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api/v1'
export type UserRole = 'citizen' | 'rescuer' | 'coordinator' | 'admin'
export type User = { id: string; full_name: string; email: string; role: UserRole; is_active: boolean; is_verified: boolean }
export type AuthResponse = { access_token: string; token_type: string; user: User }
async function request<T>(path: string, options: RequestInit = {}, token?: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { ...options, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options.headers } })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.detail ?? `Request failed (${response.status})`)
  return data as T
}
export const api = {
  login: (email: string, password: string) => request<AuthResponse>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  register: (payload: { full_name: string; email: string; password: string; role: 'citizen' | 'rescuer' }) => request<AuthResponse>('/auth/register', { method: 'POST', body: JSON.stringify(payload) }),
  me: (token: string) => request<User>('/auth/me', {}, token),
  summary: (token: string) => request<{ role: string; total_cases: number; open_cases: number; available_responders: number; data_label: string }>('/dashboard/summary', {}, token),
}

export type CaseEvent = { id: string; event_type: string; from_status: string | null; to_status: string | null; message: string; created_at: string; actor_name: string | null }
export type RescueCase = {
  id: string; public_id: string; reporter_id: string; animal_category: string; description: string;
  status: string; priority: string; latitude: number | null; longitude: number | null;
  landmark: string | null; address_text: string | null; reporter_phone: string | null;
  ai_summary: string | null; triage_reason: string | null; triage_confidence: number | null;
  needs_human_review: boolean; has_photo: boolean; created_at: string; updated_at: string;
  possible_duplicates: { public_id: string; distance_km: number; status: string; created_at: string; description: string }[];
  events: CaseEvent[];
}
export const caseApi = {
  list: (token: string) => request<RescueCase[]>('/cases', {}, token),
  get: (token: string, publicId: string) => request<RescueCase>(`/cases/${encodeURIComponent(publicId)}`, {}, token),
  create: (token: string, payload: { animal_category: string; description: string; latitude?: number; longitude?: number; landmark?: string; address_text?: string; reporter_phone?: string }) => request<RescueCase>('/cases', { method: 'POST', body: JSON.stringify(payload) }, token),
  triage: (token: string, publicId: string, payload: { priority: string; reason: string }) => request<RescueCase>(`/cases/${encodeURIComponent(publicId)}/triage`, { method: 'PATCH', body: JSON.stringify(payload) }, token),
  uploadPhoto: async (token: string, publicId: string, photo: File) => {
    const body = new FormData(); body.append('photo', photo)
    const response = await fetch(`${API_URL}/cases/${encodeURIComponent(publicId)}/photo`, { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data.detail ?? `Upload failed (${response.status})`)
    return data as { message: string; has_photo: boolean }
  }
}

export type AssignmentOffer = { offer_id: string; case_id: string; animal_category: string; description: string; priority: string; status: string; attempt_no: number; distance_km: number | null; deadline_at: string; response_reason: string | null }
export type ResponderProfile = { verified: boolean; species: string[]; service_radius_km: number; latitude: number | null; longitude: number | null; capacity: number; is_available: boolean }
export const responderApi = {
  profile: (token: string) => request<ResponderProfile>('/responders/me/profile', {}, token),
  updateProfile: (token: string, payload: {species:string[];service_radius_km:number;latitude:number;longitude:number;capacity:number}) => request<ResponderProfile>('/responders/me/profile', {method:'PUT', body:JSON.stringify(payload)}, token),
  setAvailability: (token: string, is_available: boolean) => request<{is_available:boolean}>('/responders/me/availability', {method:'PATCH', body:JSON.stringify({is_available})}, token),
  offers: (token: string) => request<AssignmentOffer[]>('/responder/offers', {}, token),
  accept: (token: string, offerId: string) => request<{status:string;case_id:string;message:string}>(`/responder/offers/${offerId}/accept`, {method:'POST'}, token),
  decline: (token: string, offerId: string, reason: string) => request<{status:string;message?:string;next_responder?:string}>(`/responder/offers/${offerId}/decline`, {method:'POST', body:JSON.stringify({reason})}, token),
  assign: (token: string, publicId: string) => request<{status:string;responder_name?:string;deadline_at?:string;message?:string}>(`/coordinator/cases/${encodeURIComponent(publicId)}/assign`, {method:'POST'}, token),
}

export const progressApi = { update: (token:string, publicId:string, status:'IN_PROGRESS'|'ON_SCENE') => request<{case_id:string;status:string}>(`/responder/cases/${encodeURIComponent(publicId)}/status`, {method:'PATCH',body:JSON.stringify({status})}, token) }

// ── New types ──────────────────────────────────────────────────────────────
export interface IncidentExtraction {
  animal_category: string; animal_color: string | null; num_animals: number | null;
  injury_description: string | null; emergency_type: string | null; location_text: string | null;
  urgency_level: string; possible_hazards: string[]; missing_info: string[];
  confidence_score: number; needs_human_review: boolean; suggested_priority: string;
  explanation: string; source: string;
}
export interface AiStatus { gemini_configured: boolean; whisper_configured: boolean; features: Record<string, boolean> }
export interface Notification { id: string; event_type: string; title: string; body: string; is_read: boolean; case_id: string | null; created_at: string }
export interface Evidence {
  id: string; evidence_type: string; has_file: boolean; file_hash: string | null;
  file_size: number | null; mime_type: string | null; rescue_notes: string | null;
  animal_condition: string | null; destination: string | null; handover_details: string | null; created_at: string;
}
export interface AnalyticsSummary {
  total_cases: number; by_priority: Record<string, number>; by_status: Record<string, number>;
  by_category: Record<string, number>; verified_rescues: number; completion_rate_pct: number; data_label: string;
}

// ── fetchJson helper (matches existing style using base request) ────────────
function fetchJson<T>(path: string, options: RequestInit = {}): Promise<T> {
  return request<T>(path, options)
}

// ── AI Extraction ──────────────────────────────────────────────────────────
export const aiApi = {
  extract: (token: string, text: string) =>
    fetchJson<IncidentExtraction>('/ai/extract-incident', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    }),
  status: (token: string) =>
    fetchJson<AiStatus>('/ai/status', { headers: { Authorization: `Bearer ${token}` } }),
}

// ── Notifications ──────────────────────────────────────────────────────────
export const notifApi = {
  list: (token: string, unreadOnly = false) =>
    fetchJson<Notification[]>(`/notifications${unreadOnly ? '?unread_only=true' : ''}`, { headers: { Authorization: `Bearer ${token}` } }),
  count: (token: string) =>
    fetchJson<{ unread: number }>('/notifications/count', { headers: { Authorization: `Bearer ${token}` } }),
  markRead: (token: string, id: string) =>
    fetchJson<{ status: string }>(`/notifications/${id}/read`, { method: 'PATCH', headers: { Authorization: `Bearer ${token}` } }),
}

// ── Evidence ───────────────────────────────────────────────────────────────
export const evidenceApi = {
  list: (token: string, publicId: string) =>
    fetchJson<Evidence[]>(`/cases/${publicId}/evidence`, { headers: { Authorization: `Bearer ${token}` } }),
  submit: (token: string, publicId: string, formData: FormData) =>
    fetchJson<{ id: string }>(`/cases/${publicId}/evidence`, { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: formData }),
  verify: (token: string, publicId: string, decision: string, reason: string) =>
    fetchJson<{ decision: string; case_status: string }>(`/cases/${publicId}/verify`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision, reason }),
    }),
  close: (token: string, publicId: string, reason: string) =>
    fetchJson<{ status: string }>(`/cases/${publicId}/close`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason }),
    }),
}

// ── Analytics ──────────────────────────────────────────────────────────────
export const analyticsApi = {
  summary: (token: string) =>
    fetchJson<AnalyticsSummary>('/analytics/summary', { headers: { Authorization: `Bearer ${token}` } }),
}

// ── Progress extended ──────────────────────────────────────────────────────
export const progressExtApi = {
  update: (token: string, publicId: string, status: string) =>
    fetchJson<{ status: string }>(`/cases/${publicId}/progress`, {
      method: 'PATCH',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    }),
}
