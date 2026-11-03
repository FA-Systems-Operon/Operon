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
