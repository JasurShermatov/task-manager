import React, { useEffect, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { patch, post } from '../lib/api'
import { useAuth } from '../lib/auth'
import { dt } from '../lib/fmt'
import { useFetch } from '../lib/hooks'
import { Lang, useT } from '../lib/i18n'

function Item({ to, title, sub, end }: { to: string; title: string; sub: string; end?: boolean }) {
  return (
    <NavLink to={to} end={end} className={({ isActive }) => 'sitem' + (isActive ? ' sitem--on' : '')}>
      <b>{title}</b><span>{sub}</span>
    </NavLink>
  )
}

/** Yon menyu holati — burger tugmasi sarlavha qatorining ichida turishi uchun. */
const SideCtx = React.createContext<{ open: boolean; setOpen: (v: boolean) => void }>(
  { open: false, setOpen: () => {} })

export default function Layout({ children }: { children: React.ReactNode }) {
  const { me, logout, isManager } = useAuth()
  const { t, lang, setLang } = useT()
  const [open, setOpen] = useState(false)
  const u = me!
  const changeLang = async (l: Lang) => {
    setLang(l)
    try { await patch('/auth/me', { lang: l }) } catch {}
  }
  return (
    <SideCtx.Provider value={{ open, setOpen }}>
      <div className="app">
        {open && <div className="side-back" onClick={() => setOpen(false)} />}
        <aside className={'side' + (open ? ' open' : '')} onClick={() => setOpen(false)}>
          <div className="side__brand">
            <div className="side__logo">SAFF<i /></div>
            <div className="side__sub">{t('app_sub')}</div>
          </div>
          <nav className="side__nav">
            {isManager && <>
              <Item to="/home" title={t('nav_home')} sub={t('sub_home')} />
              <Item to="/tasks" title={t('nav_tasks')} sub={t('sub_tasks')} />
            </>}
            {/* «Vazifalarim» hammada: boshliq bilan assistant bir-biriga vazifa bera oladi,
                demak ularning ham o'zlariga berilgan ishi bo'ladi. */}
            <Item to="/my" title={t('nav_my')} sub={t('sub_my')} />
            {isManager && <>
              <Item to="/reports" title={t('nav_reports')} sub={t('sub_reports')} />
              <Item to="/admin" title={t('nav_admin')} sub={t('sub_admin')} />
            </>}
            <Item to="/settings" title={t('nav_settings')} sub={t('sub_settings')} />
          </nav>
          <div className="side__foot">
            <div className="side__user">{u.full_name}<span>{u.role_name} · {u.login}</span></div>
            <div className="seg seg--full">
              {(['uz', 'ru', 'en'] as Lang[]).map(x => (
                <button key={x} className={lang === x ? 'on' : ''}
                        onClick={e => { e.stopPropagation(); changeLang(x) }}>
                  {x === 'uz' ? "O'zbekcha" : x === 'ru' ? 'Русский' : 'English'}
                </button>
              ))}
            </div>
            <button className="btn-ghost-dark" onClick={logout}>{t('logout')}</button>
          </div>
        </aside>
        <main className="main">{children}</main>
      </div>
    </SideCtx.Provider>
  )
}

export function PageHeader({ title, children, extra }:
  { title: string; children?: React.ReactNode; extra?: React.ReactNode }) {
  const { setOpen } = React.useContext(SideCtx)
  return (
    <div className="top">
      <div className="top__title">
        <button className="icon-btn burger" onClick={() => setOpen(true)} aria-label="menu">☰</button>
        <h1>{title}</h1>
      </div>
      {extra && <div className="top__extra">{extra}</div>}
      <div className="top__right">{children}</div>
      <NotifBell />
    </div>
  )
}

export function NotifBell() {
  const { t } = useT()
  const nav = useNavigate()
  const { isManager } = useAuth()
  const [open, setOpen] = useState(false)
  const { data: cnt, reload } = useFetch<{ count: number }>('/notifications/unread-count')
  const { data: list, reload: reloadList } = useFetch<any[]>(open ? '/notifications' : null, { limit: 30 })
  useEffect(() => { const i = setInterval(reload, 30000); return () => clearInterval(i) }, [reload])
  const markAll = async () => { await post('/notifications/read', {}); reload(); reloadList() }
  const openTask = async (n: any) => {
    await post('/notifications/read', { ids: [n.id] })
    reload(); setOpen(false)
    if (n.task_id) nav(`${isManager ? '/tasks' : '/my'}/${n.task_id}`)
  }
  return (
    <div className="notif-wrap">
      <button className="icon-btn" onClick={() => setOpen(o => !o)} aria-label="notifications">
        🔔{!!cnt?.count && <span className="badge">{cnt.count}</span>}
      </button>
      {open && <div className="notif-back" onClick={() => setOpen(false)} />}
      {open && (
        <div className="notif-pop" onClick={e => e.stopPropagation()}>
          <div className="notif-pop__h row">
            <b>🔔</b><span className="spacer" />
            <button className="btn btn--sm btn--ghost" onClick={markAll}>✓</button>
          </div>
          {!list?.length && <div className="empty">{t('empty')}</div>}
          {list?.map(n => (
            <div key={n.id} className={'notif-item' + (n.is_read ? '' : ' unread')}
                 onClick={() => openTask(n)}>
              <div className="row">
                <b className="mono xs">{n.payload?.code}</b>
                <span className="xs faint right">{dt(n.created_at)}</span>
              </div>
              <div>{n.payload?.title}</div>
              {n.payload?.reason && <div className="xs muted">{n.payload.reason}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
