import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, test } from 'vitest'
import DraftSourceView from './DraftSourceView'
import { ONBOARDING_FIELDS, type ProfileConflict, type SourceLinkedDraft } from './draftSources'

const href = (id: string, quote: string) => `/documents/${id}?quote=${encodeURIComponent(quote)}`
const empty: SourceLinkedDraft = { name: null, needs: [], goals: [], source_references: [] }
const emailConflict: ProfileConflict = {
  field: 'email', explanation: 'The sources give different contact emails.',
  alternatives: [
    { value: 'sales@example.test', document_id: 'call', quote: 'Use sales@example.test' },
    { value: 'hello@example.test', document_id: 'form', quote: 'Use hello@example.test' },
  ],
}
const checked = { rules_version: 1, missing_fields: [] }
const row = (label: string) => within(screen.getByText(label, { selector: 'dt' }).parentElement!)

test('shows each missing mandatory field even when it has no extracted value', () => {
  render(<DraftSourceView draft={{ ...empty, assessment: {
    ...checked, missing_fields: ONBOARDING_FIELDS.map(({ key }) => key),
  } }} getSourceHref={href} />)
  for (const { label } of ONBOARDING_FIELDS) {
    expect(row(label).getByText('Missing information:')).toBeInTheDocument()
    expect(row(label).getByText(/was not extracted/)).toHaveTextContent(label)
  }
  expect(screen.getAllByText('Missing information:')).toHaveLength(9)
})

test('shows both conflict alternatives and their links beside the field', () => {
  render(<DraftSourceView draft={{ ...empty, assessment: checked, conflicts: [emailConflict] }} getSourceHref={href} />)
  const conflict = within(row('Email').getByRole('region', { name: 'Potential conflict for Email' }))
  expect(conflict.getByText(emailConflict.explanation)).toBeInTheDocument()
  emailConflict.alternatives.forEach((alternative, index) => {
    expect(conflict.getByText(alternative.value, { selector: 'strong' })).toBeInTheDocument()
    expect(conflict.getByRole('link', { name: `View conflict source ${index + 1} for Email` }))
      .toHaveAttribute('href', href(alternative.document_id, alternative.quote))
  })
  expect(row('Email').queryByText('Missing information:')).not.toBeInTheDocument()
  expect(row('Website').queryByText('Potential conflict:')).not.toBeInTheDocument()
})

test('keeps group and item conflicts beside their respective goals', () => {
  render(<DraftSourceView draft={{ ...empty, goals: ['Grow bookings'], assessment: checked, conflicts: [
    { ...emailConflict, field: 'goals' }, { ...emailConflict, field: 'goals/0' },
  ] }} getSourceHref={href} />)
  expect(row('Goals').getByRole('region', { name: 'Potential conflict for Goals' })).toBeInTheDocument()
  expect(row('Goal 1').getByRole('region', { name: 'Potential conflict for Goal 1' })).toBeInTheDocument()
  expect(screen.getAllByText('Potential conflict:')).toHaveLength(2)
})

test('renders populated onboarding values with their ordinary source evidence', () => {
  render(<DraftSourceView draft={{ ...empty, website: 'https://example.test', assessment: checked,
    source_references: [{ field: 'website', document_id: 'call', quote: 'Our site is example.test' }],
  }} getSourceHref={href} />)
  expect(row('Website').getByText('https://example.test')).toBeInTheDocument()
  expect(row('Website').getByRole('link', { name: 'View source for Website' }))
    .toHaveAttribute('href', href('call', 'Our site is example.test'))
})

test('distinguishes legacy drafts and unknown assessment versions from checked drafts', () => {
  const { rerender } = render(<DraftSourceView draft={empty} getSourceHref={href} />)
  expect(screen.getByText('Information checks were not recorded for this draft.')).toBeInTheDocument()
  expect(screen.queryByText(/No missing information/)).not.toBeInTheDocument()
  rerender(<DraftSourceView draft={{ ...empty, assessment: { ...checked, rules_version: 2 } }} getSourceHref={href} />)
  expect(screen.getByText('Information checks were not recorded for this draft.')).toBeInTheDocument()
  rerender(<DraftSourceView draft={{ ...empty, assessment: checked }} getSourceHref={href} />)
  expect(screen.getByText('No missing information or potential conflicts were recorded.')).toBeInTheDocument()
})

test.each(['goals/99', 'password'])('reports unsupported conflict path %s without claiming a clean draft', (field) => {
  render(<DraftSourceView draft={{ ...empty, assessment: checked, conflicts: [{ ...emailConflict, field }] }} getSourceHref={href} />)
  expect(screen.getByText(/Some information warnings could not be displayed/)).toBeInTheDocument()
  expect(screen.queryByText(/No missing information/)).not.toBeInTheDocument()
})

test('reports unsupported missing paths and renders model text safely', () => {
  const text = '<img src=x onerror=alert(1)>'
  const { container } = render(<DraftSourceView draft={{ ...empty,
    assessment: { ...checked, missing_fields: ['password'] },
    conflicts: [{ ...emailConflict, explanation: text }],
  }} getSourceHref={href} />)
  expect(screen.getByText(/Some information warnings could not be displayed/)).toBeInTheDocument()
  expect(screen.getByText(text)).toBeInTheDocument()
  expect(container.querySelector('img')).toBeNull()
})


test('conflict evidence links are reachable using the keyboard', async () => {
  const user = userEvent.setup()
  render(<DraftSourceView draft={{ ...empty, assessment: checked, conflicts: [emailConflict] }} getSourceHref={href} />)
  await user.tab()
  expect(screen.getByRole('link', { name: 'View conflict source 1 for Email' })).toHaveFocus()
  await user.tab()
  expect(screen.getByRole('link', { name: 'View conflict source 2 for Email' })).toHaveFocus()
})
