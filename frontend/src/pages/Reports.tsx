import React, { useState } from 'react'
import { api } from '../lib/api'
import { PageHeader } from '../components/Layout'
import Modal from '../components/Modal'
import { dt, pctClass, ROLE_KEY } from '../lib/fmt'
import { useFetch } from '../lib/hooks'
import { useT } from '../lib/i18n'
import { useToast } from '../lib/toast'

const PERIODS = ['week', 'month', 'year'] as const

/** Hisobot: ekranda foiz va son, kerak bo'lsa Excel yoki CSV bo'lib yuklanadi. */
export default function Reports() {
  const { t } = useT()
  const { toastErr } = useToast()
  const [period, setPeriod] = useState<string>('month')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [role, setRole] = useState('')
  const [person, setPerson] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)

  const params = {
    period, role: role || undefined,
    date_from: period === 'custom' ? from : undefined,
    date_to: period === 'custom' ? to : undefined,
  }
  const { data } = useFetch<any>(
    period === 'custom' && !(from && to) ? null : '/reports/summary', params, [period, from, to, role])

  const download = async (fmt: 'xlsx' | 'csv') => {
    setBusy(true)
    try {
      // api() manzilga API_BASE ni o'zi qo'shadi va Authorization sarlavhasini beradi,
      // shuning uchun to'liq havola yasamaymiz - faqat yo'l va parametrlar.
      const r: Response = await api('/reports/export',
        { params: { ...params, format: fmt }, raw: true })
      if (!r.ok) throw new Error(String(r.status))
      const blob = await r.blob()
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `saff-hisobot-${data?.date_from}-${data?.date_to}.${fmt}`
      document.body.appendChild(a); a.click(); a.remove()
      URL.revokeObjectURL(a.href)
    } catch (e) { toastErr(e) } finally { setBusy(false) }
  }

  const rows = data?.rows || []
  const tot = data?.totals

  return (
    <>
      <PageHeader title={t('nav_reports')}
                  extra={data && <span className="chip mono">{data.date_from} … {data.date_to}</span>}>
        <button className="btn" disabled={busy || !data} onClick={() => download('xlsx')}>⬇ {t('rep_xlsx')}</button>
        <button className="btn" disabled={busy || !data} onClick={() => download('csv')}>⬇ {t('rep_csv')}</button>
      </PageHeader>

      <div className="bar">
        <div className="seg seg--light">
          {PERIODS.map(p => (
            <button key={p} className={period === p ? 'on' : ''} onClick={() => setPeriod(p)}>
              {t(('rep_' + p) as any)}
            </button>
          ))}
          <button className={period === 'custom' ? 'on' : ''} onClick={() => setPeriod('custom')}>
            {t('rep_custom')}
          </button>
        </div>
        {period === 'custom' && <>
          <input className="inp inp--sm" type="date" value={from} onChange={e => setFrom(e.target.value)} />
          <input className="inp inp--sm" type="date" value={to} onChange={e => setTo(e.target.value)} />
        </>}
        <select className="sel sel--sm" value={role} onChange={e => setRole(e.target.value)}>
          <option value="">{t('rep_role')}: {t('rep_all')}</option>
          <option value="bolim_boshligi">{t('rep_heads')}</option>
          <option value="ijrochi">{t('rep_workers')}</option>
        </select>
      </div>

      <div className="content">
        {!data && <div className="empty">{t('loading')}</div>}
        {data && (
          <div className="tbl-wrap">
            <table className="tbl tbl--num">
              <thead>
                <tr>
                  <th>{t('rep_who')}</th><th>{t('rep_dep')}</th>
                  <th>{t('rep_given')}</th><th>{t('rep_ontime')}</th><th>{t('rep_late')}</th>
                  <th>{t('rep_notdone')}</th><th>{t('rep_inprog')}</th>
                  <th>{t('rep_returned')}</th><th>{t('rep_avg')}</th><th>{t('rep_pct')}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r: any) => (
                  <tr key={r.user_id} className="clickable" onClick={() => setPerson(r.user_id)}>
                    <td><div className="b">{r.full_name}</div>
                      <div className="xs muted">{t(ROLE_KEY[r.role] || 'r_ijrochi')}{r.position ? ` · ${r.position}` : ''}</div></td>
                    <td className="small">{r.department_name || '—'}</td>
                    <td className="mono">{r.given}</td>
                    <td className="mono is-good">{r.on_time}</td>
                    <td className="mono is-warn">{r.late_done}</td>
                    <td className="mono is-bad">{r.not_done}</td>
                    <td className="mono muted">{r.in_progress}</td>
                    <td className="mono muted">{r.returned}</td>
                    <td className="mono">{r.avg_late_days ? r.avg_late_days : '—'}</td>
                    <td><span className={pctClass(r.percent)}>{r.percent}%</span></td>
                  </tr>
                ))}
                {tot && (
                  <tr className="tbl__total">
                    <td className="b">{t('rep_total')}</td><td />
                    <td className="mono b">{tot.given}</td>
                    <td className="mono b">{tot.on_time}</td>
                    <td className="mono b">{tot.late_done}</td>
                    <td className="mono b">{tot.not_done}</td>
                    <td className="mono b">{tot.in_progress}</td>
                    <td className="mono b">{tot.returned}</td>
                    <td className="mono b">{tot.avg_late_days || '—'}</td>
                    <td><span className={pctClass(tot.percent)}>{tot.percent}%</span></td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {person && <PersonView id={person} period={period} from={from} to={to} onClose={() => setPerson(null)} />}
    </>
  )
}

