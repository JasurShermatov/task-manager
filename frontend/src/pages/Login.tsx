import React, { useState } from 'react'
import { useAuth } from '../lib/auth'
import { useT, Lang } from '../lib/i18n'

export default function Login() {
  const { login } = useAuth()
  const { t, lang, setLang } = useT()
  const [l, setL] = useState('')
  const [p, setP] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true); setErr('')
    try { await login(l.trim(), p) } catch (ex: any) { setErr(ex?.status === 429 ? ex.message : t('login_err')) } finally { setBusy(false) }
  }
  return (
    <div className="login">
      <form className="login__box" onSubmit={submit}>
        <div>
          <div className="side__logo" style={{ color: '#0b0b0c' }}>SAFF<i /></div>
          <div className="side__sub" style={{ color: '#9a9aa0' }}>{t('app_sub')}</div>
        </div>
        <label className="lbl">{t('login_field')}<input className="inp" value={l} onChange={e => setL(e.target.value)} autoFocus autoComplete="username" /></label>
        <label className="lbl">{t('password')}<input className="inp" type="password" value={p} onChange={e => setP(e.target.value)} autoComplete="current-password" /></label>
        {err && <div className="alert">{err}</div>}
        <button className="btn btn--p" disabled={busy || !l || !p} style={{ justifyContent: 'center' }}>{t('login_btn')}</button>
        <div className="seg seg--full" style={{ background: '#efeff1' }}>
          {(['uz', 'ru', 'en'] as Lang[]).map(x => <button type="button" key={x} className={lang === x ? 'on' : ''} style={lang === x ? { background: '#0b0b0c', color: '#fff' } : { color: '#6b6b70' }} onClick={() => setLang(x)}>{x === 'uz' ? "O'zbekcha" : x === 'ru' ? 'Русский' : 'English'}</button>)}
        </div>
      </form>
    </div>
  )
}
