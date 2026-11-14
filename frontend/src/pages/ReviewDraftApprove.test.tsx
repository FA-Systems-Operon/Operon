import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import type { ReviewDraft } from '../api'
import ReviewDraftPage from './ReviewDraftPage'

// #62: Approve saves the loaded (possibly edited) draft as a new approved version.

const DRAFT = {
  version: {
    id: 'v2',
    client_profile_id: 'p1',
    version_number: 2,
    status: 'in_review',
    created_at: '2026-11-09T14:03:00Z',
    approved_by: null,
    approved_at: null,
    data: { name: 'Maya Chen', needs: [], goals: [], source_references: [], conflicts: [] },
  },
  client: { id: 'c1', name: 'Plateau Basements', created_at: '2026-10-28T00:00:00Z' },
  documents: [],
} as unknown as ReviewDraft

const APPROVED = {
  ...DRAFT.version,
  id: 'v3',
  version_number: 3,
  status: 'approved',
  approved_by: 'u1',
  approved_at: '2026-11-14T10:00:00Z',
}

function reply(status: number, body: unknown) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) } as Response)
}

async function openDraft(props: { canReview?: boolean } = {}, ...later: Promise<Response>[]) {
  const fetchMock = vi.fn().mockReturnValueOnce(reply(200, DRAFT))
  for (const next of later) fetchMock.mockReturnValueOnce(next)
  vi.stubGlobal('fetch', fetchMock)
  render(<ReviewDraftPage profileId="p1" versionId="v2" {...props} />)
  await screen.findByRole('heading', { name: 'Plateau Basements' })
  return fetchMock
}

beforeEach(() => {
  document.cookie = 'operon_csrf=csrf-token'
  window.location.hash = '#/reviews/draft?profile=p1&version=v2'
})

afterEach(() => {
  vi.unstubAllGlobals()
  document.cookie = 'operon_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT'
})

test('approve posts with the session and CSRF token, then opens the approved version', async () => {
  const user = userEvent.setup()
  const fetchMock = await openDraft({}, reply(201, { version: APPROVED, newly_stale_artifact_version_ids: [] }))

  await user.click(screen.getByRole('button', { name: 'Approve' }))

  expect(await screen.findByText('Version 3')).toBeInTheDocument()
  const [url, init] = fetchMock.mock.calls[1]
  expect(url).toBe('/api/v1/reviews/profiles/p1/versions/v2/approve')
  expect(init).toMatchObject({
    method: 'POST',
    credentials: 'include',
    headers: { 'X-CSRF-Token': 'csrf-token' },
  })
  expect(window.location.hash).toBe('#/reviews/draft?profile=p1&version=v3')
  expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
  expect(screen.queryByText('Draft edits saved.')).not.toBeInTheDocument()
})

test('a second click while approving sends only one request', async () => {
  const user = userEvent.setup()
  let finish: (value: Response) => void = () => {}
  const pending = new Promise<Response>((resolve) => { finish = resolve })
  const fetchMock = await openDraft({}, pending)

  await user.click(screen.getByRole('button', { name: 'Approve' }))
  expect(screen.getByRole('button', { name: 'Approving…' })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Approving…' }))
  finish(await reply(201, { version: APPROVED, newly_stale_artifact_version_ids: [] }))

  expect(await screen.findByText('Version 3')).toBeInTheDocument()
  expect(fetchMock).toHaveBeenCalledTimes(2)
})

test('a stale draft is not approved and asks the reviewer to reload', async () => {
  const user = userEvent.setup()
  await openDraft({}, reply(409, { detail: 'Draft changed' }))

  await user.click(screen.getByRole('button', { name: 'Approve' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Open the latest draft from the review inbox.')
  expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled()
  expect(screen.getByText('Version 2')).toBeInTheDocument()
})

test('a refused role is explained', async () => {
  const user = userEvent.setup()
  await openDraft({}, reply(403, { detail: 'Your role cannot do this' }))

  await user.click(screen.getByRole('button', { name: 'Approve' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Your role cannot approve drafts.')
})

test('viewers see the draft without edit, reject or approve controls', async () => {
  await openDraft({ canReview: false })

  expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Reject' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Save changes' })).not.toBeInTheDocument()
})
