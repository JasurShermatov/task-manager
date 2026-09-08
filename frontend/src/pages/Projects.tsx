import React, { useMemo, useState } from 'react'
import { patch, post, invalidate } from '../lib/api'
import { useFetch } from '../lib/hooks'
import { useT } from '../lib/i18n'
import { useToast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { PageHeader } from '../components/Layout'
import { Modal } from '../components/Modal'

export default function Projects() {
  const { t } = useT()
  const { can } = useAuth()
  const { toastErr } = useToast()
  const editable = can('admin.projects')

  const { data: projects, reload } = useFetch<any[]>('/projects', { include_inactive: true })
  const { data: stats } = useFetch<any>('/projects/stats')
  const [q, setQ] = useState('')
  const [sel, setSel] = useState<number | null>(null)
  const [newProject, setNewProject] = useState(false)
  const [adding, setAdding] = useState<{ parent: any | null; kind: string } | null>(null)
  const [name, setName] = useState('')

  const rows = useMemo(() => {
    const s = q.trim().toLowerCase()
    return (projects || []).filter(p => !s || p.name.toLowerCase().includes(s) || p.code.toLowerCase().includes(s))
  }, [projects, q])

  const pid = rows.some(p => p.id === sel) ? sel : rows[0]?.id ?? null
  const current = rows.find(p => p.id === pid) || null
  const { data: locs, reload: reloadLocs } = useFetch<any[]>(pid ? '/locations' : null, pid ? { project_id: pid } : undefined)

  const children = (parent: number | null) =>
    (locs || []).filter(l => l.parent_id === parent).sort((a, b) => a.sort_order - b.sort_order)
  const counts = useMemo(() => {
    const all = locs || []
    return { blocks: all.filter(l => l.kind === 'block').length,
             floors: all.filter(l => l.kind === 'floor').length,
             zones: all.filter(l => l.kind === 'zone').length }
  }, [locs])

  const addLoc = async () => {
    if (!name.trim() || !adding) return
    try {
      await post('/locations', {
        project_id: pid, parent_id: adding.parent?.id ?? null, name: name.trim(), kind: adding.kind,
        sort_order: children(adding.parent?.id ?? null).length,
      })
      setName(''); setAdding(null); reloadLocs(); invalidate()
    } catch (e) { toastErr(e) }
  }
  const archive = async (p: any) => {
    try { await patch(`/projects/${p.id}`, { is_active: !p.is_active }); reload() } catch (e) { toastErr(e) }
  }

  const Node = ({ l, depth }: { l: any; depth: number }) => {
    const kids = children(l.id)
    return (
      <li className={'node node--' + l.kind}>
        <div className="node__row">
          <span className="node__name">{l.name}</span>
          <span className="node__kind">{t('pj_' + (l.kind === 'block' ? 'blocks' : l.kind === 'floor' ? 'floors' : 'zones'))}</span>
          {!!kids.length && <span className="node__count">{kids.length}</span>}
          {editable && l.kind !== 'zone' && (
            <button className="btn btn--sm btn--ghost node__add"
                    onClick={() => { setAdding({ parent: l, kind: l.kind === 'block' ? 'floor' : 'zone' }); setName('') }}>
              {l.kind === 'block' ? t('pj_add_floor') : t('pj_add_zone')}
            </button>
          )}
        </div>
        {!!kids.length && <ul>{kids.map(c => <Node key={c.id} l={c} depth={depth + 1} />)}</ul>}
      </li>
    )
  }

  return (
    <>
      <PageHeader title={t('pj_title')} extra={<span className="chip">{rows.length}</span>}>
        <input className="inp inp--sm" placeholder={t('pj_search')} value={q} onChange={e => setQ(e.target.value)} />
        {editable && <button className="btn btn--sm btn--p" onClick={() => setNewProject(true)}>+ {t('pj_new')}</button>}
      </PageHeader>

      <div className="content split">
        <div className="split__list">
          {!rows.length && <div className="empty">{t('empty')}</div>}
          {rows.map(p => {
            const st = stats?.[p.id]
            return (
              <button key={p.id} className={'site' + (pid === p.id ? ' site--on' : '') + (p.is_active ? '' : ' site--off')}
                      onClick={() => setSel(p.id)}>
                <div className="site__top">
                  <span className="code">{p.code}</span>
                  {!p.is_active && <span className="pill pill--g">{t('pj_archived')}</span>}
                </div>
                <div className="site__name">{p.name}</div>
                <div className="site__meta">
                  <span>{st?.total ?? 0} {t('pj_tasks')}</span>
                  <span>· {st?.open ?? 0} {t('pj_open')}</span>
                  {!!st?.overdue && <span className="c-block b">· {st.overdue} {t('pj_late')}</span>}
                </div>
              </button>
            )
          })}
        </div>

        <div className="split__pane">
          {!current ? <div className="empty">{t('pj_pick')}</div> : (
            <>
              <div className="row wrap" style={{ marginBottom: 16 }}>
                <div style={{ minWidth: 0 }}>
                  <div className="row" style={{ gap: 8 }}>
                    <span className="code">{current.code}</span>
                    <span className={'pill ' + (current.is_active ? 'pill--ok' : 'pill--g')}>
                      {current.is_active ? t('pj_active') : t('pj_archived')}</span>
                  </div>
                  <h2 style={{ margin: '6px 0 0', fontSize: 22, fontWeight: 800, letterSpacing: '-.01em' }}>{current.name}</h2>
                </div>
                <span className="spacer" />
                {editable && <button className="btn btn--sm btn--ghost" onClick={() => archive(current)}>
                  {current.is_active ? t('ty_archive') : t('ty_restore')}</button>}
              </div>

              <div className="stats" style={{ marginBottom: 18 }}>
                <div><b>{counts.blocks}</b><span>{t('pj_blocks')}</span></div>
                <div><b>{counts.floors}</b><span>{t('pj_floors')}</span></div>
                <div><b>{counts.zones}</b><span>{t('pj_zones')}</span></div>
                <div><b>{stats?.[current.id]?.total ?? 0}</b><span>{t('pj_tasks')}</span></div>
              </div>

              <div className="blk">
                <div className="blk__t">{t('pj_locations')}
                  {editable && <button className="btn btn--sm" style={{ marginLeft: 'auto' }}
                                       onClick={() => { setAdding({ parent: null, kind: 'block' }); setName('') }}>{t('pj_add_block')}</button>}
                </div>
                {!children(null).length
                  ? <div className="empty" style={{ padding: 24 }}>{editable ? t('pj_add_first') : t('pj_empty_locs')}</div>
                  : <ul className="tree tree--root">{children(null).map(l => <Node key={l.id} l={l} depth={0} />)}</ul>}
              </div>
            </>
          )}
        </div>
      </div>

      {adding && (
        <Modal title={adding.parent ? `${adding.parent.name} → ${t('pj_' + (adding.kind === 'floor' ? 'floors' : 'zones'))}` : t('pj_add_block')}
               sm onClose={() => setAdding(null)} footer={
          <><button className="btn" onClick={() => setAdding(null)}>{t('cancel')}</button>
            <button className="btn btn--p" disabled={!name.trim()} onClick={addLoc}>{t('add')}</button></>}>
          <label className="lbl full">{t('pj_loc_name')}
            <input className="inp" autoFocus value={name} onChange={e => setName(e.target.value)}
                   onKeyDown={e => e.key === 'Enter' && addLoc()} /></label>
        </Modal>
      )}
      {newProject && <NewProject onClose={() => setNewProject(false)} onSaved={() => { setNewProject(false); reload() }} />}
    </>
  )
}

function NewProject({ onClose, onSaved }: any) {
  const { t } = useT()
  const { toastErr } = useToast()
  const [f, setF] = useState({ code: '', name: '' })
  const save = async () => { try { await post('/projects', f); onSaved() } catch (e) { toastErr(e) } }
  return (
    <Modal title={t('pj_new')} sm onClose={onClose} footer={
      <><button className="btn" onClick={onClose}>{t('cancel')}</button>
        <button className="btn btn--p" disabled={!f.code.trim() || !f.name.trim()} onClick={save}>{t('save')}</button></>}>
      <label className="lbl full">{t('pj_code')} <i>*</i>
        <input className="inp" value={f.code} placeholder="YUN-01" onChange={e => setF({ ...f, code: e.target.value.toUpperCase() })} /></label>
      <label className="lbl full">{t('pj_name')} <i>*</i>
        <input className="inp" autoFocus value={f.name} onChange={e => setF({ ...f, name: e.target.value })} /></label>
    </Modal>
  )
}
