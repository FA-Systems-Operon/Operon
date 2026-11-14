import { describe, expect, it } from 'vitest'
import {
  mapSourceReferences,
  editableReviewRows,
  reviewRows,
  type ProfileConflict,
  type SourceLinkedDraft,
} from './draftSources'

const DOC = '6f1c2d3e-0000-4000-8000-000000000001'

const draft: SourceLinkedDraft = {
  name: 'Ada Lovelace',
  needs: ['Payroll help', 'Bookkeeping'],
  goals: ['Hire staff', 'Open a shop', 'Export abroad'],
  source_references: [
    { field: 'name', document_id: DOC, quote: 'My name is Ada' },
    { field: 'needs/0', document_id: DOC, quote: 'payroll is a mess' },
    { field: 'goals/2', document_id: DOC, quote: 'sell overseas' },
    { field: 'goals/2', document_id: DOC, quote: 'ship to Europe' },
  ],
}

describe('mapSourceReferences', () => {
  it('returns name, needs and goals in order with readable labels', () => {
    expect(mapSourceReferences(draft).map((field) => [field.key, field.label, field.value])).toEqual([
      ['name', 'Name', 'Ada Lovelace'],
      ['needs/0', 'Need 1', 'Payroll help'],
      ['needs/1', 'Need 2', 'Bookkeeping'],
      ['goals/0', 'Goal 1', 'Hire staff'],
      ['goals/1', 'Goal 2', 'Open a shop'],
      ['goals/2', 'Goal 3', 'Export abroad'],
    ])
  })

  it('attaches references to their fields, keeping multiple refs in order', () => {
    const byKey = Object.fromEntries(
      mapSourceReferences(draft).map((field) => [field.key, field.references.map((r) => r.quote)]),
    )
    expect(byKey).toEqual({
      name: ['My name is Ada'],
      'needs/0': ['payroll is a mess'],
      'needs/1': [],
      'goals/0': [],
      'goals/1': [],
      'goals/2': ['sell overseas', 'ship to Europe'],
    })
  })

  it('ignores references to absent or malformed fields', () => {
    const fields = mapSourceReferences({
      name: null,
      needs: ['Payroll help'],
      goals: [],
      source_references: [
        { field: 'name', document_id: DOC, quote: 'null name' },
        { field: 'needs/1', document_id: DOC, quote: 'out of range' },
        { field: 'needs/00', document_id: DOC, quote: 'malformed' },
        { field: 'goals/0', document_id: DOC, quote: 'empty list' },
        { field: 'notes', document_id: DOC, quote: 'unknown field' },
      ],
    })
    expect(fields).toEqual([{ key: 'needs/0', label: 'Need 1', value: 'Payroll help', references: [] }])
  })

  it('treats an empty draft or missing keys as no fields', () => {
    expect(mapSourceReferences({ name: null, needs: [], goals: [], source_references: [] })).toEqual([])
    expect(mapSourceReferences({})).toEqual([])
  })
})

const conflict = (field: string): ProfileConflict => ({
  field,
  explanation: 'The sources disagree.',
  alternatives: [
    { value: 'a@example.test', document_id: 'call', quote: 'Use a@example.test' },
    { value: 'b@example.test', document_id: 'form', quote: 'Use b@example.test' },
  ],
})

describe('reviewRows', () => {
  const empty: SourceLinkedDraft = { name: null, needs: [], goals: [], source_references: [] }
  const shape = (draft: Partial<SourceLinkedDraft>) =>
    reviewRows(draft).rows.map((row) => [row.label, row.value, row.flag])

  it('adds conflicting and missing fields to the populated ones, in field order', () => {
    expect(
      shape({
        ...empty,
        goals: ['Grow bookings'],
        website: 'https://example.test',
        conflicts: [conflict('email'), conflict('goals/0'), conflict('goals')],
        assessment: { rules_version: 1, missing_fields: ['phone_number', 'website'] },
      }),
    ).toEqual([
      ['Goals', 'a@example.test or b@example.test', 'conflict'],
      ['Goal 1', 'Grow bookings', 'conflict'],
      ['Website', 'https://example.test', null],
      ['Phone number', 'Not mentioned', 'missing'],
      ['Email', 'a@example.test or b@example.test', 'conflict'],
    ])
  })

  it('keeps each conflict on its row for the evidence panel', () => {
    const [row] = reviewRows({ ...empty, conflicts: [conflict('name')] }).rows

    expect(row.conflicts).toEqual([conflict('name')])
    expect(row.references).toEqual([])
  })

  it('reports nothing missing for drafts that were never checked', () => {
    const legacy = { ...empty, assessment: { rules_version: 2, missing_fields: ['email'] } }

    expect(reviewRows(legacy)).toEqual({ rows: [], unsupported: false })
  })

  it.each([
    ['conflict', { conflicts: [conflict('goals/99')] }],
    ['missing field', { assessment: { rules_version: 1, missing_fields: ['password'] } }],
  ])('flags an unsupported %s instead of dropping it silently', (_, flags) => {
    expect(reviewRows({ ...empty, ...flags })).toEqual({ rows: [], unsupported: true })
  })
})

