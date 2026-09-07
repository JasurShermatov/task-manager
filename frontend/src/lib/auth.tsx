import React, { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, onUnauthorized, tokens, invalidate } from './api'
import { useT, Lang } from './i18n'

export type Me = { user: any; permissions: string[]; scope: { type: string; id: number | null } }

type AuthCtx = { me: Me | null; loading: boolean; login: (l: string, p: string) => Promise<void>; logout: () => void; can: (p: string) => boolean; reload: () => Promise<void> }
const Ctx = createContext<AuthCtx>(null as any)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)
  const { setLang } = useT()

  const reload = useCallback(async () => {
    if (!tokens.access && !tokens.refresh) { setMe(null); setLoading(false); return }
    try {
      const m = await api<Me>('/auth/me')
      setMe(m)
      if (m.user?.lang) setLang(m.user.lang as Lang)
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
  const can = (p: string) => !!me?.permissions?.includes(p)
  return <Ctx.Provider value={{ me, loading, login, logout, can, reload }}>{children}</Ctx.Provider>
}

export const useAuth = () => useContext(Ctx)
