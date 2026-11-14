import { act, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import App from './App'

function jsonResponse(body: unknown) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) } as Response)
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn().mockImplementation(() => jsonResponse([])))
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  vi.useRealTimers()
  window.location.hash = ''
})

function openAt(hash: string) {
  window.location.hash = hash
  render(<App />)
}

function activeTab() {
  const menu = screen.getByRole('navigation', { name: 'Main' })
  return within(menu).queryByRole('link', { current: 'page' })
}

test('opens on Command with the New intake entry point', () => {
  openAt('')

  expect(screen.getByRole('heading', { name: 'Command' })).toBeInTheDocument()
  expect(activeTab()).toHaveTextContent('Command')
  expect(screen.getByRole('link', { name: 'New intake' })).toHaveAttribute(
    'href',
    '#/sources/new',
  )
})

test('shows every menu item with its link', () => {
  openAt('#/')

  const menu = within(screen.getByRole('navigation', { name: 'Main' }))
  expect(menu.getByRole('link', { name: 'Command' })).toHaveAttribute('href', '#/')
  expect(menu.getByRole('link', { name: 'Brain' })).toHaveAttribute('href', '#/brain')
  expect(menu.getByRole('link', { name: 'Workforce' })).toHaveAttribute('href', '#/workforce')
  expect(screen.getByRole('link', { name: 'Reviews' })).toHaveAttribute('href', '#/reviews')
  expect(screen.getByRole('link', { name: 'Operon' })).toHaveAttribute('href', '#/')
})

test.each([
  ['#/brain', 'Brain'],
  ['#/workforce', 'Workforce'],
])('%s is an empty page with its tab marked', (hash, title) => {
  openAt(hash)

  expect(screen.getByRole('heading', { name: title })).toBeInTheDocument()
  expect(activeTab()).toHaveTextContent(title)
  // The only text is the title kept for screen readers.
  expect(screen.getByRole('main').textContent).toBe(title)
})

