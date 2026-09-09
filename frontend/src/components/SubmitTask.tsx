import React, { useState } from 'react'
import { invalidate, post, upload } from '../lib/api'
import { useT } from '../lib/i18n'
import { useToast } from '../lib/toast'
import Modal from './Modal'

/** Topshirish: nima qilindi + dalil.
 *
 *  Dalil odatda majburiy — server ham rad etadi, shuning uchun tugma o'chiq turadi va
 *  sabab yozib qo'yiladi. Boshliq bilan assistant bir-biriga bergan vazifada esa dalil
 *  shart emas (ular ko'pincha bir-biriga savol beradi) — buni server `needs_proof` bilan
 *  aytadi, biz o'zimiz rolga qarab hisoblamaymiz. */
export default function SubmitTask({ task, onClose, onDone }:
  { task: any; onClose: () => void; onDone?: () => void }) {
  const { t } = useT()
  const { toast, toastErr } = useToast()
  const [note, setNote] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [busy, setBusy] = useState(false)
  const needProof = task.needs_proof !== false

  const add = (list: FileList | null) => {
    if (!list) return
    setFiles(f => [...f, ...Array.from(list)])
  }

  const send = async () => {
    setBusy(true)
    try {
      for (const f of files) {
        const form = new FormData()
        form.append('file', f)
        form.append('kind', 'proof')
        await upload(`/tasks/${task.id}/files`, form)
      }
      await post(`/tasks/${task.id}/submit`, { note: note.trim() || '—' })
      toast(`${t('sb_ok')}: ${task.code}`)
      invalidate()
      onDone?.()
      onClose()
    } catch (e) { toastErr(e) } finally { setBusy(false) }
  }

  return (
    <Modal title={`${t('sb_title')} · ${task.code}`} onClose={onClose}>
      <div className="modal__b modal__b--one">
        <div className="b">{task.title}</div>
        <label className="lbl">{t('sb_note')}
          <textarea className="inp" autoFocus value={note} onChange={e => setNote(e.target.value)} />
        </label>
        <label className="lbl">{t('sb_proof')}{needProof ? ' *' : ''}
          <div className="drop">
            <input type="file" multiple accept="image/*,application/pdf,.doc,.docx,.xls,.xlsx"
                   onChange={e => add(e.target.files)} />
            <span className="muted small">{t('sb_drop')}</span>
          </div>
        </label>
        {!!files.length && (
          <div className="files">
            {files.map((f, i) => (
              <div key={i} className="file">
                {f.type.startsWith('image/')
                  ? <img src={URL.createObjectURL(f)} alt={f.name} />
                  : <span className="file__doc">📄</span>}
                <span className="file__n ellipsis">{f.name}</span>
                <button className="icon-btn file__x" onClick={() => setFiles(x => x.filter((_, j) => j !== i))}
                        aria-label="remove">✕</button>
              </div>
            ))}
          </div>
        )}
        {!files.length && (needProof
          ? <div className="field-err">{t('sb_proof_req')}</div>
          : <div className="hint">{t('sb_proof_opt')}</div>)}
      </div>
      <div className="modal__f">
        <button className="btn" onClick={onClose}>{t('cancel')}</button>
        <button className="btn btn--p" onClick={send} disabled={busy || (needProof && !files.length)}>{t('a_submit')}</button>
      </div>
    </Modal>
  )
}
