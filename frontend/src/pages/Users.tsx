import React, { useState } from 'react'
import { patch, post, invalidate } from '../lib/api'
import { useFetch } from '../lib/hooks'
import { useT, fmtDateTime } from '../lib/i18n'
import { useToast } from '../lib/toast'
import { useRefs, locLabel } from '../lib/refs'
import { PageHeader } from '../components/Layout'
import { Modal, Confirm } from '../components/Modal'

export default function Users() {
  const { t, lang } = useT()
  const { toastErr } = useToast()
  const [showBlocked, setShowBlocked] = useState(true)
  const { data, reload } = useFetch<any[]>('/users', { include_inactive: true })
  const { data: roles, reload: reloadRoles } = useFetch<any[]>('/roles')
  const { data: perms } = useFetch<string[]>('/roles/permissions')
  const { data: meta } = useFetch<any>('/meta')
  const pwMin = meta?.password_min ?? 4
  const { projects, locations } = useRefs()
  const [edit, setEdit] = useState<any>(null)
  const [tab, setTab] = useState<'users' | 'roles'>('users')
  const rows = (data || []).filter(u => showBlocked || u.is_active)
  const scopeLabel = (u: any) => u.scope_type === 'system' ? t('us_scope_system')
    : u.scope_type === 'project' ? (projects.find(p => p.id === u.scope_id)?.name || t('us_scope_project'))
    : (locations.find(l => l.id === u.scope_id)?.name || t('us_scope_location'))
  return (
    <>
      <PageHeader title={t('us_title')}>
        {tab === 'users' && <>
          <label className="check"><input type="checkbox" checked={showBlocked} onChange={e => setShowBlocked(e.target.checked)} />{t('us_blocked')}</label>
          <button className="btn btn--sm btn--p" onClick={() => setEdit({ full_name: '', login: '', password: '', role_id: roles?.[0]?.id, scope_type: 'system', scope_id: null, lang: 'uz', phone: '' })}>+ {t('us_new')}</button>
        </>}
      </PageHeader>
      <div className="tabs">
        <button className={'tab' + (tab === 'users' ? ' on' : '')} onClick={() => setTab('users')}>{t('us_title')}<em>{rows.length}</em></button>
        <button className={'tab' + (tab === 'roles' ? ' on' : '')} onClick={() => setTab('roles')}>{t('us_roles')}<em>{roles?.length || 0}</em></button>
      </div>
      <div className="content">
        {tab === 'users' ? (
          <>
            <div className="alert alert--info" style={{ marginBottom: 16 }}>{t('us_block_hint')}</div>
            <div className="tbl-wrap">
              <table className="tbl">
                <thead><tr><th>{t('us_name')}</th><th>{t('us_login')}</th><th>{t('us_role')}</th><th>{t('us_scope')}</th><th>{t('us_tg')}</th><th>{t('us_lang')}</th><th /></tr></thead>
                <tbody>{rows.map(u => (
                  <tr key={u.id} style={{ opacity: u.is_active ? 1 : .5 }}>
                    <td><b>{u.full_name}</b>{u.phone && <div className="xs muted">{u.phone}</div>}</td>
                    <td className="mono small">{u.login}</td>
                    <td>{u.role?.name}</td>
                    <td className="small muted">{scopeLabel(u)}</td>
                    <td>{u.telegram_user_id ? <span className="pill pill--t">✈ {t('us_linked')}</span> : <span className="pill pill--g">{t('us_not_linked')}</span>}</td>
                    <td className="mono xs">{u.lang}</td>
                    <td className="row" style={{ justifyContent: 'flex-end' }}>
                      <button className="btn btn--sm" onClick={() => setEdit(u)}>{t('edit')}</button>
                      <button className="btn btn--sm btn--ghost" onClick={async () => {
                        try { await post(`/users/${u.id}/${u.is_active ? 'block' : 'unblock'}`, {}); reload(); invalidate() } catch (e) { toastErr(e) }
                      }}>{u.is_active ? t('us_block') : t('us_unblock')}</button>
                    </td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </>
        ) : (
          <RolesGrid roles={roles || []} perms={perms || []} reload={reloadRoles} />
        )}
      </div>
      {edit && <UserDialog item={edit} roles={roles || []} projects={projects} locations={locations} pwMin={pwMin}
                           onClose={() => setEdit(null)} onSaved={() => { setEdit(null); reload(); invalidate() }} />}
    </>
  )
}

function RolesGrid({ roles, perms, reload }: any) {
  const { t } = useT()
  const { toastErr } = useToast()
  const [busy, setBusy] = useState(false)
  const toggle = async (role: any, p: string) => {
    if (role.code === 'admin' || busy) return
    setBusy(true)
    const next = role.permissions_json.includes(p) ? role.permissions_json.filter((x: string) => x !== p) : [...role.permissions_json, p]
    try { await patch(`/roles/${role.id}`, { permissions_json: next }); reload() } catch (e) { toastErr(e) } finally { setBusy(false) }
  }
  return (
    <div style={{ overflowX: 'auto' }}>
      <div className="perm-grid" style={{ gridTemplateColumns: `220px repeat(${roles.length}, minmax(80px,1fr))`, minWidth: 640 }}>
        <div className="h">{t('us_perm')}</div>
        {roles.map((r: any) => <div key={r.id} className="h c">{r.name}</div>)}
        {perms.map((p: string) => (
          <React.Fragment key={p}>
            <div className="mono xs">{p}</div>
            {roles.map((r: any) => (
              <div key={r.id} className="c" onClick={() => toggle(r, p)} style={{ cursor: r.code === 'admin' ? 'default' : 'pointer' }}>
                {r.permissions_json.includes(p) ? '✓' : <span className="faint">—</span>}
              </div>
            ))}
          </React.Fragment>
        ))}
      </div>
    </div>
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
        await post('/users', { full_name: f.full_name, login: f.login, password: f.password, phone: f.phone || null,
                               role_id: Number(f.role_id), scope_type: f.scope_type, scope_id: f.scope_type === 'system' ? null : Number(f.scope_id), lang: f.lang })
      }
      onSaved()
    } catch (e) { toastErr(e) }
  }
  const blocks = locations.filter((l: any) => l.kind === 'block')
  const valid = f.full_name?.trim() && (item.id || (f.login?.trim() && f.password?.length >= pwMin))
    && (!f.password || f.password.length >= pwMin) && (f.scope_type === 'system' || f.scope_id)
  return (
    <Modal title={item.id ? t('edit') : t('us_new')} onClose={onClose} footer={
      <><button className="btn" onClick={onClose}>{t('cancel')}</button><button className="btn btn--p" disabled={!valid} onClick={save}>{t('save')}</button></>}>
      <label className="lbl">{t('us_name')} <i>*</i><input className="inp" value={f.full_name} onChange={e => setF({ ...f, full_name: e.target.value })} /></label>
      <label className="lbl">{t('us_login')} <i>*</i><input className="inp" value={f.login} disabled={!!item.id} onChange={e => setF({ ...f, login: e.target.value })} /></label>
      <label className="lbl">{t('us_pw', { n: pwMin })} {!item.id && <i>*</i>}
        <input className="inp" type="password" value={f.password} onChange={e => setF({ ...f, password: e.target.value })} autoComplete="new-password" />
        {!!f.password && f.password.length < pwMin && <span className="field-err">{t('pf_pw_short', { n: pwMin })}</span>}</label>
      <label className="lbl">{t('us_phone')}<input className="inp" value={f.phone || ''} onChange={e => setF({ ...f, phone: e.target.value })} /></label>
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
