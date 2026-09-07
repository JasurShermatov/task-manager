import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError, subscribe } from './api'

export function useFetch<T = any>(path: string | null, params?: Record<string, any>, deps: any[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(!!path)
  const key = JSON.stringify([path, params])
  const seq = useRef(0)
  const load = useCallback(async (silent = false) => {
    if (!path) { setData(null); setLoading(false); return }
    const my = ++seq.current
    if (!silent) setLoading(true)
    try {
      const d = await api<T>(path, { params })
      if (my === seq.current) { setData(d); setError(null) }
    } catch (e: any) {
      if (my === seq.current) setError(e instanceof ApiError ? e : new ApiError(0, { message: String(e) }))
    } finally { if (my === seq.current) setLoading(false) }
  }, [key])
  useEffect(() => { load() }, [load, ...deps])
  useEffect(() => subscribe(() => load(true)), [load])
  return { data, error, loading, reload: () => load(true), setData }
}

export function useDebounce<T>(v: T, ms = 300): T {
  const [d, setD] = useState(v)
  useEffect(() => { const t = setTimeout(() => setD(v), ms); return () => clearTimeout(t) }, [v, ms])
  return d
}

export function useLocalStorage<T>(key: string, init: T): [T, (v: T) => void] {
  const [v, setV] = useState<T>(() => { try { const s = localStorage.getItem(key); return s ? JSON.parse(s) : init } catch { return init } })
  const set = (nv: T) => { setV(nv); try { localStorage.setItem(key, JSON.stringify(nv)) } catch {} }
  return [v, set]
}
