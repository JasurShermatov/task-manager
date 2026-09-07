import React, { useState } from 'react'
import { API_BASE, tokens } from '../lib/api'
import { useFetch } from '../lib/hooks'
import { useT, fmtDate } from '../lib/i18n'
import { useToast } from '../lib/toast'
import { useRefs } from '../lib/refs'
import { PageHeader } from '../components/Layout'
import { StatusDot } from '../components/TaskCard'

export default function Reports() {
  const { t, lang } = useT()
  const { toastErr } = useToast()
  const { projects } = useRefs()
  const [project, setProject] = useState<string>('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const params: any = {}
  if (project) params.project_id = project
  if (from) params.date_from = from
  if (to) params.date_to = to
  const { data, loading } = useFetch<any>('/reports/summary', params)

  const exportCsv = () => {
    const u = new URL(API_BASE + '/reports/export.csv', window.location.origin)
    for (const [k, v] of Object.entries(params)) u.searchParams.set(k, String(v))
    u.searchParams.set('lang', lang)
    fetch(u.toString(), { headers: { Authorization: `Bearer ${tokens.access}` } })
      .then(r => r.blob()).then(b => { const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = 'hisobot.csv'; a.click() })
      .catch(e => toastErr(e))
  }

  const k = data?.kpi
  const maxDaily = Math.max(1, ...(data?.daily_done || []).map((d: any) => d.done))
  const maxReason = Math.max(1, ...(data?.blocked_reasons || []).map((r: any) => r.count))
  return (
    <>
      <PageHeader title={t('r_title')}>
        <button className="btn btn--sm" onClick={exportCsv}>↓ CSV</button>
      </PageHeader>
      <div className="bar">
        <select className="sel sel--sm" value={project} onChange={e => setProject(e.target.value)}>
          <option value="">{t('all')} — {t('f_project')}</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <span className="small muted">{t('r_from')}</span>
        <input className="inp inp--sm" type="date" value={from} onChange={e => setFrom(e.target.value)} />
        <span className="small muted">{t('r_to')}</span>
        <input className="inp inp--sm" type="date" value={to} onChange={e => setTo(e.target.value)} />
      </div>
      {loading && <div className="empty">{t('loading')}</div>}
      {data && (
        <div className="content">
          <div className="kpis" style={{ border: '1px solid var(--line)', borderRadius: 8, marginBottom: 24, overflow: 'hidden' }}>
            <div className="kpi"><strong>{k.open}</strong><span>{t('kpi_open')}</span><small>{k.total} {t('r_total').toLowerCase()}</small></div>
            <div className="kpi"><strong className="c-block">{k.overdue}</strong><span>{t('kpi_overdue')}</span><small>{k.overdue_by_assignee} / {k.overdue_by_reviewer}</small></div>
            <div className="kpi"><strong className="c-review">{k.blocked}</strong><span>{t('kpi_blocked')}</span><small>&nbsp;</small></div>
            <div className="kpi"><strong className="c-done">{k.on_time_pct ?? '—'}{k.on_time_pct != null ? '%' : ''}</strong><span>{t('kpi_ontime')}</span><small>{k.done} {t('r_done').toLowerCase()}</small></div>
            <div className="kpi"><strong>{k.avg_duration_days ?? '—'}</strong><span>{t('r_avg')}</span><small>{t('r_days')} · {t('r_return')} {k.return_pct}%</small></div>
          </div>

          <div className="grid2">
            <div className="section">
              <h3>{t('r_by_status')}</h3>
              {Object.entries(data.by_status).map(([s, n]: any) => (
                <div className="hbar" key={s}>
                  <span className="row"><StatusDot s={s} />{t('st_' + s)}</span>
                  <i style={{ width: `${Math.round(n / Math.max(1, k.total) * 100)}%` }} />
                  <em>{n}</em>
                </div>
              ))}
            </div>
            <div className="section">
              <h3>{t('r_block_reasons')}</h3>
              {!data.blocked_reasons.length && <div className="muted small">{t('empty')}</div>}
              {data.blocked_reasons.map((r: any) => (
                <div className="hbar" key={r.code}>
                  <span>{t('br_' + r.code)}</span>
                  <i style={{ width: `${Math.round(r.count / maxReason * 100)}%`, background: 'var(--block)' }} />
                  <em>{r.count}{r.days ? ` · ${r.days}${t('r_block_days')}` : ''}</em>
                </div>
              ))}
            </div>
          </div>

          <div className="section">
            <h3>{t('r_daily')}</h3>
            <div className="bars" style={{ marginBottom: 24 }}>
              {data.daily_done.map((d: any) => (
                <div key={d.date} style={{ height: `${Math.max(2, d.done / maxDaily * 100)}%` }} title={`${d.date}: ${d.done}`}>
                  <span>{d.date.slice(8)}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="section">
            <h3>{t('r_staff')}</h3>
            <div className="tbl-wrap">
              <table className="tbl">
                <thead><tr><th>{t('r_name')}</th><th className="num">{t('r_total')}</th><th className="num">{t('r_open')}</th><th className="num">{t('r_done')}</th>
                  <th className="num">{t('r_ontime')}</th><th className="num">{t('r_return')}</th><th className="num">{t('r_overdue')}</th></tr></thead>
                <tbody>{data.staff.map((s: any) => (
                  <tr key={s.user_id}><td><b>{s.name}</b></td><td className="num">{s.total}</td><td className="num">{s.open}</td><td className="num">{s.done}</td>
                    <td className="num">{s.on_time_pct ?? '—'}</td><td className="num">{s.return_pct}</td>
                    <td className={'num' + (s.overdue ? ' c-block b' : '')}>{s.overdue}</td></tr>
                ))}
                {!data.staff.length && <tr><td colSpan={7}><div className="empty">{t('empty')}</div></td></tr>}</tbody>
              </table>
            </div>
          </div>

          <div className="section">
            <h3>{t('r_reviewers')}</h3>
            <div className="tbl-wrap">
              <table className="tbl">
                <thead><tr><th>{t('r_name')}</th><th className="num">{t('r_queue')}</th></tr></thead>
                <tbody>{data.reviewers.filter((r: any) => r.queue > 0).map((r: any) => (
                  <tr key={r.user_id}><td>{r.name}</td><td className="num">{r.queue}</td></tr>
                ))}
                {!data.reviewers.some((r: any) => r.queue > 0) && <tr><td colSpan={2}><div className="empty">{t('empty')}</div></td></tr>}</tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
