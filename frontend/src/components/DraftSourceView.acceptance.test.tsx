import { render, screen, within } from '@testing-library/react'
import { expect, test } from 'vitest'
import DraftSourceView from './DraftSourceView'
import type { SourceLinkedDraft } from './draftSources'

// AT 3.2 (#48): when a reviewer opens a generated draft, every field links to the
// transcript or intake passage it came from. This is a copy of the saved data in
// tests/test_source_profile_acceptance.py ("transcript_and_intake"); the IDs stand
// in for the stored documents. The review page that hosts this is #57.
const TRANSCRIPT = '6f1c2d3e-0000-4000-8000-000000000001'
const INTAKE = '6f1c2d3e-0000-4000-8000-000000000002'

const saved: SourceLinkedDraft = {
  name: 'Maya Chen',
  needs: ['More qualified consultations', 'More contact form completions'],
  goals: ['30 qualified bookings per month', 'Launch a referral program'],
  source_references: [
    { field: 'name', document_id: INTAKE, quote: 'Contact name: Maya Chen' },
    { field: 'needs/0', document_id: TRANSCRIPT, quote: 'booking more qualified consultations' },
    { field: 'needs/1', document_id: TRANSCRIPT, quote: 'few people complete our contact form' },
    { field: 'goals/0', document_id: TRANSCRIPT, quote: 'from 15 to 30 per month' },
    { field: 'goals/0', document_id: INTAKE, quote: 'Goal: 30 qualified bookings per month' },
    { field: 'goals/1', document_id: INTAKE, quote: 'Goal: Launch a customer referral program' },
  ],
}

// Written out by hand, not derived from the draft: label -> [document, quote] links.
const expected: Record<string, [string, string][]> = {
  Name: [[INTAKE, 'Contact name: Maya Chen']],
  'Need 1': [[TRANSCRIPT, 'booking more qualified consultations']],
  'Need 2': [[TRANSCRIPT, 'few people complete our contact form']],
  'Goal 1': [
    [TRANSCRIPT, 'from 15 to 30 per month'],
    [INTAKE, 'Goal: 30 qualified bookings per month'],
  ],
  'Goal 2': [[INTAKE, 'Goal: Launch a customer referral program']],
}

const getSourceHref = (documentId: string, quote: string) =>
  `/documents/${documentId}?quote=${encodeURIComponent(quote)}`

test('every field of a saved draft links to the passage it came from', () => {
  const { container } = render(<DraftSourceView draft={saved} getSourceHref={getSourceHref} />)

  const labels = [...container.querySelectorAll('dt')].map((term) => term.textContent)
  expect(labels).toEqual(Object.keys(expected))
  for (const [label, sources] of Object.entries(expected)) {
    const row = within(screen.getByText(label, { selector: 'dt' }).parentElement!)
    const links = row.getAllByRole('link', { name: `View source for ${label}` })
    expect(links.map((link) => link.getAttribute('href'))).toEqual(
      sources.map(([documentId, quote]) => getSourceHref(documentId, quote)),
    )
    for (const [, quote] of sources) {
      expect(row.getByText(quote, { selector: 'q' })).toBeInTheDocument()
    }
  }
  expect(screen.queryByText('No source linked')).not.toBeInTheDocument()
})
