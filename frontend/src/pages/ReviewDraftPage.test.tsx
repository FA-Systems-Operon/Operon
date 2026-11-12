import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StrictMode } from 'react'
import { afterEach, expect, test, vi } from 'vitest'
import type { ReviewDraft } from '../api'
import { ONBOARDING_FIELDS } from '../components/draftSources'
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

  expect(screen.getByRole('button', { name: 'Edit Name' })).toHaveTextContent('Maya Chen')
  expect(screen.getByRole('button', { name: 'Edit Need 1' })).toHaveTextContent('Basement finishing')
  expect(screen.getByRole('button', { name: 'Edit Need 2' })).toHaveTextContent('Bathrooms')
  expect(screen.getByRole('button', { name: 'Edit Goal 1' })).toHaveTextContent('Fill the winter schedule')
  expect(screen.getAllByRole('button', { name: /^Edit / })).toHaveLength(13)
  expect(row('Website').closest('.review-field')).toHaveAttribute('data-flag', 'missing')
  expect(row('Email').closest('.review-field')).toHaveAttribute('data-flag', 'conflict')
  expect(row('Name').closest('.review-field')).not.toHaveAttribute('data-flag')
})

test('selects the first field and shows its quote and document', async () => {
  await openDraft()

  expect(row('Name')).toHaveAttribute('aria-pressed', 'true')
  expect(evidence().getByRole('heading', { name: 'Name' })).toBeInTheDocument()
  expect(evidence().getByText('Contact name: Maya Chen', { selector: 'q' })).toBeInTheDocument()
  expect(evidence().getByText('intake.md · Intake')).toBeInTheDocument()
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

  expect((await screen.findByRole('button', { name: 'Phone number' })).closest('.review-field')).toHaveTextContent(
    /2 sources$/,
  )
  await userEvent.click(row('Phone number'))
  expect(evidence().getAllByRole('listitem').map((item) => item.textContent)).toEqual([
    `call.txt · Transcript514-555-0100${quote}`,
    'intake.md · Intake438-555-0199Phone: 438-555-0199',
  ])
})