test('Reviews opens the review inbox and marks the Reviews link', async () => {
  openAt('#/reviews')

  expect(screen.getByRole('heading', { name: 'Review inbox' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Reviews' })).toHaveAttribute('aria-current', 'page')
  expect(activeTab()).toBeNull()
  expect(await screen.findByText('No drafts waiting for review.')).toBeInTheDocument()
})

test('a draft link from the inbox opens that draft under Reviews', async () => {
  const fetchMock = vi.fn().mockImplementation(() =>
    jsonResponse({
      version: { version_number: 2, status: 'draft', data: {}, created_at: '2026-11-09T14:03:00Z' },
      client: { id: 'c1', name: 'Plateau Basements' },
      documents: [],
    }),
  )
  vi.stubGlobal('fetch', fetchMock)
  openAt('#/reviews/draft?profile=p1&version=v2')

  expect(await screen.findByRole('heading', { name: 'Plateau Basements' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Reviews' })).toHaveAttribute('aria-current', 'page')
  expect(fetchMock).toHaveBeenCalledWith('/api/v1/reviews/profiles/p1/versions/v2')
})

test('Add sources opens under the Brain tab with the client from the link', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(() =>
      jsonResponse([{ id: 'c1', name: 'Plateau Basements', created_at: '' }]),
    ),
  )
  openAt('#/sources/new?client=c1')

  expect(screen.getByRole('heading', { name: 'Add sources' })).toBeInTheDocument()
  expect(activeTab()).toHaveTextContent('Brain')
  expect(await screen.findByRole('combobox', { name: 'Client' })).toHaveValue('c1')
})

test('a draft progress link (or a refresh) shows that job under the Brain tab', async () => {
  const fetchMock = vi.fn().mockImplementation((url: string) =>
    jsonResponse(
      url === '/api/v1/clients'
        ? [{ id: 'c1', name: 'Plateau Basements', created_at: '' }]
        : { id: 'j1', client_id: 'c1', status: 'running', attempts: 1, created_at: '' },
    ),
  )
  vi.stubGlobal('fetch', fetchMock)
  openAt('#/sources/draft?client=c1&job=j1')

  expect(await screen.findByRole('heading', { name: 'Drafting Plateau Basements' })).toBeVisible()
  expect(activeTab()).toHaveTextContent('Brain')
  expect(fetchMock).toHaveBeenCalledWith('/api/v1/clients/c1/onboarding-jobs/j1')
})

test('following New intake opens Add sources with no client chosen', async () => {
  openAt('#/')

  window.location.hash = '#/sources/new'
  window.dispatchEvent(new HashChangeEvent('hashchange'))

  expect(await screen.findByRole('heading', { name: 'Add sources' })).toBeInTheDocument()
  expect(screen.getByRole('combobox', { name: 'Client' })).toHaveValue('')
})

test('the status page is still reachable for developers', () => {
  openAt('#/status')

  expect(screen.getByRole('heading', { name: 'Status' })).toBeInTheDocument()
  expect(activeTab()).toBeNull()
})

test('an unknown address shows an empty Page not found', () => {
  openAt('#/nowhere')

  expect(screen.getByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
  expect(activeTab()).toBeNull()
})

// Answers /api/v1/reviews from the queue in order; anything else gets [].
function mockReviewReplies(...replies: Promise<Response>[]) {
  const fetchMock = vi.fn((url: string) =>
    url === '/api/v1/reviews' ? (replies.shift() ?? jsonResponse([])) : jsonResponse([]),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function navigate(hash: string) {
  act(() => {
    window.location.hash = hash
    window.dispatchEvent(new HashChangeEvent('hashchange'))
  })
}

async function settled(fetchMock: ReturnType<typeof vi.fn>, calls: number) {
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(calls))
  await act(async () => {})
}

test('the Reviews button shows how many drafts are waiting', async () => {
  mockReviewReplies(jsonResponse([{}, {}]))
  openAt('#/brain')

  const reviews = await screen.findByRole('link', { name: 'Reviews, 2 waiting' })
  expect(reviews).toHaveTextContent(/^Reviews2$/)
})

test('no badge when nothing is waiting', async () => {
  const fetchMock = mockReviewReplies(jsonResponse([]))
  openAt('#/brain')
  await settled(fetchMock, 1)

  expect(screen.getByRole('link', { name: 'Reviews' })).toHaveTextContent(/^Reviews$/)
})

test('no badge and no error when the count fails to load', async () => {
  const fetchMock = mockReviewReplies(
    Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) } as Response),
  )
  openAt('#/brain')
  await settled(fetchMock, 1)

  expect(screen.getByRole('link', { name: 'Reviews' })).toHaveTextContent(/^Reviews$/)
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

test('the count refreshes when the route changes', async () => {
  mockReviewReplies(jsonResponse([{}, {}]), jsonResponse([{}]))
  openAt('#/brain')
  expect(await screen.findByRole('link', { name: 'Reviews, 2 waiting' })).toBeInTheDocument()

  navigate('#/workforce')

  expect(await screen.findByRole('link', { name: 'Reviews, 1 waiting' })).toBeInTheDocument()
})

test('a late count from an earlier route is ignored', async () => {
  let answerFirst: (body: unknown) => void = () => {}
  const first = new Promise<Response>((resolve) => {
    answerFirst = (body) => resolve({ ok: true, json: () => Promise.resolve(body) } as Response)
  })
  mockReviewReplies(first, jsonResponse([{}]))
  openAt('#/brain')
  navigate('#/workforce')
  expect(await screen.findByRole('link', { name: 'Reviews, 1 waiting' })).toBeInTheDocument()

  await act(async () => answerFirst([{}, {}, {}]))

  expect(screen.getByRole('link', { name: 'Reviews, 1 waiting' })).toBeInTheDocument()
})

// Only the interval is faked, so React Testing Library's own waiting still works.
function fakeInterval() {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
}

function setHidden(hidden: boolean) {
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(hidden)
  act(() => {
    document.dispatchEvent(new Event('visibilitychange'))
  })
}

async function waitSeconds(seconds: number) {
  await act(async () => {
    vi.advanceTimersByTime(seconds * 1000)
  })
}

test('the count refreshes every 30 seconds while the page is visible', async () => {
  fakeInterval()
  mockReviewReplies(jsonResponse([{}]), jsonResponse([{}, {}]))
  openAt('#/brain')
  expect(await screen.findByRole('link', { name: 'Reviews, 1 waiting' })).toBeInTheDocument()

  await waitSeconds(30)

  expect(await screen.findByRole('link', { name: 'Reviews, 2 waiting' })).toBeInTheDocument()
})

test('no refresh while the tab is hidden', async () => {
  fakeInterval()
  const fetchMock = mockReviewReplies(jsonResponse([{}]))
  openAt('#/brain')
  await settled(fetchMock, 1)

  setHidden(true)
  await waitSeconds(90)

  expect(fetchMock).toHaveBeenCalledTimes(1)
})

test('the count refreshes as soon as the tab is shown again', async () => {
  const fetchMock = mockReviewReplies(jsonResponse([{}]), jsonResponse([{}, {}, {}]))
  openAt('#/brain')
  await settled(fetchMock, 1)
  setHidden(true)

  setHidden(false)

  expect(await screen.findByRole('link', { name: 'Reviews, 3 waiting' })).toBeInTheDocument()
  expect(fetchMock).toHaveBeenCalledTimes(2)
})

test('no refresh after the nav has closed', async () => {
  fakeInterval()
  const fetchMock = mockReviewReplies(jsonResponse([{}]))
  window.location.hash = '#/brain'
  const { unmount } = render(<App />)
  await settled(fetchMock, 1)

  unmount()
  await waitSeconds(30)
  setHidden(false)

  expect(fetchMock).toHaveBeenCalledTimes(1)
})
