import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StrictMode } from 'react'
import { afterEach, expect, test, vi } from 'vitest'
import type { ReviewInboxItem } from '../api'
import ReviewInboxPage, { formatGenerated } from './ReviewInboxPage'

function item(overrides: Partial<ReviewInboxItem>): ReviewInboxItem {
  return {
    version_id: 'v1',
    client_profile_id: 'p1',
    version_number: 2,
    client_id: 'c1',
    client_name: 'Plateau Basements',
    created_at: '2026-11-09T14:03:00Z',
    status: 'draft',
    ...overrides,
  }
}

// Newest first, as the API sends them. The same client has two profiles with drafts.
const DRAFTS = [
  item({ version_id: 'v9', client_profile_id: 'p3', client_name: 'Acme Plumbing' }),
  item({ version_id: 'v5', created_at: '2026-11-08T09:30:00Z', status: 'in_review' }),
  item({ version_id: 'v3', client_profile_id: 'p2', created_at: '2026-11-01T17:45:00Z' }),
]

function reply(status: number, body: unknown) {
  return Promise.resolve({
    ok: status < 400,
    status,
    json: () => Promise.resolve(body),
  } as Response)
}

function mockReviews(...replies: Promise<Response>[]) {
  const fetchMock = vi.fn()
  for (const next of replies) {
    fetchMock.mockReturnValueOnce(next)
  }
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

type Late = { answer: (body: unknown) => void; fail: (error: Error) => void }

afterEach(() => {
  vi.unstubAllGlobals()
})

test('shows a row per draft in the order the API returns', async () => {
  mockReviews(reply(200, DRAFTS))
  render(<ReviewInboxPage />)

  const rows = await screen.findAllByRole('listitem')

  expect(rows.map((row) => within(row).getByRole('link').textContent)).toEqual([
    `Acme Plumbing${formatGenerated('2026-11-09T14:03:00Z')}v2Draft`,
    `Plateau Basements${formatGenerated('2026-11-08T09:30:00Z')}v2In review`,
    `Plateau Basements${formatGenerated('2026-11-01T17:45:00Z')}v2Draft`,
  ])
  expect(rows[1].querySelector('time')).toHaveAttribute('datetime', '2026-11-08T09:30:00Z')
  // Shown in the attention colour, unlike a plain draft.
  expect(within(rows[1]).getByText('In review')).toHaveAttribute('data-status', 'in_review')
})

test('each row links to its draft', async () => {
  mockReviews(reply(200, DRAFTS))
  render(<ReviewInboxPage />)

  const links = await screen.findAllByRole('link')

  expect(links.map((link) => link.getAttribute('href'))).toEqual([
    '#/reviews/draft?profile=p3&version=v9',
    '#/reviews/draft?profile=p1&version=v5',
    '#/reviews/draft?profile=p2&version=v3',
  ])
})

test('formatGenerated gives a readable local date and time', () => {
  const text = formatGenerated('2026-11-09T14:03:00Z')

  expect(text).toContain('2026')
  expect(text).not.toContain('T14')
})

test('shows loading until the drafts arrive', async () => {
  mockReviews(reply(200, []))
  render(<ReviewInboxPage />)

  expect(screen.getByRole('status')).toHaveTextContent('Loading drafts…')
  expect(await screen.findByText('No drafts waiting for review.')).toBeInTheDocument()
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  expect(screen.queryByRole('list')).not.toBeInTheDocument()
})

test('shows an error and loads again on Try again', async () => {
  const fetchMock = mockReviews(reply(500, {}), reply(200, DRAFTS))
  render(<ReviewInboxPage />)

  expect(await screen.findByRole('alert')).toHaveTextContent(
    "Couldn't load the drafts waiting for review.",
  )
  await userEvent.click(screen.getByRole('button', { name: 'Try again' }))

  expect(await screen.findAllByRole('listitem')).toHaveLength(3)
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  expect(fetchMock).toHaveBeenCalledTimes(2)
})

// StrictMode (as in main.tsx) runs the effect twice on the same page during
// development, so the first request's reply can arrive after the second's.
test.each([
  ['list', (late: Late) => late.answer(DRAFTS)],
  ['failure', (late: Late) => late.fail(new TypeError('Failed to fetch'))],
])('ignores a %s from an earlier request that arrives late', async (_, settle) => {
  const late = {} as Late
  mockReviews(
    new Promise((resolve, reject) => {
      late.answer = (body) =>
        resolve({ ok: true, status: 200, json: () => Promise.resolve(body) } as Response)
      late.fail = reject
    }),
    reply(200, []),
  )
  render(
    <StrictMode>
      <ReviewInboxPage />
    </StrictMode>,
  )
  expect(await screen.findByText('No drafts waiting for review.')).toBeInTheDocument()

  await act(async () => settle(late))

  expect(screen.getByText('No drafts waiting for review.')).toBeInTheDocument()
  expect(screen.queryByRole('list')).not.toBeInTheDocument()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})
