import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { patch, post, invalidate } from '../lib/api'
import { useFetch } from '../lib/hooks'
import { useT, fmtDate } from '../lib/i18n'
import { useToast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { useRefs, locLabel } from '../lib/refs'
import { PageHeader } from '../components/Layout'
import { Modal } from '../components/Modal'

const DAYS = ['MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU']

export default function Templates() {
  const { t, lang } = useT()
  const { can } = useAuth()
  const { data, reload } = useFetch<any[]>('/task-templates', { include_inactive: true })
  const { data: rules, reload: reloadRules } = useFetch<any[]>(can('tasks.bulk_create') ? '/task-recurring-rules' : null)
  const { types, users, projects } = useRefs()
  const [edit, setEdit] = useState<any>(null)
  const [use, setUse] = useState<any>(null)
  const [rule, setRule] = useState<any>(null)
  return (
    <>
      <PageHeader title={t('tp_title')}>
        <button className="btn btn--sm btn--p" onClick={() => setEdit({ name: '', type_id: types[0]?.id, title_pattern: '', default_duration_days: 3, checklist_json: [], required_evidence_kinds: [] })}>+ {t('tp_new')}</button>
      </PageHeader>
      <div className="content">
        <div className="tbl-wrap section">
          <table className="tbl">
            <thead><tr><th>{t('tp_name')}</th><th>{t('cr_type')}</th><th>{t('tp_pattern')}</th><th className="num">{t('ty_days')}</th><th className="num">{t('ty_checklist')}</th><th /></tr></thead>
            <tbody>{(data || []).map(x => (
              <tr key={x.id} style={{ opacity: x.is_active ? 1 : .5 }}>
                <td><b>{x.name}</b></td>
                <td className="muted">{types.find(y => y.id === x.type_id)?.name || '—'}</td>
                <td className="mono xs">{x.title_pattern}</td>
                <td className="num">{x.default_duration_days}</td>
                <td className="num">{(x.checklist_json || []).length}</td>
                <td className="row" style={{ justifyContent: 'flex-end' }}>
                  <button className="btn btn--sm btn--p" onClick={() => setUse(x)}>{t('tp_use')}</button>
                  <button className="btn btn--sm" onClick={() => setEdit(x)}>{t('edit')}</button>
                  <button className="btn btn--sm btn--ghost" onClick={async () => { await patch(`/task-templates/${x.id}`, { is_active: !x.is_active }); reload() }}>
                    {x.is_active ? t('ty_archive') : t('ty_restore')}</button>
                </td>
              </tr>
            ))}
            {!data?.length && <tr><td colSpan={6}><div className="empty">{t('empty')}</div></td></tr>}</tbody>
          </table>
        </div>

        {can('tasks.bulk_create') && (
          <div className="section">
            <div className="row" style={{ marginBottom: 10 }}><h3 style={{ margin: 0 }}>{t('tp_recurring')}</h3><span className="spacer" />
              <button className="btn btn--sm" onClick={() => setRule({ template_id: data?.[0]?.id, project_id: projects[0]?.id, assignee_id: users[0]?.id, reviewer_id: users[0]?.id, rrule: 'FREQ=DAILY' })}>+ {t('add')}</button></div>
            <div className="tbl-wrap">
              <table className="tbl">
                <thead><tr><th>{t('tp_name')}</th><th>{t('cr_project')}</th><th>{t('cr_assignee')}</th><th>{t('tp_rrule')}</th><th>{t('tp_next')}</th><th /></tr></thead>
                <tbody>{(rules || []).map(r => (
                  <tr key={r.id} style={{ opacity: r.is_active ? 1 : .5 }}>
                    <td>{data?.find(x => x.id === r.template_id)?.name || r.template_id}</td>
                    <td>{projects.find(p => p.id === r.project_id)?.name}</td>
                    <td>{users.find(u => u.id === r.assignee_id)?.full_name}</td>
                    <td className="mono xs">{r.rrule}</td>
                    <td className="mono xs">{r.next_run_at ? fmtDate(r.next_run_at, lang) : '—'}</td>
                    <td style={{ textAlign: 'right' }}>
                      <button className="btn btn--sm btn--ghost" onClick={async () => { await patch(`/task-recurring-rules/${r.id}`, { is_active: !r.is_active }); reloadRules() }}>
                        {r.is_active ? t('ty_archive') : t('ty_restore')}</button></td>
                  </tr>
                ))}
                {!rules?.length && <tr><td colSpan={6}><div className="empty">{t('empty')}</div></td></tr>}</tbody>
              </table>
            </div>
          </div>
        )}
      </div>
      {edit && <TplDialog item={edit} types={types} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); reload() }} />}
      {use && <UseDialog tpl={use} onClose={() => setUse(null)} />}
      {rule && <RuleDialog item={rule} templates={data || []} onClose={() => setRule(null)} onSaved={() => { setRule(null); reloadRules() }} />}
    </>
  )
}

