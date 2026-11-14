import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import type { ReviewDraft } from '../api'
import ReviewDraftPage from '../pages/ReviewDraftPage'

// #63 smoke checks for the Reject action; the dedicated rejection suite is #64.

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

function reply(status: number, body: unknown) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) } as Response)
}

async function openDraft(...later: Promise<Response>[]) {
  const fetchMock = vi.fn().mockReturnValueOnce(reply(200, DRAFT))
  for (const next of later) fetchMock.mockReturnValueOnce(next)
  vi.stubGlobal('fetch', fetchMock)
  render(<ReviewDraftPage profileId="p1" versionId="v2" />)
  await screen.findByRole('heading', { name: 'Plateau Basements' })
  return fetchMock
}

afterEach(() => {
  vi.unstubAllGlobals()
})

test('reject needs a reason before anything is sent', async () => {
  const user = userEvent.setup()
  const fetchMock = await openDraft()

  await user.click(screen.getByRole('button', { name: 'Reject' }))
  await user.type(screen.getByLabelText('Reason for rejecting'), '   ')
  await user.click(screen.getByRole('button', { name: 'Reject draft' }))

  expect(screen.getByRole('alert')).toHaveTextContent('Enter a reason for rejecting this draft.')
  expect(fetchMock).toHaveBeenCalledTimes(1)
})

test('reject sends the trimmed reason and shows the draft as rejected', async () => {
  const user = userEvent.setup()
  const rejected = {
    ...DRAFT.version,
    status: 'rejected',
    rejection_reason: 'Wrong client',
    rejected_at: '2026-11-14T10:00:00Z',
  }
  const fetchMock = await openDraft(reply(200, rejected))

  await user.click(screen.getByRole('button', { name: 'Reject' }))
  await user.type(screen.getByLabelText('Reason for rejecting'), '  Wrong client ')
  await user.click(screen.getByRole('button', { name: 'Reject draft' }))

  expect(await screen.findByText('Reason: Wrong client')).toBeInTheDocument()
  const [url, init] = fetchMock.mock.calls[1]
  expect(url).toBe('/api/v1/reviews/profiles/p1/versions/v2/reject')
  expect(init).toMatchObject({ method: 'POST', body: JSON.stringify({ reason: 'Wrong client' }) })
  expect(screen.queryByRole('button', { name: 'Reject' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Save changes' })).not.toBeInTheDocument()
  expect(screen.getAllByText('Rejected').length).toBeGreaterThan(0)
})

test('a conflict keeps the draft and asks the reviewer to reload', async () => {
  const user = userEvent.setup()
  await openDraft(reply(409, { detail: 'Draft changed' }))

  await user.click(screen.getByRole('button', { name: 'Reject' }))
  await user.type(screen.getByLabelText('Reason for rejecting'), 'Wrong client')
  await user.click(screen.getByRole('button', { name: 'Reject draft' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Open the latest draft from the review inbox.')
  expect(screen.getByRole('button', { name: 'Reject draft' })).toBeDisabled()
})

test('cancel closes the form without rejecting', async () => {
  const user = userEvent.setup()
  const fetchMock = await openDraft()

  await user.click(screen.getByRole('button', { name: 'Reject' }))
  await user.click(screen.getByRole('button', { name: 'Cancel' }))

  expect(screen.getByRole('button', { name: 'Reject' })).toBeInTheDocument()
  expect(fetchMock).toHaveBeenCalledTimes(1)
})

test('save waits while a rejection is in flight, and the rejection error stays visible', async () => {
  const user = userEvent.setup()
  let finish: (value: Response) => void = () => {}
  const pending = new Promise<Response>((resolve) => { finish = resolve })
  const fetchMock = await openDraft(pending)

  // An unsaved edit, so Save is available before rejecting.
  await user.click(screen.getByRole('button', { name: 'Edit Name' }))
  await user.clear(screen.getByRole('textbox', { name: 'Name' }))
  await user.type(screen.getByRole('textbox', { name: 'Name' }), 'Corrected')
  await user.keyboard('{Enter}')
  expect(screen.getByRole('button', { name: 'Save changes' })).toBeEnabled()

  await user.click(screen.getByRole('button', { name: 'Reject' }))
  await user.type(screen.getByLabelText('Reason for rejecting'), 'Wrong client')
  await user.click(screen.getByRole('button', { name: 'Reject draft' }))

  expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Save changes' }))
  finish(await reply(500, {}))

  expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't confirm the draft was rejected.")
  expect(screen.getByRole('button', { name: 'Save changes' })).toBeEnabled()
  // Only the draft load and the reject request: no save slipped through.
  expect(fetchMock).toHaveBeenCalledTimes(2)
})
