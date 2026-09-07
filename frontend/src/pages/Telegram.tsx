import React, { useEffect, useState } from 'react'
import { api, del, post } from '../lib/api'
import { useT, fmtDateTime } from '../lib/i18n'
import { useToast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { PageHeader } from '../components/Layout'

export default function Telegram() {
  const { t, lang } = useT()
  const { me, reload } = useAuth()
  const { toastErr } = useToast()
  const [code, setCode] = useState<{ code: string; expires_at: string } | null>(null)
  const [left, setLeft] = useState(0)
  const u = me!.user

  useEffect(() => {
    if (!code) return
    const i = setInterval(() => {
      const s = Math.max(0, Math.round((new Date(code.expires_at + 'Z').getTime() - Date.now()) / 1000))
      setLeft(s)
      if (s === 0) { setCode(null); clearInterval(i) }
    }, 1000)
    return () => clearInterval(i)
  }, [code])

  useEffect(() => {
    if (!code) return
    const i = setInterval(async () => { await reload() }, 4000)
    return () => clearInterval(i)
  }, [code])

  useEffect(() => { if (u.telegram_user_id) setCode(null) }, [u.telegram_user_id])

  const getCode = async () => { try { setCode(await post('/telegram/link-code', {})) } catch (e) { toastErr(e) } }
  const unlink = async () => { try { await del('/telegram/unlink'); await reload() } catch (e) { toastErr(e) } }

  return (
    <>
      <PageHeader title={t('tg_title')} />
      <div className="content" style={{ maxWidth: 620 }}>
        <p className="muted">{t('tg_desc')}</p>
        {u.telegram_user_id ? (
          <div className="blk">
            <div className="row"><span className="pill pill--t">✈ {t('tg_linked')}</span>
              <span className="spacer" />
              <button className="btn btn--sm btn--danger" onClick={unlink}>{t('tg_unlink')}</button></div>
            <div className="small muted" style={{ marginTop: 8 }}>ID: <span className="mono">{u.telegram_user_id}</span> · {t('tg_since')}: {fmtDateTime(u.telegram_linked_at, lang)}</div>
          </div>
        ) : (
          <div className="blk">
            {!code ? (
              <button className="btn btn--p" onClick={getCode}>{t('tg_get_code')}</button>
            ) : (
              <div>
                <div className="mono" style={{ fontSize: 40, fontWeight: 700, letterSpacing: '.15em' }}>{code.code}</div>
                <div className="small muted">{t('tg_code_hint')} · {Math.floor(left / 60)}:{String(left % 60).padStart(2, '0')}</div>
                <button className="btn btn--sm" style={{ marginTop: 10 }} onClick={getCode}>↻</button>
              </div>
            )}
          </div>
        )}
      </div>
    </>
  )
}
