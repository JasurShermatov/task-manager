import React, { createContext, useCallback, useContext, useState } from 'react'
import { ApiError } from './api'

type Toast = { id: number; text: string; kind: 'ok' | 'err' }
const Ctx = createContext<{ toast: (t: string, kind?: 'ok' | 'err') => void; toastErr: (e: any, fallback?: string) => void }>(null as any)

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<Toast[]>([])
  const toast = useCallback((text: string, kind: 'ok' | 'err' = 'ok') => {
    const id = Date.now() + Math.random()
    setItems(x => [...x, { id, text, kind }])
    setTimeout(() => setItems(x => x.filter(i => i.id !== id)), kind === 'err' ? 6000 : 3000)
  }, [])
  const toastErr = useCallback((e: any, fallback = 'Xato') => {
    if (e instanceof ApiError) {
      let msg = e.message || fallback
      if (e.data?.items) msg += ': ' + e.data.items.join(', ')
      if (e.data?.kinds) msg += ': ' + e.data.kinds.join(', ')
      if (e.data?.codes) msg += ': ' + e.data.codes.join(', ')
      const fe = Object.entries(e.fieldErrors || {})
      if (fe.length && !e.data?.items) msg += ' — ' + fe.map(([k, v]) => `${k}: ${v}`).join(', ')
      toast(msg, 'err')
    } else toast(e?.message || fallback, 'err')
  }, [toast])
  return (
    <Ctx.Provider value={{ toast, toastErr }}>
      {children}
      <div className="toast-wrap">{items.map(i => <div key={i.id} className={'toast' + (i.kind === 'err' ? ' toast--err' : '')}>{i.text}</div>)}</div>
    </Ctx.Provider>
  )
}
export const useToast = () => useContext(Ctx)
