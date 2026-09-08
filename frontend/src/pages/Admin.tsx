import React, { useMemo, useState } from 'react'
import { patch, post, get, invalidate } from '../lib/api'
import { useFetch } from '../lib/hooks'
import { useT, fmtDateTime } from '../lib/i18n'
import { useToast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { useRefs, initials, locLabel } from '../lib/refs'
import { PageHeader } from '../components/Layout'
import { Modal } from '../components/Modal'

type Tab = 'users' | 'roles' | 'bot' | 'panels'

export default function Admin() {
  const { t } = useT()
  const { can } = useAuth()
  const [tab, setTab] = useState<Tab>('users')
  const tabs: [Tab, string, boolean][] = [
    ['users', t('ad_tab_users'), can('admin.users')],
    ['roles', t('ad_tab_roles'), can('admin.roles')],
    ['bot', t('ad_tab_bot'), can('admin.bot')],
    ['panels', t('ad_tab_panels'), true],
  ]
  const allowed = tabs.filter(x => x[2])
  const active = allowed.some(x => x[0] === tab) ? tab : allowed[0]?.[0]

  return (
    <>
      <PageHeader title={t('ad_title')} />
      <div className="tabs">
        {allowed.map(([k, label]) => (
          <button key={k} className={'tab' + (active === k ? ' on' : '')} onClick={() => setTab(k)}>{label}</button>
        ))}
      </div>
      <div className="content">
        {active === 'users' && <AccessTab />}
        {active === 'roles' && <RolesTab />}
        {active === 'bot' && <BotTab />}
        {active === 'panels' && <PanelsTab />}
      </div>
    </>
  )
}

/* ------------------------------------------------------------------ kirish huquqlari */
function AccessTab() {
  const { t, lang } = useT()
  const { toastErr, toast } = useToast()
  const { projects, locations } = useRefs()
  const { data: users, reload } = useFetch<any[]>('/users', { include_inactive: true })
  const { data: roles } = useFetch<any[]>('/roles')
  const { data: meta } = useFetch<any>('/meta')
  const pwMin = meta?.password_min ?? 4
  const [edit, setEdit] = useState<any>(null)
  const [pwFor, setPwFor] = useState<any>(null)
  const [q, setQ] = useState('')

  const rows = (users || []).filter(u => {
    const s = q.trim().toLowerCase()
    return !s || u.full_name.toLowerCase().includes(s) || u.login.toLowerCase().includes(s)
  })
  const scopeOf = (u: any) => u.scope_type === 'system' ? t('us_scope_system')
    : u.scope_type === 'project' ? (projects.find(p => p.id === u.scope_id)?.name || '—')
    : (locLabel(locations, u.scope_id) || '—')

  const toggleActive = async (u: any) => {
    try { await post(`/users/${u.id}/${u.is_active ? 'block' : 'unblock'}`, {}); reload(); invalidate() }
    catch (e) { toastErr(e) }
  }

  return (
    <>
      <div className="row wrap" style={{ marginBottom: 14 }}>
        <input className="inp inp--sm" style={{ minWidth: 220 }} placeholder={t('sf_search')} value={q} onChange={e => setQ(e.target.value)} />
        <span className="spacer" />
        <button className="btn btn--sm btn--p" onClick={() => setEdit({
          full_name: '', login: '', password: '', role_id: roles?.find(r => r.code === 'bajaruvchi')?.id ?? roles?.[0]?.id,
          scope_type: 'system', scope_id: null, lang: 'uz', phone: '',
        })}>{t('ad_new_user')}</button>
      </div>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr>
            <th>{t('us_name')}</th><th>{t('us_login')}</th><th>{t('us_role')}</th><th>{t('us_scope')}</th>
            <th>{t('us_tg')}</th><th>{t('sf_last_login')}</th><th />
          </tr></thead>
          <tbody>
            {rows.map(u => (
              <tr key={u.id} style={{ opacity: u.is_active ? 1 : .5 }}>
                <td><div className="row"><span className="av">{initials(u.full_name)}</span><b>{u.full_name}</b></div></td>
                <td className="mono small">{u.login}</td>
                <td>{u.role?.name}</td>
                <td className="small muted">{scopeOf(u)}</td>
                <td>{u.telegram_user_id ? <span className="pill pill--t">✈</span> : <span className="faint">—</span>}</td>
                <td className="mono xs muted">{u.last_login_at ? fmtDateTime(u.last_login_at, lang) : t('sf_never')}</td>
                <td>
                  <div className="row" style={{ justifyContent: 'flex-end' }}>
                    <button className="btn btn--sm" onClick={() => setEdit(u)}>{t('edit')}</button>
                    <button className="btn btn--sm" onClick={() => setPwFor(u)}>{t('ad_reset_pw')}</button>
                    <button className="btn btn--sm btn--ghost" onClick={() => toggleActive(u)}>
                      {u.is_active ? t('us_block') : t('us_unblock')}</button>
                  </div>
                </td>
              </tr>
            ))}
            {!rows.length && <tr><td colSpan={7}><div className="empty">{t('sf_none')}</div></td></tr>}
          </tbody>
        </table>
      </div>
      <div className="hint" style={{ marginTop: 12 }}>{t('us_block_hint')}</div>

      {edit && <UserDialog item={edit} roles={roles || []} projects={projects} locations={locations} pwMin={pwMin}
                           onClose={() => setEdit(null)} onSaved={() => { setEdit(null); reload(); invalidate() }} />}
      {pwFor && <PasswordDialog u={pwFor} pwMin={pwMin} onClose={() => setPwFor(null)}
                                onSaved={() => { setPwFor(null); toast(t('ad_pw_set')) }} />}
    </>
  )
}

function PasswordDialog({ u, pwMin, onClose, onSaved }: any) {
  const { t } = useT()
  const { toastErr } = useToast()
  const [pw, setPw] = useState('')
  const save = async () => {
    try { await patch(`/users/${u.id}`, { password: pw }); onSaved() } catch (e) { toastErr(e) }
  }
  return (
    <Modal title={t('ad_pw_for', { name: u.full_name })} sm onClose={onClose} footer={
      <><button className="btn" onClick={onClose}>{t('cancel')}</button>
        <button className="btn btn--p" disabled={pw.length < pwMin} onClick={save}>{t('save')}</button></>}>
      <label className="lbl full">{t('pf_pw_new', { n: pwMin })}
        <input className="inp" autoFocus value={pw} onChange={e => setPw(e.target.value)} />
        {!!pw && pw.length < pwMin && <span className="field-err">{t('pf_pw_short', { n: pwMin })}</span>}
        <span className="hint">{t('ad_pw_copy')}</span></label>
    </Modal>
  )
}

function UserDialog({ item, roles, projects, locations, pwMin, onClose, onSaved }: any) {
  const { t } = useT()
  const { toastErr } = useToast()
  const [f, setF] = useState<any>({ ...item, password: '' })
  const save = async () => {
    try {
      if (item.id) {
        const body: any = {}
        for (const k of ['full_name', 'phone', 'role_id', 'scope_type', 'scope_id', 'lang']) if (f[k] !== item[k]) body[k] = f[k]
        if (f.password) body.password = f.password
        await patch(`/users/${item.id}`, body)
      } else {
        await post('/users', {
          full_name: f.full_name, login: f.login, password: f.password, phone: f.phone || null,
          role_id: Number(f.role_id), scope_type: f.scope_type,
          scope_id: f.scope_type === 'system' ? null : Number(f.scope_id), lang: f.lang,
        })
      }
      onSaved()
    } catch (e) { toastErr(e) }
  }
  const blocks = locations.filter((l: any) => l.kind === 'block')
  const valid = f.full_name?.trim() && (item.id || (f.login?.trim() && f.password?.length >= pwMin))
    && (!f.password || f.password.length >= pwMin) && (f.scope_type === 'system' || f.scope_id)
  return (
    <Modal title={item.id ? f.full_name : t('ad_new_user')} onClose={onClose} footer={
      <><button className="btn" onClick={onClose}>{t('cancel')}</button>
        <button className="btn btn--p" disabled={!valid} onClick={save}>{t('save')}</button></>}>
      <label className="lbl">{t('us_name')} <i>*</i>
        <input className="inp" value={f.full_name} onChange={e => setF({ ...f, full_name: e.target.value })} /></label>
      <label className="lbl">{t('us_phone')}
        <input className="inp" value={f.phone || ''} onChange={e => setF({ ...f, phone: e.target.value })} /></label>
      <label className="lbl">{t('us_login')} <i>*</i>
        <input className="inp" value={f.login} disabled={!!item.id} onChange={e => setF({ ...f, login: e.target.value })} /></label>
      <label className="lbl">{t('us_pw', { n: pwMin })} {!item.id && <i>*</i>}
        <input className="inp" value={f.password} onChange={e => setF({ ...f, password: e.target.value })} />
        {!!f.password && f.password.length < pwMin && <span className="field-err">{t('pf_pw_short', { n: pwMin })}</span>}</label>
      <label className="lbl">{t('us_role')} <i>*</i>
        <select className="sel" value={f.role_id} onChange={e => setF({ ...f, role_id: Number(e.target.value) })}>
          {roles.map((r: any) => <option key={r.id} value={r.id}>{r.name}</option>)}</select></label>
      <label className="lbl">{t('us_lang')}
        <select className="sel" value={f.lang} onChange={e => setF({ ...f, lang: e.target.value })}>
          <option value="uz">O'zbekcha</option><option value="ru">Русский</option><option value="en">English</option></select></label>
      <label className="lbl">{t('us_scope')}
        <select className="sel" value={f.scope_type} onChange={e => setF({ ...f, scope_type: e.target.value, scope_id: null })}>
          <option value="system">{t('us_scope_system')}</option>
          <option value="project">{t('us_scope_project')}</option>
          <option value="location">{t('us_scope_location')}</option></select></label>
      {f.scope_type === 'project' && (
        <label className="lbl">{t('cr_project')} <i>*</i>
          <select className="sel" value={f.scope_id || ''} onChange={e => setF({ ...f, scope_id: Number(e.target.value) })}>
            <option value="">—</option>{projects.map((p: any) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      )}
      {f.scope_type === 'location' && (
        <label className="lbl">{t('us_scope_location')} <i>*</i>
          <select className="sel" value={f.scope_id || ''} onChange={e => setF({ ...f, scope_id: Number(e.target.value) })}>
            <option value="">—</option>{blocks.map((l: any) => <option key={l.id} value={l.id}>{locLabel(locations, l.id)}</option>)}</select></label>
      )}
    </Modal>
  )
}

/* ------------------------------------------------------------------ rollar */
function RolesTab() {
  const { t } = useT()
  const { toastErr } = useToast()
  const { data: roles, reload } = useFetch<any[]>('/roles')
  const { data: groups } = useFetch<any[]>('/roles/permission-groups')
  const [busy, setBusy] = useState(false)

  const label = (p: string) => {
    const key = 'perm_' + p.replace('.', '_')
    const v = t(key)
    return v === key ? p : v
  }
  const toggle = async (role: any, p: string) => {
    if (role.code === 'admin' || busy) return
    setBusy(true)
    const next = role.permissions_json.includes(p)
      ? role.permissions_json.filter((x: string) => x !== p)
      : [...role.permissions_json, p]
    try { await patch(`/roles/${role.id}`, { permissions_json: next }); await reload() }
    catch (e) { toastErr(e) } finally { setBusy(false) }
  }
  if (!roles || !groups) return <div className="empty">{t('loading')}</div>
  const cols = `minmax(200px, 1.4fr) repeat(${roles.length}, minmax(74px, 1fr))`
  return (
    <>
      <div className="hint" style={{ marginBottom: 12 }}>{t('ad_roles_hint')}</div>
      <div className="matrix-wrap">
        <div className="matrix" style={{ gridTemplateColumns: cols }}>
          <div className="matrix__h matrix__sticky" />
          {roles.map(r => <div key={r.id} className="matrix__h matrix__c">{r.name}</div>)}
          {groups.map(g => (
            <React.Fragment key={g.group}>
              <div className="matrix__grp matrix__sticky" style={{ gridColumn: `1 / span ${roles.length + 1}` }}>
                {t('pg_' + g.group)}
              </div>
              {g.permissions.map((p: string) => (
                <React.Fragment key={p}>
                  <div className="matrix__sticky matrix__name">{label(p)}<em>{p}</em></div>
                  {roles.map(r => {
                    const on = r.permissions_json.includes(p)
                    const locked = r.code === 'admin'
                    return (
                      <div key={r.id} className={'matrix__c matrix__cell' + (on ? ' on' : '') + (locked ? ' locked' : '')}
                           onClick={() => toggle(r, p)} title={locked ? '' : label(p)}>
                        {on ? '✓' : ''}
                      </div>
                    )
                  })}
                </React.Fragment>
              ))}
            </React.Fragment>
          ))}
        </div>
      </div>
    </>
  )
}

/* ------------------------------------------------------------------ bot */
function BotTab() {
  const { t } = useT()
  const { toast, toastErr } = useToast()
  const { data, reload } = useFetch<any>('/settings')
  const [val, setVal] = useState<string | null>(null)
  const current = val ?? (data?.bot_username || '')
  const url = current ? `https://t.me/${current}` : ''
  const save = async () => {
    try { await patch('/settings', { bot_username: current }); await reload(); setVal(null); toast(t('ad_bot_saved')) }
    catch (e) { toastErr(e) }
  }
  return (
    <div style={{ maxWidth: 560 }}>
      <div className="blk">
        <div className="blk__t">{t('ad_bot_title')}</div>
        <label className="lbl">{t('ad_bot_username')}
          <div className="row">
            <span className="faint mono">@</span>
            <input className="inp" style={{ flex: 1 }} value={current} placeholder="txt_task_managerBot"
                   onChange={e => setVal(e.target.value.replace(/^@/, ''))} />
          </div>
        </label>
        <div className="row" style={{ marginTop: 14 }}>
          <button className="btn btn--p" disabled={!current || current === data?.bot_username} onClick={save}>{t('save')}</button>
          {url
            ? <a className="btn btn--tg" href={url} target="_blank" rel="noreferrer">✈ {t('ad_bot_open')}</a>
            : <span className="faint small">{t('ad_bot_empty')}</span>}
        </div>
        <div className="hint" style={{ marginTop: 12 }}>{t('ad_bot_hint')}</div>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ rol panellari */
const PANELS: [string, string, string | null][] = [
  ['nav_tasks', 'sub_tasks', null],
  ['nav_table', 'sub_table', null],
  ['nav_reports', 'sub_reports', 'reports.read'],
  ['nav_bulk', 'sub_bulk', 'tasks.bulk_create'],
  ['nav_projects', 'sub_projects', 'tasks.create'],
  ['nav_templates', 'sub_templates', 'admin.templates'],
  ['nav_types', 'sub_types', 'admin.task_types'],
  ['nav_staff', 'sub_staff', 'admin.users'],
  ['nav_admin', 'sub_admin', 'admin.users'],
  ['nav_telegram', 'sub_telegram', null],
  ['nav_profile', 'sub_profile', null],
]

function PanelsTab() {
  const { t } = useT()
  const { data: roles } = useFetch<any[]>('/roles')
  if (!roles) return <div className="empty">{t('loading')}</div>
  const cols = `minmax(190px, 1.2fr) repeat(${roles.length}, minmax(74px, 1fr))`
  return (
    <>
      <div className="hint" style={{ marginBottom: 12 }}>{t('ad_panels_hint')}</div>
      <div className="matrix-wrap">
        <div className="matrix" style={{ gridTemplateColumns: cols }}>
          <div className="matrix__h matrix__sticky" />
          {roles.map(r => <div key={r.id} className="matrix__h matrix__c">{r.name}</div>)}
          {PANELS.map(([nav, sub, perm]) => (
            <React.Fragment key={nav}>
              <div className="matrix__sticky matrix__name">{t(nav)}<em>{t(sub)}</em></div>
              {roles.map(r => {
                const on = !perm || r.permissions_json.includes(perm)
                return <div key={r.id} className={'matrix__c matrix__cell locked' + (on ? ' on' : '')}
                            title={on ? t('ad_sees') : t('ad_hidden')}>{on ? '✓' : '—'}</div>
              })}
            </React.Fragment>
          ))}
        </div>
      </div>
    </>
  )
}