function PersonView({ id, period, from, to, onClose }:
  { id: number; period: string; from: string; to: string; onClose: () => void }) {
  const { t } = useT()
  const { data } = useFetch<any>(`/reports/person/${id}`, {
    period, date_from: period === 'custom' ? from : undefined,
    date_to: period === 'custom' ? to : undefined,
  })
  const s = data?.stat
  return (
    <Modal title={data?.user?.full_name || t('rep_person')} onClose={onClose}>
      <div className="modal__b modal__b--one">
        {!data && <div className="empty">{t('loading')}</div>}
        {data && <>
          <div className="kv">
            <span>{t('ad_role')}</span><b>{data.user.role_name}</b>
            <span>{t('rep_period')}</span><b className="mono">{data.date_from} … {data.date_to}</b>
            {s && <>
              <span>{t('rep_given')}</span><b className="mono">{s.given}</b>
              <span>{t('rep_ontime')}</span><b className="mono is-good">{s.on_time}</b>
              <span>{t('rep_late')}</span><b className="mono is-warn">{s.late_done}</b>
              <span>{t('rep_notdone')}</span><b className="mono is-bad">{s.not_done}</b>
              <span>{t('rep_pct')}</span><b><span className={pctClass(s.percent)}>{s.percent}%</span></b>
            </>}
          </div>
          {!!data.late?.length && <section>
            <div className="lbl">{t('rep_late_list')}</div>
            <div className="tbl-wrap"><table className="tbl"><tbody>
              {data.late.map((x: any) => (
                <tr key={x.id}>
                  <td className="mono small nowrap">{x.code}</td>
                  <td>{x.title}</td>
                  <td className="mono small nowrap is-bad">{t('late_days', { d: x.late_days })}</td>
                </tr>
              ))}
            </tbody></table></div>
          </section>}
          {!!data.not_done?.length && <section>
            <div className="lbl">{t('rep_notdone_list')}</div>
            <div className="tbl-wrap"><table className="tbl"><tbody>
              {data.not_done.map((x: any) => (
                <tr key={x.id}>
                  <td className="mono small nowrap">{x.code}</td>
                  <td>{x.title}</td>
                  <td className="mono small nowrap">{dt(x.due_at)}</td>
                </tr>
              ))}
            </tbody></table></div>
          </section>}
        </>}
      </div>
      <div className="modal__f"><button className="btn" onClick={onClose}>{t('close')}</button></div>
    </Modal>
  )
}
