import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import App from '../App'
import responses from '../../../tests/fixtures/review_inbox/responses.json'
import { reviewDraftHref, useRoute } from '../router'

const { draft } = responses
const baseUrl = `/api/v1/reviews/profiles/${draft.version.client_profile_id}/versions/`

function reply(status: number, body: unknown) {
  return { ok: status < 400, status, json: async () => body } as Response
}

function mockApi(handleDraft: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/api/v1/me') return reply(200, { id: 'reviewer', role: 'reviewer', email: 'reviewer@example.test' })
    if (url === '/api/v1/reviews') return reply(200, [])
    return handleDraft(url, init)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function navigate(versionId: string) {
  act(() => {
    window.history.replaceState(null, '', reviewDraftHref(draft.version.client_profile_id, versionId))
    window.dispatchEvent(new HashChangeEvent('hashchange'))
  })
}

async function editName(name: string) {
  await userEvent.click(await screen.findByRole('button', { name: 'Edit Name' }))
  await userEvent.clear(screen.getByRole('textbox', { name: 'Name' }))
  await userEvent.type(screen.getByRole('textbox', { name: 'Name' }), `${name}{Enter}`)
}

function RouteStateProbe() {
  return <p data-testid="route-version">{useRoute().query.get('version')}</p>
}

afterEach(() => {
  vi.unstubAllGlobals()
  window.history.replaceState(null, '', '#')
})

test('the app confirms saves without fetching again, uses the saved base and reloads on reopen', async () => {
  const saved = {
    ...draft.version, id: 'saved-v3', version_number: 3,
    data: { ...draft.version.data, name: 'Reviewer correction' },
  }
  const next = { ...saved, id: 'saved-v4', version_number: 4, data: { ...saved.data, name: 'Second correction' } }
  let reopening = false
  const fetchMock = mockApi((url, init) => {
    if (url === `${baseUrl}${draft.version.id}`) return reply(200, draft)
    if (url === `${baseUrl}${draft.version.id}/edits` && init?.method === 'POST') return reply(201, saved)
    if (url === `${baseUrl}${saved.id}/edits` && init?.method === 'POST') return reply(201, next)
    if (url === `${baseUrl}${next.id}` && reopening) return reply(200, { ...draft, version: next })
    // Reads are unavailable during saving; successful POST replies are sufficient.
    throw new TypeError('Failed to fetch')
  })
  window.history.replaceState(null, '', reviewDraftHref(draft.version.client_profile_id, draft.version.id))
  const view = render(<><App /><RouteStateProbe /></>)
  await editName('Reviewer correction')
  await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))
  await screen.findByText('Version 3')
  expect(window.location.hash).toBe(reviewDraftHref(saved.client_profile_id, saved.id))
  // Save must notify the router itself; injecting an event here masks stale state.
  expect(screen.getByTestId('route-version')).toHaveTextContent(saved.id)
  expect(await screen.findByRole('button', { name: 'Edit Name' })).toHaveTextContent('Reviewer correction')
  expect(screen.getByText('Draft edits saved.')).toBeInTheDocument()
  expect(fetchMock).not.toHaveBeenCalledWith(`${baseUrl}${saved.id}`)
  expect(screen.queryByText('Loading draft…')).not.toBeInTheDocument()

  await editName('Second correction')
  await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))
  await screen.findByText('Version 4')
  expect(screen.getByText('Draft edits saved.')).toBeInTheDocument()
  expect(screen.getByTestId('route-version')).toHaveTextContent(next.id)
  expect(window.location.hash).toBe(reviewDraftHref(next.client_profile_id, next.id))
  expect(fetchMock).toHaveBeenCalledWith(`${baseUrl}${saved.id}/edits`, expect.objectContaining({
    method: 'POST', body: JSON.stringify({ changes: { name: 'Second correction' } }),
  }))
  expect(fetchMock).not.toHaveBeenCalledWith(`${baseUrl}${next.id}`)

  navigate(draft.version.id)
  expect(await screen.findByRole('button', { name: 'Edit Name' })).toHaveTextContent(draft.version.data.name)
  expect(screen.getByText(`Version ${draft.version.version_number}`)).toBeInTheDocument()
  expect(screen.queryByText('Draft edits saved.')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled()

  reopening = true
  navigate(next.id)
  expect(await screen.findByRole('button', { name: 'Edit Name' })).toHaveTextContent('Second correction')
  view.unmount()
  render(<App />)
  expect(await screen.findByRole('button', { name: 'Edit Name' })).toHaveTextContent('Second correction')
  expect(fetchMock.mock.calls.filter(([url]) => url === `${baseUrl}${next.id}`)).toHaveLength(2)
  expect(screen.queryByText('Draft edits saved.')).not.toBeInTheDocument()
})

test.each([404, 500])('opening another version clears a previous %s load error', async (status) => {
  mockApi((url) => url === `${baseUrl}${draft.version.id}` ? reply(200, draft) : reply(status, {}))
  window.history.replaceState(null, '', reviewDraftHref(draft.version.client_profile_id, 'unavailable'))
  render(<App />)
  if (status === 404) await screen.findByText(/This draft wasn't found/)
  else await screen.findByRole('alert')

  navigate(draft.version.id)
  expect(await screen.findByRole('button', { name: 'Edit Name' })).toHaveTextContent(draft.version.data.name)
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  expect(screen.queryByText(/This draft wasn't found/)).not.toBeInTheDocument()
})

test('a save completed after navigating to another version does not replace that version', async () => {
  const other = { ...draft.version, id: 'other-version', version_number: 2 }
  let finish!: (response: Response) => void
  mockApi((url, init) => {
    if (init?.method === 'POST') return new Promise((resolve) => { finish = resolve })
    return reply(200, url === `${baseUrl}${other.id}` ? { ...draft, version: other } : draft)
  })
  window.history.replaceState(null, '', reviewDraftHref(draft.version.client_profile_id, draft.version.id))
  render(<App />)
  await editName('Reviewer correction')
  await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))
  navigate(other.id)
  await screen.findByText('Version 2')

  await act(async () => finish(reply(201, { ...other, id: 'late-save', version_number: 3 })))
  expect(window.location.hash).toBe(reviewDraftHref(other.client_profile_id, other.id))
  expect(screen.getByText('Version 2')).toBeInTheDocument()
  expect(screen.queryByText('Draft edits saved.')).not.toBeInTheDocument()
})
