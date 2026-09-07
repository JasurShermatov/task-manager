import React, { useEffect, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { useT, Lang, fmtDateTime } from '../lib/i18n'
import { useFetch } from '../lib/hooks'
import { patch, post, invalidate } from '../lib/api'

function Item({ to, title, sub, end }: { to: string; title: string; sub: string; end?: boolean }) {
  return (
    <NavLink to={to} end={end} className={({ isActive }) => 'sitem' + (isActive ? ' sitem--on' : '')}>
      <b>{title}</b><span>{sub}</span>
    </NavLink>
  )
}

export default function Layout({ children }: { children: React.ReactNode }) {
  const { me, logout, can } = useAuth()
  const { t, lang, setLang } = useT()
  const [open, setOpen] = useState(false)
  const u = me!.user
  const changeLang = async (l: Lang) => {
    setLang(l)
    try { await patch(`/users/${u.id}`, { lang: l }) } catch {}
  }
  return (
    <div className="app">
      <aside className={'side' + (open ? ' open' : '')} onClick={() => setOpen(false)}>
        <div className="side__brand">
          <div className="side__logo">SAFF<i /></div>
          <div className="side__sub">{t('app_sub')}</div>
        </div>
        <nav className="side__nav">
          <div className="sgrp">{t('grp_work')}</div>
          <Item to="/tasks" title={t('nav_tasks')} sub={t('sub_tasks')} />
          <Item to="/table" title={t('nav_table')} sub={t('sub_table')} />
          {can('reports.read') && <Item to="/reports" title={t('nav_reports')} sub={t('sub_reports')} />}
          {can('tasks.bulk_create') && <Item to="/bulk" title={t('nav_bulk')} sub={t('sub_bulk')} />}
          <div className="sgrp">{t('grp_settings')}</div>
          {(can('admin.projects') || can('tasks.create')) && <Item to="/projects" title={t('nav_projects')} sub={t('sub_projects')} />}
          {can('admin.templates') && <Item to="/settings/templates" title={t('nav_templates')} sub={t('sub_templates')} />}
          {can('admin.task_types') && <Item to="/settings/types" title={t('nav_types')} sub={t('sub_types')} />}
          {can('admin.users') && <Item to="/settings/users" title={t('nav_users')} sub={t('sub_users')} />}
          <Item to="/settings/telegram" title={t('nav_telegram')} sub={t('sub_telegram')} />
          <Item to="/settings/profile" title={t('nav_profile')} sub={t('sub_profile')} />
        </nav>
        <div className="side__foot">
          <div className="side__user">{u.full_name}<span>{u.role?.name} · {u.login}</span></div>
          <div className="seg">
            {(['uz', 'ru', 'en'] as Lang[]).map(x => <button key={x} className={lang === x ? 'on' : ''} onClick={e => { e.stopPropagation(); changeLang(x) }}>{x === 'uz' ? "O'zbekcha" : x === 'ru' ? 'Русский' : 'English'}</button>)}
          </div>
          <button className="btn-ghost-dark" onClick={logout}>{t('logout')}</button>
        </div>
      </aside>
      <main className="main">
        <div style={{ position: 'absolute', top: 14, left: 12 }}>
          <button className="icon-btn burger" onClick={() => setOpen(true)}>☰</button>
        </div>
        {children}
      </main>
    </div>
  )
}

export function PageHeader({ title, children, extra }: { title: string; children?: React.ReactNode; extra?: React.ReactNode }) {
  const { me, can } = useAuth()
  const { t } = useT()
  const viewOnly = !can('tasks.create') && !can('tasks.start')
  return (
    <div className="top">
      <h1>{title}</h1>
      {extra}
      {viewOnly && <span className="chip chip--warn">{t('perm_view_only')}</span>}
      <div className="top__right">
        {children}
        <NotifBell />
      </div>
    </div>
  )
}

export function NotifBell() {
  const { t, lang } = useT()
  const nav = useNavigate()
  const [open, setOpen] = useState(false)
  const { data: cnt, reload } = useFetch<{ count: number }>('/notifications/unread-count')
  const { data: list, reload: reloadList } = useFetch<any[]>(open ? '/notifications' : null, { limit: 30 })
  useEffect(() => { const i = setInterval(reload, 30000); return () => clearInterval(i) }, [reload])
  const markAll = async () => { await post('/notifications/read', {}); reload(); reloadList() }
  const openTask = async (n: any) => {
    await post('/notifications/read', { ids: [n.id] }); reload(); setOpen(false)
    if (n.task_id) nav(`/tasks/${n.task_id}`)
  }
  return (
    <div style={{ position: 'relative' }}>
      <button className="icon-btn" onClick={() => setOpen(o => !o)} title={t('notif')}>🔔{!!cnt?.count && <span className="badge">{cnt.count}</span>}</button>
      {open && <div className="notif-back" onClick={() => setOpen(false)} />}
      {open && (
        <div className="notif-pop" onClick={e => e.stopPropagation()}>
          <div className="notif-pop__h row">
            <b>{t('notif')}</b><span className="spacer" />
            <button className="btn btn--sm btn--ghost" onClick={markAll}>{t('mark_read')}</button>
          </div>
          {!list?.length && <div className="empty">{t('notif_empty')}</div>}
          {list?.map(n => (
            <div key={n.id} className={'notif-item' + (n.is_read ? '' : ' unread')} onClick={() => openTask(n)}>
              <div className="row"><b className="mono xs">{n.payload_json?.code}</b><span className="xs faint right">{fmtDateTime(n.created_at, lang)}</span></div>
              <div>{t('h_' + n.event) !== 'h_' + n.event ? t('h_' + n.event) : n.event} — {n.payload_json?.title}</div>
              {n.payload_json?.reason && <div className="xs muted">{n.payload_json.reason}{n.payload_json.note ? ': ' + n.payload_json.note : ''}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
