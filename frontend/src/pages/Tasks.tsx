import React, { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import CreateTask from '../components/CreateTask'
import { PageHeader } from '../components/Layout'
import TaskDrawer from '../components/TaskDrawer'
import { dt, STATUS_KEY, STATUS_PILL } from '../lib/fmt'
import { useDebounce, useFetch } from '../lib/hooks'
import { useT } from '../lib/i18n'

const STATUSES = ['new', 'progress', 'submitted', 'done', 'cancelled']

export default function Tasks() {
  const { t } = useT()
  const nav = useNavigate()
  const { id } = useParams()
  const [creating, setCreating] = useState(false)
  const [status, setStatus] = useState('')
  const [assignee, setAssignee] = useState('')
  const [dep, setDep] = useState('')
  const [overdue, setOverdue] = useState(false)
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const qd = useDebounce(q, 300)

  const { data: people } = useFetch<any[]>('/users', { active: true, limit: 300 })
  const { data: deps } = useFetch<any[]>('/departments', { active: true })
  const { data, loading } = useFetch<any>('/tasks', {
    status: status || undefined, assignee_id: assignee || undefined,
    department_id: dep || undefined, overdue: overdue || undefined,
    q: qd || undefined, page, per_page: 50,
  })

  const clear = () => { setStatus(''); setAssignee(''); setDep(''); setOverdue(false); setQ(''); setPage(1) }
  const on = (fn: (v: any) => void) => (e: any) => { fn(e.target.value); setPage(1) }
  const items = data?.items || []
  const pages = Math.max(1, Math.ceil((data?.total || 0) / (data?.per_page || 50)))

  return (
    <>
      <PageHeader title={t('nav_tasks')} extra={<span className="chip">{data?.total ?? 0}</span>}>
        <button className="btn btn--p" onClick={() => setCreating(true)}>{t('new_task')}</button>
      </PageHeader>

      <div className="bar">
        <input className="inp inp--sm" placeholder={t('search')} value={q} onChange={on(setQ)} />
        <select className="sel sel--sm" value={status} onChange={on(setStatus)}>
          <option value="">{t('f_status')}: {t('all')}</option>
          {STATUSES.map(s => <option key={s} value={s}>{t(STATUS_KEY[s])}</option>)}
        </select>
        <select className="sel sel--sm" value={assignee} onChange={on(setAssignee)}>
          <option value="">{t('f_assignee')}: {t('all')}</option>
          {people?.map(p => <option key={p.id} value={p.id}>{p.full_name}</option>)}
        </select>
        <select className="sel sel--sm" value={dep} onChange={on(setDep)}>
          <option value="">{t('f_dep')}: {t('all')}</option>
          {deps?.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
        <label className="row small nowrap">
          <input type="checkbox" checked={overdue} onChange={e => { setOverdue(e.target.checked); setPage(1) }} />
          {t('f_overdue')}
        </label>
        <button className="btn btn--sm btn--ghost" onClick={clear}>{t('f_clear')}</button>
      </div>

      <div className="content">
        {loading && !items.length && <div className="empty">{t('loading')}</div>}
        {!loading && !items.length && <div className="empty">{t('t_none')}</div>}
        {!!items.length && (
          <div className="tbl-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th>{t('t_code')}</th><th>{t('t_title')}</th><th>{t('t_who')}</th>
                  <th>{t('t_due')}</th><th>{t('t_status')}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((tk: any) => (
                  <tr key={tk.id} className="clickable" onClick={() => nav(`/tasks/${tk.id}`)}>
                    <td className="mono small nowrap">{tk.code}</td>
                    <td>
                      <div className="b">{tk.title}</div>
                      {!!tk.return_count && <span className="pill pill--w">↩️ {tk.return_count}</span>}
                    </td>
                    <td>
                      <div>{tk.assignee_name}</div>
                      {tk.department_name && <div className="xs muted">{tk.department_name}</div>}
                    </td>
                    <td className="mono small nowrap">
                      {dt(tk.due_at)}
                      {tk.is_late && <div className="xs is-bad">
                        {tk.late_days ? t('late_days', { d: tk.late_days })
                          : t('late_hours', { h: Math.max(1, tk.late_hours) })}
                      </div>}
                    </td>
                    <td className="nowrap">
                      <span className={'pill ' + (STATUS_PILL[tk.status] || 'pill--g')}>
                        {t(STATUS_KEY[tk.status])}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {pages > 1 && (
          <div className="row" style={{ marginTop: 12, justifyContent: 'center' }}>
            <button className="btn btn--sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>◀</button>
            <span className="mono small">{page} / {pages}</span>
            <button className="btn btn--sm" disabled={page >= pages} onClick={() => setPage(p => p + 1)}>▶</button>
          </div>
        )}
      </div>

      {id && <TaskDrawer id={Number(id)} onClose={() => nav('/tasks')} />}
      {creating && <CreateTask onClose={() => setCreating(false)} />}
    </>
  )
}
