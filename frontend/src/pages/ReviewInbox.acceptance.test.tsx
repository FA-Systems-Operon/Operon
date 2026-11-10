import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import responses from '../../../tests/fixtures/review_inbox/responses.json'
import App from '../App'
import { formatGenerated } from './ReviewInboxPage'

// AT 4.1 (#65): a reviewer opens the review inbox, sees the draft with its client and
// generation time, and selects it to see the proposed fields beside their evidence.
// The API replies are tests/fixtures/review_inbox/responses.json, which
// tests/test_review_inbox_acceptance.py checks against the real endpoints.
const { inbox_item: ITEM, draft: DRAFT } = responses
const DRAFT_URL = `/api/v1/reviews/profiles/${ITEM.client_profile_id}/versions/${ITEM.version_id}`

type Reply = [status: number, body: unknown]

// Answers the inbox with each reply in turn (the last one repeats) and the draft.
function fakeApi(...inbox: Reply[]) {
  const fetchMock = vi.fn(async (url: string) => {
    const [status, body]: Reply =
      url === '/api/v1/reviews' ? (inbox.shift() ?? [200, [ITEM]]) : [200, DRAFT]
    if (url !== '/api/v1/reviews' && url !== DRAFT_URL) throw new Error(`Unexpected ${url}`)
    return { ok: status < 400, status, json: async () => body } as Response
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function openInbox() {
  window.location.hash = '#/reviews'
  render(<App />)
}

afterEach(() => {
  vi.unstubAllGlobals()
  window.location.hash = ''
})

test('criterion 1: the draft is listed with its client name and generation time', async () => {
  fakeApi([200, [ITEM]])
  openInbox()

  const row = await screen.findByRole('link', { name: /Plateau Basements/ })

  expect(row).toHaveTextContent(formatGenerated(ITEM.created_at))
  expect(within(row).getByText(formatGenerated(ITEM.created_at))).toHaveAttribute(
    'datetime',
    ITEM.created_at,
  )
})

test('criterion 2: selecting the draft opens its fields and evidence side by side', async () => {
  const fetchMock = fakeApi([200, [ITEM]])
  openInbox()

  await userEvent.click(await screen.findByRole('link', { name: /Plateau Basements/ }))

  expect(await screen.findByRole('heading', { name: 'Plateau Basements' })).toBeInTheDocument()
  expect(fetchMock).toHaveBeenLastCalledWith(DRAFT_URL)
  expect(screen.getByRole('link', { name: 'Reviews' })).toHaveAttribute('aria-current', 'page')
  // The proposed fields, one button each, and the evidence for the selected one.
  const fields = screen.getByRole('button', { name: /^Name/ }).closest('ul')!
  expect(
    within(fields)
      .getAllByRole('button')
      .map((button) => button.textContent),
  ).toEqual([
    'NameMaya Chenintake',
    'Need 1More qualified bookingstranscript',
    'Goal 130 bookings per monthtranscript',
    'Goal 2Launch a referral programintake',
    '○ WebsiteNot mentioned',
    '○ EmailNot mentioned',
  ])
  const evidence = screen.getByRole('region', { name: 'Name' })
  expect(within(evidence).getByText('Contact name: Maya Chen')).toBeInTheDocument()
  // Side by side: both columns sit in the same two-column body.
  expect(fields.closest('.review-draft-body')).toBe(evidence.parentElement)

  await userEvent.click(screen.getByRole('button', { name: /^Goal 1/ }))

  const goal = screen.getByRole('region', { name: 'Goal 1' })
  expect(within(goal).getByRole('listitem')).toHaveTextContent(
    'transcript.txt · TranscriptWe want 30 bookings per month.',
  )
})

test('an empty inbox says no drafts are waiting', async () => {
  fakeApi([200, []])
  openInbox()

  expect(await screen.findByText('No drafts waiting for review.')).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: /Plateau Basements/ })).not.toBeInTheDocument()
})

test('an inbox that fails to load says so, and Try again loads the draft', async () => {
  fakeApi([500, {}], [200, [ITEM]])
  openInbox()

  expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't load the drafts")
  await userEvent.click(screen.getByRole('button', { name: 'Try again' }))

  expect(await screen.findByRole('link', { name: /Plateau Basements/ })).toBeInTheDocument()
})
