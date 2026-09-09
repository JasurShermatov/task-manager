import React, { useState } from 'react'
import { del, invalidate, patch, post } from '../lib/api'
import { PageHeader } from '../components/Layout'
import Modal, { Confirm } from '../components/Modal'
import { useAuth } from '../lib/auth'
import { useDebounce, useFetch } from '../lib/hooks'
import { Key, useT } from '../lib/i18n'
import { useToast } from '../lib/toast'

type Tab = 'deps' | 'staff' | 'asst'

/** Administratsiya — uchta alohida oyna: «Bo'limlar» (bo'lim + boshlig'i),
 *  «Asosiy bo'lim xodimlari» va «Assistantlar».
 *  Assistantlar oynasi faqat boshliqqa ko'rinadi — assistant o'ziga teng hisob ocha olmaydi.
 *  Server ham shuni tekshiradi, bu yerda faqat tugmani yashiramiz. */
export default function Admin() {
  const { t } = useT()
  const { me } = useAuth()
  const isBoss = me?.role === 'boss'
  const [tab, setTab] = useState<Tab>('deps')
  return (
    <>
      <PageHeader title={t('nav_admin')} />
      <div className="bar">
        <div className="seg seg--light">
          <button className={tab === 'deps' ? 'on' : ''} onClick={() => setTab('deps')}>{t('ad_deps')}</button>
          <button className={tab === 'staff' ? 'on' : ''} onClick={() => setTab('staff')}>{t('ad_staff')}</button>
          {isBoss && (
            <button className={tab === 'asst' ? 'on' : ''} onClick={() => setTab('asst')}>{t('ad_assistants')}</button>
          )}
        </div>
      </div>
      <div className="content">
        {tab === 'deps' ? <Departments /> : tab === 'staff' ? <Staff /> : isBoss ? <Assistants /> : null}
      </div>
    </>
  )
}

// ---------------------------------------------------------------- bo'limlar
function Departments() {
  const { t } = useT()
  const { toast, toastErr } = useToast()
  const { data: deps, reload } = useFetch<any[]>('/departments')
  const { data: heads, reload: reloadHeads } = useFetch<any[]>('/users', { role: 'bolim_boshligi', active: true })
  const [editing, setEditing] = useState<any>(null)
  const [person, setPerson] = useState<any>(null)
  const [askDel, setAskDel] = useState<any>(null)

  const refresh = () => { reload(); reloadHeads(); invalidate() }
  const saveDep = async (name: string) => {
    try {
      if (editing?.id) await patch(`/departments/${editing.id}`, { name, sort_order: editing.sort_order || 0 })
      else await post('/departments', { name, sort_order: (deps?.length || 0) })
      toast(t('ad_saved')); setEditing(null); refresh()
    } catch (e) { toastErr(e) }
  }
  const removeDep = async () => {
    try { await del(`/departments/${askDel.id}`); refresh() } catch (e) { toastErr(e) } finally { setAskDel(null) }
  }

  return (
    <>
      <div className="row wrap" style={{ marginBottom: 12 }}>
        <button className="btn btn--p" onClick={() => setEditing({ name: '' })}>{t('ad_new_dep')}</button>
        <button className="btn" onClick={() => setPerson({ role: 'bolim_boshligi' })}>{t('ad_new_head')}</button>
      </div>

      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr>
            <th>{t('ad_dep_name')}</th><th>{t('ad_head')}</th>
            <th>{t('ad_open')}</th><th>{t('ad_late')}</th><th />
          </tr></thead>
          <tbody>
            {deps?.map(d => {
              const head = heads?.find(h => h.department_id === d.id)
              return (
                <tr key={d.id} className={d.is_active ? '' : 'is-off'}>
                  <td className="b">{d.name}</td>
                  <td>
                    {head
                      ? <button className="link" onClick={() => setPerson(head)}>{head.full_name}</button>
                      : <span className="muted small">{t('ad_no_head')}</span>}
                  </td>
                  <td className="mono">{d.open_tasks}</td>
                  <td className={'mono' + (d.late_tasks ? ' is-bad' : '')}>{d.late_tasks}</td>
                  <td className="nowrap right-cell">
                    <button className="btn btn--sm" onClick={() => setEditing(d)}>{t('edit')}</button>
                    <button className="btn btn--sm btn--danger" onClick={() => setAskDel(d)}>{t('delete')}</button>
                  </td>
                </tr>
              )
            })}
            {!deps?.length && <tr><td colSpan={5}><div className="empty">{t('empty')}</div></td></tr>}
          </tbody>
        </table>
      </div>

      {editing && <DepForm dep={editing} onSave={saveDep} onClose={() => setEditing(null)} />}
      {person && <PersonForm user={person} departments={deps || []} lockRole="bolim_boshligi"
                             onClose={() => { setPerson(null); refresh() }} />}
      {askDel && <Confirm text={`${t('ad_del_dep')} ${askDel.name}`} onOk={removeDep} onClose={() => setAskDel(null)} />}
    </>
  )
}

