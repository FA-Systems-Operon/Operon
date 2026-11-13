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

const isString = (value: unknown): value is string => typeof value === 'string'
const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null
const arrayOf = <T>(value: unknown, keep: (item: unknown) => item is T): T[] =>
  Array.isArray(value) ? value.filter(keep) : []
const isReference = (item: unknown): item is SourceReference =>
  isObject(item) && isString(item.field) && isString(item.document_id) && isString(item.quote)
const isAlternative = (item: unknown): item is ProfileConflict['alternatives'][number] =>
  isObject(item) && isString(item.value) && isString(item.document_id) && isString(item.quote)

/**
 * The draft with every value of the wrong type treated as empty. Profile edits (PUT)
 * accept any JSON, so saved data can't be trusted to match SourceLinkedDraft: a
 * non-array becomes [], non-string items are skipped, and a non-string value is unset.
 * Needs and goals are read in mapSourceReferences, which keeps each item's position.
 */
function readDraft(raw: unknown): Partial<SourceLinkedDraft> {
  const data = isObject(raw) ? raw : {}
  const draft: Partial<SourceLinkedDraft> = {
    name: isString(data.name) ? data.name : null,
    source_references: arrayOf(data.source_references, isReference),
    conflicts: (Array.isArray(data.conflicts) ? data.conflicts : []).flatMap((conflict) =>
      isObject(conflict) && isString(conflict.field)
        ? [
            {
              field: conflict.field,
              explanation: isString(conflict.explanation) ? conflict.explanation : '',
              alternatives: arrayOf(conflict.alternatives, isAlternative),
            },
          ]
        : [],
    ),
    assessment:
      isObject(data.assessment) && typeof data.assessment.rules_version === 'number'
        ? {
            rules_version: data.assessment.rules_version,
            missing_fields: arrayOf(data.assessment.missing_fields, isString),
          }
        : null,
  }
  for (const { key } of ONBOARDING_FIELDS) {
    const value = data[key]
    if (isString(value)) draft[key] = value
  }
  return draft
}

/** One row per populated field, each with the references that target it. */
export function mapSourceReferences(input: Partial<SourceLinkedDraft>): DraftField[] {
  const draft = readDraft(input)
  const fields: DraftField[] = []
  if (draft.name != null) {
    fields.push({ key: 'name', label: 'Name', value: draft.name, references: [] })
  }
  const raw: Record<string, unknown> = isObject(input) ? input : {}
  for (const [group, label] of [['needs', 'Need'], ['goals', 'Goal']] as const) {
    const items: unknown[] = Array.isArray(raw[group]) ? raw[group] : []
    let shown = 0
    // Keyed by the item's place in the saved list, so references still match when an
    // item of the wrong type before it is skipped; labels count only the items shown.
    items.forEach((value, index) => {
      if (!isString(value)) return
      shown += 1
      fields.push({ key: `${group}/${index}`, label: `${label} ${shown}`, value, references: [] })
    })
  }

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
export function reviewRows(input: Partial<SourceLinkedDraft>): {
  rows: ReviewRow[]
  unsupported: boolean
} {
  const draft = readDraft(input)
  // The raw input: mapSourceReferences reads needs and goals by their saved positions.
  const rows: ReviewRow[] = mapSourceReferences(input).map((field) => ({
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
