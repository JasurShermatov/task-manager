import React, { useMemo, useState } from 'react'
import { post, invalidate } from '../lib/api'
import { useT, fmtDate } from '../lib/i18n'
import { useToast } from '../lib/toast'
import { useRefs, locLabel } from '../lib/refs'
import { PageHeader } from '../components/Layout'

export default function Bulk() {
  const { t, lang } = useT()
  const { toastErr, toast } = useToast()
  const [projectId, setProjectId] = useState<number | ''>('')
  const { projects, users, locations } = useRefs(projectId || null)
  const [source, setSource] = useState<number | ''>('')
  const [targets, setTargets] = useState<number[]>([])
  const [step, setStep] = useState(0)
  const [policy, setPolicy] = useState('keep')
  const [assignee, setAssignee] = useState<number | ''>('')
  const [deps, setDeps] = useState('none')
  const [preview, setPreview] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<any>(null)

  const candidates = useMemo(() => locations.filter(l => l.id !== source), [locations, source])

  const body = () => ({
    source_location_id: Number(source), target_location_ids: targets, date_step_days: Number(step) || 0,
    assignee_policy: policy === 'keep' ? 'keep' : `user:${assignee}`, dependency_policy: deps,
    as_draft: true, dry_run: true,
  })
  const doPreview = async () => {
    setBusy(true); setResult(null)
    try { setPreview(await post('/tasks/bulk-copy', body())) } catch (e) { toastErr(e); setPreview(null) } finally { setBusy(false) }
  }
  const doRun = async () => {
    setBusy(true)
    try {
      const r = await post('/tasks/bulk-copy', { ...body(), dry_run: false })
      setResult(r); setPreview(null); invalidate(); toast(t('bk_result', { n: r.created?.length ?? r.total }))
    } catch (e) { toastErr(e) } finally { setBusy(false) }
  }
  const canPreview = source && targets.length && (policy === 'keep' || assignee)

  return (
    <>
      <PageHeader title={t('bk_title')} />
      <div className="content" style={{ maxWidth: 900 }}>
        <div className="alert alert--info" style={{ marginBottom: 16 }}>{t('bk_hint')}</div>
        <div className="grid2">
          <label className="lbl">{t('cr_project')} <i>*</i>
            <select className="sel" value={projectId} onChange={e => { setProjectId(Number(e.target.value)); setSource(''); setTargets([]); setPreview(null) }}>
              <option value="">—</option>{projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
          <label className="lbl">{t('bk_source')} <i>*</i>
            <select className="sel" value={source} onChange={e => { setSource(Number(e.target.value)); setPreview(null) }}>
              <option value="">—</option>{locations.map(l => <option key={l.id} value={l.id}>{locLabel(locations, l.id)}</option>)}</select></label>
          <label className="lbl">{t('bk_step')}
            <input className="inp" type="number" min={0} value={step} onChange={e => { setStep(Number(e.target.value)); setPreview(null) }} /></label>
          <label className="lbl">{t('bk_assignee')}
            <select className="sel" value={policy} onChange={e => { setPolicy(e.target.value); setPreview(null) }}>
              <option value="keep">{t('bk_keep')}</option><option value="set">{t('bk_set')}</option></select></label>
          {policy === 'set' && <label className="lbl">{t('cr_assignee')} <i>*</i>
            <select className="sel" value={assignee} onChange={e => { setAssignee(Number(e.target.value)); setPreview(null) }}>
              <option value="">—</option>{users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}</select></label>}
          <label className="lbl">{t('bk_deps')}
            <select className="sel" value={deps} onChange={e => { setDeps(e.target.value); setPreview(null) }}>
              <option value="none">{t('bk_deps_none')}</option><option value="chain">{t('bk_deps_chain')}</option></select></label>
        </div>

        <div className="section" style={{ marginTop: 20 }}>
          <h3>{t('bk_targets')} <span className="mono faint xs">{targets.length}</span></h3>
          <div className="row wrap">
            {candidates.map(l => (
              <button key={l.id} className={'tog' + (targets.includes(l.id) ? ' on' : '')}
                      onClick={() => { setTargets(s => s.includes(l.id) ? s.filter(x => x !== l.id) : [...s, l.id]); setPreview(null) }}>
                {locLabel(locations, l.id)}
              </button>
            ))}
            {!candidates.length && <span className="muted small">{t('empty')}</span>}
          </div>
        </div>

        <div className="row" style={{ marginTop: 16 }}>
          <button className="btn" disabled={!canPreview || busy} onClick={doPreview}>{t('bk_preview')}</button>
          <button className="btn btn--p" disabled={!preview || busy} onClick={doRun}>{t('bk_run', { n: preview?.total ?? 0 })}</button>
        </div>

        {result && <div className="alert alert--ok" style={{ marginTop: 16 }}>{t('bk_result', { n: result.created?.length ?? result.total })} — <span className="mono xs">{(result.created || []).slice(0, 30).join(', ')}</span></div>}

        {preview && (
          <div className="section" style={{ marginTop: 20 }}>
            <h3>{t('bk_preview')} — {preview.total}</h3>
            <div className="tbl-wrap">
              <table className="tbl">
                <thead><tr><th>{t('t_location')}</th><th>{t('t_title')}</th><th>{t('cr_start')}</th><th>{t('cr_end')}</th></tr></thead>
                <tbody>{preview.items.slice(0, 120).map((it: any, i: number) => (
                  <tr key={i}><td className="small">{it.target_location}</td><td>{it.title}</td>
                    <td className="mono small">{fmtDate(it.planned_start, lang)}</td><td className="mono small">{fmtDate(it.planned_end, lang)}</td></tr>
                ))}</tbody>
              </table>
            </div>
            {preview.items.length > 120 && <div className="small muted" style={{ marginTop: 8 }}>… {preview.items.length - 120}</div>}
          </div>
        )}
      </div>
    </>
  )
}
