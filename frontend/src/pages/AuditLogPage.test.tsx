import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import type { AuditEvent } from '../api'
import type { AuthUser } from '../auth'
import AuditLogPage, { actionLabel, describeObject, formatWhen } from './AuditLogPage'

const ADMIN: AuthUser = { id: 'u1', email: 'ada@example.test', display_name: 'Ada', role: 'admin' }

function event(overrides: Partial<AuditEvent>): AuditEvent {
  return {
    id: 'e1',
    created_at: '2026-11-09T14:03:05Z',
    action: 'approve',
    actor_id: 'u2',
    actor_name: 'Rita Reviewer',
    actor_email: 'rita@example.test',
    object_type: 'client_profile',
    object_id: 'p1234567-0000',
    version_id: 'v7654321-0000',
    client_id: 'c1',
    client_name: 'Plateau Basements',
    version_number: 3,
    document_filename: null,
    ...overrides,
  }
}

function reply(status: number, body: unknown) {
  return Promise.resolve({
    ok: status < 400,
    status,
    json: () => Promise.resolve(body),
  } as Response)
}

function mockFetch(...replies: Promise<Response>[]) {
  const fetchMock = vi.fn()
  for (const next of replies) fetchMock.mockReturnValueOnce(next)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  vi.unstubAllGlobals()
})

test('shows readable rows in the order the API returns', async () => {
  const fetchMock = mockFetch(
    reply(200, {
      items: [
        event({}),
        event({
          id: 'e2',
          action: 'upload',
          object_type: 'source_document',
          object_id: 'd1234567-0000',
          version_id: null,
          version_number: null,
          document_filename: 'call-notes.txt',
        }),
      ],
      next_cursor: null,
    }),
  )
  render(<AuditLogPage user={ADMIN} />)

  const rows = (await screen.findAllByRole('row')).slice(1)

  expect(fetchMock).toHaveBeenCalledWith('/api/v1/audit-events')
  expect(rows.map((row) => within(row).getAllByRole('cell').map((cell) => cell.textContent))).toEqual([
    [formatWhen('2026-11-09T14:03:05Z'), 'Rita Reviewer', 'Approved', 'Profile v3v7654321', 'Plateau Basements'],
    [formatWhen('2026-11-09T14:03:05Z'), 'Rita Reviewer', 'Uploaded', 'call-notes.txtd1234567', 'Plateau Basements'],
  ])
  expect(screen.queryByRole('button', { name: 'Load older events' })).not.toBeInTheDocument()
})

test('loads older events after the ones already shown', async () => {
  const fetchMock = mockFetch(
    reply(200, { items: [event({})], next_cursor: 'abc=' }),
    reply(200, { items: [event({ id: 'e2', action: 'reject' })], next_cursor: null }),
  )
  render(<AuditLogPage user={ADMIN} />)

  await userEvent.click(await screen.findByRole('button', { name: 'Load older events' }))

  expect(await screen.findByText('Rejected')).toBeInTheDocument()
  expect(screen.getByText('Approved')).toBeInTheDocument()
  expect(fetchMock).toHaveBeenLastCalledWith('/api/v1/audit-events?cursor=abc%3D')
  expect(screen.queryByRole('button', { name: 'Load older events' })).not.toBeInTheDocument()
})

test('shows a loading message, then an empty message', async () => {
  mockFetch(reply(200, { items: [], next_cursor: null }))
  render(<AuditLogPage user={ADMIN} />)

  expect(screen.getByRole('status')).toHaveTextContent('Loading audit events…')
  expect(await screen.findByText('No audit events recorded yet.')).toBeInTheDocument()
})

test('a failed load can be tried again', async () => {
  mockFetch(reply(500, {}), reply(200, { items: [event({})], next_cursor: null }))
  render(<AuditLogPage user={ADMIN} />)

  expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't load the audit log.")
  await userEvent.click(screen.getByRole('button', { name: 'Try again' }))

  expect(await screen.findByText('Approved')).toBeInTheDocument()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

test('a failed older page keeps the rows already shown and retries that page', async () => {
  const fetchMock = mockFetch(
    reply(200, { items: [event({})], next_cursor: 'abc' }),
    reply(500, {}),
    reply(200, { items: [event({ id: 'e2', action: 'edit' })], next_cursor: null }),
  )
  render(<AuditLogPage user={ADMIN} />)

  await userEvent.click(await screen.findByRole('button', { name: 'Load older events' }))
  expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't load the audit log.")
  expect(screen.getByText('Approved')).toBeInTheDocument()

  await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
  expect(await screen.findByText('Edited')).toBeInTheDocument()
  expect(fetchMock).toHaveBeenLastCalledWith('/api/v1/audit-events?cursor=abc')
})

test('a 403 says the log is admin only', async () => {
  mockFetch(reply(403, { detail: 'Your role cannot do this' }))
  render(<AuditLogPage user={ADMIN} />)

  expect(await screen.findByRole('alert')).toHaveTextContent('Only admins can view the audit log.')
})

test.each(['reviewer', 'viewer'] as const)('a %s is not shown the log and nothing is fetched', (role) => {
  const fetchMock = mockFetch()
  render(<AuditLogPage user={{ ...ADMIN, role }} />)

  expect(screen.getByRole('alert')).toHaveTextContent('Only admins can view the audit log.')
  expect(fetchMock).not.toHaveBeenCalled()
})

test('labels fall back to the raw value for unknown actions and objects', () => {
  expect(actionLabel('job_requeued')).toBe('Restarted draft')
  expect(actionLabel('something_new')).toBe('something_new')
  expect(describeObject(event({ object_type: 'onboarding_job' }))).toBe('Onboarding job')
  expect(describeObject(event({ version_number: null }))).toBe('Profile')
  expect(describeObject(event({ object_type: 'source_document', document_filename: null }))).toBe('Document')
  expect(describeObject(event({ object_type: 'playbook' }))).toBe('playbook')
})
