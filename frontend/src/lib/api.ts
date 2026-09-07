// Fetch wrapper with JWT + silent refresh + typed errors.
export const API_BASE: string = (import.meta as any).env?.VITE_API_BASE || '/api'

export class ApiError extends Error {
  status: number
  code: string
  fieldErrors: Record<string, string>
  data: any
  constructor(status: number, body: any) {
    super(body?.message || `HTTP ${status}`)
    this.status = status
    this.code = body?.code || 'ERROR'
    this.fieldErrors = body?.field_errors || {}
    this.data = body || {}
  }
}

const LS_ACCESS = 'saff.access'
const LS_REFRESH = 'saff.refresh'

export const tokens = {
  get access() { try { return localStorage.getItem(LS_ACCESS) } catch { return null } },
  get refresh() { try { return localStorage.getItem(LS_REFRESH) } catch { return null } },
  set(a: string, r: string) { try { localStorage.setItem(LS_ACCESS, a); localStorage.setItem(LS_REFRESH, r) } catch {} },
  clear() { try { localStorage.removeItem(LS_ACCESS); localStorage.removeItem(LS_REFRESH) } catch {} },
}

let refreshing: Promise<boolean> | null = null
async function doRefresh(): Promise<boolean> {
  if (refreshing) return refreshing
  refreshing = (async () => {
    const rt = tokens.refresh
    if (!rt) return false
    try {
      const r = await fetch(`${API_BASE}/auth/refresh`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh_token: rt }) })
      if (!r.ok) { tokens.clear(); return false }
      const d = await r.json()
      tokens.set(d.access_token, d.refresh_token)
      return true
    } catch { return false } finally { refreshing = null }
  })()
  return refreshing
}

export const onUnauthorized: { handler: null | (() => void) } = { handler: null }

type Opts = { method?: string; body?: any; form?: FormData; params?: Record<string, any>; raw?: boolean; retry?: boolean }

export async function api<T = any>(path: string, opts: Opts = {}): Promise<T> {
  const url = new URL((path.startsWith('http') ? '' : API_BASE) + path, window.location.origin)
  if (opts.params) for (const [k, v] of Object.entries(opts.params)) if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v))
  const headers: Record<string, string> = { 'X-Source': 'web', 'X-Request-Id': Math.random().toString(36).slice(2, 12) }
  if (tokens.access) headers.Authorization = `Bearer ${tokens.access}`
  let body: any = undefined
  if (opts.form) body = opts.form
  else if (opts.body !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(opts.body) }
  const r = await fetch(url.toString(), { method: opts.method || (body ? 'POST' : 'GET'), headers, body })
  if (r.status === 401 && opts.retry !== false) {
    if (await doRefresh()) return api<T>(path, { ...opts, retry: false })
    onUnauthorized.handler?.()
    throw new ApiError(401, { code: 'UNAUTHORIZED', message: 'Sessiya tugadi' })
  }
  if (opts.raw) return r as any
  if (r.status === 204) return undefined as any
  const text = await r.text()
  let data: any = null
  try { data = text ? JSON.parse(text) : null } catch { data = { message: text } }
  if (!r.ok) throw new ApiError(r.status, data)
  return data as T
}

export const get = <T = any>(p: string, params?: Record<string, any>) => api<T>(p, { params })
export const post = <T = any>(p: string, body?: any) => api<T>(p, { method: 'POST', body: body ?? {} })
export const patch = <T = any>(p: string, body: any) => api<T>(p, { method: 'PATCH', body })
export const del = <T = any>(p: string) => api<T>(p, { method: 'DELETE' })
export const upload = <T = any>(p: string, form: FormData) => api<T>(p, { method: 'POST', form })

// ---- tiny event bus for cache invalidation ----
type Listener = () => void
const listeners = new Set<Listener>()
export function invalidate() { listeners.forEach(l => l()) }
export function subscribe(l: Listener) { listeners.add(l); return () => { listeners.delete(l) } }
