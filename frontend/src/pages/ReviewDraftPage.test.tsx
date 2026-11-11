import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StrictMode } from 'react'
import { afterEach, expect, test, vi } from 'vitest'
import type { ReviewDraft } from '../api'
import ReviewDraftPage from './ReviewDraftPage'
import { formatGenerated } from './ReviewInboxPage'

const CALL = 'doc-call'
const FORM = 'doc-form'

const DRAFT = {
  version: {
    id: 'v2',
    client_profile_id: 'p1',
    version_number: 2,
    status: 'in_review',
    created_at: '2026-11-09T14:03:00Z',
    approved_by: null,
    approved_at: null,
    data: {
      name: 'Maya Chen',
      needs: ['Basement finishing', 'Bathrooms'],
      goals: ['Fill the winter schedule'],
      email: null,
      source_references: [
        { field: 'name', document_id: FORM, quote: 'Contact name: Maya Chen' },
        { field: 'needs/0', document_id: CALL, quote: 'we finish basements' },
        { field: 'goals/0', document_id: CALL, quote: 'fill the winter' },
        { field: 'goals/0', document_id: FORM, quote: 'Goal: busy winter' },
      ],
      conflicts: [
        {
          field: 'email',
          explanation: 'The sources give different emails.',
          alternatives: [
            { value: 'maya@call.test', document_id: CALL, quote: 'email me at maya@call.test' },
            { value: 'maya@form.test', document_id: FORM, quote: 'Email: maya@form.test' },
          ],
        },
      ],
      assessment: { rules_version: 1, missing_fields: ['website'] },
    },
  },
  client: { id: 'c1', name: 'Plateau Basements', created_at: '2026-10-28T00:00:00Z' },
  documents: [
    { id: CALL, original_filename: 'call.txt', kind: 'transcript' },
    { id: FORM, original_filename: 'intake.md', kind: 'intake' },
  ],
} as ReviewDraft

function reply(status: number, body: unknown) {
  return Promise.resolve({
    ok: status < 400,
    status,
    json: () => Promise.resolve(body),
  } as Response)
}