function TplDialog({ item, types, onClose, onSaved }: any) {
  const { t } = useT()
  const { toastErr } = useToast()
  const [f, setF] = useState<any>({ ...item })
  const [ck, setCk] = useState<any[]>(item.checklist_json || [])
  const save = async () => {
    const body = { name: f.name, type_id: Number(f.type_id), title_pattern: f.title_pattern, default_duration_days: Number(f.default_duration_days) || 1,
                   checklist_json: ck.filter(c => c.title.trim()).map((c, i) => ({ ...c, sort_order: i })), required_evidence_kinds: f.required_evidence_kinds || [] }
    try { item.id ? await patch(`/task-templates/${item.id}`, body) : await post('/task-templates', body); onSaved() } catch (e) { toastErr(e) }
  }
  return (
    <Modal title={item.id ? t('edit') : t('tp_new')} onClose={onClose} footer={
      <><button className="btn" onClick={onClose}>{t('cancel')}</button>
        <button className="btn btn--p" disabled={!f.name?.trim() || !f.title_pattern?.trim() || !f.type_id} onClick={save}>{t('save')}</button></>}>
      <label className="lbl">{t('tp_name')} <i>*</i><input className="inp" value={f.name} onChange={e => setF({ ...f, name: e.target.value })} /></label>
      <label className="lbl">{t('cr_type')} <i>*</i>
        <select className="sel" value={f.type_id} onChange={e => {
          const ty = types.find((x: any) => x.id === Number(e.target.value))
          setF({ ...f, type_id: Number(e.target.value), required_evidence_kinds: ty?.required_evidence_kinds || [] })
          if (!ck.length) setCk(ty?.default_checklist_json || [])
        }}>{types.map((x: any) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
      <label className="lbl full">{t('tp_pattern')} <i>*</i>
        <input className="inp" value={f.title_pattern} onChange={e => setF({ ...f, title_pattern: e.target.value })} placeholder="Monolit plita — {joy} betonlash" />
        <span className="hint">{t('tp_pattern_hint')}</span></label>
      <label className="lbl">{t('ty_days')}<input className="inp" type="number" min={1} value={f.default_duration_days} onChange={e => setF({ ...f, default_duration_days: e.target.value })} /></label>
      <div className="full">
        <div className="lbl" style={{ marginBottom: 6 }}>{t('cr_checklist')}</div>
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

function UseDialog({ tpl, onClose }: any) {
  const { t } = useT()
  const nav = useNavigate()
  const { toastErr, toast } = useToast()
  const [projectId, setProjectId] = useState<number | ''>('')
  const { projects, users, locations } = useRefs(projectId || null)
  const [f, setF] = useState<any>({ location_id: '', assignee_id: '', reviewer_id: '', planned_start: new Date().toISOString().slice(0, 10), priority: 'normal' })
  const create = async () => {
    try {
      const tk = await post(`/task-templates/${tpl.id}/instantiate`, {
        project_id: Number(projectId), location_id: f.location_id ? Number(f.location_id) : null,
        assignee_id: Number(f.assignee_id), reviewer_id: Number(f.reviewer_id), planned_start: f.planned_start,
        priority: f.priority, variables: {},
      })
      invalidate(); toast(t('created_ok')); onClose(); nav(`/tasks/${tk.id}`)
    } catch (e) { toastErr(e) }
  }
  return (
    <Modal title={`${t('tp_use')} — ${tpl.name}`} onClose={onClose} footer={
      <><button className="btn" onClick={onClose}>{t('cancel')}</button>
        <button className="btn btn--p" disabled={!projectId || !f.assignee_id || !f.reviewer_id} onClick={create}>{t('cr_create')}</button></>}>
      <label className="lbl">{t('cr_project')} <i>*</i>
        <select className="sel" value={projectId} onChange={e => setProjectId(Number(e.target.value))}>
          <option value="">—</option>{projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      <label className="lbl">{t('cr_location')}
        <select className="sel" value={f.location_id} onChange={e => setF({ ...f, location_id: e.target.value })}>
          <option value="">—</option>{locations.map(l => <option key={l.id} value={l.id}>{locLabel(locations, l.id)}</option>)}</select></label>
      <label className="lbl">{t('cr_assignee')} <i>*</i>
        <select className="sel" value={f.assignee_id} onChange={e => setF({ ...f, assignee_id: e.target.value })}>
          <option value="">—</option>{users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}</select></label>
      <label className="lbl">{t('cr_reviewer')} <i>*</i>
        <select className="sel" value={f.reviewer_id} onChange={e => setF({ ...f, reviewer_id: e.target.value })}>
          <option value="">—</option>{users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}</select></label>
      <label className="lbl">{t('cr_start')}<input className="inp" type="date" value={f.planned_start} onChange={e => setF({ ...f, planned_start: e.target.value })} /></label>
      <label className="lbl">{t('priority')}
        <select className="sel" value={f.priority} onChange={e => setF({ ...f, priority: e.target.value })}>
          {['low', 'normal', 'high'].map(p => <option key={p} value={p}>{t('pr_' + p)}</option>)}</select></label>
    </Modal>
  )
}

function RuleDialog({ item, templates, onClose, onSaved }: any) {
  const { t } = useT()
  const { toastErr } = useToast()
  const [f, setF] = useState<any>({ ...item })
  const { projects, users, locations } = useRefs(f.project_id || null)
  const [freq, setFreq] = useState(item.rrule?.startsWith('FREQ=WEEKLY') ? 'WEEKLY' : 'DAILY')
  const [days, setDays] = useState<string[]>(['MO', 'WE', 'FR'])
  const save = async () => {
    const rrule = freq === 'DAILY' ? 'FREQ=DAILY' : `FREQ=WEEKLY;BYDAY=${days.join(',')}`
    try { await post('/task-recurring-rules', { ...f, rrule, project_id: Number(f.project_id), template_id: Number(f.template_id), assignee_id: Number(f.assignee_id), reviewer_id: Number(f.reviewer_id), location_id: f.location_id ? Number(f.location_id) : null }); onSaved() } catch (e) { toastErr(e) }
  }
  return (
    <Modal title={t('tp_recurring')} onClose={onClose} footer={
      <><button className="btn" onClick={onClose}>{t('cancel')}</button><button className="btn btn--p" onClick={save}>{t('save')}</button></>}>
      <label className="lbl">{t('cr_template')}<select className="sel" value={f.template_id} onChange={e => setF({ ...f, template_id: e.target.value })}>
        {templates.map((x: any) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
      <label className="lbl">{t('cr_project')}<select className="sel" value={f.project_id} onChange={e => setF({ ...f, project_id: e.target.value, location_id: '' })}>
        {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      <label className="lbl">{t('cr_location')}<select className="sel" value={f.location_id || ''} onChange={e => setF({ ...f, location_id: e.target.value })}>
        <option value="">—</option>{locations.map(l => <option key={l.id} value={l.id}>{locLabel(locations, l.id)}</option>)}</select></label>
      <label className="lbl">{t('cr_assignee')}<select className="sel" value={f.assignee_id} onChange={e => setF({ ...f, assignee_id: e.target.value })}>
        {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}</select></label>
      <label className="lbl">{t('cr_reviewer')}<select className="sel" value={f.reviewer_id} onChange={e => setF({ ...f, reviewer_id: e.target.value })}>
        {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}</select></label>
      <label className="lbl">{t('tp_rrule')}<select className="sel" value={freq} onChange={e => setFreq(e.target.value)}>
        <option value="DAILY">{t('tp_daily')}</option><option value="WEEKLY">{t('tp_weekly')}</option></select></label>
      {freq === 'WEEKLY' && <div className="lbl full">{t('tp_days')}
        <div className="row wrap">{DAYS.map(d => (
          <button key={d} className={'tog' + (days.includes(d) ? ' on' : '')} onClick={() => setDays(s => s.includes(d) ? s.filter(x => x !== d) : [...s, d])}>{d}</button>
        ))}</div></div>}
    </Modal>
  )
}
