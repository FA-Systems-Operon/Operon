
import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import App from './App'

const mockUser = {
  id: 'test-user',
  email: 'staff@example.com',
  role: 'staff',
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
