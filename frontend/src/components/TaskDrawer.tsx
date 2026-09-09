import React, { useState } from 'react'
import { invalidate, patch, post, upload } from '../lib/api'
import { useAuth } from '../lib/auth'
import { dt, STATUS_KEY, STATUS_PILL, toLocalInput } from '../lib/fmt'
import { useFetch } from '../lib/hooks'
import { useT } from '../lib/i18n'
import { useToast } from '../lib/toast'
import Modal from './Modal'

/** Vazifa kartochkasi: hamma tafsilot, fayllar, izohlar va amallar bitta joyda. */
export default function TaskDrawer({ id, onClose }: { id: number; onClose: () => void }) {
  const { t } = useT()
  const { me, isManager } = useAuth()
  const { toast, toastErr } = useToast()
  const { data: tk, reload } = useFetch<any>(`/tasks/${id}`)
  const { data: history } = useFetch<any[]>(`/tasks/${id}/history`)
  const [comment, setComment] = useState('')
  const [ask, setAsk] = useState<'' | 'return' | 'cancel' | 'due'>('')
  const [reason, setReason] = useState('')
  const [due, setDue] = useState('')
  const [busy, setBusy] = useState(false)

  if (!tk) return (
    <><div className="drawer-bg" onClick={onClose} /><div className="drawer"><div className="empty">{t('loading')}</div></div></>
  )
  const p = tk.permissions || {}
  const mine = tk.assignee_id === me?.id

  const run = async (fn: () => Promise<any>, ok?: string) => {
    setBusy(true)
    try { await fn(); await reload(); invalidate(); if (ok) toast(ok) } catch (e) { toastErr(e) } finally { setBusy(false) }
  }
  const sendComment = async () => {
    if (!comment.trim()) return
    await run(() => post(`/tasks/${id}/comments`, { text: comment.trim() }))
    setComment('')
  }
  const addFile = async (f: File | null) => {
    if (!f) return
    const form = new FormData()
    form.append('file', f)
    form.append('kind', 'proof')
    await run(() => upload(`/tasks/${id}/files`, form))
  }
  const confirmAsk = async () => {
    if (ask === 'due') {
      if (!due) return
      await run(() => patch(`/tasks/${id}`, { due_at: due }))
    } else {
      if (!reason.trim()) return toast(t('dlg_reason_req'), 'err')
      await run(() => post(`/tasks/${id}/${ask}`, { reason: reason.trim() }))
    }
    setAsk(''); setReason(''); setDue('')
  }

  return (
    <>
      <div className="drawer-bg" onClick={onClose} />
      <div className="drawer">
        <div className="drawer__h">
          <div className="row wrap">
            <span className="mono small b">{tk.code}</span>
            <span className={'pill ' + (STATUS_PILL[tk.status] || 'pill--g')}>{t(STATUS_KEY[tk.status])}</span>
            {tk.is_late && <span className="pill pill--b">
              {tk.late_days ? t('late_days', { d: tk.late_days }) : t('late_hours', { h: Math.max(1, tk.late_hours) })}
            </span>}
            {!!tk.return_count && <span className="pill pill--w">↩️ {tk.return_count}</span>}
            <span className="spacer" />
            <button className="icon-btn" onClick={onClose} aria-label="close">✕</button>
          </div>
          <h2>{tk.title}</h2>
          <div className="kv">
            <span>{t('t_who')}</span>
            <b>{tk.assignee_name}{tk.department_name ? ` · ${tk.department_name}` : ''}</b>
            <span>{t('t_due')}</span><b className="mono">{dt(tk.due_at)}</b>
            <span>{t('d_created_by')}</span><b>{tk.created_by_name}</b>
            <span>{t('d_created_at')}</span><b className="mono">{dt(tk.created_at)}</b>
            {tk.due_changed_count > 0 && <>
              <span>{t('d_original')}</span>
              <b className="mono">{dt(tk.original_due_at)} · {t('d_times', { n: tk.due_changed_count })}</b>
            </>}
            {tk.accepted_by_name && <><span>{t('d_accepted_by')}</span><b>{tk.accepted_by_name}</b></>}
          </div>
        </div>

        <div className="drawer__b">
          {tk.description && <section><div className="lbl">{t('d_desc')}</div><p className="pre">{tk.description}</p></section>}
          {tk.submit_note && <section><div className="lbl">{t('d_note')}</div><p className="pre">{tk.submit_note}</p></section>}

          <section>
            <div className="row"><div className="lbl">{t('d_files')}</div><span className="spacer" />
              {(mine || isManager) && (
                <label className="btn btn--sm">
                  {t('a_upload')}
                  <input type="file" hidden onChange={e => addFile(e.target.files?.[0] || null)} />
                </label>
              )}
            </div>
            {!tk.files?.length && <div className="muted small">{t('d_no_files')}</div>}
            <div className="files">
              {tk.files?.map((f: any) => (
                <a key={f.id} className="file" href={f.url} target="_blank" rel="noreferrer">
                  {f.mime_type?.startsWith('image/')
                    ? <img src={f.url} alt={f.filename} loading="lazy" />
                    : <span className="file__doc">📄</span>}
                  <span className="file__n ellipsis">{f.filename}</span>
                </a>
              ))}
            </div>
          </section>

          <section>
            <div className="lbl">{t('d_comments')}</div>
            <div className="cmts">
              {tk.comments?.map((c: any) => (
                <div key={c.id} className="cmt">
                  <div className="row xs muted"><b>{c.author_name}</b><span className="right mono">{dt(c.created_at)}</span></div>
                  <div className="pre">{c.text}</div>
                </div>
              ))}
              {!tk.comments?.length && <div className="muted small">—</div>}
            </div>
            <div className="row" style={{ marginTop: 8 }}>
              <input className="inp" style={{ flex: 1 }} value={comment} placeholder={t('a_comment')}
                     onChange={e => setComment(e.target.value)}
                     onKeyDown={e => { if (e.key === 'Enter') sendComment() }} />
              <button className="btn" onClick={sendComment} disabled={busy || !comment.trim()}>{t('a_send')}</button>
            </div>
          </section>

          <section>
            <div className="lbl">{t('d_history')}</div>
            <div className="histbox">
              {history?.map(h => (
                <div key={h.id} className="hrow">
                  <span className="mono xs faint">{dt(h.created_at)}</span>
                  <span className="b small">{h.action}</span>
                  <span className="small muted">{h.actor_name}</span>
                </div>
              ))}
            </div>
          </section>
        </div>

        <div className="drawer__f">
          {p.start && <button className="btn" disabled={busy} onClick={() => run(() => post(`/tasks/${id}/start`))}>{t('a_start')}</button>}
          {p.accept && <button className="btn btn--ok" disabled={busy} onClick={() => run(() => post(`/tasks/${id}/accept`))}>{t('a_accept')}</button>}
          {p.return && <button className="btn btn--warn" disabled={busy} onClick={() => setAsk('return')}>{t('a_return')}</button>}
          {p.edit && <button className="btn" disabled={busy} onClick={() => { setDue(toLocalInput(tk.due_at)); setAsk('due') }}>{t('a_edit_due')}</button>}
          {p.cancel && <button className="btn btn--danger" disabled={busy} onClick={() => setAsk('cancel')}>{t('a_cancel')}</button>}
        </div>
      </div>

      {ask && (
        <Modal title={ask === 'return' ? t('dlg_return') : ask === 'cancel' ? t('dlg_cancel') : t('a_edit_due')}
               onClose={() => setAsk('')} small>
          <div className="modal__b modal__b--one">
            {ask === 'due'
              ? <label className="lbl">{t('t_due')}
                  <input className="inp" type="datetime-local" value={due} onChange={e => setDue(e.target.value)} />
                </label>
              : <label className="lbl">{t('dlg_reason_req')}
                  <textarea className="inp" autoFocus value={reason} onChange={e => setReason(e.target.value)} />
                </label>}
          </div>
          <div className="modal__f">
            <button className="btn" onClick={() => setAsk('')}>{t('cancel')}</button>
            <button className="btn btn--p" onClick={confirmAsk} disabled={busy}>{t('save')}</button>
          </div>
        </Modal>
      )}
    </>
  )
}
