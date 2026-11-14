import { expect, test } from 'vitest'
import type { ReviewDraft } from './api'
import { applyEdit, createEditSession, fieldValue, isEditablePath, validateEdit } from './draftEdits'

const draft = (data: unknown) => ({
  client: { id: 'c1' },
  version: { id: 'v2', client_profile_id: 'p1', version_number: 2, created_at: '2026-11-12', data },
}) as ReviewDraft

test('tracks the immutable base, repeated corrections, exact reverts and unrelated JSON', () => {
  const input = draft({ name: 'Ada', email: null, unknown: { preserve: true }, assessment: { rules_version: 1 } })
  const original = structuredClone(input)
  let session = createEditSession(input)
  expect(session.base).toEqual({ clientId: 'c1', profileId: 'p1', versionId: 'v2', versionNumber: 2, createdAt: '2026-11-12' })
  session = applyEdit(session, 'name', ' Grace ')
  session = applyEdit(session, 'name', 'Katherine')
  expect(session.changes.name).toEqual({ originalPresent: true, originalValue: 'Ada', currentValue: 'Katherine' })
  expect(session.currentData.unknown).toEqual({ preserve: true })
  expect(session.currentData.assessment).toEqual({ rules_version: 1 })
  session = applyEdit(session, 'name', 'Ada')
  expect(session.changes).toEqual({})
  expect(session.currentData).toEqual(original.version.data)
  expect(input).toEqual(original)
})

test('distinguishes absent and null values, clears nullable scalars, and restores absence', () => {
  let session = createEditSession(draft({ name: 'Ada', email: null }))
  session = applyEdit(session, 'website', 'example.test')
  expect(session.changes.website).toEqual({ originalPresent: false, originalValue: undefined, currentValue: 'example.test' })
  session = applyEdit(session, 'email', 'ada@example.test')
  expect(session.changes.email?.originalPresent).toBe(true)
  session = applyEdit(session, 'website', '  ')
  expect(Object.hasOwn(session.currentData, 'website')).toBe(false)
  session = applyEdit(session, 'name', '')
  expect(session.currentData.name).toBeNull()
  expect(session.changes.name?.currentValue).toBeNull()
})

test('edits only existing string list items without compacting malformed entries or changing evidence', () => {
  const data = { needs: [null, 'Need'], goals: [], source_references: [{ field: 'needs/1', quote: 'Need' }] }
  const session = createEditSession(draft(data))
  for (const path of ['needs', 'needs/0', 'needs/01', 'needs/2', 'goals/0', 'password']) {
    expect(isEditablePath(session.originalData, path)).toBe(false)
  }
  expect(isEditablePath(session.originalData, 'needs/1')).toBe(true)
  const changed = applyEdit(session, 'needs/1', 'Corrected')
  expect(changed.currentData.needs).toEqual([null, 'Corrected'])
  expect(changed.currentData.source_references).toEqual(data.source_references)
  expect(fieldValue(changed.currentData, 'needs/1')).toBe('Corrected')
  expect(applyEdit(changed, 'needs/1', '   ')).toBe(changed)
  expect(applyEdit(changed, 'needs/2', 'New')).toBe(changed)
  expect(data.needs).toEqual([null, 'Need'])
})

test('uses nonblank text rules rather than format validation and tolerates legacy data', () => {
  expect(validateEdit('email', 'not an email')).toEqual({ value: 'not an email', error: null })
  expect(validateEdit('name', ' ')).toEqual({ value: null, error: null })
  expect(validateEdit('goals/0', '\t')).toEqual({ value: null, error: 'List items must not be blank.' })
  expect(createEditSession(draft(null)).currentData).toEqual({})
  const session = createEditSession(draft({ name: 42 }))
  expect(applyEdit(session, 'name', '').currentData.name).toBe(42)
  expect(applyEdit(session, 'name', 'Ada').currentData.name).toBe('Ada')
})
