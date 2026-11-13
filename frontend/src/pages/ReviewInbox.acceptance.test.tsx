import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import responses from '../../../tests/fixtures/review_inbox/responses.json'
import App from '../App'
import { formatGenerated } from './ReviewInboxPage'

// AT 4.1 (#65): a reviewer opens the review inbox, sees the draft with its client and
// generation time, and selects it to see the proposed fields beside their evidence.
// The API replies are tests/fixtures/review_inbox/responses.json, which
// tests/test_review_inbox_acceptance.py checks against the real endpoints.
const { inbox_item: ITEM, draft: DRAFT } = responses
const DRAFT_URL = `/api/v1/reviews/profiles/${ITEM.client_profile_id}/versions/${ITEM.version_id}`

const REVIEWER = {
  id: 'test-user', email: 'staff@example.com', display_name: 'Test User', role: 'reviewer',
}

type Reply = [status: number, body: unknown]

// Answers every /api/v1/reviews call with the same reply until the test switches it.
// The nav's waiting-count badge (TopNav) asks too, on load and on each route change,
// so both see the same inbox, however many times either asks. The draft URL gets the draft.
function fakeApi(inbox: Reply) {
  let reply = inbox

  const fetchMock = vi.fn(async (url: string) => {
    // Return a signed-in user when the app checks authentication.
    if (url === '/api/v1/me') {
      return {
        ok: true,
        status: 200,
        json: async () => REVIEWER,
      } as Response
    }

    if (url !== '/api/v1/reviews' && url !== DRAFT_URL) {
      throw new Error(`Unexpected ${url}`)
    }

    const [status, body]: Reply = url === DRAFT_URL ? [200, DRAFT] : reply

    return {
      ok: status < 400,
      status,
      json: async () => body,
    } as Response
  })

  vi.stubGlobal('fetch', fetchMock)

  const answerInboxWith = (next: Reply) => {
    reply = next
  }

  return { fetchMock, answerInboxWith }
}

function openInbox() {
  window.location.hash = '#/reviews'
  render(<App />)
}

afterEach(() => {
  vi.unstubAllGlobals()
  window.location.hash = ''
})

test('criterion 1: the draft is listed with its client name and generation time', async () => {
  fakeApi([200, [ITEM]])
  openInbox()

  const row = await screen.findByRole('link', { name: /Plateau Basements/ })

  expect(row).toHaveTextContent(formatGenerated(ITEM.created_at))
  expect(within(row).getByText(formatGenerated(ITEM.created_at))).toHaveAttribute(
    'datetime',
    ITEM.created_at,
  )
})

test('criterion 2: selecting the draft opens its fields and evidence side by side', async () => {
  const { fetchMock } = fakeApi([200, [ITEM]])
  openInbox()

  await userEvent.click(await screen.findByRole('link', { name: /Plateau Basements/ }))

  expect(await screen.findByRole('heading', { name: 'Plateau Basements' })).toBeInTheDocument()
  // The nav badge may ask for the inbox again after the route change, so not "last".
  expect(fetchMock).toHaveBeenCalledWith(DRAFT_URL)
  // Named "Reviews, N waiting" while drafts are waiting.
  expect(screen.getByRole('link', { name: /^Reviews/ })).toHaveAttribute('aria-current', 'page')
  // Each field has an evidence selector and an inline value editor.
  const fields = screen.getByRole('button', { name: /^Name/ }).closest('ul')!
  expect(within(fields).getByRole('button', { name: 'Edit Name' })).toHaveTextContent('Maya Chen')
  expect(within(fields).getByRole('button', { name: 'Edit Goal 1' })).toHaveTextContent('30 bookings per month')
  expect(within(fields).getByRole('button', { name: 'Edit Website' })).toHaveTextContent('Not mentioned')
  const evidence = screen.getByRole('region', { name: 'Name' })
  expect(within(evidence).getByText('Contact name: Maya Chen')).toBeInTheDocument()
  // Side by side: both columns sit in the same two-column body.
  expect(fields.closest('.review-draft-body')).toBe(evidence.parentElement)

  await userEvent.click(screen.getByRole('button', { name: /^Goal 1/ }))

  const goal = screen.getByRole('region', { name: 'Goal 1' })
  expect(within(goal).getByRole('listitem')).toHaveTextContent(
    'transcript.txt · TranscriptWe want 30 bookings per month.',
  )
})

test('an empty inbox says no drafts are waiting', async () => {
  fakeApi([200, []])
  openInbox()

  expect(await screen.findByText('No drafts waiting for review.')).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: /Plateau Basements/ })).not.toBeInTheDocument()
})

test('an inbox that fails to load says so, and Try again loads the draft', async () => {
  const { answerInboxWith } = fakeApi([500, {}])
  openInbox()

  expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't load the drafts")
  answerInboxWith([200, [ITEM]])
  await userEvent.click(screen.getByRole('button', { name: 'Try again' }))

  expect(await screen.findByRole('link', { name: /Plateau Basements/ })).toBeInTheDocument()
})


test('production navigation opens inline editing and reopening discards local edits', async () => {
  const { fetchMock } = fakeApi([200, [ITEM]])
  openInbox()
  const open = async () => {
    await userEvent.click(await screen.findByRole('link', { name: /Plateau Basements/ }))
    await screen.findByRole('heading', { name: 'Plateau Basements' })
  }
  await open()
  await userEvent.click(screen.getByRole('button', { name: 'Edit Name' }))
  await userEvent.clear(screen.getByRole('textbox', { name: 'Name' }))
  await userEvent.type(screen.getByRole('textbox'), 'Local only{Enter}')
  expect(screen.getByRole('status')).toHaveTextContent('Unsaved local changes')
  expect(screen.getByRole('region', { name: 'Name' })).toHaveTextContent('Original version evidence')
  await userEvent.click(screen.getByRole('link', { name: '← Review inbox' }))
  await open()
  expect(screen.getByRole('button', { name: 'Edit Name' })).toHaveTextContent('Maya Chen')
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  for (const call of fetchMock.mock.calls) {
    expect(call).toEqual(call[0] === '/api/v1/me'
      ? ['/api/v1/me', { method: 'GET', credentials: 'include' }]
      : [call[0]])
  }
})


test('opening another version clears applied changes and invalid typing', async () => {
  const otherVersion = 'another-version'
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const body = url === '/api/v1/me' ? REVIEWER : url === '/api/v1/reviews' ? [ITEM]
      : { ...DRAFT, version: { ...DRAFT.version, id: url.endsWith(otherVersion) ? otherVersion : ITEM.version_id } }
    return { ok: true, status: 200, json: async () => body } as Response
  }))
  openInbox()
  await userEvent.click(await screen.findByRole('link', { name: /Plateau Basements/ }))
  await userEvent.click(await screen.findByRole('button', { name: 'Edit Name' }))
  await userEvent.clear(screen.getByRole('textbox'))
  await userEvent.type(screen.getByRole('textbox'), 'Local correction{Enter}')
  await userEvent.click(screen.getByRole('button', { name: 'Edit Need 1' }))
  await userEvent.clear(screen.getByRole('textbox'))
  await userEvent.tab()
  expect(screen.getByRole('alert')).toBeInTheDocument()
  await act(async () => {
    window.location.hash = `#/reviews/draft?profile=${ITEM.client_profile_id}&version=${otherVersion}`
  })
  expect(await screen.findByRole('button', { name: 'Edit Name' })).toHaveTextContent('Maya Chen')
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
})
