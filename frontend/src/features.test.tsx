import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import App from './App'
import { isEnabled, isHiddenPage } from './features'

// Synthetic user for testing only.
const mockUser = { id: 'test-user', email: 'staff@example.com', role: 'staff' }

function jsonResponse(body: unknown) {
  return Promise.resolve({
    ok: true,
    status: 200,
    json: () => Promise.resolve(body),
  } as Response)
}

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((input: RequestInfo | URL) =>
      jsonResponse(String(input) === '/api/v1/me' ? mockUser : []),
    ),
  )
  // setupTests turns every flag on; these tests start from the Release 1 default.
  vi.stubEnv('FEATURE_BRAIN', 'false')
  vi.stubEnv('FEATURE_WORKFORCE', 'false')
})

afterEach(() => {
  vi.unstubAllGlobals()
  window.location.hash = ''
})

function openAt(hash: string) {
  window.location.hash = hash
  render(<App />)
}

async function menu() {
  return within(await screen.findByRole('navigation', { name: 'Main' }))
}

function activeTab() {
  const nav = screen.getByRole('navigation', { name: 'Main' })
  return within(nav).queryByRole('link', { current: 'page' })
}

test.each([
  ['true', true],
  ['false', false],
  ['', false],
  ['TRUE', false],
  ['1', false],
])('FEATURE_BRAIN=%j is on: %s', (value, on) => {
  vi.stubEnv('FEATURE_BRAIN', value)
  expect(isEnabled('brain')).toBe(on)
})

test('a flag that is not set at all is off', () => {
  vi.stubEnv('FEATURE_WORKFORCE', undefined)
  expect(isEnabled('workforce')).toBe(false)
})

test('only the page of a flag that is off is hidden', () => {
  vi.stubEnv('FEATURE_WORKFORCE', 'true')

  expect(isHiddenPage('/brain')).toBe(true)
  expect(isHiddenPage('/workforce')).toBe(false)
  expect(isHiddenPage('/')).toBe(false)
  expect(isHiddenPage('/sources/new')).toBe(false)
})

test('with both flags off the menu has only Command and Reviews', async () => {
  openAt('#/')
  const nav = await menu()

  expect(nav.getByRole('link', { name: 'Command' })).toBeInTheDocument()
  expect(nav.queryByRole('link', { name: 'Brain' })).not.toBeInTheDocument()
  expect(nav.queryByRole('link', { name: 'Workforce' })).not.toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Reviews' })).toBeInTheDocument()
})

test('each flag shows only its own tab', async () => {
  vi.stubEnv('FEATURE_WORKFORCE', 'true')
  openAt('#/')
  const nav = await menu()

  expect(nav.queryByRole('link', { name: 'Brain' })).not.toBeInTheDocument()
  expect(nav.getByRole('link', { name: 'Workforce' })).toHaveAttribute('href', '#/workforce')
})

test.each([
  ['#/brain', 'Brain'],
  ['#/workforce', 'Workforce'],
])('opening hidden %s shows Command instead of a blank page', async (hash, title) => {
  openAt(hash)

  expect(await screen.findByRole('heading', { name: 'Command' })).toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: title })).not.toBeInTheDocument()
  expect(window.location.hash).toBe('#/')
  expect(activeTab()).toHaveTextContent('Command')
})

test('with Brain hidden, Add sources still opens and marks Command', async () => {
  openAt('#/sources/new')

  expect(await screen.findByRole('button', { name: 'Upload and draft' })).toBeInTheDocument()
  expect(window.location.hash).toBe('#/sources/new')
  expect(activeTab()).toHaveTextContent('Command')
})

test('with Brain hidden, draft progress still opens and marks Command', async () => {
  openAt('#/sources/draft?client=c1&job=j1')

  await menu()
  expect(window.location.hash).toBe('#/sources/draft?client=c1&job=j1')
  expect(activeTab()).toHaveTextContent('Command')
})

test('with Brain on, the pages come back as before', async () => {
  vi.stubEnv('FEATURE_BRAIN', 'true')
  openAt('#/sources/new')

  const nav = await menu()
  expect(nav.getByRole('link', { name: 'Brain' })).toHaveAttribute('aria-current', 'page')
})

// --- signed out: the login redirect and the hidden-page redirect together ------

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

// A signed-out visitor: /api/v1/me answers 401, and login succeeds.
function signedOut() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/v1/me') return json(401, { detail: 'Not authenticated' })
      if (url === '/api/v1/auth/login') return json(200, { user: mockUser, csrf_token: 'c' })
      return json(200, [])
    }),
  )
}

test.each([
  ['#/brain', 'Brain'],
  ['#/workforce', 'Workforce'],
])('signed out, hidden %s goes to login and comes back to Command', async (hash, title) => {
  signedOut()
  openAt(hash)

  // The hidden page isn't kept as the place to return to after login.
  await waitFor(() => expect(window.location.hash).toBe('#/login?next=%2F'))
  expect(screen.queryByRole('heading', { name: title })).not.toBeInTheDocument()

  const typing = userEvent.setup()
  await typing.type(screen.getByLabelText('Email address'), 'staff@example.com')
  await typing.type(screen.getByLabelText('Password'), 'a-long-password-123')
  await typing.click(screen.getByRole('button', { name: 'Sign in' }))

  expect(await screen.findByRole('heading', { name: 'Command' })).toBeInTheDocument()
  expect(window.location.hash).toBe('#/')
  expect(screen.queryByRole('heading', { name: title })).not.toBeInTheDocument()
})

test('a login link that returns to a hidden page lands on Command instead', async () => {
  signedOut()
  openAt('#/login?next=%2Fbrain')

  const typing = userEvent.setup()
  await typing.type(screen.getByLabelText('Email address'), 'staff@example.com')
  await typing.type(screen.getByLabelText('Password'), 'a-long-password-123')
  await typing.click(screen.getByRole('button', { name: 'Sign in' }))

  expect(await screen.findByRole('heading', { name: 'Command' })).toBeInTheDocument()
  expect(window.location.hash).toBe('#/')
  expect(screen.queryByRole('heading', { name: 'Brain' })).not.toBeInTheDocument()
})
