import React, { useState } from 'react'
import { patch } from '../lib/api'
import { useT, Lang } from '../lib/i18n'
import { useToast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { useRefs } from '../lib/refs'
import { useFetch } from '../lib/hooks'
import { PageHeader } from '../components/Layout'

export default function Profile() {
  const { t, setLang } = useT()
  const { me, reload } = useAuth()
  const { toast, toastErr } = useToast()
  const { projects, locations } = useRefs()
  const { data: meta } = useFetch<any>('/meta')
  const pwMin = meta?.password_min ?? 4
  const u = me!.user
  const [f, setF] = useState({ full_name: u.full_name, phone: u.phone || '', lang: u.lang || 'uz' })
  const [pw, setPw] = useState({ a: '', b: '' })
  const [busy, setBusy] = useState(false)

  const scope = u.scope_type === 'system' ? t('us_scope_system')
    : u.scope_type === 'project' ? (projects.find(p => p.id === u.scope_id)?.name || t('us_scope_project'))
    : (locations.find(l => l.id === u.scope_id)?.name || t('us_scope_location'))

  const saveProfile = async () => {
    setBusy(true)
    try {
      await patch(`/users/${u.id}`, { full_name: f.full_name.trim(), phone: f.phone || null, lang: f.lang })
      setLang(f.lang as Lang)
      await reload()
      toast(t('pf_saved'))
    } catch (e) { toastErr(e) } finally { setBusy(false) }
  }

  const savePw = async () => {
    setBusy(true)
    try {
      await patch(`/users/${u.id}`, { password: pw.a })
      setPw({ a: '', b: '' })
      toast(t('pf_pw_saved'))
    } catch (e) { toastErr(e) } finally { setBusy(false) }
  }

  const pwShort = !!pw.a && pw.a.length < pwMin
  const pwMismatch = !!pw.b && pw.a !== pw.b
  const pwOk = pw.a.length >= pwMin && pw.a === pw.b

  return (
    <>
      <PageHeader title={t('pf_title')} />
      <div className="content" style={{ maxWidth: 640 }}>
        <div className="blk section">
          <div className="blk__t">{t('pf_title')}</div>
          <dl className="kv" style={{ marginBottom: 14 }}>
            <dt>{t('pf_login')}</dt><dd className="mono">{u.login}</dd>
            <dt>{t('pf_role')}</dt><dd>{u.role?.name}</dd>
            <dt>{t('pf_scope')}</dt><dd>{scope}</dd>
          </dl>
          <div className="grid2">
            <label className="lbl">{t('pf_name')}
              <input className="inp" value={f.full_name} onChange={e => setF({ ...f, full_name: e.target.value })} /></label>
            <label className="lbl">{t('pf_phone')}
              <input className="inp" value={f.phone} onChange={e => setF({ ...f, phone: e.target.value })} /></label>
            <label className="lbl">{t('pf_lang')}
              <select className="sel" value={f.lang} onChange={e => setF({ ...f, lang: e.target.value })}>
                <option value="uz">O'zbekcha</option><option value="ru">Русский</option><option value="en">English</option>
              </select></label>
          </div>
          <button className="btn btn--p" style={{ marginTop: 14 }} disabled={busy || !f.full_name.trim()} onClick={saveProfile}>{t('save')}</button>
        </div>

        <div className="blk">
          <div className="blk__t">{t('pf_pw')}</div>
          <div className="grid2">
            <label className="lbl">{t('pf_pw_new', { n: pwMin })}
              <input className="inp" type="password" autoComplete="new-password" value={pw.a} onChange={e => setPw({ ...pw, a: e.target.value })} />
              {pwShort && <span className="field-err">{t('pf_pw_short', { n: pwMin })}</span>}</label>
            <label className="lbl">{t('pf_pw_confirm')}
              <input className="inp" type="password" autoComplete="new-password" value={pw.b} onChange={e => setPw({ ...pw, b: e.target.value })} />
              {pwMismatch && <span className="field-err">{t('pf_pw_mismatch')}</span>}</label>
          </div>
          <div className="hint" style={{ marginTop: 8 }}>{t('pf_pw_hint')}</div>
          <button className="btn btn--p" style={{ marginTop: 14 }} disabled={busy || !pwOk} onClick={savePw}>{t('pf_pw')}</button>
        </div>
      </div>
    </>
  )
}