function DepForm({ dep, onSave, onClose }: { dep: any; onSave: (n: string) => void; onClose: () => void }) {
  const { t } = useT()
  const [name, setName] = useState(dep.name || '')
  return (
    <Modal title={dep.id ? t('edit') : t('ad_new_dep')} onClose={onClose} small>
      <div className="modal__b modal__b--one">
        <label className="lbl">{t('ad_dep_name')} *
          <input className="inp" autoFocus value={name} onChange={e => setName(e.target.value)} />
        </label>
      </div>
      <div className="modal__f">
        <button className="btn" onClick={onClose}>{t('cancel')}</button>
        <button className="btn btn--p" disabled={!name.trim()} onClick={() => onSave(name.trim())}>{t('save')}</button>
      </div>
    </Modal>
  )
}

// ---------------------------------------------------------------- asosiy bo'lim xodimlari
function Staff() {
  const { t } = useT()
  const [q, setQ] = useState('')
  const [active, setActive] = useState('true')
  const qd = useDebounce(q, 300)
  const { data: rows, reload } = useFetch<any[]>('/users',
    { role: 'ijrochi', q: qd || undefined, active: active === 'all' ? undefined : active === 'true', limit: 500 },
    [qd, active])
  const [person, setPerson] = useState<any>(null)

  return (
    <>
      <div className="row wrap" style={{ marginBottom: 12 }}>
        <button className="btn btn--p" onClick={() => setPerson({ role: 'ijrochi' })}>{t('ad_new_staff')}</button>
        <input className="inp inp--sm" placeholder={t('search')} value={q} onChange={e => setQ(e.target.value)} />
        <select className="sel sel--sm" value={active} onChange={e => setActive(e.target.value)}>
          <option value="true">{t('ad_active')}</option>
          <option value="false">{t('ad_blocked')}</option>
          <option value="all">{t('all')}</option>
        </select>
        <span className="chip">{rows?.length ?? 0}</span>
      </div>

      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr>
            <th>{t('ad_name')}</th><th>{t('ad_position')}</th><th>{t('ad_login')}</th>
            <th>{t('ad_open')}</th><th>{t('ad_late')}</th><th>{t('ad_status')}</th><th />
          </tr></thead>
          <tbody>
            {rows?.map(u => (
              <tr key={u.id} className={u.is_active ? '' : 'is-off'}>
                <td className="b">{u.full_name}</td>
                <td className="small">{u.position || '—'}</td>
                <td className="mono small">{u.login}</td>
                <td className="mono">{u.open_tasks}</td>
                <td className={'mono' + (u.late_tasks ? ' is-bad' : '')}>{u.late_tasks}</td>
                <td>
                  <span className={'pill ' + (u.is_active ? 'pill--ok' : 'pill--g')}>
                    {u.is_active ? t('ad_active') : t('ad_blocked')}
                  </span>
                  {u.telegram_user_id && <span className="pill pill--t" style={{ marginLeft: 4 }}>TG</span>}
                </td>
                <td className="nowrap right-cell">
                  <button className="btn btn--sm" onClick={() => setPerson(u)}>{t('edit')}</button>
                </td>
              </tr>
            ))}
            {!rows?.length && <tr><td colSpan={7}><div className="empty">{t('empty')}</div></td></tr>}
          </tbody>
        </table>
      </div>

      {person && <PersonForm user={person} departments={[]} lockRole="ijrochi"
                             onClose={() => { setPerson(null); reload(); invalidate() }} />}
    </>
  )
}

// ---------------------------------------------------------------- assistantlar (faqat boshliq)
function Assistants() {
  const { t } = useT()
  const [active, setActive] = useState('true')
  const { data: rows, reload } = useFetch<any[]>('/users',
    { role: 'assistant', active: active === 'all' ? undefined : active === 'true' }, [active])
  const [person, setPerson] = useState<any>(null)

  return (
    <>
      <p className="muted small" style={{ margin: '0 0 12px' }}>{t('ad_asst_hint')}</p>
      <div className="row wrap" style={{ marginBottom: 12 }}>
        <button className="btn btn--p" onClick={() => setPerson({ role: 'assistant' })}>{t('ad_new_asst')}</button>
        <select className="sel sel--sm" value={active} onChange={e => setActive(e.target.value)}>
          <option value="true">{t('ad_active')}</option>
          <option value="false">{t('ad_blocked')}</option>
          <option value="all">{t('all')}</option>
        </select>
        <span className="chip">{rows?.length ?? 0}</span>
      </div>

      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr>
            <th>{t('ad_name')}</th><th>{t('ad_position')}</th><th>{t('ad_login')}</th>
            <th>{t('ad_status')}</th><th />
          </tr></thead>
          <tbody>
            {rows?.map(u => (
              <tr key={u.id} className={u.is_active ? '' : 'is-off'}>
                <td className="b">{u.full_name}</td>
                <td className="small">{u.position || '—'}</td>
                <td className="mono small">{u.login}</td>
                <td>
                  <span className={'pill ' + (u.is_active ? 'pill--ok' : 'pill--g')}>
                    {u.is_active ? t('ad_active') : t('ad_blocked')}
                  </span>
                  {u.telegram_user_id && <span className="pill pill--t" style={{ marginLeft: 4 }}>TG</span>}
                </td>
                <td className="nowrap right-cell">
                  <button className="btn btn--sm" onClick={() => setPerson(u)}>{t('edit')}</button>
                </td>
              </tr>
            ))}
            {!rows?.length && <tr><td colSpan={5}><div className="empty">{t('empty')}</div></td></tr>}
          </tbody>
        </table>
      </div>

      {person && <PersonForm user={person} departments={[]} lockRole="assistant"
                             onClose={() => { setPerson(null); reload(); invalidate() }} />}
    </>
  )
}

