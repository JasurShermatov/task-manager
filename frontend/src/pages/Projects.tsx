import React, { useState } from 'react'
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
  const { data: projects, reload } = useFetch<any[]>('/projects', { include_inactive: true })
  const [sel, setSel] = useState<number | null>(null)
  const pid = sel ?? projects?.[0]?.id ?? null
  const { data: locs, reload: reloadLocs } = useFetch<any[]>(pid ? '/locations' : null, pid ? { project_id: pid } : undefined)
  const [newProject, setNewProject] = useState(false)
  const [adding, setAdding] = useState<{ parent: any | null; kind: string } | null>(null)
  const [name, setName] = useState('')

  const addLoc = async () => {
    if (!name.trim() || !adding) return
    try {
      await post('/locations', { project_id: pid, parent_id: adding.parent?.id ?? null, name: name.trim(), kind: adding.kind,
                                 sort_order: (locs?.filter(l => l.parent_id === (adding.parent?.id ?? null)).length || 0) })
      setName(''); setAdding(null); reloadLocs(); invalidate()
    } catch (e) { toastErr(e) }
  }
  const children = (parent: number | null) => (locs || []).filter(l => l.parent_id === parent).sort((a, b) => a.sort_order - b.sort_order)
  const editable = can('admin.projects')

  const Node = ({ l }: { l: any }) => (
    <li>
      <span className="row">
        <b>{l.name}</b><span className="kind">{l.kind}</span>
        {editable && l.kind !== 'zone' && (
          <button className="btn btn--sm btn--ghost" onClick={() => { setAdding({ parent: l, kind: l.kind === 'block' ? 'floor' : 'zone' }); setName('') }}>
            {l.kind === 'block' ? t('pj_add_floor') : t('pj_add_zone')}</button>
        )}
      </span>
      {!!children(l.id).length && <ul>{children(l.id).map(c => <Node key={c.id} l={c} />)}</ul>}
    </li>
  )

  return (
    <>
      <PageHeader title={t('pj_title')}>
        {editable && <button className="btn btn--sm btn--p" onClick={() => setNewProject(true)}>+ {t('pj_new')}</button>}
      </PageHeader>
      <div className="content">
        <div className="grid2">
          <div>
            <h3>{t('nav_projects')}</h3>
            <div className="tbl-wrap">
              <table className="tbl">
                <thead><tr><th>{t('pj_code')}</th><th>{t('pj_name')}</th><th /></tr></thead>
                <tbody>{(projects || []).map(p => (
                  <tr key={p.id} className="clickable" style={{ opacity: p.is_active ? 1 : .5, background: p.id === pid ? 'var(--bg-3)' : undefined }} onClick={() => setSel(p.id)}>
                    <td className="mono small">{p.code}</td><td><b>{p.name}</b></td>
                    <td style={{ textAlign: 'right' }}>{editable &&
                      <button className="btn btn--sm btn--ghost" onClick={async e => { e.stopPropagation(); await patch(`/projects/${p.id}`, { is_active: !p.is_active }); reload() }}>
                        {p.is_active ? t('ty_archive') : t('ty_restore')}</button>}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </div>
          <div>
            <div className="row"><h3 style={{ margin: 0 }}>{t('pj_locations')}</h3><span className="spacer" />
              {editable && pid && <button className="btn btn--sm" onClick={() => { setAdding({ parent: null, kind: 'block' }); setName('') }}>{t('pj_add_block')}</button>}</div>
            <div className="tree blk" style={{ marginTop: 10 }}>
              {!children(null).length && <div className="muted small">{t('empty')}</div>}
              <ul style={{ paddingLeft: 0 }}>{children(null).map(l => <Node key={l.id} l={l} />)}</ul>
            </div>
          </div>
        </div>
      </div>
      {adding && (
        <Modal title={t('pj_loc_name')} sm onClose={() => setAdding(null)} footer={
          <><button className="btn" onClick={() => setAdding(null)}>{t('cancel')}</button>
            <button className="btn btn--p" disabled={!name.trim()} onClick={addLoc}>{t('add')}</button></>}>
          <label className="lbl full">{adding.kind}
            <input className="inp" autoFocus value={name} onChange={e => setName(e.target.value)} onKeyDown={e => e.key === 'Enter' && addLoc()} /></label>
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
      <label className="lbl full">{t('pj_code')} <i>*</i><input className="inp" value={f.code} onChange={e => setF({ ...f, code: e.target.value.toUpperCase() })} /></label>
      <label className="lbl full">{t('pj_name')} <i>*</i><input className="inp" value={f.name} onChange={e => setF({ ...f, name: e.target.value })} /></label>
    </Modal>
  )
}
