
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import App from './App'

const mockUser = {
  id: 'test-user',
  email: 'staff@example.com',
  display_name: 'Test User',
  role: 'reviewer',
}

function mockSession(status: 'authenticated' | 'unauthenticated' | 'error') {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      if (String(input) !== '/api/v1/me') {
        return {
          ok: true,
          status: 200,
          json: async () => [],
        } as Response
      }

      if (status === 'error') {
        throw new Error('Network unavailable')
      }

      if (status === 'unauthenticated') {
        return {
          ok: false,
          status: 401,
          json: async () => ({ detail: 'Not authenticated' }),
        } as Response
      }

      return {
        ok: true,
        status: 200,
        json: async () => mockUser,
      } as Response
    }),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
  window.location.hash = ''
})

test('redirects signed-out visitors to login', async () => {
  mockSession('unauthenticated')
  window.location.hash = '#/brain'

  render(<App />)

  await waitFor(() => {
    expect(window.location.hash).toBe('#/login?next=%2Fbrain')
  })

  expect(
    await screen.findByRole('heading', { name: 'Welcome back' }),
  ).toBeInTheDocument()

  expect(screen.queryByRole('heading', { name: 'Brain' }))
    .not.toBeInTheDocument()
})

test('shows protected pages for authenticated users', async () => {
  mockSession('authenticated')
  window.location.hash = '#/brain'

  render(<App />)

  expect(
    await screen.findByRole('heading', { name: 'Brain' }),
  ).toBeInTheDocument()
})

test('does not expose protected content during session checking', () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => new Promise(() => {})),
  )

  window.location.hash = '#/reviews'
  render(<App />)

  expect(screen.getByText('Checking your session...'))
    .toBeInTheDocument()

  expect(screen.queryByRole('heading', { name: 'Reviews' }))
    .not.toBeInTheDocument()
})

test('shows an error if the session cannot be verified', async () => {
  mockSession('error')
  window.location.hash = '#/brain'

  render(<App />)

  expect(
    await screen.findByRole('heading', { name: 'Connection problem' }),
  ).toBeInTheDocument()

  expect(screen.queryByRole('heading', { name: 'Brain' }))
    .not.toBeInTheDocument()
})

test('allows access to login without authentication', async () => {
  mockSession('unauthenticated')
  window.location.hash = '#/login'

  render(<App />)

  expect(
    screen.getByRole('heading', { name: 'Welcome back' }),
  ).toBeInTheDocument()

  expect(screen.queryByRole('navigation', { name: 'Main' }))
    .not.toBeInTheDocument()
})

test('preserves query parameters when redirecting', async () => {
  mockSession('unauthenticated')
  window.location.hash = '#/sources/new?client=c1'

  render(<App />)

  await waitFor(() => {
    expect(window.location.hash).toBe(
      '#/login?next=%2Fsources%2Fnew%3Fclient%3Dc1',
    )
  })
})

test('successful login clears a previous session error', async () => {
  let resolveSession!: (response: Response) => void

  const sessionRequest = new Promise<Response>((resolve) => {
    resolveSession = resolve
  })

  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)

      if (url === '/api/v1/me') {
        return sessionRequest
      }

      if (url === '/api/v1/auth/login') {
        return new Response(
          JSON.stringify({
            user: {
              id: 'test-user',
              email: 'staff@example.com',
              display_name: 'Test User',
              role: 'reviewer',
            },
          }),
          {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          },
        )
      }

      return new Response('[]', { status: 200 })
    }),
  )

  window.location.hash = '#/login'
  render(<App />)

  // The session check fails after the login screen is displayed.
  await act(async () => {
    resolveSession(new Response(null, { status: 500 }))
  })

  const user = userEvent.setup()

  await user.type(
    screen.getByLabelText('Email address'),
    'staff@example.com',
  )

  await user.type(
    screen.getByLabelText('Password'),
    'test-password-123',
  )

  await user.click(screen.getByRole('button', { name: 'Sign in' }))

  await waitFor(() => {
    expect(window.location.hash).toBe('#/')
  })

  expect(
    await screen.findByRole('button', { name: 'Log out' }),
  ).toBeInTheDocument()

  expect(
    screen.queryByText('Connection problem'),
  ).not.toBeInTheDocument()
})

test('a late session check cannot override a successful login', async () => {
  let resolveSession!: (response: Response) => void

  const sessionRequest = new Promise<Response>((resolve) => {
    resolveSession = resolve
  })

  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)

      if (url === '/api/v1/me') {
        return sessionRequest
      }

      if (url === '/api/v1/auth/login') {
        return new Response(
          JSON.stringify({ user: mockUser }),
          {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          },
        )
      }

      return new Response('[]', { status: 200 })
    }),
  )

  window.location.hash = '#/login'
  render(<App />)

  const user = userEvent.setup()

  await user.type(
    screen.getByLabelText('Email address'),
    'staff@example.com',
  )

  await user.type(
    screen.getByLabelText('Password'),
    'test-password-123',
  )

  await user.click(screen.getByRole('button', { name: 'Sign in' }))

  expect(
    await screen.findByRole('button', { name: 'Log out' }),
  ).toBeInTheDocument()

  // The original session check finishes AFTER successful login.
  await act(async () => {
    resolveSession(new Response(null, { status: 401 }))
  })

  // The older 401 must not sign the user out.
  expect(window.location.hash).toBe('#/')

  expect(
    screen.getByRole('button', { name: 'Log out' }),
  ).toBeInTheDocument()

  expect(
    screen.queryByRole('heading', { name: 'Welcome back' }),
  ).not.toBeInTheDocument()
})
