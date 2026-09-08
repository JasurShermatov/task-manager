import React, { useEffect, useRef, useState } from 'react'
import { api, get, post, upload, invalidate } from '../lib/api'
import { useFetch } from '../lib/hooks'
import { useT } from '../lib/i18n'
import { useToast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { useRefs, locLabel } from '../lib/refs'
import { Modal } from './Modal'

const addDays = (n: number) => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10) }

export default function CreateTask({ onClose, onCreated, defaults }: {
  onClose: () => void; onCreated: (t: any) => void; defaults?: any
}) {
  const { t, lang } = useT()
  const { toastErr } = useToast()
  const { me, can } = useAuth()
  const [projectId, setProjectId] = useState<number | ''>(defaults?.project_id ?? '')
  const { projects, users, types, locations } = useRefs(projectId || null)
  const { data: templates } = useFetch<any[]>('/task-templates')
  const { data: meta } = useFetch<any>('/meta')
  const [f, setF] = useState<any>({
    title: '', description: '', priority: 'normal', assignee_id: '', reviewer_id: me?.user.id ?? '',
    planned_start: addDays(0), planned_end: addDays(3), type_id: '', location_id: defaults?.location_id ?? '',
    planned_quantity: '', unit: '', planned_crew_size: '', depends_on: '', template_id: '',
  })
  const [checklist, setChecklist] = useState<{ title: string; is_required: boolean }[]>([])
  const [busy, setBusy] = useState(false)
  const [voiceInfo, setVoiceInfo] = useState<string>('')
  const [cands, setCands] = useState<any[]>([])

  const canAccept = (u: any) => !!u?.role?.permissions_json?.includes('tasks.accept')
  const canDo = (u: any) => !!u?.role?.permissions_json?.includes('tasks.start')
  const reviewerOptions = users.filter(u => canAccept(u) || u.id === f.reviewer_id)
  const assigneeOptions = users.filter(u => canDo(u) || u.id === f.assignee_id)
  useEffect(() => { if (projects.length === 1 && !projectId) setProjectId(projects[0].id) }, [projects])
  // kim tekshiradi: loyihaning tekshiruvchisi -> rahbari -> "tasks.accept" huquqi bor boshqa odam -> o'zim
  // (faqat qabul qilish huquqi bo'lgan odamgina tayinlanadi - aks holda vazifa tekshiruvda osilib qoladi)
  useEffect(() => {
    if (!projectId || !users.length) return
    const pick = users.find(u => u.role?.code === 'tekshiruvchi' && u.id !== me?.user.id)
      || users.find(u => u.role?.code === 'rahbar' && u.id !== me?.user.id)
      || users.find(u => canAccept(u) && u.id !== me?.user.id)
    const self = can('tasks.accept') ? me?.user.id : undefined
    setF((s: any) => (s.reviewer_id && s.reviewer_id !== me?.user.id) ? s : { ...s, reviewer_id: pick?.id ?? self ?? '' })
  }, [projectId, users.length])
  useEffect(() => {
    if (!f.type_id && types.length) applyType(types[0].id)
  }, [types])

  const applyType = (tid: number) => {
    const ty = types.find(x => x.id === tid)
    setF((s: any) => ({ ...s, type_id: tid, planned_end: addDays(Math.max(0, (ty?.default_duration_days || 3) - 1)) }))
    setChecklist((ty?.default_checklist_json || []).map((c: any) => ({ title: c.title, is_required: c.is_required !== false })))
  }
  const applyTemplate = (id: string) => {
    setF((s: any) => ({ ...s, template_id: id }))
    const tp = templates?.find(x => String(x.id) === id)
    if (!tp) return
    const loc = f.location_id ? locations.find(l => l.id === Number(f.location_id)) : null
    setF((s: any) => ({
      ...s, template_id: id, type_id: tp.type_id,
      title: tp.title_pattern.replace('{joy}', loc?.name || '').replace('{sana}', new Date().toLocaleDateString()),
      planned_end: addDays(Math.max(0, tp.default_duration_days - 1)),
    }))
    setChecklist((tp.checklist_json || []).map((c: any) => ({ title: c.title, is_required: c.is_required !== false })))
  }

  const submit = async () => {
    if (f.assignee_id && f.assignee_id === f.reviewer_id) return toastErr({ message: t('cr_self_review') })
    setBusy(true)
    try {
      const deps: number[] = []
      for (const raw of String(f.depends_on).split(',').map((x: string) => x.trim()).filter(Boolean)) {
        const code = raw.toUpperCase().startsWith('V-') ? raw.toUpperCase() : 'V-' + raw.replace(/\D/g, '')
        const other = await get(`/tasks/by-code/${code}`)
        deps.push(other.id)
      }
      const body = {
        project_id: Number(projectId), location_id: f.location_id ? Number(f.location_id) : null, type_id: Number(f.type_id),
        title: f.title.trim(), description: f.description || null, priority: f.priority,
        assignee_id: Number(f.assignee_id), reviewer_id: Number(f.reviewer_id),
        planned_start: f.planned_start, planned_end: f.planned_end,
        planned_quantity: f.planned_quantity === '' ? null : Number(f.planned_quantity),
        unit: f.unit || null, planned_crew_size: f.planned_crew_size === '' ? null : Number(f.planned_crew_size),
        checklist: checklist.map((c, i) => ({ ...c, sort_order: i })), depends_on: deps,
        template_id: f.template_id ? Number(f.template_id) : null,
      }
      const tk = await post('/tasks', body)
      invalidate(); onCreated(tk)
    } catch (e) { toastErr(e) } finally { setBusy(false) }
  }

  const onParsed = (p: any) => {
    setVoiceInfo(p.transcript)
    if (p.project_id) setProjectId(p.project_id)
    setF((s: any) => ({
      ...s,
      title: p.title || s.title,
      description: p.description || s.description,
      priority: p.priority || s.priority,
      planned_start: p.planned_start || s.planned_start,
      planned_end: p.planned_end || s.planned_end,
      type_id: p.type_id || s.type_id,
      location_id: p.location_id ?? s.location_id,
      assignee_id: p.assignee_id ?? s.assignee_id,
    }))
    setCands(p.assignee_id ? [] : (p.assignee_candidates || []))
    if (p.type_id) {
      const ty = types.find(x => x.id === p.type_id)
      if (ty) setChecklist((ty.default_checklist_json || []).map((c: any) => ({ title: c.title, is_required: c.is_required !== false })))
    }
  }

  const valid = f.title.trim() && projectId && f.type_id && f.assignee_id && f.reviewer_id && f.planned_start && f.planned_end
  return (
    <Modal title={t('cr_title')} onClose={onClose} footer={
      <><button className="btn" onClick={onClose}>{t('cancel')}</button>
        <button className="btn btn--p" disabled={!valid || busy} onClick={submit}>{t('cr_create')}</button></>}>
      <div className="full">
        <VoiceInput enabled={!!meta?.voice_enabled} projectId={projectId || null} onParsed={onParsed} info={voiceInfo} />
        {!!cands.length && (
          <div className="voice-box" style={{ marginTop: 8 }}>
            <span className="small b">{t('cr_pick_assignee')}:</span>
            {cands.map(c => (
              <button key={c.id} className="btn btn--sm" onClick={() => { setF((s: any) => ({ ...s, assignee_id: c.id })); setCands([]) }}>
                {c.full_name}
                {c.hint && <span className="faint xs"> · {c.hint}</span>}
                <span className="faint mono xs"> {c.score}%</span>
              </button>
            ))}
          </div>
        )}
      </div>
      <label className="lbl">{t('cr_template')}
        <select className="sel" value={f.template_id} onChange={e => applyTemplate(e.target.value)}>
          <option value="">{t('cr_no_template')}</option>
          {templates?.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}
        </select></label>
      <label className="lbl">{t('cr_project')} <i>*</i>
        <select className="sel" value={projectId} onChange={e => { setProjectId(Number(e.target.value)); setF({ ...f, location_id: '' }) }}>
          <option value="">—</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select></label>
      <label className="lbl full">{t('cr_name')} <i>*</i>
        <input className="inp" value={f.title} onChange={e => setF({ ...f, title: e.target.value })} /></label>
      <label className="lbl">{t('cr_type')} <i>*</i>
        <select className="sel" value={f.type_id} onChange={e => applyType(Number(e.target.value))}>
          <option value="">—</option>
          {types.map(x => <option key={x.id} value={x.id}>{x.group_name ? x.group_name + ' · ' : ''}{x.name}</option>)}
        </select>
        <span className="hint">{t('cr_type_hint')}</span></label>
      <label className="lbl">{t('cr_location')}
        <select className="sel" value={f.location_id} onChange={e => setF({ ...f, location_id: e.target.value })}>
          <option value="">—</option>
          {locations.map(l => <option key={l.id} value={l.id}>{locLabel(locations, l.id)}</option>)}
        </select></label>
      <label className="lbl">{t('cr_assignee')} <i>*</i>
        <select className="sel" value={f.assignee_id} onChange={e => setF({ ...f, assignee_id: Number(e.target.value) })}>
          <option value="">—</option>
          {assigneeOptions.map(u => <option key={u.id} value={u.id}>{u.full_name} · {u.role?.name}</option>)}
        </select></label>
      <label className="lbl">{t('cr_reviewer')} <i>*</i>
        <select className="sel" value={f.reviewer_id} onChange={e => setF({ ...f, reviewer_id: Number(e.target.value) })}>
          <option value="">—</option>
          {reviewerOptions.map(u => <option key={u.id} value={u.id}>{u.full_name} · {u.role?.name}</option>)}
        </select>
        {f.assignee_id && f.assignee_id === f.reviewer_id && <span className="field-err">{t('cr_self_review')}</span>}</label>
      <label className="lbl">{t('cr_start')} <i>*</i>
        <input className="inp" type="date" value={f.planned_start} onChange={e => setF({ ...f, planned_start: e.target.value })} /></label>
      <label className="lbl">{t('cr_end')} <i>*</i>
        <input className="inp" type="date" value={f.planned_end} onChange={e => setF({ ...f, planned_end: e.target.value })} /></label>
      <label className="lbl">{t('priority')}
        <select className="sel" value={f.priority} onChange={e => setF({ ...f, priority: e.target.value })}>
          {['low', 'normal', 'high'].map(p => <option key={p} value={p}>{t('pr_' + p)}</option>)}
        </select></label>
      <label className="lbl">{t('cr_qty')}
        <input className="inp" type="number" step="0.01" value={f.planned_quantity} onChange={e => setF({ ...f, planned_quantity: e.target.value })} /></label>
      <label className="lbl">{t('cr_unit')}
        <select className="sel" value={f.unit} onChange={e => setF({ ...f, unit: e.target.value })}>
          <option value="">—</option>
          {(meta?.units || []).map((u: string) => <option key={u} value={u}>{u}</option>)}
        </select></label>
      <label className="lbl">{t('cr_crew')}
        <input className="inp" type="number" value={f.planned_crew_size} onChange={e => setF({ ...f, planned_crew_size: e.target.value })} /></label>
      <label className="lbl full">{t('cr_desc')}
        <textarea className="inp" value={f.description} onChange={e => setF({ ...f, description: e.target.value })} /></label>
      <div className="full">
        <div className="lbl" style={{ marginBottom: 6 }}>{t('cr_checklist')}</div>
        {checklist.map((c, i) => (
          <div className="row" key={i} style={{ padding: '3px 0' }}>
            <input className="inp inp--sm" style={{ flex: 1 }} value={c.title}
                   onChange={e => setChecklist(cs => cs.map((x, j) => j === i ? { ...x, title: e.target.value } : x))} />
            <label className="check"><input type="checkbox" checked={c.is_required}
                   onChange={e => setChecklist(cs => cs.map((x, j) => j === i ? { ...x, is_required: e.target.checked } : x))} />{t('required')}</label>
            <button className="btn btn--sm btn--ghost" onClick={() => setChecklist(cs => cs.filter((_, j) => j !== i))}>✕</button>
          </div>
        ))}
        <button className="btn btn--sm" style={{ marginTop: 6 }} onClick={() => setChecklist(cs => [...cs, { title: '', is_required: false }])}>+ {t('a_add_item')}</button>
      </div>
      <label className="lbl full">{t('cr_deps')}
        <input className="inp" placeholder="V-1027, V-1031" value={f.depends_on} onChange={e => setF({ ...f, depends_on: e.target.value })} /></label>
    </Modal>
  )
}

