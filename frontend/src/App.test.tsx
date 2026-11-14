import { act, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import App from './App'

// Synthetic user for testing only.
const mockUser = {
  id: 'test-user',
  email: 'staff@example.com',
  role: 'staff',
}

function jsonResponse(body: unknown) {
  return Promise.resolve({
    ok: true,
    status: 200,
    json: () => Promise.resolve(body),
  } as Response)
}

beforeEach(() => {
  // Return an authenticated user for session checks.
  // Keep the existing empty-array response for other API calls.
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input)

      if (url === '/api/v1/me') {
        return jsonResponse(mockUser)
      }

      return jsonResponse([])
    }),
  )
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

test('opens on Command with the New intake entry point', async () => {
  openAt('')

  expect(
    await screen.findByRole('heading', { name: 'Command' }),
  ).toBeInTheDocument()

  expect(activeTab()).toHaveTextContent('Command')

  expect(screen.getByRole('link', { name: 'New intake' })).toHaveAttribute(
    'href',
    '#/sources/new',
  )
})

test('shows every menu item with its link', async () => {
  openAt('#/')

  const menu = within(
    await screen.findByRole('navigation', { name: 'Main' }),
  )

  expect(menu.getByRole('link', { name: 'Command' })).toHaveAttribute(
    'href',
    '#/',
  )

  expect(menu.getByRole('link', { name: 'Brain' })).toHaveAttribute(
    'href',
    '#/brain',
  )

  expect(menu.getByRole('link', { name: 'Workforce' })).toHaveAttribute(
    'href',
    '#/workforce',
  )

  expect(screen.getByRole('link', { name: 'Reviews' })).toHaveAttribute(
    'href',
    '#/reviews',
  )

  expect(screen.getByRole('link', { name: 'Operon' })).toHaveAttribute(
    'href',
    '#/',
  )
})

test.each([
  ['#/brain', 'Brain'],
  ['#/workforce', 'Workforce'],
])('%s is an empty page with its tab marked', async (hash, title) => {
  openAt(hash)

  expect(
    await screen.findByRole('heading', { name: title }),
  ).toBeInTheDocument()

  expect(activeTab()).toHaveTextContent(title)

  // The only text is the title kept for screen readers.
  expect(screen.getByRole('main').textContent).toBe(title)
})

test('Reviews opens the review inbox and marks the Reviews link', async () => {
  openAt('#/reviews')

  expect(
    await screen.findByRole('heading', { name: 'Review inbox' }),
  ).toBeInTheDocument()

  expect(screen.getByRole('link', { name: 'Reviews' })).toHaveAttribute(
    'aria-current',
    'page',
  )

  expect(activeTab()).toBeNull()

  expect(
    await screen.findByText('No drafts waiting for review.'),
  ).toBeInTheDocument()
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
    vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input)

      if (url === '/api/v1/me') {
        return jsonResponse(mockUser)
      }

      return jsonResponse([
        {
          id: 'c1',
          name: 'Plateau Basements',
          created_at: '',
        },
      ])
    }),
  )

  openAt('#/sources/new?client=c1')

  expect(
    await screen.findByRole('heading', { name: 'Add sources' }),
  ).toBeInTheDocument()

  expect(activeTab()).toHaveTextContent('Brain')

  await waitFor(() => {
  expect(
    screen.getByRole('combobox', { name: 'Client' }),
  ).toHaveValue('c1')
  })
})

test('following New intake opens Add sources with no client chosen', async () => {
  openAt('#/')

  await screen.findByRole('heading', { name: 'Command' })

  window.location.hash = '#/sources/new'
  window.dispatchEvent(new HashChangeEvent('hashchange'))

  expect(
    await screen.findByRole('heading', { name: 'Add sources' }),
  ).toBeInTheDocument()

  expect(
    await screen.findByRole('combobox', { name: 'Client' }),
  ).toHaveValue('')
})

test('the status page is still reachable for developers', async () => {
  openAt('#/status')

  expect(
    await screen.findByRole('heading', { name: 'Status' }),
  ).toBeInTheDocument()

  expect(activeTab()).toBeNull()
})

test('an unknown address shows an empty Page not found', async () => {
  openAt('#/nowhere')

  expect(
    await screen.findByRole('heading', { name: 'Page not found' }),
  ).toBeInTheDocument()

  expect(activeTab()).toBeNull()
})

// Answers /api/v1/reviews from the queue in order; anything else gets [].
function mockReviewReplies(...replies: Promise<Response>[]) {
  const fetchMock = vi.fn((url: string) => {
    if (url === '/api/v1/me') {
      return jsonResponse(mockUser)
    }

    if (url === '/api/v1/reviews') {
      return replies.shift() ?? jsonResponse([])
    }

    return jsonResponse([])
  })

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
  await waitFor(() =>
    expect(
      fetchMock.mock.calls.filter(([url]) => url === '/api/v1/reviews'),
    ).toHaveLength(calls),
  )
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
    answerFirst = (body) =>
      resolve({
        ok: true,
        json: () => Promise.resolve(body),
      } as Response)
  })

  const fetchMock = mockReviewReplies(first, jsonResponse([{}]))

  openAt('#/brain')

  // Wait until authentication finishes and the first Reviews request starts.
  await screen.findByRole('link', { name: 'Reviews' })

  await waitFor(() =>
    expect(
      fetchMock.mock.calls.filter(([url]) => url === '/api/v1/reviews'),
    ).toHaveLength(1),
  )

  // Now navigate so the second request starts.
  navigate('#/workforce')

  expect(
    await screen.findByRole('link', { name: 'Reviews, 1 waiting' }),
  ).toBeInTheDocument()

  // The older request finishes last and must not overwrite the newer count.
  await act(async () => {
    answerFirst([{}, {}, {}])
  })

  expect(
    screen.getByRole('link', { name: 'Reviews, 1 waiting' }),
  ).toBeInTheDocument()
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

  expect(
  fetchMock.mock.calls.filter(([url]) => url === '/api/v1/reviews'),
).toHaveLength(1)
})

test('the count refreshes as soon as the tab is shown again', async () => {
  const fetchMock = mockReviewReplies(jsonResponse([{}]), jsonResponse([{}, {}, {}]))
  openAt('#/brain')
  await settled(fetchMock, 1)
  setHidden(true)

  setHidden(false)

  expect(await screen.findByRole('link', { name: 'Reviews, 3 waiting' })).toBeInTheDocument()
  expect(
  fetchMock.mock.calls.filter(([url]) => url === '/api/v1/reviews'),
).toHaveLength(2)
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

 expect(
  fetchMock.mock.calls.filter(([url]) => url === '/api/v1/reviews'),
).toHaveLength(1)
})