// Profile edits (PUT) accept any JSON, so saved data can have the wrong types.
describe('draft data of the wrong type', () => {
  const malformed = (data: unknown) => data as Partial<SourceLinkedDraft>

  it.each([
    ['a string', 'Payroll help'],
    ['an object', { 0: 'Payroll help' }],
    ['null', null],
  ])('treats needs and goals given as %s as empty', (_, value) => {
    const fields = mapSourceReferences(malformed({ name: 'Ada', needs: value, goals: value }))
    expect(fields.map((field) => field.key)).toEqual(['name'])
  })

  it.each([null, 'draft', ['Payroll help']])('treats a whole draft of %j as empty', (data) => {
    expect(reviewRows(malformed(data))).toEqual({ rows: [], unsupported: false })
  })

  it('skips non-string items and keeps each reference on its own item', () => {
    const fields = mapSourceReferences(
      malformed({
        needs: ['Payroll help', 7, null, { text: 'Taxes' }, 'Bookkeeping'],
        source_references: [
          { field: 'needs/1', document_id: DOC, quote: 'about the 7' },
          { field: 'needs/4', document_id: DOC, quote: 'the books are behind' },
        ],
      }),
    )
    expect(fields.map(({ key, label, value, references }) => [key, label, value, references.length])).toEqual([
      ['needs/0', 'Need 1', 'Payroll help', 0],
      ['needs/4', 'Need 2', 'Bookkeeping', 1],
    ])
  })

  it('treats a name, field value or source_references of the wrong type as empty', () => {
    const fields = mapSourceReferences(
      malformed({
        name: 42,
        email: { address: 'ada@example.test' },
        needs: ['Payroll help'],
        source_references: { field: 'needs/0', document_id: DOC, quote: 'payroll' },
      }),
    )
    expect(fields).toEqual([{ key: 'needs/0', label: 'Need 1', value: 'Payroll help', references: [] }])
  })

  it('skips malformed references, conflicts and assessments', () => {
    const quote = 'ada@example.test'
    const { rows, unsupported } = reviewRows(
      malformed({
        email: 'ada@example.test',
        source_references: [null, 'email', { field: 'email', document_id: DOC }, { field: 'email', document_id: DOC, quote }],
        conflicts: [null, { field: 7 }, { field: 'phone_number', explanation: { why: 1 }, alternatives: 'both' }],
        assessment: { rules_version: 1, missing_fields: 'website' },
      }),
    )
    expect(unsupported).toBe(false)
    expect(rows.map(({ key, flag, references, conflicts }) => [key, flag, references, conflicts])).toEqual([
      ['phone_number', 'conflict', [], [{ field: 'phone_number', explanation: '', alternatives: [] }]],
      ['email', null, [{ field: 'email', document_id: DOC, quote }], []],
    ])
  })
})


it('editable rows add absent scalars but preserve raw list paths and group conflict evidence', () => {
  const input = { needs: [null, 'Need'], goals: [], conflicts: [conflict('goals')], source_references: [] } as unknown as SourceLinkedDraft
  const original = structuredClone(input)
  const result = editableReviewRows(input)
  expect(result.rows.map(({ key }) => key)).toEqual([
    'name', 'needs/1', 'goals', 'business_number', 'website', 'domain_platform',
    'meta_business_manager', 'facebook_page', 'instagram', 'phone_number', 'email', 'business_address',
  ])
  expect(result.rows.find(({ key }) => key === 'goals')?.conflicts).toEqual([conflict('goals')])
  expect(input).toEqual(original)
})
