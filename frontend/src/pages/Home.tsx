import React, { useState } from 'react'
import CreateTask from '../components/CreateTask'
import { PageHeader } from '../components/Layout'
import TaskDrawer from '../components/TaskDrawer'
import { dt, STATUS_KEY, STATUS_PILL } from '../lib/fmt'
import { useFetch } from '../lib/hooks'
import { useT } from '../lib/i18n'

function Kpi({ n, label, tone, onClick }:
  { n: number | string; label: string; tone?: string; onClick?: () => void }) {
  return (
    <div className={'kpi' + (onClick ? '' : ' kpi--flat')} onClick={onClick}>
      <strong className={tone}>{n}</strong>
      <span>{label}</span>
    </div>
  )
}

function TaskRow({ tk, onOpen }: { tk: any; onOpen: (id: number) => void }) {
  const { t } = useT()
  return (
    <tr className="clickable" onClick={() => onOpen(tk.id)}>
      <td className="mono small nowrap">{tk.code}</td>
      <td><div className="b">{tk.title}</div><div className="xs muted">{tk.assignee_name}</div></td>
      <td className="mono small nowrap">{dt(tk.due_at)}</td>
      <td className="nowrap">
        {tk.is_late
          ? <span className="pill pill--b">{tk.late_days
            ? t('late_days', { d: tk.late_days })
            : t('late_hours', { h: Math.max(1, tk.late_hours) })}</span>
          : <span className={'pill ' + (STATUS_PILL[tk.status] || 'pill--g')}>{t(STATUS_KEY[tk.status])}</span>}
      </td>
    </tr>
  )
}

export default function Home() {
  const { t } = useT()
  const [open, setOpen] = useState<number | null>(null)
  const [creating, setCreating] = useState(false)
  const { data: d } = useFetch<any>('/reports/dashboard')
  const { data: late } = useFetch<any>('/tasks', { overdue: true, per_page: 8 })
  const { data: sub } = useFetch<any>('/tasks', { status: 'submitted', per_page: 8 })

  return (
    <>
      <PageHeader title={t('nav_home')}>
        <button className="btn btn--p" onClick={() => setCreating(true)}>{t('new_task')}</button>
      </PageHeader>

      <div className="kpis">
        <Kpi n={d?.late_tasks ?? '—'} label={t('k_late')} tone={d?.late_tasks ? 'is-bad' : ''} />
        <Kpi n={d?.submitted_tasks ?? '—'} label={t('k_submitted')} tone={d?.submitted_tasks ? 'is-warn' : ''} />
        <Kpi n={d?.due_today ?? '—'} label={t('k_today')} />
        <Kpi n={d?.open_tasks ?? '—'} label={t('k_open')} />
        <Kpi n={d ? `${d.percent_this_month}%` : '—'} label={t('k_percent')}
             tone={d && d.percent_this_month >= 80 ? 'is-good' : ''} />
      </div>

      <div className="content grid2">
        <section className="panel">
          <div className="panel__h"><b>{t('home_late')}</b>
            <span className="chip">{late?.total ?? 0}</span></div>
          {late?.items?.length
            ? <div className="tbl-wrap"><table className="tbl"><tbody>
                {late.items.map((x: any) => <TaskRow key={x.id} tk={x} onOpen={setOpen} />)}
              </tbody></table></div>
            : <div className="empty">{t('home_none')}</div>}
        </section>

        <section className="panel">
          <div className="panel__h"><b>{t('home_sub')}</b>
            <span className="chip">{sub?.total ?? 0}</span></div>
          {sub?.items?.length
            ? <div className="tbl-wrap"><table className="tbl"><tbody>
                {sub.items.map((x: any) => <TaskRow key={x.id} tk={x} onOpen={setOpen} />)}
              </tbody></table></div>
            : <div className="empty">{t('empty')}</div>}
        </section>
      </div>

      {open && <TaskDrawer id={open} onClose={() => setOpen(null)} />}
      {creating && <CreateTask onClose={() => setCreating(false)} />}
    </>
  )
}
