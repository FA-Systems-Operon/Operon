import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import App from '../App'
import responses from '../../../tests/fixtures/review_inbox/responses.json'
import { reviewDraftHref, useRoute } from '../router'

function RouteStateProbe() {
  return <p data-testid="route-version">{useRoute().query.get('version')}</p>
}

afterEach(() => {
  vi.unstubAllGlobals()
  window.history.replaceState(null, '', '#')
})

test('the app keeps the saved version when its route changes and reloads it on reopen', async () => {
  const { draft } = responses
  const saved = {
    ...draft.version, id: 'saved-v3', version_number: 3,
    data: { ...draft.version.data, name: 'Reviewer correction', assessment: null },
  }
  const baseUrl = `/api/v1/reviews/profiles/${draft.version.client_profile_id}/versions/`
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    let body: unknown
    if (url === '/api/v1/me') body = { id: 'reviewer', role: 'reviewer', email: 'reviewer@example.test' }
    else if (url === '/api/v1/reviews') body = []
    else if (url === `${baseUrl}${draft.version.id}`) body = draft
    else if (url === `${baseUrl}saved-v3`) body = { ...draft, version: saved }
    else if (url === `${baseUrl}${draft.version.id}/edits` && init?.method === 'POST') body = saved
    else throw new Error(`Unexpected ${url}`)
    return { ok: true, status: init?.method === 'POST' ? 201 : 200, json: async () => body } as Response
  })
  vi.stubGlobal('fetch', fetchMock)
  window.history.replaceState(null, '', reviewDraftHref(draft.version.client_profile_id, draft.version.id))
  const view = render(<><App /><RouteStateProbe /></>)
  await userEvent.click(await screen.findByRole('button', { name: 'Edit Name' }))
  await userEvent.clear(screen.getByRole('textbox', { name: 'Name' }))
  await userEvent.type(screen.getByRole('textbox', { name: 'Name' }), 'Reviewer correction{Enter}')
  await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))
  await screen.findByText('Version 3')
  expect(window.location.hash).toBe(reviewDraftHref(saved.client_profile_id, saved.id))
  // Save must notify the router itself; injecting an event here masks stale state.
  expect(screen.getByTestId('route-version')).toHaveTextContent(saved.id)
  expect(await screen.findByRole('button', { name: 'Edit Name' })).toHaveTextContent('Reviewer correction')
  view.unmount()
  render(<App />)
  expect(await screen.findByRole('button', { name: 'Edit Name' })).toHaveTextContent('Reviewer correction')
  expect(fetchMock).toHaveBeenCalledWith(`${baseUrl}saved-v3`)
})
