import React, { useState } from 'react'
import { del, patch, post } from '../lib/api'
import { PageHeader } from '../components/Layout'
import { useAuth } from '../lib/auth'
import { dt } from '../lib/fmt'
import { useFetch } from '../lib/hooks'
import { useT } from '../lib/i18n'
import { useToast } from '../lib/toast'

export default function Settings() {
  const { t } = useT()
  const { me, isManager, reload } = useAuth()
  const { toast, toastErr } = useToast()
  const { data: cfg, reload: reloadCfg } = useFetch<any>('/settings')
  const [name, setName] = useState(me?.full_name || '')
  const [phone, setPhone] = useState(me?.phone || '')
  const [pass, setPass] = useState('')
  const [code, setCode] = useState<any>(null)
  const [hours, setHours] = useState<string>('')
  const [busy, setBusy] = useState(false)

  const saveProfile = async () => {
    setBusy(true)
    try {
      await patch('/auth/me', { full_name: name.trim(), phone: phone.trim() || null })
      await reload(); toast(t('ad_saved'))
    } catch (e) { toastErr(e) } finally { setBusy(false) }
  }
  const savePass = async () => {
    setBusy(true)
    try { await patch('/auth/me', { password: pass }); setPass(''); toast(t('ad_saved')) }
    catch (e) { toastErr(e) } finally { setBusy(false) }
  }
  const getCode = async () => {
    try { setCode(await post('/telegram/link-code')) } catch (e) { toastErr(e) }
  }
  const unlink = async () => {
    try { await del('/telegram/unlink'); await reload(); toast(t('ad_saved')) } catch (e) { toastErr(e) }
  }
  const saveHours = async () => {
    setBusy(true)
    try { await patch('/settings', { reminder_hours: hours }); await reloadCfg(); toast(t('ad_saved')) }
    catch (e) { toastErr(e) } finally { setBusy(false) }
  }

  return (
    <>
      <PageHeader title={t('nav_settings')} />
      <div className="content grid2">
        <section className="panel">
          <div className="panel__h"><b>{t('se_profile')}</b></div>
          <div className="panel__b">
            <label className="lbl">{t('ad_name')}
              <input className="inp" value={name} onChange={e => setName(e.target.value)} />
            </label>
            <label className="lbl">{t('ad_phone')}
              <input className="inp" value={phone} onChange={e => setPhone(e.target.value)} />
            </label>
            <div className="row"><span className="muted small">{me?.role_name} · {me?.login}</span>
              <span className="spacer" />
              <button className="btn btn--p" disabled={busy} onClick={saveProfile}>{t('save')}</button>
            </div>
            <hr />
            <label className="lbl">{t('se_pass')}
              <input className="inp" type="password" value={pass} onChange={e => setPass(e.target.value)} />
            </label>
            <div className="row"><span className="spacer" />
              <button className="btn" disabled={busy || !pass} onClick={savePass}>{t('save')}</button>
            </div>
          </div>
        </section>

        <section className="panel">
          <div className="panel__h"><b>{t('se_tg')}</b></div>
          <div className="panel__b">
            {me?.telegram_user_id ? (
              <>
                <div className="row"><span className="pill pill--ok">{t('se_linked')}</span></div>
                <div className="row"><span className="spacer" />
                  <button className="btn btn--danger btn--sm" onClick={unlink}>{t('se_unlink')}</button>
                </div>
              </>
            ) : (
              <>
                <p className="muted small">{t('se_code_hint')}</p>
                {code
                  ? <>
                      <div className="code">{code.code}</div>
                      <div className="xs muted mono">{dt(code.expires_at)}</div>
                      {code.deep_link && <a className="btn btn--tg" href={code.deep_link}
                                            target="_blank" rel="noreferrer">{t('se_open_bot')}</a>}
                    </>
                  : <button className="btn btn--p" onClick={getCode}>{t('se_code')}</button>}
              </>
            )}
            {cfg?.bot_url && !code && (
              <a className="btn btn--tg btn--sm" href={cfg.bot_url} target="_blank" rel="noreferrer">
                {t('se_open_bot')}
              </a>
            )}
          </div>
        </section>

        {isManager && (
          <section className="panel">
            <div className="panel__h"><b>{t('se_reminders')}</b></div>
            <div className="panel__b">
              <label className="lbl">{t('se_reminders')}
                <input className="inp" placeholder={cfg?.reminder_hours || '9,13,17'}
                       value={hours} onChange={e => setHours(e.target.value)} />
                <span className="hint">{t('se_reminders_hint')}</span>
              </label>
              <div className="row"><span className="spacer" />
                <button className="btn btn--p" disabled={busy || !hours.trim()} onClick={saveHours}>
                  {t('save')}
                </button>
              </div>
            </div>
          </section>
        )}
      </div>
    </>
  )
}
