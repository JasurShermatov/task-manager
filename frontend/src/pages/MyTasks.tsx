import React, { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { invalidate, post } from '../lib/api'
import { PageHeader } from '../components/Layout'
import SubmitTask from '../components/SubmitTask'
import TaskDrawer from '../components/TaskDrawer'
import { dt, STATUS_KEY, STATUS_PILL } from '../lib/fmt'
import { useFetch } from '../lib/hooks'
import { useT } from '../lib/i18n'
import { useToast } from '../lib/toast'

/** «Vazifalarim»: faqat o'ziga berilgan vazifalar va bitta ish — dalil bilan topshirish.
 *  Boshliq va assistant ham shu ekranga kiradi, chunki ular bir-biriga vazifa bera oladi;
 *  shuning uchun so'rovda `mine: true` — aks holda boshqaruvchiga hamma vazifa ko'rinardi. */
export default function MyTasks() {
  const { t } = useT()
  const nav = useNavigate()
  const { id } = useParams()
  const { toastErr } = useToast()
  const [submitting, setSubmitting] = useState<any>(null)
  const { data, reload } = useFetch<any>('/tasks',
    { status: 'new,progress,submitted', mine: true, per_page: 50 })
  const { data: done } = useFetch<any>('/tasks', { status: 'done', mine: true, per_page: 10 })

  const start = async (tk: any) => {
    try { await post(`/tasks/${tk.id}/start`); invalidate(); reload() } catch (e) { toastErr(e) }
  }

  const items = data?.items || []
  return (
    <>
      <PageHeader title={t('nav_my')} extra={<span className="chip">{data?.total ?? 0}</span>} />
      <div className="content">
        {!items.length && <div className="empty">{t('empty')}</div>}
        <div className="mine">
          {items.map((tk: any) => (
            <article key={tk.id} className={'mcard' + (tk.is_late ? ' mcard--late' : '')}>
              <div className="row wrap mcard__top">
                <span className="mono xs">{tk.code}</span>
                <span className={'pill ' + (STATUS_PILL[tk.status] || 'pill--g')}>{t(STATUS_KEY[tk.status])}</span>
                {tk.is_late && <span className="pill pill--b">
                  {tk.late_days ? t('late_days', { d: tk.late_days })
                    : t('late_hours', { h: Math.max(1, tk.late_hours) })}
                </span>}
                {!!tk.return_count && <span className="pill pill--w">↩️ {tk.return_count}</span>}
              </div>
              <h3 onClick={() => nav(`/my/${tk.id}`)}>{tk.title}</h3>
              <div className="mcard__meta mono xs">📅 {dt(tk.due_at)} · 👤 {tk.created_by_name}</div>
              {tk.description && <p className="pre small muted">{tk.description}</p>}
              <div className="row wrap mcard__act">
                {tk.permissions?.start &&
                  <button className="btn btn--sm" onClick={() => start(tk)}>{t('a_start')}</button>}
                {tk.permissions?.submit &&
                  <button className="btn btn--sm btn--p" onClick={() => setSubmitting(tk)}>{t('a_submit')}</button>}
                <button className="btn btn--sm btn--ghost" onClick={() => nav(`/my/${tk.id}`)}>{t('a_comment')}</button>
              </div>
            </article>
          ))}
        </div>

        {!!done?.items?.length && (
          <section className="panel" style={{ marginTop: 22 }}>
            <div className="panel__h"><b>{t('st_done')}</b><span className="chip">{done.total}</span></div>
            <div className="tbl-wrap"><table className="tbl"><tbody>
              {done.items.map((tk: any) => (
                <tr key={tk.id} className="clickable" onClick={() => nav(`/my/${tk.id}`)}>
                  <td className="mono small nowrap">{tk.code}</td>
                  <td>{tk.title}</td>
                  <td className="mono small nowrap">{dt(tk.done_at)}</td>
                </tr>
              ))}
            </tbody></table></div>
          </section>
        )}
      </div>

      {id && <TaskDrawer id={Number(id)} onClose={() => nav('/my')} />}
      {submitting && <SubmitTask task={submitting} onClose={() => setSubmitting(null)} onDone={reload} />}
    </>
  )
}