function mockDraft(...replies: Promise<Response>[]) {
  const fetchMock = vi.fn()
  for (const next of replies) {
    fetchMock.mockReturnValueOnce(next)
  }
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

async function openDraft() {
  mockDraft(reply(200, DRAFT))
  render(<ReviewDraftPage profileId="p1" versionId="v2" />)
  await screen.findByRole('heading', { name: 'Plateau Basements' })
}

const row = (label: string) => screen.getByRole('button', { name: new RegExp(`^\\W*${label}`) })
const evidence = () => within(screen.getByRole('region', { name: /./ }))

afterEach(() => {
  vi.unstubAllGlobals()
})

test('shows the client, status, version, generated time and a way back', async () => {
  await openDraft()

  expect(screen.getByText('In review')).toBeInTheDocument()
  expect(screen.getByText('Version 2')).toBeInTheDocument()
  expect(screen.getByText(formatGenerated('2026-11-09T14:03:00Z'))).toHaveAttribute(
    'datetime',
    '2026-11-09T14:03:00Z',
  )
  expect(screen.getByRole('link', { name: '← Review inbox' })).toHaveAttribute('href', '#/reviews')
})

test('lists one row per field with its value and source tag, flags marked', async () => {
  await openDraft()

  expect(screen.getAllByRole('button').map((button) => button.textContent)).toEqual([
    'NameMaya Chenintake',
    'Need 1Basement finishingtranscript',
    'Need 2Bathrooms',
    'Goal 1Fill the winter schedule2 sources',
    '○ WebsiteNot mentioned',
    '▲ Emailmaya@call.test or maya@form.test2 sources',
  ])
  expect(row('Website')).toHaveAttribute('data-flag', 'missing')
  expect(row('Email')).toHaveAttribute('data-flag', 'conflict')
  expect(row('Name')).not.toHaveAttribute('data-flag')
})

test('selects the first field and shows its quote and document', async () => {
  await openDraft()

  expect(row('Name')).toHaveAttribute('aria-pressed', 'true')
  expect(evidence().getByRole('heading', { name: 'Name' })).toBeInTheDocument()
  expect(evidence().getByText('Contact name: Maya Chen', { selector: 'q' })).toBeInTheDocument()
  expect(evidence().getByText('intake.md · Intake')).toBeInTheDocument()
  expect(evidence().getByText(/matched word for word/)).toBeInTheDocument()
})

test('clicking a field shows every quote with its document', async () => {
  await openDraft()

  await userEvent.click(row('Goal 1'))

  expect(row('Goal 1')).toHaveAttribute('aria-pressed', 'true')
  expect(row('Name')).toHaveAttribute('aria-pressed', 'false')
  const sources = evidence()
    .getAllByRole('listitem')
    .map((item) => item.textContent)
  expect(sources).toEqual([
    'call.txt · Transcriptfill the winter',
    'intake.md · IntakeGoal: busy winter',
  ])
})

test('a field can be chosen from the keyboard, and a conflict shows both sides', async () => {
  await openDraft()

  row('Email').focus()
  await userEvent.keyboard('{Enter}')

  expect(evidence().getByText('▲ Sources disagree')).toBeInTheDocument()
  expect(evidence().getByText('The sources give different emails.')).toBeInTheDocument()
  expect(evidence().getByText('maya@call.test', { selector: 'strong' })).toBeInTheDocument()
  expect(evidence().getByText('Email: maya@form.test', { selector: 'q' })).toBeInTheDocument()
  expect(evidence().getByText(/won't pick one/)).toBeInTheDocument()
})

test('a quote that is both a source and a conflict side shows once, with its value', async () => {
  const quote = 'call me on 514-555-0100'
  const data = {
    phone_number: '514-555-0100',
    source_references: [{ field: 'phone_number', document_id: CALL, quote }],
    conflicts: [
      {
        field: 'phone_number',
        explanation: 'The sources give different numbers.',
        alternatives: [
          { value: '514-555-0100', document_id: CALL, quote },
          { value: '438-555-0199', document_id: FORM, quote: 'Phone: 438-555-0199' },
        ],
      },
    ],
  }
  mockDraft(reply(200, { ...DRAFT, version: { ...DRAFT.version, data } }))
  render(<ReviewDraftPage profileId="p1" versionId="v2" />)

  expect(await screen.findByRole('button', { name: /Phone number/ })).toHaveTextContent(
    /2 sources$/,
  )
  expect(evidence().getAllByRole('listitem').map((item) => item.textContent)).toEqual([
    `call.txt · Transcript514-555-0100${quote}`,
    'intake.md · Intake438-555-0199Phone: 438-555-0199',
  ])
})

test('says when a field has no source, or was not found at all', async () => {
  await openDraft()

  await userEvent.click(row('Need 2'))
  expect(evidence().getByText('No source linked to this field.')).toBeInTheDocument()
  expect(evidence().queryByText(/matched word for word/)).not.toBeInTheDocument()

  await userEvent.click(row('Website'))
  expect(evidence().getByText('Not found in the transcript or intake answers.')).toBeInTheDocument()
})

test('names quotes whose document is gone or has no kind, and empty versions', async () => {
  const data = {
    name: 'Maya Chen',
    needs: ['Bathrooms'],
    source_references: [
      { field: 'name', document_id: 'deleted', quote: 'Maya Chen' },
      { field: 'needs/0', document_id: 'old', quote: 'bathrooms too' },
    ],
    conflicts: [{ field: 'password', explanation: '', alternatives: [] }],
  }
  const documents = [{ id: 'old', original_filename: 'notes.txt', kind: null }]
  mockDraft(reply(200, { ...DRAFT, version: { ...DRAFT.version, data }, documents }))
  render(<ReviewDraftPage profileId="p1" versionId="v2" />)

  expect(await screen.findByText('Unknown document')).toBeInTheDocument()
  expect(row('Name')).toHaveTextContent(/source$/)
  expect(screen.getByText(/Some warnings could not be shown/)).toBeInTheDocument()
  await userEvent.click(row('Need 1'))
  expect(evidence().getByText('notes.txt')).toBeInTheDocument()
})

test('says so when the version has no fields', async () => {
  mockDraft(reply(200, { ...DRAFT, version: { ...DRAFT.version, data: {} } }))
  render(<ReviewDraftPage profileId="p1" versionId="v2" />)

  expect(await screen.findByText('This version has no proposed fields.')).toBeInTheDocument()
  expect(screen.queryByRole('button')).not.toBeInTheDocument()
})

test.each([
  ['p1', null],
  [null, 'v2'],
])('a link missing the profile or version (%s, %s) is not found', (profileId, versionId) => {
  const fetchMock = mockDraft()
  render(<ReviewDraftPage profileId={profileId} versionId={versionId} />)

  expect(screen.getByText(/This draft wasn't found/)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: '← Review inbox' })).toHaveAttribute('href', '#/reviews')
  expect(fetchMock).not.toHaveBeenCalled()
})

test('a version that is not in that profile is not found', async () => {
  mockDraft(reply(404, { detail: 'Profile version not found' }))
  render(<ReviewDraftPage profileId="p1" versionId="v9" />)

  expect(screen.getByRole('status')).toHaveTextContent('Loading draft…')
  expect(await screen.findByText(/This draft wasn't found/)).toBeInTheDocument()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

test('shows an error and loads again on Try again', async () => {
  const fetchMock = mockDraft(reply(500, {}), reply(200, DRAFT))
  render(<ReviewDraftPage profileId="p1" versionId="v2" />)

  expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't load this draft.")
  await userEvent.click(screen.getByRole('button', { name: 'Try again' }))

  expect(await screen.findByRole('heading', { name: 'Plateau Basements' })).toBeInTheDocument()
  expect(fetchMock).toHaveBeenCalledTimes(2)
})

type Late = { answer: () => void; fail: (error: Error) => void }

// StrictMode (as in main.tsx) runs the effect twice on the same page during
// development, so the first request's reply can arrive after the second's.
test.each([
  ['draft', (late: Late) => late.answer()],
  ['failure', (late: Late) => late.fail(new TypeError('Failed to fetch'))],
])('ignores a %s from an earlier request that arrives late', async (_, settle) => {
  const late = {} as Late
  const other = { ...DRAFT, client: { ...DRAFT.client, name: 'Stale Client' } }
  mockDraft(
    new Promise((resolve, reject) => {
      late.answer = () =>
        resolve({ ok: true, status: 200, json: () => Promise.resolve(other) } as Response)
      late.fail = reject
    }),
    reply(200, DRAFT),
  )
  render(
    <StrictMode>
      <ReviewDraftPage profileId="p1" versionId="v2" />
    </StrictMode>,
  )
  expect(await screen.findByRole('heading', { name: 'Plateau Basements' })).toBeInTheDocument()

  await act(async () => settle(late))

  expect(screen.getByRole('heading', { name: 'Plateau Basements' })).toBeInTheDocument()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})
