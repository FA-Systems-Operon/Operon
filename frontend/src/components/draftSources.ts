// Mirrors SourceLinkedProfile in backend/src/ai/source_prompt.py (#39/#40).
export type SourceReference = {
  field: string
  document_id: string
  quote: string
}

export const ONBOARDING_FIELDS = [
  { key: 'business_number', label: 'Business number' },
  { key: 'website', label: 'Website' },
  { key: 'domain_platform', label: 'Domain platform' },
  { key: 'meta_business_manager', label: 'Meta Business Manager account' },
  { key: 'facebook_page', label: 'Facebook Page' },
  { key: 'instagram', label: 'Instagram' },
  { key: 'phone_number', label: 'Phone number' },
  { key: 'email', label: 'Email' },
  { key: 'business_address', label: 'Business address' },
] as const

export type OnboardingField = typeof ONBOARDING_FIELDS[number]['key']

export type ProfileConflict = {
  field: string
  explanation: string
  alternatives: { value: string; document_id: string; quote: string }[]
}

export type SourceLinkedDraft = {
  name: string | null
  needs: string[]
  goals: string[]
  source_references: SourceReference[]
  conflicts?: ProfileConflict[]
  assessment?: { rules_version: number; missing_fields: string[] } | null
} & Partial<Record<OnboardingField, string | null>>

export type DraftField = {
  key: string
  label: string
  value: string
  references: SourceReference[]
}

/** One row per populated field, each with the references that target it. */
export function mapSourceReferences(draft: Partial<SourceLinkedDraft>): DraftField[] {
  const fields: DraftField[] = []
  if (draft.name != null) {
    fields.push({ key: 'name', label: 'Name', value: draft.name, references: [] })
  }
  draft.needs?.forEach((value, index) => {
    fields.push({ key: `needs/${index}`, label: `Need ${index + 1}`, value, references: [] })
  })
  draft.goals?.forEach((value, index) => {
    fields.push({ key: `goals/${index}`, label: `Goal ${index + 1}`, value, references: [] })
  })

  for (const { key, label } of ONBOARDING_FIELDS) {
    const value = draft[key]
    if (value != null) fields.push({ key, label, value, references: [] })
  }

  // Keys are generated canonically, so refs to absent or malformed fields
  // (e.g. "needs/7", "needs/01") match nothing and are dropped.
  const byKey = new Map(fields.map((field) => [field.key, field]))
  for (const reference of draft.source_references ?? []) {
    byKey.get(reference.field)?.references.push(reference)
  }
  return fields
}

export type ReviewRow = DraftField & {
  flag: 'missing' | 'conflict' | null
  conflicts: ProfileConflict[]
}

// Field and group keys in the order DraftSourceView shows them.
const ROW_ORDER = ['name', 'needs', 'goals', ...ONBOARDING_FIELDS.map(({ key }) => key)]
const ROW_LABELS: Record<string, string> = {
  name: 'Name',
  needs: 'Needs',
  goals: 'Goals',
  ...Object.fromEntries(ONBOARDING_FIELDS.map(({ key, label }) => [key, label])),
}

/**
 * The review page's rows (#57): every populated field, plus the conflicting and
 * missing fields DraftSourceView flags (#44). A conflicting field is saved as null,
 * so it gets a row of its own. `unsupported` is true when a flag names a field
 * this page can't show, so the reviewer is told rather than shown a clean draft.
 */
export function reviewRows(draft: Partial<SourceLinkedDraft>): {
  rows: ReviewRow[]
  unsupported: boolean
} {
  const rows: ReviewRow[] = mapSourceReferences(draft).map((field) => ({
    ...field,
    flag: null,
    conflicts: [],
  }))
  const byKey = new Map(rows.map((row) => [row.key, row]))
  let unsupported = false
  const addRow = (key: string, value: string, flag: ReviewRow['flag']) => {
    const row: ReviewRow = { key, label: ROW_LABELS[key], value, references: [], flag, conflicts: [] }
    rows.push(row)
    byKey.set(key, row)
    return row
  }

  for (const conflict of draft.conflicts ?? []) {
    let row = byKey.get(conflict.field)
    if (!row && !(conflict.field in ROW_LABELS)) {
      unsupported = true
      continue
    }
    const values = conflict.alternatives.map(({ value }) => value)
    row ??= addRow(conflict.field, values.join(' or '), null)
    row.flag = 'conflict'
    row.conflicts.push(conflict)
  }
  // Older drafts were never checked, so nothing is reported missing for them.
  if (draft.assessment?.rules_version === 1) {
    for (const key of draft.assessment.missing_fields) {
      if (!ONBOARDING_FIELDS.some((field) => field.key === key)) {
        unsupported = true
      } else if (!byKey.has(key)) {
        addRow(key, 'Not mentioned', 'missing')
      }
    }
  }

  // A group-level row ("goals") comes before its items; the stable sort keeps item order.
  const rank = (key: string) =>
    ROW_ORDER.indexOf(key.split('/')[0]) * 2 + (key.includes('/') ? 1 : 0)
  rows.sort((a, b) => rank(a.key) - rank(b.key))
  return { rows, unsupported }
}
