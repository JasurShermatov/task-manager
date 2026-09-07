import React, { useEffect, useRef, useState } from 'react'
import { api, del, get, patch, post, upload, invalidate } from '../lib/api'
import { useFetch } from '../lib/hooks'
import { useT, fmtDate, fmtDateTime, STATUS_COLOR } from '../lib/i18n'
import { useToast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { initials, useRefs } from '../lib/refs'
import { StatusDot } from './TaskCard'
import { Modal, Confirm } from './Modal'

const BLOCK_REASONS = ['material_yoq', 'hujjat_kutilmoqda', 'texnika_band', 'ishchi_yetmadi', 'oldingi_ish', 'obhavo', 'qaror_kutilmoqda', 'boshqa']
const KINDS = ['before', 'during', 'after', 'document']

export default function TaskDrawer({ id, onClose }: { id: number; onClose: () => void }) {
  const { t, lang } = useT()
  const { toast, toastErr } = useToast()
  const { me } = useAuth()
  const { data: tk, reload, setData } = useFetch<any>(`/tasks/${id}`)
  const [tab, setTab] = useState('general')
  const [dlg, setDlg] = useState<null | 'block' | 'return' | 'reopen' | 'delete' | 'cancel' | 'edit'>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape' && !dlg) onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose, dlg])

  const act = async (fn: () => Promise<any>) => {
    setBusy(true)
    try { const d = await fn(); if (d) setData(d); else await reload(); invalidate(); toast(t('updated')) }
    catch (e: any) { if (e?.code === 'VERSION_CONFLICT') { await reload(); toastErr(e, t('err_version')) } else toastErr(e) }
    finally { setBusy(false) }
  }

  if (!tk) return (
    <><div className="drawer-bg" onClick={onClose} /><div className="drawer"><div className="empty">{t('loading')}</div></div></>
  )
  const p = tk.permissions || {}
  const TABS = [
    ['general', t('tab_general')],
    ['checklist', `${t('tab_checklist')} ${tk.checklist_done}/${tk.checklist_total}`],
    ['daily', t('tab_daily')],
    ['files', `${t('tab_files')} ${tk.attachments?.length || 0}`],
    ['comments', t('tab_comments')],
    ['history', t('tab_history')],
  ]
  return (
    <>
      <div className="drawer-bg" onClick={onClose} />
      <div className="drawer">
        <div className="drawer__h">
          <div className="row wrap">
            <span className="code">{tk.code}</span>
            <span className={`pri pri--${tk.priority}`}>{t('pr_' + tk.priority)}</span>
            <span className="st"><StatusDot s={tk.status} />{t('st_' + tk.status)}</span>
            {tk.overdue_days > 0 && <span className="flag flag--o" style={{ margin: 0 }}>⏱ {t('c_overdue', { d: tk.overdue_days })}</span>}
            {tk.return_count > 0 && <span className="flag flag--d" style={{ margin: 0 }}>↩ {tk.return_count}</span>}
            <span className="spacer" />
            <button className="btn btn--sm btn--ghost" onClick={onClose}>✕</button>
          </div>
          <h2>{tk.title}</h2>
          <div className="loc">{tk.project_name}{tk.location_path?.length ? ' · ' + tk.location_path.map((x: any) => x.name).join(' · ') : ''}</div>
        </div>
        <div className="drawer__tabs">
          {TABS.map(([k, label]) => (
            <button key={k} className={'tab' + (tab === k ? ' on' : '')} onClick={() => setTab(k as string)}>{label}</button>
          ))}
        </div>
        <div className="drawer__b">
          {tk.status === 'blocked' && (
            <div className="alert">⛔ <b>{t('br_' + tk.blocked_reason)}</b> — {tk.blocked_note}
              <div className="xs" style={{ marginTop: 4 }}>{t('d_blocked_since')}: {fmtDateTime(tk.blocked_at, lang)}</div></div>
          )}
          {tab === 'general' && <General tk={tk} onEdit={() => setDlg('edit')} reload={reload} />}
          {tab === 'checklist' && <Checklist tk={tk} setData={setData} />}
          {tab === 'daily' && <Daily tk={tk} reload={reload} />}
          {tab === 'files' && <Files tk={tk} reload={reload} />}
          {tab === 'comments' && <Comments tk={tk} />}
          {tab === 'history' && <History tk={tk} />}
        </div>
        <div className="drawer__f">
          {p.start && <button className="btn btn--p" disabled={busy} onClick={() => act(() => post(`/tasks/${id}/start`))}>▶ {t('a_start')}</button>}
          {p.submit_review && <button className="btn btn--p" disabled={busy} onClick={() => act(() => post(`/tasks/${id}/submit-review`))}>✓ {t('a_submit')}</button>}
          {p.accept && <button className="btn btn--ok" disabled={busy} onClick={() => act(() => post(`/tasks/${id}/accept`))}>✓ {t('a_accept')}</button>}
          {p.return && <button className="btn btn--warn" disabled={busy} onClick={() => setDlg('return')}>↩ {t('a_return')}</button>}
          {p.block && <button className="btn btn--danger" disabled={busy} onClick={() => setDlg('block')}>⛔ {t('a_block')}</button>}
          {p.unblock && <button className="btn" disabled={busy} onClick={() => act(() => post(`/tasks/${id}/unblock`))}>🔓 {t('a_unblock')}</button>}
          {p.reopen && <button className="btn" disabled={busy} onClick={() => setDlg('reopen')}>🔄 {t('a_reopen')}</button>}
          {p.edit && <button className="btn" disabled={busy} onClick={() => setDlg('edit')}>✎ {t('a_edit')}</button>}
          <span className="spacer" />
          {p.cancel && <button className="btn btn--ghost small" disabled={busy} onClick={() => setDlg('cancel')}>{t('a_cancel')}</button>}
          {p.delete && !p.cancel && <button className="btn btn--ghost small" disabled={busy} onClick={() => setDlg('delete')}>{t('a_delete')}</button>}
        </div>
      </div>
      {dlg === 'block' && <BlockDialog onClose={() => setDlg(null)} onSubmit={(reason, note) => { setDlg(null); act(() => post(`/tasks/${id}/block`, { reason, note })) }} />}
      {dlg === 'return' && <ReasonDialog title={t('dlg_return_title')} onClose={() => setDlg(null)} onSubmit={r => { setDlg(null); act(() => post(`/tasks/${id}/return`, { reason: r })) }} />}
      {dlg === 'reopen' && <ReasonDialog title={t('dlg_reopen_note')} optional onClose={() => setDlg(null)} onSubmit={r => { setDlg(null); act(() => post(`/tasks/${id}/reopen`, { to: 'progress', note: r })) }} />}
      {dlg === 'cancel' && <Confirm text={t('dlg_confirm_cancel')} onClose={() => setDlg(null)} onOk={() => { setDlg(null); act(() => post(`/tasks/${id}/transition`, { to: 'cancelled' })) }} />}
      {dlg === 'delete' && <Confirm text={t('dlg_confirm_delete')} onClose={() => setDlg(null)} onOk={async () => { setDlg(null); try { await del(`/tasks/${id}`); invalidate(); onClose() } catch (e) { toastErr(e) } }} />}
      {dlg === 'edit' && <EditDialog tk={tk} onClose={() => setDlg(null)} onSaved={(d: any) => { setDlg(null); setData(d); invalidate() }} />}
    </>
  )
}

function General({ tk, onEdit, reload }: any) {
  const { t, lang } = useT()
  const { toastErr } = useToast()
  const [dep, setDep] = useState('')
  const addDep = async () => {
    const code = dep.trim().toUpperCase()
    if (!code) return
    try {
      const other = await get(`/tasks/by-code/${code.startsWith('V-') ? code : 'V-' + code.replace(/\D/g, '')}`)
      await post(`/tasks/${tk.id}/dependencies`, { depends_on_task_id: other.id })
      setDep(''); reload()
    } catch (e) { toastErr(e) }
  }
  const rmDep = async (did: number) => { try { await del(`/tasks/${tk.id}/dependencies/${did}`); reload() } catch (e) { toastErr(e) } }
  return (
    <>
      <dl className="kv">
        <dt>{t('d_type')}</dt><dd>{tk.type_name}</dd>
        <dt>{t('d_assignee')}</dt><dd><span className="av" style={{ verticalAlign: 'middle', marginRight: 6 }}>{initials(tk.assignee_name)}</span>{tk.assignee_name}</dd>
        <dt>{t('d_reviewer')}</dt><dd><span className="av av--rev" style={{ verticalAlign: 'middle', marginRight: 6 }}>{initials(tk.reviewer_name)}</span>{tk.reviewer_name}</dd>
        <dt>{t('d_plan')}</dt><dd>{fmtDate(tk.planned_start, lang)} — {fmtDate(tk.planned_end, lang)}</dd>
        <dt>{t('d_fact')}</dt><dd>{tk.actual_start ? fmtDate(tk.actual_start, lang) : '—'} — {tk.actual_end ? fmtDate(tk.actual_end, lang) : <span className="muted">{t('d_ongoing')}</span>}</dd>
        {!!tk.planned_quantity && <>
          <dt>{t('d_qty')}</dt>
          <dd><b>{Number(tk.actual_quantity)} / {Number(tk.planned_quantity)} {tk.unit || ''}</b>
            {tk.quantity_over_plan && <span className="pill pill--w" style={{ marginLeft: 6 }}>{t('dl_over')}</span>}</dd>
        </>}
        {!!tk.planned_crew_size && <><dt>{t('d_crew')}</dt><dd>{tk.planned_crew_size}</dd></>}
        <dt>{t('c_progress')}</dt><dd>{tk.progress_percent}%</dd>
        <dt>{t('d_created')}</dt><dd>{fmtDateTime(tk.created_at, lang)}</dd>
      </dl>
      {tk.description && <div className="blk"><div className="blk__t">{t('d_desc')}</div><div style={{ whiteSpace: 'pre-wrap' }}>{tk.description}</div></div>}
      <div className="blk">
        <div className="blk__t">{t('d_deps')}<em>{tk.dependencies?.length || 0}</em></div>
        {!tk.dependencies?.length && <div className="muted small">{t('d_no_deps')}</div>}
        {tk.dependencies?.map((d: any) => (
          <div key={d.id} className="row" style={{ padding: '4px 0' }}>
            <StatusDot s={d.status} /><span className="code">{d.code}</span><span className="ellipsis">{d.title}</span>
            <span className="spacer" />
            {tk.permissions?.edit && <button className="btn btn--sm btn--ghost" onClick={() => rmDep(d.id)}>✕</button>}
          </div>
        ))}
        {tk.permissions?.edit && (
          <div className="row" style={{ marginTop: 8 }}>
            <input className="inp inp--sm" placeholder={t('d_add_dep')} value={dep} onChange={e => setDep(e.target.value)} onKeyDown={e => e.key === 'Enter' && addDep()} />
            <button className="btn btn--sm" onClick={addDep}>+</button>
          </div>
        )}
        {!!tk.dependents?.length && (
          <div style={{ marginTop: 10 }}>
            <div className="blk__t">{t('d_dependents')}</div>
            {tk.dependents.map((d: any) => <div key={d.id} className="row" style={{ padding: '3px 0' }}><StatusDot s={d.status} /><span className="code">{d.code}</span><span className="ellipsis">{d.title}</span></div>)}
          </div>
        )}
      </div>
    </>
  )
}

function Checklist({ tk, setData }: any) {
  const { t } = useT()
  const { toastErr } = useToast()
  const [adding, setAdding] = useState('')
  const [busy, setBusy] = useState(false)
  const can = tk.permissions?.checklist
  const toggle = async (item: any) => {
    if (!can || busy) return
    setBusy(true)
    const prev = tk
    setData({ ...tk, checklist: tk.checklist.map((c: any) => c.id === item.id ? { ...c, is_done: !c.is_done } : c) })
    try { const d = await patch(`/tasks/${tk.id}/checklist`, { items: [{ id: item.id, is_done: !item.is_done }] }); setData(d); invalidate() }
    catch (e) { setData(prev); toastErr(e) } finally { setBusy(false) }
  }
  const add = async () => {
    if (!adding.trim()) return
    try { const d = await post(`/tasks/${tk.id}/checklist`, { title: adding.trim(), is_required: false }); setData(d); setAdding(''); invalidate() }
    catch (e) { toastErr(e) }
  }
  const missing = tk.checklist?.filter((c: any) => c.is_required && !c.is_done) || []
  return (
    <>
      {!!missing.length && tk.status === 'progress' && <div className="alert">{t('ck_required_missing')}: {missing.map((m: any) => m.title).join(', ')}</div>}
      <div className="blk">
        <div className="blk__t">{t('tab_checklist')}<em>{t('ck_done_of', { a: tk.checklist_done, b: tk.checklist_total })}</em></div>
        {!tk.checklist?.length && <div className="muted small">{t('empty')}</div>}
        {tk.checklist?.map((c: any) => (
          <div key={c.id} className={'ck' + (can ? '' : ' dis')} onClick={() => toggle(c)}>
            <span className={'box' + (c.is_done ? ' on' : '')}>{c.is_done ? '✓' : ''}</span>
            <span style={{ flex: 1, textDecoration: c.is_done ? 'line-through' : 'none', color: c.is_done ? 'var(--muted)' : undefined }}>{c.title}</span>
            {c.is_required && <span className="req">{t('required')}</span>}
          </div>
        ))}
        {can && (
          <div className="row" style={{ marginTop: 10 }}>
            <input className="inp inp--sm" placeholder={t('ck_new')} value={adding} onChange={e => setAdding(e.target.value)} onKeyDown={e => e.key === 'Enter' && add()} />
            <button className="btn btn--sm" onClick={add}>{t('a_add_item')}</button>
          </div>
        )}
      </div>
    </>
  )
}

function Daily({ tk, reload }: any) {
  const { t, lang } = useT()
  const { toastErr, toast } = useToast()
  const { data: rows, reload: rl } = useFetch<any[]>(`/tasks/${tk.id}/daily-progress`)
  const [f, setF] = useState({ date: new Date().toISOString().slice(0, 10), quantity: '', workers_count: '', work_hours: '', note: '' })
  const can = tk.permissions?.progress
  const submit = async () => {
    try {
      await post(`/tasks/${tk.id}/daily-progress`, {
        date: f.date, quantity: f.quantity === '' ? null : Number(f.quantity),
        workers_count: f.workers_count === '' ? null : Number(f.workers_count),
        work_hours: f.work_hours === '' ? null : Number(f.work_hours), note: f.note || null,
      })
      setF({ ...f, quantity: '', workers_count: '', work_hours: '', note: '' }); rl(); reload(); invalidate(); toast(t('updated'))
    } catch (e) { toastErr(e) }
  }
  const pct = tk.planned_quantity ? Math.round(Number(tk.actual_quantity) / Number(tk.planned_quantity) * 100) : 0
  return (
    <>
      {!!tk.planned_quantity && <div className={'alert ' + (tk.quantity_over_plan ? '' : 'alert--info')}>
        {t('dl_total', { a: Number(tk.actual_quantity), b: Number(tk.planned_quantity), u: tk.unit || '', p: pct })}
      </div>}
      {can && (
        <div className="blk">
          <div className="blk__t">{t('a_add_daily')}</div>
          <div className="grid3">
            <label className="lbl">{t('dl_date')}<input className="inp inp--sm" type="date" value={f.date} onChange={e => setF({ ...f, date: e.target.value })} /></label>
            <label className="lbl">{t('dl_qty')} {tk.unit ? `(${tk.unit})` : ''}<input className="inp inp--sm" type="number" step="0.01" value={f.quantity} onChange={e => setF({ ...f, quantity: e.target.value })} /></label>
            <label className="lbl">{t('dl_workers')}<input className="inp inp--sm" type="number" value={f.workers_count} onChange={e => setF({ ...f, workers_count: e.target.value })} /></label>
          </div>
          <div className="row" style={{ marginTop: 10 }}>
            <input className="inp inp--sm" style={{ flex: 1 }} placeholder={t('dl_note')} value={f.note} onChange={e => setF({ ...f, note: e.target.value })} />
            <button className="btn btn--sm btn--p" onClick={submit}>{t('add')}</button>
          </div>
        </div>
      )}
      <div className="blk">
        <div className="blk__t">{t('tab_daily')}<em>{rows?.length || 0}</em></div>
        {!rows?.length && <div className="muted small">{t('dl_empty')}</div>}
        {rows?.map(r => (
          <div key={r.id} className="row" style={{ padding: '6px 0', borderBottom: '1px solid var(--line)' }}>
            <span className="mono small" style={{ width: 62 }}>{fmtDate(r.date, lang)}</span>
            <b>{r.quantity != null ? `${Number(r.quantity)} ${tk.unit || ''}` : '—'}</b>
            {r.workers_count != null && <span className="small muted">👷 {r.workers_count}</span>}
            {r.note && <span className="small ellipsis" style={{ flex: 1 }}>{r.note}</span>}
            <span className="spacer" />
            {r.is_duplicate && <span className="pill pill--w">{t('dl_dup')}</span>}
            <span className="xs faint">{r.created_by_name}</span>
          </div>
        ))}
      </div>
    </>
  )
}

function Files({ tk, reload }: any) {
  const { t, lang } = useT()
  const { toastErr } = useToast()
  const [kind, setKind] = useState('during')
  const [busy, setBusy] = useState(false)
  const inp = useRef<HTMLInputElement>(null)
  const req: string[] = tk.required_evidence_kinds || []
  const have = new Set((tk.attachments || []).map((a: any) => a.kind))
  const send = async (files: FileList | null) => {
    if (!files?.length) return
    setBusy(true)
    try {
      for (const f of Array.from(files)) {
        const fd = new FormData()
        fd.append('file', f)
        fd.append('kind', f.type.startsWith('image/') ? kind : 'document')
        await upload(`/tasks/${tk.id}/attachments`, fd)
      }
      reload(); invalidate()
    } catch (e) { toastErr(e) } finally { setBusy(false); if (inp.current) inp.current.value = '' }
  }
  const remove = async (aid: number) => { try { await del(`/tasks/${tk.id}/attachments/${aid}`); reload(); invalidate() } catch (e) { toastErr(e) } }
  return (
    <>
      {!!req.length && (
        <div className={'alert ' + (req.every(k => have.has(k)) ? 'alert--ok' : 'alert--info')}>
          {t('fl_required', { k: req.map(k => t('fl_' + k) + (have.has(k) ? ' ✓' : ` (${t('fl_missing')})`)).join(', ') })}
        </div>
      )}
      {tk.permissions?.upload && (
        <div className="blk">
          <div className="row wrap">
            <select className="sel sel--sm" value={kind} onChange={e => setKind(e.target.value)}>
              {KINDS.map(k => <option key={k} value={k}>{t('fl_' + k)}</option>)}
            </select>
            <input ref={inp} type="file" multiple accept="image/*,.pdf,.doc,.docx,.xls,.xlsx,.txt" onChange={e => send(e.target.files)} className="small" />
            {busy && <span className="small muted">…</span>}
          </div>
        </div>
      )}
      <div className="blk">
        <div className="blk__t">{t('tab_files')}<em>{tk.attachments?.length || 0}</em></div>
        {!tk.attachments?.length && <div className="muted small">{t('fl_empty')}</div>}
        <div className="thumbs">
          {tk.attachments?.map((a: any) => (
            <a className="th" key={a.id} href={a.url} target="_blank" rel="noreferrer" title={`${a.filename} · ${a.uploaded_by_name} · ${fmtDateTime(a.created_at, lang)}`}>
              {a.mime_type?.startsWith('image/') ? <img src={a.url} alt={a.filename} loading="lazy" /> : <span style={{ padding: 6 }}>{a.filename.slice(0, 22)}</span>}
              <b>{t('fl_' + a.kind).slice(0, 6)}</b>
              {tk.permissions?.delete_attachment && <button onClick={e => { e.preventDefault(); remove(a.id) }}>✕</button>}
            </a>
          ))}
        </div>
      </div>
    </>
  )
}

function Comments({ tk }: any) {
  const { t, lang } = useT()
  const { toastErr } = useToast()
  const { data: rows, reload } = useFetch<any[]>(`/tasks/${tk.id}/comments`)
  const [txt, setTxt] = useState('')
  const send = async () => {
    if (!txt.trim()) return
    try { await post(`/tasks/${tk.id}/comments`, { text: txt.trim() }); setTxt(''); reload() } catch (e) { toastErr(e) }
  }
  return (
    <div className="blk">
      <div className="blk__t">{t('tab_comments')}<em>{rows?.length || 0}</em></div>
      {!rows?.length && <div className="muted small">{t('empty')}</div>}
      {rows?.map(c => (
        <div className="cmt" key={c.id}>
          <div><span className="who">{c.author_name}</span><span className="when">{fmtDateTime(c.created_at, lang)}</span>
            {c.source !== 'web' && <span className="src mono" style={{ marginLeft: 6 }}>{t('sources')[c.source] || c.source}</span>}</div>
          <div style={{ whiteSpace: 'pre-wrap' }}>{c.text}</div>
        </div>
      ))}
      {tk.permissions?.comment && (
        <div className="row" style={{ marginTop: 10 }}>
          <input className="inp inp--sm" style={{ flex: 1 }} placeholder="@login …" value={txt} onChange={e => setTxt(e.target.value)} onKeyDown={e => e.key === 'Enter' && send()} />
          <button className="btn btn--sm btn--p" onClick={send}>{t('add')}</button>
        </div>
      )}
    </div>
  )
}

function History({ tk }: any) {
  const { t, lang, d } = useT()
  const { data: rows } = useFetch<any[]>(`/tasks/${tk.id}/history`)
  const val = (v: any) => typeof v === 'object' ? JSON.stringify(v) : String(v)
  return (
    <div className="blk">
      <div className="blk__t">{t('tab_history')}<em>{rows?.length || 0}</em></div>
      {rows?.map(h => {
        const label = t('h_' + h.action) !== 'h_' + h.action ? t('h_' + h.action) : h.action
        const changes = Object.keys({ ...h.old_values_json, ...h.new_values_json })
          .filter(k => k !== 'status').slice(0, 6)
        return (
          <div className="hist" key={h.id}>
            <time>{fmtDateTime(h.created_at, lang)}</time>
            <div style={{ flex: 1 }}>
              <b>{label}</b> — {h.actor_name}
              <span className="src">{(d as any).sources?.[h.source] || h.source}</span>
              {!!changes.length && (
                <div className="xs muted" style={{ marginTop: 2 }}>
                  {changes.map(k => (
                    <div key={k}>{k}: {h.old_values_json?.[k] !== undefined ? <s>{val(h.old_values_json[k])}</s> : ''} {h.new_values_json?.[k] !== undefined ? '→ ' + val(h.new_values_json[k]) : ''}</div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function BlockDialog({ onClose, onSubmit }: { onClose: () => void; onSubmit: (r: string, n: string) => void }) {
  const { t } = useT()
  const [r, setR] = useState('material_yoq')
  const [n, setN] = useState('')
  return (
    <Modal title={t('dlg_block_title')} onClose={onClose} sm footer={
      <><button className="btn" onClick={onClose}>{t('cancel')}</button>
        <button className="btn btn--danger" disabled={!n.trim()} onClick={() => onSubmit(r, n.trim())}>{t('a_block')}</button></>}>
      <label className="lbl full">{t('dlg_reason')}
        <select className="sel" value={r} onChange={e => setR(e.target.value)}>
          {BLOCK_REASONS.map(b => <option key={b} value={b}>{t('br_' + b)}</option>)}
        </select></label>
      <label className="lbl full">{t('dlg_note')} <i>*</i>
        <textarea className="inp" value={n} onChange={e => setN(e.target.value)} autoFocus />
        {!n.trim() && <span className="field-err">{t('dlg_note_req')}</span>}</label>
    </Modal>
  )
}

function ReasonDialog({ title, optional, onClose, onSubmit }: { title: string; optional?: boolean; onClose: () => void; onSubmit: (r: string) => void }) {
  const { t } = useT()
  const [r, setR] = useState('')
  return (
    <Modal title={title} onClose={onClose} sm footer={
      <><button className="btn" onClick={onClose}>{t('cancel')}</button>
        <button className="btn btn--p" disabled={!optional && !r.trim()} onClick={() => onSubmit(r.trim())}>{t('save')}</button></>}>
      <label className="lbl full"><textarea className="inp" value={r} onChange={e => setR(e.target.value)} autoFocus /></label>
    </Modal>
  )
}

function EditDialog({ tk, onClose, onSaved }: any) {
  const { t } = useT()
  const { toastErr } = useToast()
  const { users, types, locations } = useRefs(tk.project_id)
  const [f, setF] = useState<any>({
    title: tk.title, description: tk.description || '', priority: tk.priority, assignee_id: tk.assignee_id,
    reviewer_id: tk.reviewer_id, planned_start: tk.planned_start, planned_end: tk.planned_end,
    planned_quantity: tk.planned_quantity ?? '', unit: tk.unit || '', planned_crew_size: tk.planned_crew_size ?? '',
    location_id: tk.location_id ?? '', type_id: tk.type_id, date_change_reason: '',
  })
  const datesChanged = f.planned_start !== tk.planned_start || f.planned_end !== tk.planned_end
  const save = async () => {
    const body: any = { row_version: tk.row_version }
    for (const k of ['title', 'description', 'priority', 'assignee_id', 'reviewer_id', 'planned_start', 'planned_end', 'unit', 'type_id']) {
      if (f[k] !== (tk[k] ?? '')) body[k] = f[k] === '' ? null : f[k]
    }
    if (String(f.planned_quantity) !== String(tk.planned_quantity ?? '')) body.planned_quantity = f.planned_quantity === '' ? null : Number(f.planned_quantity)
    if (String(f.planned_crew_size) !== String(tk.planned_crew_size ?? '')) body.planned_crew_size = f.planned_crew_size === '' ? null : Number(f.planned_crew_size)
    if (String(f.location_id) !== String(tk.location_id ?? '')) body.location_id = f.location_id === '' ? null : Number(f.location_id)
    if (datesChanged) body.date_change_reason = f.date_change_reason
    try { onSaved(await patch(`/tasks/${tk.id}`, body)) } catch (e) { toastErr(e) }
  }
  const byId = new Map(locations.map(l => [l.id, l]))
  const label = (l: any) => { const p: string[] = []; let c: any = l; let g = 0; while (c && g++ < 6) { p.unshift(c.name); c = c.parent_id ? byId.get(c.parent_id) : null } return p.join(' · ') }
  return (
    <Modal title={t('a_edit')} onClose={onClose} footer={
      <><button className="btn" onClick={onClose}>{t('cancel')}</button>
        <button className="btn btn--p" disabled={datesChanged && !f.date_change_reason.trim()} onClick={save}>{t('save')}</button></>}>
      <label className="lbl full">{t('cr_name')}<input className="inp" value={f.title} onChange={e => setF({ ...f, title: e.target.value })} /></label>
      <label className="lbl">{t('cr_type')}<select className="sel" value={f.type_id} onChange={e => setF({ ...f, type_id: Number(e.target.value) })}>
        {types.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
      <label className="lbl">{t('priority')}<select className="sel" value={f.priority} onChange={e => setF({ ...f, priority: e.target.value })}>
        {['low', 'normal', 'high'].map(p => <option key={p} value={p}>{t('pr_' + p)}</option>)}</select></label>
      <label className="lbl">{t('cr_assignee')}<select className="sel" value={f.assignee_id} onChange={e => setF({ ...f, assignee_id: Number(e.target.value) })}>
        {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}</select></label>
      <label className="lbl">{t('cr_reviewer')}<select className="sel" value={f.reviewer_id} onChange={e => setF({ ...f, reviewer_id: Number(e.target.value) })}>
        {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}</select></label>
      <label className="lbl">{t('cr_start')}<input className="inp" type="date" value={f.planned_start} onChange={e => setF({ ...f, planned_start: e.target.value })} /></label>
      <label className="lbl">{t('cr_end')}<input className="inp" type="date" value={f.planned_end} onChange={e => setF({ ...f, planned_end: e.target.value })} /></label>
      <label className="lbl">{t('cr_location')}<select className="sel" value={f.location_id} onChange={e => setF({ ...f, location_id: e.target.value })}>
        <option value="">—</option>{locations.map(l => <option key={l.id} value={l.id}>{label(l)}</option>)}</select></label>
      <label className="lbl">{t('cr_qty')}<input className="inp" type="number" step="0.01" value={f.planned_quantity} onChange={e => setF({ ...f, planned_quantity: e.target.value })} /></label>
      <label className="lbl">{t('cr_unit')}<input className="inp" value={f.unit} onChange={e => setF({ ...f, unit: e.target.value })} /></label>
      <label className="lbl">{t('cr_crew')}<input className="inp" type="number" value={f.planned_crew_size} onChange={e => setF({ ...f, planned_crew_size: e.target.value })} /></label>
      <label className="lbl full">{t('d_desc')}<textarea className="inp" value={f.description} onChange={e => setF({ ...f, description: e.target.value })} /></label>
      {datesChanged && <label className="lbl full">{t('dlg_date_reason')} <i>*</i>
        <input className="inp" value={f.date_change_reason} onChange={e => setF({ ...f, date_change_reason: e.target.value })} /></label>}
    </Modal>
  )
}
