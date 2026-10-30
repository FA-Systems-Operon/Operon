import { describe, expect, it } from 'vitest'
import { mapSourceReferences, type SourceLinkedDraft } from './draftSources'

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
