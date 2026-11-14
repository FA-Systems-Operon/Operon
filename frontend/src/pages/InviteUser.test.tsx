import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import App from '../App'

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

// A signed-in user with the given role, plus whatever routes the test adds.
function mockSignedIn(role: 'admin' | 'reviewer', routes: Record<string, () => Response> = {}) {
  const me = { id: 'u1', email: 'a@example.com', display_name: 'A', role }
  const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
    const url = String(input)
    if (url === '/api/v1/me') return json(200, me)
    const handler = routes[url]
    return handler ? handler() : json(200, [])
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const invite = {
  id: 'i1',
  email: 'nina@example.com',
  role: 'viewer',
  expires_at: '2026-11-14T12:00:00Z',
  invite_token: 'tok_abc-123',
}

afterEach(() => {
  vi.unstubAllGlobals()
  window.location.hash = ''
})

test('an admin creates an invite link and sees it once', async () => {
  document.cookie = 'operon_csrf=test-csrf-token'
  const fetchMock = mockSignedIn('admin', {
    '/api/v1/users/invite': () => json(201, invite),
  })
  const typing = userEvent.setup()
  window.location.hash = '#/invite'
  render(<App />)

  await typing.type(await screen.findByLabelText('Email address'), 'nina@example.com')
  await typing.click(screen.getByRole('button', { name: 'Create invite link' }))

  const link = (await screen.findByLabelText('Invitation link')) as HTMLInputElement
  expect(link.value).toBe(`${window.location.origin}/#/accept-invite?token=tok_abc-123`)

  // Generic invite: only the email is sent, with the CSRF header the backend requires.
  const call = fetchMock.mock.calls.find(([url]) => String(url) === '/api/v1/users/invite')
  expect(JSON.parse(String(call?.[1]?.body))).toEqual({ email: 'nina@example.com' })
  expect(call?.[1]?.headers).toMatchObject({ 'X-CSRF-Token': 'test-csrf-token' })
})

test('the invite page shows the backend message for an existing account', async () => {
  mockSignedIn('admin', {
    '/api/v1/users/invite': () =>
      json(409, { detail: 'An account with that email already exists' }),
  })
  const typing = userEvent.setup()
  window.location.hash = '#/invite'
  render(<App />)

  await typing.type(await screen.findByLabelText('Email address'), 'nina@example.com')
  await typing.click(screen.getByRole('button', { name: 'Create invite link' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'An account with that email already exists',
  )
  expect(screen.queryByLabelText('Invitation link')).not.toBeInTheDocument()
})

test('an invalid email is caught before any request', async () => {
  const fetchMock = mockSignedIn('admin')
  const typing = userEvent.setup()
  window.location.hash = '#/invite'
  render(<App />)

  await typing.type(await screen.findByLabelText('Email address'), 'not-an-email')
  await typing.click(screen.getByRole('button', { name: 'Create invite link' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Enter a valid email address.')
  expect(
    fetchMock.mock.calls.some(([url]) => String(url) === '/api/v1/users/invite'),
  ).toBe(false)
})

test('people who are not admins do not get the invite form or the nav link', async () => {
  mockSignedIn('reviewer')
  window.location.hash = '#/invite'
  render(<App />)

  expect(await screen.findByRole('alert')).toHaveTextContent('Only admins can invite people.')
  expect(screen.queryByLabelText('Email address')).not.toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Invite' })).not.toBeInTheDocument()
})

test('admins get an Invite link in the top bar', async () => {
  mockSignedIn('admin')
  window.location.hash = '#/brain'
  render(<App />)

  expect(await screen.findByRole('link', { name: 'Invite' })).toHaveAttribute('href', '#/invite')
})
