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
  window.history.replaceState(null, '', '#')
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


test('the unapplied-edits banner clears after cancel or correction of invalid pending input', async () => {
  await openDraft()
  const banner = () => screen.queryByText(/Some edits have not been applied/)
  expect(banner()).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Edit Need 1' }))
  await userEvent.clear(screen.getByRole('textbox', { name: 'Need 1' }))
  await userEvent.tab()
  expect(banner()).toBeInTheDocument()
  await userEvent.click(screen.getByRole('textbox', { name: 'Need 1' }))
  await userEvent.keyboard('{Escape}')
  expect(banner()).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Edit Need 1' }))
  await userEvent.clear(screen.getByRole('textbox', { name: 'Need 1' }))
  await userEvent.keyboard('{Enter}')
  expect(banner()).toBeInTheDocument()
  await userEvent.type(screen.getByRole('textbox', { name: 'Need 1' }), 'Corrected need')
  expect(banner()).not.toBeInTheDocument()
  await userEvent.keyboard('{Enter}')
  expect(screen.getByRole('button', { name: 'Edit Need 1' })).toHaveTextContent('Corrected need')
  expect(banner()).not.toBeInTheDocument()
})

test('dirty display labels original conflict proposals, source counts and unsupported warnings', async () => {
  const data = { ...DRAFT.version.data, conflicts: [
    ...DRAFT.version.data.conflicts!,
    { field: 'unknown', explanation: 'Unsupported warning', alternatives: [] },
  ] }
  mockDraft(reply(200, { ...DRAFT, version: { ...DRAFT.version, data } }))
  render(<ReviewDraftPage profileId="p1" versionId="v2" />)
  await screen.findByRole('heading', { name: 'Plateau Basements' })
  await edit('Name', 'Corrected')
  expect(screen.getByText(/Some original-version warnings/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Edit Email' })).toHaveAccessibleDescription(
    'Original proposal: maya@call.test or maya@form.test',
  )
  expect(row('Email').closest('.review-field')).toHaveTextContent('2 original sources')
  await userEvent.click(row('Email'))
  expect(evidence().getByText(/Original version evidence/)).toBeInTheDocument()
  expect(evidence().getByText('The sources give different emails.')).toBeInTheDocument()
  expect(screen.queryByText('▲ Sources disagree')).not.toBeInTheDocument()
  await edit('Name', 'Maya Chen')
  expect(screen.queryByText(/Some original-version warnings/)).not.toBeInTheDocument()
  expect(screen.getByText(/Some warnings could not be shown/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Edit Email' })).toHaveAccessibleDescription(
    'maya@call.test or maya@form.test',
  )
  expect(row('Email').closest('.review-field')).toHaveTextContent('2 sources')
})

// #60 save scenarios: reusable by #66; no Approve action is added here.
const SAVED = {
  ...DRAFT.version,
  id: 'v3', version_number: 3, status: 'draft',
  data: { ...DRAFT.version.data, name: 'Corrected', email: 'chosen@example.test', assessment: null },
} as ReviewDraft['version']

const approvalBlocked = () => document.querySelector('.review-draft')?.getAttribute('data-approval-blocked')

test('save posts only corrections, adopts the returned version and survives reopening its URL', async () => {
  const fetchMock = mockDraft(reply(200, DRAFT), reply(201, SAVED), reply(200, { ...DRAFT, version: SAVED }))
  const view = render(<ReviewDraftPage profileId="p1" versionId="v2" />)
  await screen.findByRole('heading', { name: 'Plateau Basements' })
  expect(approvalBlocked()).toBe('false')
  await edit('Name', 'Corrected')
  await edit('Email', 'chosen@example.test')
  expect(approvalBlocked()).toBe('true')
  await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))
  expect(await screen.findByText('Draft edits saved.')).toBeInTheDocument()
  const [url, init] = fetchMock.mock.calls[1]
  expect(url).toBe('/api/v1/reviews/profiles/p1/versions/v2/edits')
  expect(init.method).toBe('POST')
  expect(JSON.parse(init.body)).toEqual({ changes: { name: 'Corrected', email: 'chosen@example.test' } })
  expect(screen.getByText('Version 3')).toBeInTheDocument()
  expect(window.location.hash).toBe('#/reviews/draft?profile=p1&version=v3')
  expect(approvalBlocked()).toBe('false')
  expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled()
  expect(screen.getByText(/Information checks have not been recomputed/)).toBeInTheDocument()
  await userEvent.click(row('Email'))
  expect(screen.getByRole('button', { name: 'Edit Email' })).toHaveTextContent('chosen@example.test')
  expect(evidence().getAllByRole('listitem')).toHaveLength(2)
  expect(evidence().getByText(/Conflicts remain unresolved/)).toBeInTheDocument()
  expect(document.querySelector('[data-flag]')).toBeNull()
  view.unmount()
  render(<ReviewDraftPage profileId="p1" versionId="v3" />)
  expect(await screen.findByRole('button', { name: 'Edit Name' })).toHaveTextContent('Corrected')
  expect(fetchMock).toHaveBeenLastCalledWith('/api/v1/reviews/profiles/p1/versions/v3')
  await userEvent.click(row('Name'))
  expect(evidence().getByText(/retained as history/)).toBeInTheDocument()
})

