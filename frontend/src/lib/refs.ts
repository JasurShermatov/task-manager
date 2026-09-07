import { useFetch } from './hooks'

export type Project = { id: number; code: string; name: string; is_active: boolean }
export type Location = { id: number; project_id: number; parent_id: number | null; name: string; kind: string; sort_order: number }
export type User = { id: number; full_name: string; login: string; role: { code: string; name: string }; scope_type: string; scope_id: number | null; is_active: boolean; telegram_user_id?: number | null; lang?: string; phone?: string | null }
export type TaskType = { id: number; name: string; group_name: string | null; default_duration_days: number; required_evidence_kinds: string[]; default_checklist_json: any[]; is_active: boolean }

export function useRefs(projectId?: number | null) {
  const projects = useFetch<Project[]>('/projects')
  const users = useFetch<User[]>('/users')
  const types = useFetch<TaskType[]>('/task-types')
  const locations = useFetch<Location[]>('/locations', projectId ? { project_id: projectId } : undefined)
  return { projects: projects.data || [], users: users.data || [], types: types.data || [], locations: locations.data || [], loading: projects.loading || users.loading || types.loading }
}

export function locPath(locs: Location[], id: number | null | undefined): Location[] {
  const by = new Map(locs.map(l => [l.id, l]))
  const out: Location[] = []
  let cur = id ? by.get(id) : undefined
  let g = 0
  while (cur && g++ < 10) { out.unshift(cur); cur = cur.parent_id ? by.get(cur.parent_id) : undefined }
  return out
}

export function locLabel(locs: Location[], id: number | null | undefined) {
  return locPath(locs, id).map(l => l.name).join(' · ')
}

export function initials(name?: string) {
  if (!name) return '?'
  const p = name.trim().split(/\s+/)
  return ((p[0]?.[0] || '') + (p[1]?.[0] || '')).toUpperCase()
}
