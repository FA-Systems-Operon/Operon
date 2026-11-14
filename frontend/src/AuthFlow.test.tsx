import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import App from './App'
import { safeNext } from './auth'

const invitee = {
  id: 'u1',
  email: 'nina@example.com',
  display_name: 'Nina',
  role: 'viewer',
}

function json(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
}

// A signed-out visitor: /api/v1/me answers 401, plus whatever routes the test adds.
function mockBackend(routes: Record<string, () => Response>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
    const url = String(input)
    if (url === '/api/v1/me') return json(401, { detail: 'Not authenticated' })
    const handler = routes[url]
    return handler ? handler() : json(200, [])
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function bodyOf(fetchMock: ReturnType<typeof mockBackend>, url: string) {
  const call = fetchMock.mock.calls.find(([called]) => String(called) === url)
  return call ? JSON.parse(String(call[1]?.body)) : undefined
}

afterEach(() => {
  vi.unstubAllGlobals()
  window.location.hash = ''
})

// --- login -----------------------------------------------------------------

test('login sends the visitor to the page they originally asked for', async () => {
  const fetchMock = mockBackend({
    '/api/v1/auth/login': () => json(200, { user: invitee, csrf_token: 'c' }),
  })
  const typing = userEvent.setup()
  window.location.hash = '#/login?next=%2Fbrain'
  render(<App />)

  await typing.type(screen.getByLabelText('Email address'), 'nina@example.com')
  await typing.type(screen.getByLabelText('Password'), 'a-long-password-123')
  await typing.click(screen.getByRole('button', { name: 'Sign in' }))

  // Reaching Brain also proves the app now knows the visitor is signed in.
  expect(await screen.findByRole('heading', { name: 'Brain' })).toBeInTheDocument()
  expect(window.location.hash).toBe('#/brain')
  expect(bodyOf(fetchMock, '/api/v1/auth/login')).toEqual({
    email: 'nina@example.com',
    password: 'a-long-password-123',
  })
})

test('login shows the server message when the password is wrong', async () => {
  mockBackend({
    '/api/v1/auth/login': () => json(401, { detail: 'Invalid email or password' }),
  })
  const typing = userEvent.setup()
  window.location.hash = '#/login'
  render(<App />)

  await typing.type(screen.getByLabelText('Email address'), 'nina@example.com')
  await typing.type(screen.getByLabelText('Password'), 'wrong-password-123')
  await typing.click(screen.getByRole('button', { name: 'Sign in' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password')
  expect(window.location.hash).toBe('#/login')
})

test('login tells the visitor how long the lockout lasts', async () => {
  mockBackend({
    '/api/v1/auth/login': () =>
      json(429, { detail: 'Too many failed login attempts' }, { 'Retry-After': '600' }),
  })
  const typing = userEvent.setup()
  window.location.hash = '#/login'
  render(<App />)

  await typing.type(screen.getByLabelText('Email address'), 'nina@example.com')
  await typing.type(screen.getByLabelText('Password'), 'wrong-password-123')
  await typing.click(screen.getByRole('button', { name: 'Sign in' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Try again in 10 minutes.')
})

test('safeNext only allows paths inside the app', () => {
  expect(safeNext('/brain')).toBe('/brain')
  expect(safeNext('/sources/new?client=c1')).toBe('/sources/new?client=c1')
  expect(safeNext('//evil.example')).toBe('/')
  expect(safeNext('https://evil.example')).toBe('/')
  expect(safeNext(null)).toBe('/')
})

// --- accept invitation -----------------------------------------------------

async function fillInviteForm(password = 'a-long-password-123') {
  const typing = userEvent.setup()
  await typing.type(screen.getByLabelText('Your name'), 'Nina')
  await typing.type(screen.getByLabelText('Password'), password)
  await typing.type(screen.getByLabelText('Confirm password'), password)
  await typing.click(screen.getByRole('button', { name: 'Create account' }))
}

test('accepting an invitation creates the account, then signs the user in', async () => {
  const fetchMock = mockBackend({
    // The backend only creates the account here...
    '/api/v1/auth/accept-invite': () => json(201, invitee),
    // ...so the page signs in with the same email and password.
    '/api/v1/auth/login': () => json(200, { user: invitee, csrf_token: 'c' }),
  })
  window.location.hash = '#/accept-invite?token=abc123'
  render(<App />)

  await fillInviteForm()

  await waitFor(() => expect(window.location.hash).toBe('#/'))
  expect(bodyOf(fetchMock, '/api/v1/auth/accept-invite')).toEqual({
    token: 'abc123',
    display_name: 'Nina',
    password: 'a-long-password-123',
  })
  expect(bodyOf(fetchMock, '/api/v1/auth/login')).toEqual({
    email: 'nina@example.com',
    password: 'a-long-password-123',
  })
  expect(await screen.findByRole('button', { name: 'Log out' })).toBeInTheDocument()
})

test('if sign-in fails after the account is created, the user is told to sign in', async () => {
  mockBackend({
    '/api/v1/auth/accept-invite': () => json(201, invitee),
    '/api/v1/auth/login': () => json(500, { detail: 'boom' }),
  })
  window.location.hash = '#/accept-invite?token=abc123'
  render(<App />)

  await fillInviteForm()

  expect(await screen.findByRole('alert')).toHaveTextContent('Your account is ready')
})

test('a password shorter than the backend minimum never reaches the server', async () => {
  const fetchMock = mockBackend({})
  window.location.hash = '#/accept-invite?token=abc123'
  render(<App />)

  await fillInviteForm('short-pass')

  expect(await screen.findByRole('alert')).toHaveTextContent('at least 12 characters')
  expect(
    fetchMock.mock.calls.some(([url]) => String(url) === '/api/v1/auth/accept-invite'),
  ).toBe(false)
})

test('a used or expired invitation shows the server message', async () => {
  mockBackend({
    '/api/v1/auth/accept-invite': () =>
      json(400, { detail: 'This invitation is invalid or has expired' }),
  })
  window.location.hash = '#/accept-invite?token=used-token'
  render(<App />)

  await fillInviteForm()

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'This invitation is invalid or has expired',
  )
  expect(window.location.hash).toBe('#/accept-invite?token=used-token')
})

test('an invitation link without a token cannot be submitted', () => {
  mockBackend({})
  window.location.hash = '#/accept-invite'
  render(<App />)

  expect(screen.getByRole('button', { name: 'Create account' })).toBeDisabled()
  expect(screen.getByText('This invitation link is invalid or incomplete.')).toBeInTheDocument()
})
