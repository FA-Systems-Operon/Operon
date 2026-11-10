import { render, screen, within } from '@testing-library/react'
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

test('a draft link from the inbox opens a placeholder under Reviews', () => {
  openAt('#/reviews/draft?profile=p1&version=v2')

  expect(screen.getByRole('heading', { name: 'Draft review' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Reviews' })).toHaveAttribute('aria-current', 'page')
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