// Profile edits (PUT) accept any JSON, so the saved data can have the wrong types.
test.each([
  ['a string', 'Bathrooms'],
  ['an object', { 0: 'Bathrooms' }],
  ['null', null],
])('a draft with needs as %s and other bad data still opens', async (_, needs) => {
  const data = {
    name: 42,
    needs,
    goals: [null, 7, 'Fill the winter schedule'],
    source_references: 'none',
    conflicts: { field: 'email' },
    assessment: [],
  }
  mockDraft(reply(200, { ...DRAFT, version: { ...DRAFT.version, data } }))
  render(<ReviewDraftPage profileId="p1" versionId="v2" />)

  expect(await screen.findByRole('heading', { name: 'Plateau Basements' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Edit Goal 1' })).toHaveTextContent('Fill the winter schedule')
  expect(screen.getAllByRole('button', { name: /^Edit / })).toHaveLength(11)
  expect(evidence().getByText('No source linked to this field.')).toBeInTheDocument()
})

test('says when a field has no source, or was not found at all', async () => {
  await openDraft()

  await userEvent.click(row('Need 2'))
  expect(evidence().getByText('No source linked to this field.')).toBeInTheDocument()

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
  expect(row('Name').closest('.review-field')).toHaveTextContent(/source$/)
  expect(screen.getByText(/Some warnings could not be shown/)).toBeInTheDocument()
  await userEvent.click(row('Need 1'))
  expect(evidence().getByText('notes.txt')).toBeInTheDocument()
})

test('an empty draft offers nullable scalars but no new list items', async () => {
  mockDraft(reply(200, { ...DRAFT, version: { ...DRAFT.version, data: {} } }))
  render(<ReviewDraftPage profileId="p1" versionId="v2" />)

  await screen.findByRole('heading', { name: 'Plateau Basements' })
  expect(screen.getAllByRole('button', { name: /^Edit / })).toHaveLength(10)
  expect(screen.queryByRole('button', { name: /Edit (Need|Goal)/ })).not.toBeInTheDocument()
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


async function edit(label: string, text: string) {
  await userEvent.click(screen.getByRole('button', { name: `Edit ${label}` }))
  const input = screen.getByRole('textbox', { name: label })
  await userEvent.clear(input)
  if (text) await userEvent.type(input, text)
  await userEvent.keyboard('{Enter}')
}

test('local edits invalidate every badge and restore on full revert without writes', async () => {
  const original = structuredClone(DRAFT)
  const fetchMock = mockDraft(reply(200, DRAFT))
  render(<ReviewDraftPage profileId="p1" versionId="v2" />)
  await screen.findByRole('heading', { name: 'Plateau Basements' })
  await edit('Name', 'Corrected')
  expect(screen.getByRole('status')).toHaveTextContent('Unsaved local changes')
  expect(document.querySelector('[data-flag]')).toBeNull()
  expect(screen.getByText(/Original version evidence/)).toBeInTheDocument()
  expect(evidence().getByText('Contact name: Maya Chen', { selector: 'q' })).toBeInTheDocument()
  expect(screen.getByText('Reviewer-edited')).toBeInTheDocument()
  await edit('Website', 'example.test')
  await edit('Name', 'Maya Chen')
  expect(screen.getByRole('status')).toBeInTheDocument()
  await edit('Website', '')
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  expect(row('Email').closest('.review-field')).toHaveAttribute('data-flag', 'conflict')
  expect(row('Website').closest('.review-field')).toHaveAttribute('data-flag', 'missing')
  expect(screen.queryByText('Reviewer-edited')).not.toBeInTheDocument()
  expect(DRAFT).toEqual(original)
  expect(fetchMock.mock.calls).toEqual([['/api/v1/reviews/profiles/p1/versions/v2']])
})

test('conflicted scalars start empty and retain both original claims after correction', async () => {
  await openDraft()
  await userEvent.click(screen.getByRole('button', { name: 'Edit Email' }))
  expect(screen.getByRole('textbox', { name: 'Email' })).toHaveValue('')
  await userEvent.type(screen.getByRole('textbox'), 'chosen@example.test{Enter}')
  expect(screen.getByRole('button', { name: 'Edit Email' })).toHaveTextContent('chosen@example.test')
  expect(evidence().getAllByRole('listitem')).toHaveLength(2)
  expect(evidence().getByText('maya@call.test', { selector: 'strong' })).toBeInTheDocument()
  expect(screen.queryByText('▲ Sources disagree')).not.toBeInTheDocument()
  expect(screen.getByText(/Original version evidence/)).toBeInTheDocument()
})

test.each(['draft', 'in_review'])('all nullable fields can be edited in status %s', async (status) => {
  mockDraft(reply(200, { ...DRAFT, version: { ...DRAFT.version, status } }))
  render(<ReviewDraftPage profileId="p1" versionId="v2" />)
  await screen.findByRole('heading', { name: 'Plateau Basements' })
  for (const { label } of [{ label: 'Name' }, ...ONBOARDING_FIELDS]) {
    await edit(label, `Corrected ${label}`)
    expect(screen.getByRole('button', { name: `Edit ${label}` })).toHaveTextContent(`Corrected ${label}`)
  }
})

test.each(['approved', 'rejected', 'stale'])('status %s is read-only with evidence selection', async (status) => {
  mockDraft(reply(200, { ...DRAFT, version: { ...DRAFT.version, status } }))
  render(<ReviewDraftPage profileId="p1" versionId="v2" />)
  await screen.findByRole('heading', { name: 'Plateau Basements' })
  expect(screen.queryByRole('button', { name: /^Edit / })).not.toBeInTheDocument()
  await userEvent.click(row('Email'))
  expect(evidence().getAllByRole('listitem')).toHaveLength(2)
})

test('list edits retain evidence and reject blanks without changing another item', async () => {
  await openDraft()
  await edit('Need 2', 'Corrected need')
  expect(screen.getByRole('button', { name: 'Edit Need 1' })).toHaveTextContent('Basement finishing')
  await userEvent.click(screen.getByRole('button', { name: 'Edit Need 1' }))
  await userEvent.clear(screen.getByRole('textbox'))
  await userEvent.tab()
  expect(screen.getByRole('alert')).toHaveTextContent('List items must not be blank')
  expect(screen.getByText(/Some edits have not been applied/)).toBeInTheDocument()
  await userEvent.click(screen.getByRole('textbox'))
  await userEvent.keyboard('{Escape}')
  expect(screen.getByRole('button', { name: 'Edit Need 1' })).toHaveTextContent('Basement finishing')
  expect(evidence().getByText('we finish basements', { selector: 'q' })).toBeInTheDocument()
})
