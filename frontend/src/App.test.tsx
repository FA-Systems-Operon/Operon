
import { render, screen, within } from '@testing-library/react'
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

test('Reviews is an empty page and marks the Reviews link', async () => {
  openAt('#/reviews')

  expect(
    await screen.findByRole('heading', { name: 'Reviews' }),
  ).toBeInTheDocument()

  expect(screen.getByRole('link', { name: 'Reviews' })).toHaveAttribute(
    'aria-current',
    'page',
  )

  expect(activeTab()).toBeNull()
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

  expect(
    await screen.findByRole('combobox', { name: 'Client' }),
  ).toHaveValue('c1')
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
