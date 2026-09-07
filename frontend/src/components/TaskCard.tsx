import React from 'react'
import { useT, fmtDate, STATUS_COLOR } from '../lib/i18n'
import { initials } from '../lib/refs'

export type Task = any

export function TaskCardView({ tk, onClick, draggable, onDragStart, onDragEnd }: {
  tk: Task; onClick?: () => void; draggable?: boolean
  onDragStart?: (e: React.DragEvent) => void; onDragEnd?: () => void
}) {
  const { t, lang } = useT()
  const cls = tk.return_count > 0 && tk.status === 'progress' ? 'ret' : tk.status
  const pcls = tk.status === 'done' ? 'd' : tk.status === 'review' ? 'w' : 'b'
  return (
    <div className={`card card--${cls}`} onClick={onClick} draggable={draggable}
         onDragStart={onDragStart} onDragEnd={onDragEnd}>
      <div className="card__top">
        <span className="code">{tk.code}</span>
        <span className={`pri pri--${tk.priority}`}>{t('pr_' + tk.priority)}</span>
      </div>
      <div className="card__t">{tk.title}</div>
      {!!tk.location_path?.length && <div className="loc">{tk.location_path.map((p: any) => p.name).join(' · ')}</div>}
      {tk.status === 'blocked' && (
        <div className="flag flag--b">⛔ {t('br_' + tk.blocked_reason)}{tk.blocked_days ? ' · ' + t('c_blocked_days', { d: tk.blocked_days }) : ''}</div>
      )}
      {tk.status === 'review' && tk.review_days > 0 && <div className="flag flag--o">◷ {t('c_review_days', { d: tk.review_days })}</div>}
      {tk.status !== 'blocked' && tk.overdue_days > 0 && <div className="flag flag--o">⏱ {t('c_overdue', { d: tk.overdue_days })}</div>}
      {tk.return_count > 0 && tk.status !== 'done' && <div className="flag flag--d">↩ {t('c_returned', { n: tk.return_count })}</div>}
      {!!tk.dependency_pending?.length && tk.status === 'plan' && (
        <div className="flag flag--g">⇢ {t('c_waiting', { codes: tk.dependency_pending.join(', ') })}</div>
      )}
      {tk.status === 'done' && <div className="flag flag--n">✓ {t('c_accepted')} · {fmtDate(tk.actual_end, lang)}</div>}
      {(tk.progress_percent > 0 || tk.status === 'progress') && (
        <div className="prog"><i className={pcls} style={{ width: `${tk.progress_percent}%` }} /></div>
      )}
      <div className="card__f">
        <span className="av" title={tk.assignee_name}>{initials(tk.assignee_name)}</span>
        <span>{tk.checklist_total ? `☑ ${tk.checklist_done}/${tk.checklist_total}` : ''}</span>
        {!!tk.photos_count && <span>📷 {tk.photos_count}</span>}
        <span className={'due' + (tk.overdue_days > 0 ? ' due--late' : '')}>
          {tk.status === 'done' && tk.overdue_days === 0 ? t('c_ontime') : fmtDate(tk.planned_end, lang)}
        </span>
      </div>
    </div>
  )
}

export function StatusDot({ s }: { s: string }) {
  return <span className="sq" style={{ background: STATUS_COLOR[s] }} />
}
