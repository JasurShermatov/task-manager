import React, { useMemo, useState } from 'react'
import { useFetch } from '../lib/hooks'
import { useT, fmtDate, fmtDateTime } from '../lib/i18n'
import { useRefs, initials, locLabel } from '../lib/refs'
import { PageHeader } from '../components/Layout'

/** Jamoa ro'yxati — faqat ko'rish. Login/parol bu yerda yo'q, ular Administratsiyada. */
export default function Staff() {
  const { t, lang } = useT()
  const { projects, locations } = useRefs()
  const { data: users } = useFetch<any[]>('/users')
  const [q, setQ] = useState('')
  const [sel, setSel] = useState<number | null>(null)

  const rows = useMemo(() => {
    const s = q.trim().toLowerCase()
    const list = users || []
    if (!s) return list
    return list.filter(u => u.full_name.toLowerCase().includes(s) || (u.role?.name || '').toLowerCase().includes(s))
  }, [users, q])

  const current = rows.find(u => u.id === sel) || rows[0] || null
  const scopeOf = (u: any) => u.scope_type === 'system' ? t('us_scope_system')
    : u.scope_type === 'project' ? (projects.find(p => p.id === u.scope_id)?.name || t('us_scope_project'))
    : (locLabel(locations, u.scope_id) || t('us_scope_location'))

  return (
    <>
      <PageHeader title={t('sf_title')} extra={<span className="chip">{rows.length}</span>}>
        <input className="inp inp--sm" placeholder={t('sf_search')} value={q} onChange={e => setQ(e.target.value)} />
      </PageHeader>
      <div className="content split">
        <div className="split__list">
          {!rows.length && <div className="empty">{t('sf_none')}</div>}
          {rows.map(u => (
            <button key={u.id} className={'person' + (current?.id === u.id ? ' person--on' : '')} onClick={() => setSel(u.id)}>
              <span className="av av--lg">{initials(u.full_name)}</span>
              <span className="person__t">
                <b>{u.full_name}</b>
                <span>{u.role?.name} · {scopeOf(u)}</span>
              </span>
              {u.telegram_user_id ? <span className="pill pill--t">✈</span> : null}
            </button>
          ))}
        </div>
        <div className="split__pane">
          {!current ? <div className="empty">{t('sf_pick')}</div> : <PersonCard u={current} scope={scopeOf(current)} />}
          <div className="hint" style={{ marginTop: 14 }}>{t('sf_hint')}</div>
        </div>
      </div>
    </>
  )
}

function PersonCard({ u, scope }: { u: any; scope: string }) {
  const { t, lang } = useT()
  const { data: mine } = useFetch<any>('/tasks', { assignee_id: u.id, limit: 200 })
  const items: any[] = mine?.items || []
  const open = items.filter(x => ['plan', 'progress', 'review', 'blocked'].includes(x.status)).length
  const overdue = items.filter(x => x.overdue_days > 0).length
  const done = items.filter(x => x.status === 'done').length
  const onTime = items.filter(x => x.status === 'done' && x.overdue_days === 0).length
  const pct = done ? Math.round(onTime / done * 100) : null

  return (
    <div className="blk">
      <div className="row" style={{ gap: 14, marginBottom: 16 }}>
        <span className="av av--xl">{initials(u.full_name)}</span>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 20, fontWeight: 800, letterSpacing: '-.01em' }}>{u.full_name}</div>
          <div className="muted small">{u.role?.name} · {scope}</div>
        </div>
        <span className="spacer" />
        {u.is_active === false && <span className="pill pill--b">{t('us_blocked')}</span>}
      </div>

      <div className="stats">
        <div><b>{open}</b><span>{t('sf_open')}</span></div>
        <div><b className={overdue ? 'c-block' : ''}>{overdue}</b><span>{t('sf_overdue')}</span></div>
        <div><b>{done}</b><span>{t('sf_done')}</span></div>
        <div><b className={pct !== null && pct >= 70 ? 'c-done' : ''}>{pct === null ? '—' : pct + '%'}</b><span>{t('sf_ontime')}</span></div>
      </div>

      <dl className="kv" style={{ marginTop: 18 }}>
        <dt>{t('sf_contact')}</dt><dd>{u.phone || <span className="faint">{t('sf_no_phone')}</span>}</dd>
        <dt>{t('us_tg')}</dt>
        <dd>{u.telegram_user_id ? <span className="pill pill--t">✈ {t('us_linked')}</span> : <span className="pill pill--g">{t('us_not_linked')}</span>}</dd>
        <dt>{t('us_lang')}</dt><dd className="mono">{u.lang}</dd>
        <dt>{t('sf_since')}</dt><dd>{fmtDate(u.created_at, lang, true)}</dd>
        <dt>{t('sf_last_login')}</dt>
        <dd>{u.last_login_at ? fmtDateTime(u.last_login_at, lang) : <span className="faint">{t('sf_never')}</span>}</dd>
      </dl>
    </div>
  )
}
