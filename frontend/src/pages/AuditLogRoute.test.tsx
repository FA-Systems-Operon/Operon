import { render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import App from '../App'

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

// A signed-in user with the given role. The audit log has one event.
function mockSignedIn(role: 'admin' | 'reviewer' | 'viewer') {
  const me = { id: 'u1', email: 'a@example.com', display_name: 'A', role }
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url === '/api/v1/me') return json(200, me)
    if (url === '/api/v1/audit-events') {
      return json(200, {
        items: [
          {
            id: 'e1',
            created_at: '2026-11-09T14:03:05Z',
            action: 'reject',
            actor_id: 'u2',
            actor_name: 'Rita Reviewer',
            actor_email: 'rita@example.test',
            object_type: 'client_profile',
            object_id: 'p1',
            version_id: 'v1',
            client_id: 'c1',
            client_name: 'Plateau Basements',
            version_number: 2,
            document_filename: null,
          },
        ],
        next_cursor: null,
      })
    }
    return json(200, [])
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  vi.unstubAllGlobals()
  window.location.hash = ''
})

test('admins get an Audit log link that opens the log', async () => {
  mockSignedIn('admin')
  window.location.hash = '#/audit'
  render(<App />)

  const link = await screen.findByRole('link', { name: 'Audit log' })
  expect(link).toHaveAttribute('href', '#/audit')
  expect(link).toHaveAttribute('aria-current', 'page')
  expect(screen.getByRole('heading', { name: 'Audit log' })).toBeInTheDocument()
  expect(await screen.findByText('Rita Reviewer')).toBeInTheDocument()
})

test.each(['reviewer', 'viewer'] as const)(
  'a %s gets no link, no log and no request for it',
  async (role) => {
    const fetchMock = mockSignedIn(role)
    window.location.hash = '#/audit'
    render(<App />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Only admins can view the audit log.')
    expect(screen.queryByRole('link', { name: 'Audit log' })).not.toBeInTheDocument()
    expect(fetchMock.mock.calls.map(([url]) => String(url))).not.toContain('/api/v1/audit-events')
  },
)
