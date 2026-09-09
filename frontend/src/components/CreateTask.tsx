import React, { useMemo, useState } from 'react'
import { invalidate, post } from '../lib/api'
import { useAuth } from '../lib/auth'
import { plusDays } from '../lib/fmt'
import { useFetch } from '../lib/hooks'
import { useT } from '../lib/i18n'
import { useToast } from '../lib/toast'
import Modal from './Modal'
import PeoplePicker from './PeoplePicker'

/** Yangi vazifa — uch maydon: kimga, nima, qachon. Qolgani ixtiyoriy. */
export default function CreateTask({ onClose, defaultAssignee }:
  { onClose: () => void; defaultAssignee?: number }) {
  const { t } = useT()
  const { me } = useAuth()
  const { toast, toastErr } = useToast()
  const { data: people } = useFetch<any[]>('/users', { active: true, limit: 300 })
  const [assignee, setAssignee] = useState<string>(defaultAssignee ? String(defaultAssignee) : '')
  const [title, setTitle] = useState('')
  const [due, setDue] = useState(plusDays(3))
  const [desc, setDesc] = useState('')
  const [busy, setBusy] = useState(false)

  const options = useMemo(() => (people || []).filter(p => p.id !== me?.id), [people, me])
  const ready = assignee && title.trim() && due

  const save = async () => {
    setBusy(true)
    try {
      const tk = await post('/tasks', {
        title: title.trim(), assignee_id: Number(assignee), due_at: due,
        description: desc.trim() || null,
      })
      toast(`${t('nt_created')}: ${tk.code}`)
      invalidate()
      onClose()
    } catch (e) { toastErr(e) } finally { setBusy(false) }
  }

  return (
    <Modal title={t('nt_title')} onClose={onClose}>
      <div className="modal__b">
        <label className="lbl full">{t('nt_what')} *
          <input className="inp" autoFocus value={title} maxLength={250}
                 onChange={e => setTitle(e.target.value)} />
        </label>
        <div className="lbl full">{t('nt_who')} *
          <PeoplePicker people={options} value={assignee ? Number(assignee) : null}
                        onPick={id => setAssignee(String(id))} />
        </div>
        <label className="lbl">{t('nt_due')} *
          <input className="inp" type="datetime-local" value={due} onChange={e => setDue(e.target.value)} />
          <span className="hint">{t('nt_time_hint')}</span>
        </label>
        <div className="full row wrap quick">
          {[0, 1, 3, 7].map(d => (
            <button key={d} type="button" className="btn btn--sm" onClick={() => setDue(plusDays(d))}>
              {d === 0 ? t('today') : `+${d}`}
            </button>
          ))}
        </div>
        <label className="lbl full">{t('nt_desc')}
          <textarea className="inp" value={desc} maxLength={4000} onChange={e => setDesc(e.target.value)} />
        </label>
      </div>
      <div className="modal__f">
        <button className="btn" onClick={onClose}>{t('cancel')}</button>
        <button className="btn btn--p" onClick={save} disabled={busy || !ready}>{t('save')}</button>
      </div>
    </Modal>
  )
}
