import React, { useMemo, useState } from 'react'
import { useT } from '../lib/i18n'

/** Kimga vazifa berish — bitta uzun ro'yxat o'rniga ikki ustun.
 *
 *  Chapda bo'lim boshliqlari, o'ngda boshqaruvchilar va asosiy bo'lim ijrochilari.
 *  Sabab: bitta ro'yxatda 60 dan ortiq odam bo'lgani uchun cho'zilib ketardi va
 *  kerakli odamni topish uchun aylantirib chiqishga to'g'ri kelardi. Ikki ustun +
 *  qidiruv bilan odam ikki bosishda topiladi.
 */
export default function PeoplePicker({ people, value, onPick }:
  { people: any[]; value: number | null; onPick: (id: number) => void }) {
  const { t } = useT()
  const [q, setQ] = useState('')

  const { heads, others } = useMemo(() => {
    const n = q.trim().toLowerCase()
    const ok = (p: any) => !n
      || (p.full_name || '').toLowerCase().includes(n)
      || (p.position || '').toLowerCase().includes(n)
      || (p.department_name || '').toLowerCase().includes(n)
    const list = (people || []).filter(ok)
    const by = (a: any, b: any) => a.full_name.localeCompare(b.full_name)
    return {
      heads: list.filter(p => p.role === 'bolim_boshligi').sort(by),
      // boshqaruvchilar tepada — ular kam va tez-tez kerak bo'ladi
      others: [...list.filter(p => p.role === 'boss' || p.role === 'assistant').sort(by),
               ...list.filter(p => p.role === 'ijrochi').sort(by)],
    }
  }, [people, q])

  const Row = ({ p }: { p: any }) => (
    <button type="button" className={'pitem' + (value === p.id ? ' pitem--on' : '')}
            onClick={() => onPick(p.id)}>
      <b>{p.full_name}</b>
      <span>{p.department_name || p.position || p.role_name}</span>
    </button>
  )

  return (
    <div className="picker">
      <input className="inp inp--search" value={q} placeholder={t('search')}
             onChange={e => setQ(e.target.value)} />
      <div className="picker__cols">
        <div className="picker__col">
          <div className="picker__h">{t('pk_heads')}<span className="chip">{heads.length}</span></div>
          <div className="picker__list">
            {heads.map(p => <Row key={p.id} p={p} />)}
            {!heads.length && <div className="empty empty--sm">{t('empty')}</div>}
          </div>
        </div>
        <div className="picker__col">
          <div className="picker__h">{t('pk_others')}<span className="chip">{others.length}</span></div>
          <div className="picker__list">
            {others.map(p => <Row key={p.id} p={p} />)}
            {!others.length && <div className="empty empty--sm">{t('empty')}</div>}
          </div>
        </div>
      </div>
    </div>
  )
}
