import React, { useState } from 'react'
import { patch, post, invalidate } from '../lib/api'
import { useFetch } from '../lib/hooks'
import { useT } from '../lib/i18n'
import { useToast } from '../lib/toast'
import { PageHeader } from '../components/Layout'
import { Modal } from '../components/Modal'

const KINDS = ['before', 'during', 'after', 'document']

export default function Types() {
  const { t } = useT()
  const [showArchived, setShowArchived] = useState(false)
  const { data, reload } = useFetch<any[]>('/task-types', { include_inactive: true })
  const [edit, setEdit] = useState<any>(null)
  const rows = (data || []).filter(x => showArchived || x.is_active)
  return (
    <>
      <PageHeader title={t('ty_title')}>
        <label className="check"><input type="checkbox" checked={showArchived} onChange={e => setShowArchived(e.target.checked)} />{t('ty_archived')}</label>
        <button className="btn btn--sm btn--p" onClick={() => setEdit({ name: '', group_name: '', default_duration_days: 3, required_evidence_kinds: ['after'], default_checklist_json: [] })}>+ {t('ty_new')}</button>
      </PageHeader>
      <div className="content">
        <div className="alert alert--info" style={{ marginBottom: 16 }}>{t('ty_hint')}</div>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>{t('ty_name')}</th><th>{t('ty_group')}</th><th className="num">{t('ty_days')}</th><th>{t('ty_evidence')}</th><th className="num">{t('ty_checklist')}</th><th /></tr></thead>
            <tbody>{rows.map(x => (
              <tr key={x.id} style={{ opacity: x.is_active ? 1 : .5 }}>
                <td><b>{x.name}</b></td><td className="muted">{x.group_name || '—'}</td><td className="num">{x.default_duration_days}</td>
                <td className="small">{(x.required_evidence_kinds || []).map((k: string) => t('fl_' + k)).join(', ') || '—'}</td>
                <td className="num">{(x.default_checklist_json || []).length}</td>
                <td className="row" style={{ justifyContent: 'flex-end' }}>
                  <button className="btn btn--sm" onClick={() => setEdit(x)}>{t('edit')}</button>
                  <button className="btn btn--sm btn--ghost" onClick={async () => { await patch(`/task-types/${x.id}`, { is_active: !x.is_active }); reload(); invalidate() }}>
                    {x.is_active ? t('ty_archive') : t('ty_restore')}</button>
                </td>
              </tr>
            ))}
            {!rows.length && <tr><td colSpan={6}><div className="empty">{t('empty')}</div></td></tr>}</tbody>
          </table>
        </div>
      </div>
      {edit && <TypeDialog item={edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); reload(); invalidate() }} />}
    </>
  )
}

function TypeDialog({ item, onClose, onSaved }: any) {
  const { t } = useT()
  const { toastErr } = useToast()
  const [f, setF] = useState<any>({ ...item })
  const [ck, setCk] = useState<any[]>(item.default_checklist_json || [])
  const save = async () => {
    const body = { name: f.name, group_name: f.group_name || null, default_duration_days: Number(f.default_duration_days) || 1,
                   required_evidence_kinds: f.required_evidence_kinds, default_checklist_json: ck.filter(c => c.title.trim()).map((c, i) => ({ ...c, sort_order: i })) }
    try { item.id ? await patch(`/task-types/${item.id}`, body) : await post('/task-types', body); onSaved() } catch (e) { toastErr(e) }
  }
  const togKind = (k: string) => setF((s: any) => ({ ...s, required_evidence_kinds: s.required_evidence_kinds.includes(k) ? s.required_evidence_kinds.filter((x: string) => x !== k) : [...s.required_evidence_kinds, k] }))
  return (
    <Modal title={item.id ? t('edit') : t('ty_new')} onClose={onClose} footer={
      <><button className="btn" onClick={onClose}>{t('cancel')}</button><button className="btn btn--p" disabled={!f.name.trim()} onClick={save}>{t('save')}</button></>}>
      <label className="lbl">{t('ty_name')} <i>*</i><input className="inp" value={f.name} onChange={e => setF({ ...f, name: e.target.value })} /></label>
      <label className="lbl">{t('ty_group')}<input className="inp" value={f.group_name || ''} onChange={e => setF({ ...f, group_name: e.target.value })} /></label>
      <label className="lbl">{t('ty_days')}<input className="inp" type="number" min={1} value={f.default_duration_days} onChange={e => setF({ ...f, default_duration_days: e.target.value })} /></label>
      <div className="lbl">{t('ty_evidence')}
        <div className="row wrap">{KINDS.map(k => (
          <button key={k} className={'tog' + (f.required_evidence_kinds.includes(k) ? ' on' : '')} onClick={() => togKind(k)}>{t('fl_' + k)}</button>
        ))}</div></div>
      <div className="full">
        <div className="lbl" style={{ marginBottom: 6 }}>{t('ty_checklist')}</div>
        {ck.map((c, i) => (
          <div className="row" key={i} style={{ padding: '3px 0' }}>
            <input className="inp inp--sm" style={{ flex: 1 }} value={c.title} onChange={e => setCk(cs => cs.map((x, j) => j === i ? { ...x, title: e.target.value } : x))} />
            <label className="check"><input type="checkbox" checked={c.is_required !== false} onChange={e => setCk(cs => cs.map((x, j) => j === i ? { ...x, is_required: e.target.checked } : x))} />{t('required')}</label>
            <button className="btn btn--sm btn--ghost" onClick={() => setCk(cs => cs.filter((_, j) => j !== i))}>✕</button>
          </div>
        ))}
        <button className="btn btn--sm" style={{ marginTop: 6 }} onClick={() => setCk(cs => [...cs, { title: '', is_required: true }])}>+ {t('a_add_item')}</button>
      </div>
    </Modal>
  )
}
