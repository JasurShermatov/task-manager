import React, { useEffect } from 'react'
import { useT } from '../lib/i18n'

/** Oyna. Ichki qismini chaqiruvchi beradi: `.modal__b` (tanasi) va `.modal__f` (tugmalar). */
export default function Modal({ title, children, onClose, small }: {
  title: string; children: React.ReactNode; onClose: () => void; small?: boolean
}) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])
  return (
    <div className="modal-bg" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className={'modal' + (small ? ' modal--sm' : '')}>
        <div className="modal__h">
          <b>{title}</b><span className="spacer" />
          <button className="btn btn--sm btn--ghost" onClick={onClose} aria-label="close">✕</button>
        </div>
        {children}
      </div>
    </div>
  )
}

export function Confirm({ text, onOk, onClose }: { text: string; onOk: () => void; onClose: () => void }) {
  const { t } = useT()
  return (
    <Modal title={text} small onClose={onClose}>
      <div className="modal__f">
        <button className="btn" onClick={onClose}>{t('cancel')}</button>
        <button className="btn btn--danger" onClick={onOk}>{t('yes')}</button>
      </div>
    </Modal>
  )
}