export function VoiceInput({ enabled, projectId, onParsed, info }: {
  enabled: boolean; projectId: number | null; onParsed: (p: any) => void; info?: string
}) {
  const { t, lang } = useT()
  const { toastErr } = useToast()
  const [rec, setRec] = useState<MediaRecorder | null>(null)
  const [busy, setBusy] = useState(false)
  const chunks = useRef<Blob[]>([])

  // Brauzer mikrofoni faqat xavfsiz manzilda ishlaydi: HTTPS yoki localhost.
  // http://IP da navigator.mediaDevices umuman mavjud emas — tugmani bosishdan oldin aytamiz.
  const micReady = typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia

  const start = async () => {
    if (!micReady) return toastErr({ message: t('cr_voice_https') })
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mime = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : ''
      const mr = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
      chunks.current = []
      mr.ondataavailable = e => { if (e.data.size) chunks.current.push(e.data) }
      mr.onstop = async () => {
        stream.getTracks().forEach(x => x.stop())
        const blob = new Blob(chunks.current, { type: mr.mimeType || 'audio/webm' })
        if (blob.size < 800) return toastErr({ message: t('cr_voice_short') })
        setBusy(true)
        try {
          const fd = new FormData()
          fd.append('file', blob, 'voice.webm')
          fd.append('lang', lang)
          if (projectId) fd.append('project_id', String(projectId))
          onParsed(await upload('/ai/voice-task', fd))
        } catch (e) { toastErr(e) } finally { setBusy(false) }
      }
      mr.start()
      setRec(mr)
    } catch (e: any) { toastErr({ message: e?.message || 'mic' }) }
  }
  const stop = () => { rec?.stop(); setRec(null) }

  if (!enabled) return <div className="voice-box"><span className="small muted">🎙 {t('cr_voice_off')}</span></div>
  if (!micReady) return <div className="voice-box"><span className="small muted">🎙 {t('cr_voice_https')}</span></div>
  return (
    <div className="voice-box">
      {!rec && <button className="btn" disabled={busy} onClick={start}>🎙 {t('cr_voice')}</button>}
      {rec && <button className="btn btn--rec" onClick={stop}>⏹ {t('cr_voice_stop')}</button>}
      <span className="txt">{busy ? t('cr_voice_processing') : info ? `“${info}”` : t('cr_voice_hint')}</span>
    </div>
  )
}
