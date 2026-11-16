import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import responses from '../../../tests/fixtures/review_inbox/responses.json'
import ReviewDraftPage from './ReviewDraftPage'

// AT 4.3 (#67): these two clicks use the response examples checked by
// tests/test_review_decisions_acceptance.py. The backend verifies persistence.
const { draft: DRAFT, review_decisions: DECISIONS } = responses
const BASE_URL = `/api/v1/reviews/profiles/${DRAFT.version.client_profile_id}/versions`
const EDITED = {
  ...DRAFT.version,
  ...DECISIONS.edited_version,
  data: {
    ...DRAFT.version.data,
    goals: [DECISIONS.changes['goals/0'], ...DRAFT.version.data.goals.slice(1)],
  },
}
const APPROVAL = {
  version: { ...EDITED, ...DECISIONS.approved_version },
  newly_stale_artifact_version_ids: [],
}
const REJECTED = { ...DRAFT.version, ...DECISIONS.rejected_version }

beforeEach(() => {
  document.cookie = 'operon_csrf=csrf-token'
  window.location.hash = `#/reviews/draft?profile=${DRAFT.version.client_profile_id}&version=${DRAFT.version.id}`
})

afterEach(() => {
  vi.unstubAllGlobals()
  document.cookie = 'operon_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT'
  window.location.hash = ''
})

test('criterion 1: saving an edit then approving opens a new approved version with that content', async () => {
  const user = userEvent.setup()
  const fetchMock = vi.fn()
    .mockResolvedValueOnce({ ok: true, status: 200, json: async () => DRAFT })
    .mockResolvedValueOnce({ ok: true, status: 201, json: async () => EDITED })
    .mockResolvedValueOnce({ ok: true, status: 201, json: async () => APPROVAL })
  vi.stubGlobal('fetch', fetchMock)
  render(<ReviewDraftPage profileId={DRAFT.version.client_profile_id} versionId={DRAFT.version.id} />)
  await screen.findByRole('heading', { name: DRAFT.client.name })

  await user.click(screen.getByRole('button', { name: 'Edit Goal 1' }))
  await user.clear(screen.getByRole('textbox', { name: 'Goal 1' }))
  await user.type(screen.getByRole('textbox', { name: 'Goal 1' }), `${DECISIONS.changes['goals/0']}{Enter}`)
  await user.click(screen.getByRole('button', { name: 'Save changes' }))
  await screen.findByText('Draft edits saved.')
  await user.click(screen.getByRole('button', { name: 'Approve' }))

  expect(await screen.findByText(`Version ${APPROVAL.version.version_number}`)).toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent('Approved')
  expect(screen.getByText(DECISIONS.changes['goals/0'])).toBeInTheDocument()
  expect(window.location.hash).toBe(`#/reviews/draft?profile=${DRAFT.version.client_profile_id}&version=${APPROVAL.version.id}`)
  expect(fetchMock.mock.calls).toEqual([
    [`${BASE_URL}/${DRAFT.version.id}`],
    [`${BASE_URL}/${DRAFT.version.id}/edits`, {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': 'csrf-token' },
      body: JSON.stringify({ changes: DECISIONS.changes }),
    }],
    [`${BASE_URL}/${EDITED.id}/approve`, {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': 'csrf-token' },
    }],
  ])
})

test('criterion 2: rejecting with a reason keeps the same version and shows its saved rejection', async () => {
  const user = userEvent.setup()
  const fetchMock = vi.fn()
    .mockResolvedValueOnce({ ok: true, status: 200, json: async () => DRAFT })
    .mockResolvedValueOnce({ ok: true, status: 200, json: async () => REJECTED })
  vi.stubGlobal('fetch', fetchMock)
  render(<ReviewDraftPage profileId={DRAFT.version.client_profile_id} versionId={DRAFT.version.id} />)
  await screen.findByRole('heading', { name: DRAFT.client.name })

  await user.click(screen.getByRole('button', { name: 'Reject' }))
  await user.type(screen.getByLabelText('Reason for rejecting'), REJECTED.rejection_reason)
  await user.click(screen.getByRole('button', { name: 'Reject draft' }))

  expect(await screen.findByText(`Reason: ${REJECTED.rejection_reason}`)).toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent('Rejected')
  expect(screen.getByText(`Version ${DRAFT.version.version_number}`)).toBeInTheDocument()
  expect(window.location.hash).toBe(`#/reviews/draft?profile=${DRAFT.version.client_profile_id}&version=${DRAFT.version.id}`)
  expect(fetchMock.mock.calls).toEqual([
    [`${BASE_URL}/${DRAFT.version.id}`],
    [`${BASE_URL}/${DRAFT.version.id}/reject`, {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': 'csrf-token' },
      body: JSON.stringify({ reason: REJECTED.rejection_reason }),
    }],
  ])
})
