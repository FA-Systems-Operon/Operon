import type { ReviewDraft } from './api'
import { ONBOARDING_FIELDS } from './components/draftSources'

export type EditablePath = 'name' | typeof ONBOARDING_FIELDS[number]['key'] | `needs/${number}` | `goals/${number}`
export type FieldChange = { originalPresent: boolean; originalValue: unknown; currentValue: string | null }
export type DraftEditSession = {
  base: { clientId: string; profileId: string; versionId: string; versionNumber: number; createdAt: string }
  originalData: Record<string, unknown>
  currentData: Record<string, unknown>
  changes: Partial<Record<EditablePath, FieldChange>>
}

export function createEditSession(draft: ReviewDraft): DraftEditSession {
  const data: unknown = draft.version.data
  const originalData = typeof data === 'object' && data !== null && !Array.isArray(data)
    ? data as Record<string, unknown> : {}
  return {
    base: {
      clientId: draft.client.id, profileId: draft.version.client_profile_id,
      versionId: draft.version.id, versionNumber: draft.version.version_number,
      createdAt: draft.version.created_at,
    },
    originalData, currentData: originalData, changes: {},
  }
}

export function isEditablePath(data: Record<string, unknown>, path: string): path is EditablePath {
  if (path === 'name' || ONBOARDING_FIELDS.some(({ key }) => key === path)) return true
  const match = /^(needs|goals)\/(0|[1-9][0-9]*)$/.exec(path)
  if (!match) return false
  const list = data[match[1]]
  return Array.isArray(list) && typeof list[Number(match[2])] === 'string'
}

export function fieldValue(data: Record<string, unknown>, path: EditablePath): unknown {
  const [group, index] = path.split('/')
  if (index === undefined) return data[group]
  const list = data[group]
  return Array.isArray(list) ? list[Number(index)] : undefined
}

// Match nullable text and nonblank list items in source_prompt.py/profile_flags.py.
// Mandatory fields describe completeness, not a format or an apply-time requirement.
export function validateEdit(path: EditablePath, text: string): { value: string | null; error: string | null } {
  const value = text.trim()
  return path.includes('/') && !value
    ? { value: null, error: 'List items must not be blank.' }
    : { value: value || null, error: null }
}

export function applyEdit(session: DraftEditSession, path: EditablePath, text: string): DraftEditSession {
  if (!isEditablePath(session.originalData, path)) return session
  const { value, error } = validateEdit(path, text)
  if (error) return session
  const originalValue = fieldValue(session.originalData, path)
  // Opening an absent, null or malformed scalar and leaving it empty is a no-op.
  const unchanged = text === originalValue || value === originalValue || (value === null && typeof originalValue !== 'string')
  const currentData = { ...session.currentData }
  const changes = { ...session.changes }
  const [group, index] = path.split('/')
  if (index !== undefined) {
    const list = [...session.currentData[group] as unknown[]]
    list[Number(index)] = unchanged ? originalValue : value
    currentData[group] = list
  } else if (unchanged && !Object.hasOwn(session.originalData, group)) {
    delete currentData[group]
  } else {
    currentData[group] = unchanged ? originalValue : value
  }
  if (unchanged) delete changes[path]
  else changes[path] = { originalPresent: Object.hasOwn(session.originalData, group), originalValue, currentValue: value }
  return { ...session, currentData, changes }
}
