import React, { useEffect } from 'react'
import { useT } from '../lib/i18n'

export function Modal({ title, children, footer, onClose, sm }: {
  title: string; children: React.ReactNode; footer?: React.ReactNode; onClose: () => void; sm?: boolean
}) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])
  return (
    <div className="modal-bg" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className={'modal' + (sm ? ' modal--sm' : '')}>
        <div className="modal__h"><b>{title}</b><span className="spacer" /><button className="btn btn--sm btn--ghost" onClick={onClose}>✕</button></div>
        <div className="modal__b">{children}</div>
        {footer && <div className="modal__f">{footer}</div>}
      </div>
    </div>
  )
}

export function Confirm({ text, onOk, onClose }: { text: string; onOk: () => void; onClose: () => void }) {
  const { t } = useT()
  return (
    <Modal title={text} sm onClose={onClose} footer={
      <><button className="btn" onClick={onClose}>{t('cancel')}</button>
        <button className="btn btn--danger" onClick={onOk}>{t('yes')}</button></>}>
      <div className="full muted small">&nbsp;</div>
    </Modal>
  )
}