test('a second save uses the newly saved version as its base', async () => {
  const next = { ...SAVED, id: 'v4', version_number: 4, data: { ...SAVED.data, name: 'Second correction' } }
  const fetchMock = mockDraft(reply(200, DRAFT), reply(201, SAVED), reply(201, next))
  render(<ReviewDraftPage profileId="p1" versionId="v2" />)
  await screen.findByRole('heading', { name: 'Plateau Basements' })
  await edit('Name', 'Corrected')
  await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))
  await screen.findByText('Version 3')
  await edit('Name', 'Second correction')
  await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))
  await screen.findByText('Version 4')
  expect(fetchMock.mock.calls[2][0]).toBe('/api/v1/reviews/profiles/p1/versions/v3/edits')
  expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({ changes: { name: 'Second correction' } })
})

test('saving freezes edits and repeat submissions until the save finishes', async () => {
  let finish!: (response: Response) => void
  const fetchMock = mockDraft(reply(200, DRAFT), new Promise((resolve) => { finish = resolve }))
  render(<ReviewDraftPage profileId="p1" versionId="v2" />)
  await screen.findByRole('heading', { name: 'Plateau Basements' })
  await edit('Name', 'Corrected')
  await userEvent.dblClick(screen.getByRole('button', { name: 'Save changes' }))
  expect(screen.getByRole('button', { name: 'Saving…' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Edit Name' })).toBeDisabled()
  expect(approvalBlocked()).toBe('true')
  expect(fetchMock).toHaveBeenCalledTimes(2)
  await act(async () => finish(await reply(201, SAVED)))
  expect(screen.getByText('Draft edits saved.')).toBeInTheDocument()
  expect(approvalBlocked()).toBe('false')
})

test.each(['network', 'server', 'validation'])('a %s failure retains corrections and blocks approval until a successful retry', async (failure) => {
  const fetchMock = mockDraft(reply(200, DRAFT))
  render(<ReviewDraftPage profileId="p1" versionId="v2" />)
  await screen.findByRole('heading', { name: 'Plateau Basements' })
  if (failure === 'network') fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
  else fetchMock.mockReturnValueOnce(reply(failure === 'server' ? 500 : 422, { detail: [] }))
  fetchMock.mockReturnValueOnce(reply(201, SAVED))
  await edit('Name', 'Corrected')
  await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))
  expect(await screen.findByRole('alert')).toHaveTextContent(/Couldn't/)
  expect(screen.getByRole('button', { name: 'Edit Name' })).toHaveTextContent('Corrected')
  expect(screen.getByText('Version 2')).toBeInTheDocument()
  expect(approvalBlocked()).toBe('true')
  await userEvent.click(screen.getByRole('button', { name: 'Try saving again' }))
  expect(await screen.findByText('Draft edits saved.')).toBeInTheDocument()
  expect(approvalBlocked()).toBe('false')
})

test('reverting after a failed save still requires a successful freshness check', async () => {
  mockDraft(reply(200, DRAFT), reply(500, {}), reply(201, DRAFT.version))
  render(<ReviewDraftPage profileId="p1" versionId="v2" />)
  await screen.findByRole('heading', { name: 'Plateau Basements' })
  await edit('Name', 'Corrected')
  await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))
  await screen.findByRole('alert')
  await edit('Name', 'Maya Chen')
  expect(approvalBlocked()).toBe('true')
  await userEvent.click(screen.getByRole('button', { name: 'Try saving again' }))
  expect(await screen.findByText('Draft edits saved.')).toBeInTheDocument()
  expect(approvalBlocked()).toBe('false')
})

test('409 retains local edits and blocks saving and approval without silently loading newer data', async () => {
  const fetchMock = mockDraft(reply(200, DRAFT), reply(409, { detail: 'Draft changed' }))
  render(<ReviewDraftPage profileId="p1" versionId="v2" />)
  await screen.findByRole('heading', { name: 'Plateau Basements' })
  await edit('Name', 'Corrected')
  await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))
  expect(await screen.findByRole('alert')).toHaveTextContent(/Open the latest draft from the review inbox/)
  expect(screen.getByRole('button', { name: 'Edit Name' })).toHaveTextContent('Corrected')
  expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled()
  expect(approvalBlocked()).toBe('true')
  expect(fetchMock).toHaveBeenCalledTimes(2)
  expect(window.location.hash).not.toContain('version=v3')
})

test('pending valid or invalid input blocks save and approval before any mutation request', async () => {
  const fetchMock = mockDraft(reply(200, DRAFT))
  render(<ReviewDraftPage profileId="p1" versionId="v2" />)
  await screen.findByRole('heading', { name: 'Plateau Basements' })
  await edit('Name', 'Corrected')
  await userEvent.click(screen.getByRole('button', { name: 'Edit Need 1' }))
  expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled()
  expect(approvalBlocked()).toBe('true')
  await userEvent.clear(screen.getByRole('textbox', { name: 'Need 1' }))
  await userEvent.keyboard('{Enter}')
  expect(screen.getByRole('alert')).toHaveTextContent('List items must not be blank')
  expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled()
  await userEvent.keyboard('{Escape}')
  expect(screen.getByRole('button', { name: 'Save changes' })).toBeEnabled()
  expect(fetchMock).toHaveBeenCalledTimes(1)
})

test('a save response after leaving the page does not change the route', async () => {
  let finish!: (response: Response) => void
  mockDraft(reply(200, DRAFT), new Promise((resolve) => { finish = resolve }))
  const view = render(<ReviewDraftPage profileId="p1" versionId="v2" />)
  await screen.findByRole('heading', { name: 'Plateau Basements' })
  await edit('Name', 'Corrected')
  await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))
  view.unmount()
  window.history.replaceState(null, '', '#/reviews')
  await act(async () => finish(await reply(201, SAVED)))
  expect(window.location.hash).toBe('#/reviews')
})