// ---------------------------------------------------------------- xodim kartochkasi
const newTitleKey = (role: string): Key =>
  role === 'bolim_boshligi' ? 'ad_new_head' : role === 'assistant' ? 'ad_new_asst' : 'ad_new_staff'

function PersonForm({ user, departments, lockRole, onClose }:
  { user: any; departments: any[]; lockRole: string; onClose: () => void }) {
  const { t } = useT()
  const { toast, toastErr } = useToast()
  const isNew = !user.id
  const [f, setF] = useState({
    full_name: user.full_name || '', login: user.login || '', password: '',
    position: user.position || '', phone: user.phone || '',
    department_id: user.department_id ? String(user.department_id) : '',
    role: user.role || lockRole,
  })
  const [newPass, setNewPass] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k: string) => (e: any) => setF(x => ({ ...x, [k]: e.target.value }))
  const needsDep = f.role === 'bolim_boshligi'

  const save = async () => {
    setBusy(true)
    try {
      const body: any = {
        full_name: f.full_name.trim(), position: f.position.trim() || null,
        phone: f.phone.trim() || null, role: f.role,
        department_id: needsDep ? Number(f.department_id) || null : null,
      }
      if (isNew) {
        await post('/users', { ...body, login: f.login.trim(), password: f.password })
      } else {
        await patch(`/users/${user.id}`, { ...body, login: f.login.trim() })
      }
      toast(t('ad_saved')); onClose()
    } catch (e) { toastErr(e) } finally { setBusy(false) }
  }
  const toggle = async () => {
    setBusy(true)
    try {
      await post(`/users/${user.id}/${user.is_active ? 'block' : 'unblock'}`)
      onClose()
    } catch (e) { toastErr(e) } finally { setBusy(false) }
  }
  const setPass = async () => {
    setBusy(true)
    try { await post(`/users/${user.id}/password`, { password: newPass }); toast(t('ad_saved')); setNewPass('') }
    catch (e) { toastErr(e) } finally { setBusy(false) }
  }

  const ready = f.full_name.trim() && f.login.trim() && (!isNew || f.password) && (!needsDep || f.department_id)

  return (
    <Modal title={isNew ? t(newTitleKey(f.role)) : f.full_name} onClose={onClose}>
      <div className="modal__b">
        <label className="lbl full">{t('ad_name')} *
          <input className="inp" autoFocus value={f.full_name} onChange={set('full_name')} />
        </label>
        <label className="lbl">{t('ad_login')} *
          <input className="inp" value={f.login} onChange={set('login')} />
        </label>
        {isNew && <label className="lbl">{t('ad_pass')} *
          <input className="inp" value={f.password} onChange={set('password')} />
        </label>}
        <label className="lbl">{t('ad_position')}
          <input className="inp" value={f.position} onChange={set('position')} />
        </label>
        <label className="lbl">{t('ad_phone')}
          <input className="inp" value={f.phone} onChange={set('phone')} />
        </label>
        {needsDep && <label className="lbl full">{t('ad_dep')} *
          <select className="sel" value={f.department_id} onChange={set('department_id')}>
            <option value="">{t('nt_pick')}</option>
            {departments.filter(d => d.is_active).map(d => (
              <option key={d.id} value={d.id}>{d.name}</option>
            ))}
          </select>
        </label>}
        {!isNew && (
          <div className="full row wrap">
            <input className="inp inp--sm" placeholder={t('ad_newpass')} value={newPass}
                   onChange={e => setNewPass(e.target.value)} />
            <button className="btn btn--sm" disabled={busy || !newPass} onClick={setPass}>{t('ad_setpass')}</button>
          </div>
        )}
      </div>
      <div className="modal__f">
        {!isNew && (
          <button className={'btn btn--sm ' + (user.is_active ? 'btn--danger' : 'btn--ok')}
                  disabled={busy} onClick={toggle}>
            {user.is_active ? t('ad_block') : t('ad_unblock')}
          </button>
        )}
        <span className="spacer" />
        <button className="btn" onClick={onClose}>{t('cancel')}</button>
        <button className="btn btn--p" disabled={busy || !ready} onClick={save}>{t('save')}</button>
      </div>
    </Modal>
  )
}
