import React, { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, invalidate, onUnauthorized, tokens } from './api'
import { Lang, useT } from './i18n'

export type User = {
  id: number; full_name: string; login: string; role: string; role_name: string
  position: string | null; phone: string | null
  department_id: number | null; department_name: string | null
  lang: Lang; telegram_user_id: number | null; is_active: boolean
  open_tasks: number; late_tasks: number
}

const MANAGERS = ['boss', 'assistant']

type AuthCtx = {
  me: User | null
  loading: boolean
  isManager: boolean
  login: (l: string, p: string) => Promise<void>
  logout: () => void
  reload: () => Promise<void>
}
const Ctx = createContext<AuthCtx>(null as any)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const { setLang } = useT()

  const reload = useCallback(async () => {
    if (!tokens.access && !tokens.refresh) { setMe(null); setLoading(false); return }
    try {
      const u = await api<User>('/auth/me')
      setMe(u)
      if (u?.lang) setLang(u.lang)
    } catch { setMe(null) } finally { setLoading(false) }
  }, [])

  useEffect(() => { onUnauthorized.handler = () => { tokens.clear(); setMe(null) }; reload() }, [reload])

  const login = async (l: string, p: string) => {
    const d = await api('/auth/login', { method: 'POST', body: { login: l, password: p }, retry: false })
    tokens.set(d.access_token, d.refresh_token)
    await reload()
    invalidate()
  }
  const logout = () => {
    const rt = tokens.refresh
    if (rt) api('/auth/logout', { method: 'POST', body: { refresh_token: rt }, retry: false }).catch(() => {})
    tokens.clear(); setMe(null)
  }

  return (
    <Ctx.Provider value={{ me, loading, isManager: !!me && MANAGERS.includes(me.role), login, logout, reload }}>
      {children}
    </Ctx.Provider>
  )
}

export const useAuth = () => useContext(Ctx)
