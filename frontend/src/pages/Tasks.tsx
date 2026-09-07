import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { API_BASE, post, invalidate, tokens } from '../lib/api'
import { useFetch, useDebounce } from '../lib/hooks'
import { useT, fmtDate, STATUS_COLOR, STATUS_ORDER } from '../lib/i18n'
import { useToast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { useRefs, locLabel, initials } from '../lib/refs'
import { PageHeader } from '../components/Layout'
import { TaskCardView, StatusDot } from '../components/TaskCard'
import TaskDrawer from '../components/TaskDrawer'
import CreateTask from '../components/CreateTask'

export default function TasksPage({ view }: { view: 'board' | 'table' }) {
  const { t, lang } = useT()
  const { can } = useAuth()
  const { toastErr, toast } = useToast()
  const nav = useNavigate()
  const { id } = useParams()
  const [sp, setSp] = useSearchParams()
  const [creating, setCreating] = useState(false)
  const { projects, users, types, locations } = useRefs(sp.get('project_id') ? Number(sp.get('project_id')) : null)

  const [qRaw, setQRaw] = useState(sp.get('q') || '')
  const q = useDebounce(qRaw, 350)
  useEffect(() => { setParam('q', q || null) }, [q])

  const setParam = (k: string, v: string | null) => {
    const n = new URLSearchParams(sp)
    if (v === null || v === '') n.delete(k); else n.set(k, v)
    if (k !== 'offset') n.delete('offset')
    setSp(n, { replace: true })
  }
  const toggleParam = (k: string) => setParam(k, sp.get(k) ? null : '1')

  const params = useMemo(() => {
    const o: any = { limit: view === 'board' ? 200 : 50, offset: Number(sp.get('offset') || 0) }
    for (const k of ['q', 'project_id', 'location_id', 'type_id', 'assignee_id', 'reviewer_id', 'priority', 'status', 'overdue', 'blocked', 'mine', 'sort', 'order'])
      if (sp.get(k)) o[k] = sp.get(k)
    if (view === 'board') { o.limit = 300; delete o.offset }
    return o
  }, [sp, view])

  const { data: page, loading, reload } = useFetch<any>('/tasks', params)
  const { data: sum } = useFetch<any>(can('reports.read') ? '/reports/summary' : null, sp.get('project_id') ? { project_id: sp.get('project_id') } : undefined)

  const items: any[] = page?.items || []
  const byStatus = useMemo(() => {
    const m: Record<string, any[]> = { plan: [], progress: [], review: [], blocked: [], done: [] }
    for (const it of items) if (m[it.status]) m[it.status].push(it)
    return m
  }, [items])

  const kpi = sum?.kpi
  const openId = id ? Number(id) : null
  const base = view === 'board' ? '/tasks' : '/table'

  const [drag, setDrag] = useState<any>(null)
  const [over, setOver] = useState<string | null>(null)
  const drop = async (status: string) => {
    setOver(null)
    const tk = drag
    setDrag(null)
    if (!tk || tk.status === status) return
    try {
      if (status === 'blocked') { nav(`${base}/${tk.id}`); return }
      if (status === 'done') await post(`/tasks/${tk.id}/accept`)
      else if (status === 'review') await post(`/tasks/${tk.id}/submit-review`)
      else if (status === 'progress' && tk.status === 'plan') await post(`/tasks/${tk.id}/start`)
      else if (status === 'progress' && tk.status === 'review') { nav(`${base}/${tk.id}`); return }
      else if (status === 'progress' && tk.status === 'blocked') await post(`/tasks/${tk.id}/unblock`)
      else await post(`/tasks/${tk.id}/transition`, { to: status })
      reload(); invalidate(); toast(t('updated'))
    } catch (e) { toastErr(e); reload() }
  }

  const exportCsv = () => {
    const u = new URL(API_BASE + '/reports/export.csv', window.location.origin)
    for (const [k, v] of Object.entries(params)) if (v && k !== 'limit' && k !== 'offset') u.searchParams.set(k, String(v))
    u.searchParams.set('lang', lang)
    fetch(u.toString(), { headers: { Authorization: `Bearer ${tokens.access}` } })
      .then(r => r.blob()).then(b => {
        const a = document.createElement('a')
        a.href = URL.createObjectURL(b)
        a.download = `vazifalar_${new Date().toISOString().slice(0, 10)}.csv`
        a.click(); URL.revokeObjectURL(a.href)
      }).catch(e => toastErr(e))
  }

  return (
    <>
      <PageHeader title={t('nav_tasks')} extra={
        <select className="sel sel--sm" value={sp.get('project_id') || ''} onChange={e => setParam('project_id', e.target.value || null)}>
          <option value="">{t('all')} — {t('f_project')}</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>}>
        <input className="inp inp--sm" style={{ minWidth: 200 }} placeholder={t('search')} value={qRaw} onChange={e => setQRaw(e.target.value)} />
        <div className="seg" style={{ background: 'var(--bg-3)' }}>
          <button className={view === 'board' ? 'on' : ''} style={view === 'board' ? { background: '#0b0b0c', color: '#fff' } : { color: 'var(--muted)' }} onClick={() => nav('/tasks?' + sp.toString())}>{t('board')}</button>
          <button className={view === 'table' ? 'on' : ''} style={view === 'table' ? { background: '#0b0b0c', color: '#fff' } : { color: 'var(--muted)' }} onClick={() => nav('/table?' + sp.toString())}>{t('table')}</button>
        </div>
        {can('tasks.export') && <button className="btn btn--sm" onClick={exportCsv}>↓ CSV</button>}
        {can('tasks.create') && <button className="btn btn--sm btn--p" onClick={() => setCreating(true)}>{t('new_task')}</button>}
      </PageHeader>

      {kpi && (
        <div className="kpis">
          <div className={'kpi' + (!sp.get('overdue') && !sp.get('blocked') && !sp.get('status') ? ' on' : '')} onClick={() => { setParam('overdue', null); setParam('blocked', null); setParam('status', null) }}>
            <strong>{kpi.open}</strong><span>{t('kpi_open')}</span><small>{kpi.total} {t('r_total').toLowerCase()}</small></div>
          <div className={'kpi' + (sp.get('overdue') ? ' on' : '')} onClick={() => toggleParam('overdue')}>
            <strong className="c-block">{kpi.overdue}</strong><span>{t('kpi_overdue')}</span>
            <small>{kpi.overdue_by_assignee} {t('r_overdue_assignee')} · {kpi.overdue_by_reviewer} {t('r_overdue_reviewer')}</small></div>
          <div className={'kpi' + (sp.get('blocked') ? ' on' : '')} onClick={() => toggleParam('blocked')}>
            <strong className="c-review">{kpi.blocked}</strong><span>{t('kpi_blocked')}</span>
            <small>{sum.blocked_reasons?.[0] ? t('br_' + sum.blocked_reasons[0].code) : '—'}</small></div>
          <div className={'kpi' + (sp.get('status') === 'review' ? ' on' : '')} onClick={() => setParam('status', sp.get('status') === 'review' ? null : 'review')}>
            <strong className="c-review">{kpi.review}</strong><span>{t('kpi_review')}</span><small>{t('kpi_oldest', { d: kpi.review_oldest_days })}</small></div>
          <div className="kpi" onClick={() => setParam('status', sp.get('status') === 'done' ? null : 'done')}>
            <strong className="c-done">{kpi.on_time_pct ?? '—'}{kpi.on_time_pct != null ? '%' : ''}</strong><span>{t('kpi_ontime')}</span>
            <small>{t('kpi_month', { n: kpi.done })}</small></div>
        </div>
      )}

      <div className="bar">
        <select className="sel sel--sm" value={sp.get('location_id') || ''} onChange={e => setParam('location_id', e.target.value || null)}>
          <option value="">{t('f_location')}</option>
          {locations.map(l => <option key={l.id} value={l.id}>{locLabel(locations, l.id)}</option>)}
        </select>
        <select className="sel sel--sm" value={sp.get('type_id') || ''} onChange={e => setParam('type_id', e.target.value || null)}>
          <option value="">{t('f_type')}</option>
          {types.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}
        </select>
        <select className="sel sel--sm" value={sp.get('assignee_id') || ''} onChange={e => setParam('assignee_id', e.target.value || null)}>
          <option value="">{t('f_assignee')}</option>
          {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
        </select>
        <select className="sel sel--sm" value={sp.get('priority') || ''} onChange={e => setParam('priority', e.target.value || null)}>
          <option value="">{t('f_priority')}</option>
          {['high', 'normal', 'low'].map(p => <option key={p} value={p}>{t('pr_' + p)}</option>)}
        </select>
        <button className={'tog al' + (sp.get('overdue') ? ' on' : '')} onClick={() => toggleParam('overdue')}>⏱ {t('f_overdue')}</button>
        <button className={'tog al' + (sp.get('blocked') ? ' on' : '')} onClick={() => toggleParam('blocked')}>⛔ {t('f_blocked')}</button>
        <button className={'tog' + (sp.get('mine') ? ' on' : '')} onClick={() => toggleParam('mine')}>{t('f_mine')}</button>
        <span className="spacer" />
        {[...sp.keys()].length > 0 && <button className="btn btn--sm btn--ghost" onClick={() => setSp(new URLSearchParams(), { replace: true })}>{t('f_clear')}</button>}
        <span className="mono xs faint">{page?.total ?? 0}</span>
      </div>

      {loading && !items.length && <div className="empty">{t('loading')}</div>}

      {view === 'board' ? (
        <div className="board">
          {STATUS_ORDER.map(st => (
            <div key={st} className={'col' + (over === st ? ' over' : '')}
                 onDragOver={e => { e.preventDefault(); setOver(st) }}
                 onDragLeave={() => setOver(o => o === st ? null : o)}
                 onDrop={e => { e.preventDefault(); drop(st) }}>
              <div className="col__h"><span className="sq" style={{ background: STATUS_COLOR[st] }} /><b>{t('st_' + st)}</b><em>{byStatus[st].length}</em></div>
              <div className="col__b">
                {byStatus[st].map(tk => (
                  <TaskCardView key={tk.id} tk={tk} draggable onClick={() => nav(`${base}/${tk.id}?${sp.toString()}`)}
                                onDragStart={() => setDrag(tk)} onDragEnd={() => { setDrag(null); setOver(null) }} />
                ))}
                {!byStatus[st].length && <div className="xs faint" style={{ padding: 8, textAlign: 'center' }}>—</div>}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <TableView items={items} page={page} sp={sp} setParam={setParam} onOpen={(tid: number) => nav(`${base}/${tid}?${sp.toString()}`)} />
      )}

      {openId && <TaskDrawer id={openId} onClose={() => nav(`${base}?${sp.toString()}`)} />}
      {creating && <CreateTask onClose={() => setCreating(false)} defaults={{ project_id: sp.get('project_id') ? Number(sp.get('project_id')) : undefined, location_id: sp.get('location_id') ? Number(sp.get('location_id')) : undefined }}
                               onCreated={tk => { setCreating(false); reload(); nav(`${base}/${tk.id}?${sp.toString()}`) }} />}
    </>
  )
}

function TableView({ items, page, sp, setParam, onOpen }: any) {
  const { t, lang } = useT()
  const sort = sp.get('sort') || 'planned_end'
  const order = sp.get('order') || 'asc'
  const th = (key: string, label: string) => (
    <th onClick={() => { setParam('sort', key); setParam('order', sort === key && order === 'asc' ? 'desc' : 'asc') }}>
      {label}{sort === key ? (order === 'asc' ? ' ↑' : ' ↓') : ''}
    </th>
  )
  const offset = Number(sp.get('offset') || 0)
  const limit = 50
  return (
    <div className="content">
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr>
            {th('code', t('t_code'))}{th('title', t('t_title'))}
            <th>{t('t_location')}</th>{th('status', t('t_status'))}{th('priority', t('t_priority'))}
            <th>{t('t_assignee')}</th><th>{t('t_reviewer')}</th>{th('planned_end', t('t_end'))}{th('progress_percent', t('t_progress'))}
          </tr></thead>
          <tbody>
            {items.map((tk: any) => (
              <tr key={tk.id} className="clickable" onClick={() => onOpen(tk.id)}>
                <td className="mono xs">{tk.code}</td>
                <td><b>{tk.title}</b>{tk.return_count > 0 && <span className="pill pill--g" style={{ marginLeft: 6 }}>↩{tk.return_count}</span>}</td>
                <td className="xs muted">{tk.location_path?.map((p: any) => p.name).join(' · ') || tk.project_name}</td>
                <td><span className="st"><StatusDot s={tk.status} />{t('st_' + tk.status)}</span>
                  {tk.status === 'blocked' && <div className="xs muted">{t('br_' + tk.blocked_reason)}</div>}</td>
                <td><span className={`pri pri--${tk.priority}`}>{t('pr_' + tk.priority)}</span></td>
                <td className="small"><span className="av" style={{ marginRight: 5 }}>{initials(tk.assignee_name)}</span>{tk.assignee_name}</td>
                <td className="small">{tk.reviewer_name}</td>
                <td className={'mono small' + (tk.overdue_days > 0 ? ' c-block b' : '')}>{fmtDate(tk.planned_end, lang)}{tk.overdue_days > 0 ? ` (+${tk.overdue_days})` : ''}</td>
                <td style={{ minWidth: 90 }}>
                  <div className="prog"><i className={tk.status === 'done' ? 'd' : tk.status === 'review' ? 'w' : 'b'} style={{ width: `${tk.progress_percent}%` }} /></div>
                  <span className="mono xs faint">{tk.progress_percent}% · ☑{tk.checklist_done}/{tk.checklist_total}</span>
                </td>
              </tr>
            ))}
            {!items.length && <tr><td colSpan={9}><div className="empty">{t('empty')}</div></td></tr>}
          </tbody>
        </table>
      </div>
      <div className="pagin">
        <button className="btn btn--sm" disabled={offset <= 0} onClick={() => setParam('offset', String(Math.max(0, offset - limit)))}>← {t('t_prev')}</button>
        <span>{t('t_page', { a: offset + 1, b: Math.min(offset + limit, page?.total || 0), n: page?.total || 0 })}</span>
        <button className="btn btn--sm" disabled={offset + limit >= (page?.total || 0)} onClick={() => setParam('offset', String(offset + limit))}>{t('t_next')} →</button>
      </div>
    </div>
  )
}
