/** Sana va holat ko'rinishi — bitta joydan, hamma sahifada bir xil. */
import type { Key } from './i18n'

export const STATUS_KEY: Record<string, Key> = {
  new: 'st_new', progress: 'st_progress', submitted: 'st_submitted',
  done: 'st_done', cancelled: 'st_cancelled',
}
export const ROLE_KEY: Record<string, Key> = {
  boss: 'r_boss', assistant: 'r_assistant',
  bolim_boshligi: 'r_bolim_boshligi', ijrochi: 'r_ijrochi',
}
export const STATUS_PILL: Record<string, string> = {
  new: 'pill--g', progress: 'pill--t', submitted: 'pill--w',
  done: 'pill--ok', cancelled: 'pill--g',
}

const pad = (n: number) => String(n).padStart(2, '0')

/** «10.09.2026 18:00» — muddat doim soati bilan ko'rinadi. */
export function dt(v?: string | null): string {
  if (!v) return '—'
  const d = new Date(v)
  if (isNaN(+d)) return String(v)
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function day(v?: string | null): string {
  if (!v) return '—'
  const d = new Date(v)
  if (isNaN(+d)) return String(v)
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()}`
}

/** <input type="datetime-local"> uchun. */
export function toLocalInput(v?: string | null): string {
  const d = v ? new Date(v) : new Date()
  if (isNaN(+d)) return ''
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function plusDays(n: number, hour = 18): string {
  const d = new Date()
  d.setDate(d.getDate() + n)
  d.setHours(hour, 0, 0, 0)
  return toLocalInput(d.toISOString())
}

export function pctClass(p: number): string {
  if (p >= 85) return 'pct pct--hi'
  if (p >= 60) return 'pct pct--mid'
  return 'pct pct--lo'
}
