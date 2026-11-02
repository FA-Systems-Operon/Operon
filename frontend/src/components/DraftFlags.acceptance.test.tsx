import { render, screen, within } from '@testing-library/react'
import { expect, test } from 'vitest'
import cases from '../../../tests/fixtures/onboarding_flags/cases.json'
import DraftSourceView from './DraftSourceView'
import { ONBOARDING_FIELDS, type SourceLinkedDraft } from './draftSources'

// Same controlled replies and independent answer key as the backend job test.
// Real persisted document IDs are substituted by the backend; the component
// must pass each ID/quote through to the host page's source navigation callback.
const sourceHref = (id: string, quote: string) => `/sources/${id}?quote=${encodeURIComponent(quote)}`

test.each(cases)('$id: a saved draft displays the expected missing and conflicting fields', (example) => {
  const draft: SourceLinkedDraft = {
    ...example.reply,
    assessment: { rules_version: 1, missing_fields: example.expected.missing_fields },
  }
  render(<DraftSourceView draft={draft} getSourceHref={sourceHref} />)

  const missingFields: string[] = example.expected.missing_fields
  const conflictFields: string[] = example.expected.conflict_fields
  for (const { key, label } of ONBOARDING_FIELDS) {
    const row = within(screen.getByText(label, { selector: 'dt' }).parentElement!)
    const missing = row.queryByText('Missing information:')
    expect(missing !== null).toBe(missingFields.includes(key))
    const region = row.queryByRole('region', { name: `Potential conflict for ${label}` })
    expect(region !== null).toBe(conflictFields.includes(key))
    if (region) {
      const conflict = within(region)
      for (const [index, value] of example.expected.email_values.entries()) {
        expect(conflict.getByText(value, { selector: 'strong' })).toBeInTheDocument()
        const alternative = example.reply.conflicts[0].alternatives[index]
        expect(conflict.getByRole('link', { name: `View conflict source ${index + 1} for ${label}` }))
          .toHaveAttribute('href', sourceHref(alternative.document_id, alternative.quote))
      }
    }
  }
  expect(screen.queryByText(/Information checks were not recorded/)).not.toBeInTheDocument()
})
