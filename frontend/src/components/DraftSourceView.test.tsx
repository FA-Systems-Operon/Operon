import { render, screen, within } from '@testing-library/react'
import { expect, test } from 'vitest'
import DraftSourceView from './DraftSourceView'
import type { SourceLinkedDraft } from './draftSources'

const TRANSCRIPT = '6f1c2d3e-0000-4000-8000-000000000001'
const INTAKE = '6f1c2d3e-0000-4000-8000-000000000002'

const draft: SourceLinkedDraft = {
  name: 'Ada Lovelace',
  needs: ['Payroll help', 'Bookkeeping'],
  goals: ['Hire staff'],
  source_references: [
    { field: 'name', document_id: INTAKE, quote: 'Name: Ada Lovelace' },
    { field: 'needs/0', document_id: TRANSCRIPT, quote: 'payroll is a mess' },
    { field: 'goals/0', document_id: TRANSCRIPT, quote: 'hire two people' },
    { field: 'goals/0', document_id: INTAKE, quote: 'Goal: grow the team' },
  ],
}

const getSourceHref = (documentId: string, quote: string) =>
  `/documents/${documentId}?quote=${encodeURIComponent(quote)}`

function row(label: string) {
  return within(screen.getByText(label, { selector: 'dt' }).parentElement!)
}

test('renders every field with its quote and source link', () => {
  render(<DraftSourceView draft={draft} getSourceHref={getSourceHref} />)

  expect(row('Name').getByText('Ada Lovelace')).toBeInTheDocument()
  expect(row('Name').getByText('Name: Ada Lovelace', { selector: 'q' })).toBeInTheDocument()
  expect(row('Name').getByRole('link', { name: 'View source for Name' })).toHaveAttribute(
    'href',
    getSourceHref(INTAKE, 'Name: Ada Lovelace'),
  )
  expect(row('Need 1').getByText('payroll is a mess', { selector: 'q' })).toBeInTheDocument()
  expect(row('Need 1').getByRole('link', { name: 'View source for Need 1' })).toHaveAttribute(
    'href',
    getSourceHref(TRANSCRIPT, 'payroll is a mess'),
  )
})

test('shows every reference when a field has several', () => {
  render(<DraftSourceView draft={draft} getSourceHref={getSourceHref} />)

  const links = row('Goal 1').getAllByRole('link', { name: 'View source for Goal 1' })
  expect(links.map((link) => link.getAttribute('href'))).toEqual([
    getSourceHref(TRANSCRIPT, 'hire two people'),
    getSourceHref(INTAKE, 'Goal: grow the team'),
  ])
  expect(row('Goal 1').getByText('Goal: grow the team', { selector: 'q' })).toBeInTheDocument()
})

test('shows "No source linked" for a populated field without references', () => {
  render(<DraftSourceView draft={draft} getSourceHref={getSourceHref} />)

  expect(row('Need 2').getByText('Bookkeeping')).toBeInTheDocument()
  expect(row('Need 2').getByText('No source linked')).toBeInTheDocument()
  expect(row('Need 2').queryByRole('link')).not.toBeInTheDocument()
  expect(screen.getAllByText('No source linked')).toHaveLength(1)
})

test.each([
  ['an empty draft', { name: null, needs: [], goals: [], source_references: [] }],
  ['a version without draft keys', {}],
])('renders %s as not extracted', (_, empty) => {
  render(<DraftSourceView draft={empty} getSourceHref={getSourceHref} />)

  expect(row('Name').getByText('Not extracted')).toBeInTheDocument()
  expect(row('Needs').getByText('None extracted')).toBeInTheDocument()
  expect(row('Goals').getByText('None extracted')).toBeInTheDocument()
  expect(screen.queryByRole('link')).not.toBeInTheDocument()
  expect(screen.queryByText('No source linked')).not.toBeInTheDocument()
})
