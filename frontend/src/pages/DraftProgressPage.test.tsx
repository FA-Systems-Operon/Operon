import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import type { OnboardingJob } from '../api'
import DraftProgressPage, { clockTime, duration } from './DraftProgressPage'

const CLIENTS = [{ id: 'c1', name: 'Plateau Basements', created_at: '2026-10-28T00:00:00Z' }]
const JOB_URL = '/api/v1/clients/c1/onboarding-jobs/j1'

const PENDING: OnboardingJob = {
  id: 'j1',
  client_id: 'c1',
  transcript_document_id: 't1',
  intake_document_id: 'i1',
  status: 'pending',
  error: null,
  result_version_id: null,
  result_profile_id: null,
  attempts: 0,
  created_at: '2026-11-12T09:14:00Z',
  started_at: null,
  finished_at: null,
}
const RUNNING = { ...PENDING, status: 'running', attempts: 1, started_at: '2026-11-12T09:14:02Z' }
const SUCCEEDED = {
  ...RUNNING,
  status: 'succeeded',
  result_version_id: 'v1',
  result_profile_id: 'p1',
  finished_at: '2026-11-12T09:14:40Z',
}
const REASON =
  'Draft could not be saved: Reference quote for needs/1 must occur exactly in its source document t1'
const FAILED = { ...RUNNING, status: 'failed', error: REASON, finished_at: '2026-11-12T09:15:10Z' }

type Reply = [status: number, body: unknown]

function reply([status, body]: Reply) {
  return Promise.resolve({
    ok: status < 400,
    status,
    json: () => Promise.resolve(body),
  } as Response)
}

// Fakes the API. Each status check takes the next reply in `checks`; the last one repeats.
function mockApi(checks: (Reply | Error)[], options: { start?: Reply | Error } = {}) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url === '/api/v1/clients') return reply([200, CLIENTS])
    if (init?.method === 'POST') {
      const answer = options.start ?? [200, PENDING]
      return answer instanceof Error ? Promise.reject(answer) : reply(answer)
    }
    const next = checks.length > 1 ? checks.shift()! : checks[0]
    return next instanceof Error ? Promise.reject(next) : reply(next)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function statusChecks(fetchMock: ReturnType<typeof mockApi>) {
  return fetchMock.mock.calls.filter(([url, init]) => url === JOB_URL && !init?.method).length
}

function renderPage(clientId: string | null = 'c1', jobId: string | null = 'j1') {
  render(<DraftProgressPage clientId={clientId} jobId={jobId} pollMs={5} />)
}

// One step of the list. "Queued" is also a Run status, so look only in the steps.
function step(title: string) {
  return within(screen.getByRole('list')).getByText(title).closest('li') as HTMLElement
}

function runCard() {
  return screen.getByText('Run').nextElementSibling as HTMLElement
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

test('clockTime shows a 24-hour time', () => {
  // No time zone in the input, so it is read as local time on any machine.
  expect(clockTime('2026-11-12T09:14:00')).toBe('09:14')
  expect(clockTime('2026-11-12T21:05:00')).toBe('21:05')
})

test('duration shows minutes and seconds, never below zero', () => {
  const start = '2026-11-12T09:14:00Z'
  expect(duration(start, Date.parse('2026-11-12T09:14:38Z'))).toBe('0:38')
  expect(duration(start, Date.parse('2026-11-12T09:26:05Z'))).toBe('12:05')
  expect(duration(start, Date.parse('2026-11-12T09:13:00Z'))).toBe('0:00')
})

test.each([
  ['c1', null],
  [null, 'j1'],
])('a link without a client or job says the draft was not found', (clientId, jobId) => {
  const fetchMock = mockApi([[200, PENDING]])
  renderPage(clientId, jobId)

  expect(screen.getByRole('heading', { name: 'Draft not found' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Back to Command' })).toHaveAttribute('href', '#/')
  expect(statusChecks(fetchMock)).toBe(0)
})

test('follows the job from queued to drafting to ready, then stops asking', async () => {
  const fetchMock = mockApi([[200, PENDING], [200, RUNNING], [200, SUCCEEDED]])
  renderPage()

  // Queued: the first steps are done or in progress, the rest not started.
  expect(await screen.findByRole('heading', { name: 'Drafting Plateau Basements' })).toBeVisible()
  expect(screen.getByText('You can leave this page. The draft will be waiting in Reviews.'))
  expect(step('Files saved')).toHaveAttribute('data-state', 'done')
  expect(step('Queued')).toHaveAttribute('aria-current', 'step')
  expect(step('Drafting')).toHaveAttribute('data-state', 'upcoming')
  expect(runCard()).toHaveTextContent('Queued')

  await waitFor(() => expect(step('Drafting')).toHaveAttribute('aria-current', 'step'))
  expect(step('Queued')).toHaveAttribute('data-state', 'done')
  expect(runCard()).toHaveTextContent('Running')

  expect(
    await screen.findByRole('heading', { name: 'Draft ready for Plateau Basements' }),
  ).toBeVisible()
  expect(step('Drafting')).toHaveAttribute('data-state', 'done')
  expect(within(step('Drafting')).getByText('0:38')).toBeInTheDocument()
  expect(step('Ready for review')).toHaveAttribute('data-state', 'done')
  expect(screen.getByText('Waiting for a reviewer in Reviews')).toBeInTheDocument()
  expect(runCard()).toHaveTextContent('Succeeded')
  expect(screen.getByText('Ready to review')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Open draft' })).toHaveAttribute(
    'href',
    '#/reviews/draft?profile=p1&version=v1',
  )

  const checks = statusChecks(fetchMock)
  expect(checks).toBe(3)
  await new Promise((resolve) => setTimeout(resolve, 30))
  expect(statusChecks(fetchMock)).toBe(checks)
})

test('shows the files and queue times, and a running timer while drafting', async () => {
  // Only the clock and the timer's tick are faked; status checks still run.
  vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] })
  vi.setSystemTime(new Date('2026-11-12T09:14:40Z'))
  mockApi([[200, RUNNING]])
  renderPage()

  await waitFor(() => expect(step('Drafting')).toHaveAttribute('aria-current', 'step'))
  expect(within(step('Drafting')).getByText('0:38')).toBeInTheDocument()
  act(() => vi.advanceTimersByTime(1000))
  expect(within(step('Drafting')).getByText('0:39')).toBeInTheDocument()
  for (const title of ['Files saved', 'Queued']) {
    expect(within(step(title)).getByText(clockTime(PENDING.created_at))).toHaveAttribute(
      'datetime',
      PENDING.created_at,
    )
  }
  expect(screen.queryByRole('link', { name: 'Open draft' })).not.toBeInTheDocument()
})

test('a failed draft shows the reason, and Try again restarts the same job', async () => {
  const user = userEvent.setup()
  const fetchMock = mockApi([[200, FAILED], [200, PENDING]], { start: [200, PENDING] })
  renderPage()

  expect(
    await screen.findByRole('heading', { name: 'Draft failed for Plateau Basements' }),
  ).toBeVisible()
  expect(step('Drafting')).toHaveAttribute('data-state', 'failed')
  expect(within(step('Drafting')).getByText(REASON)).toBeInTheDocument()
  expect(step('Ready for review')).toHaveAttribute('data-state', 'upcoming')
  expect(runCard()).toHaveTextContent('Failed')
  expect(screen.queryByRole('link', { name: 'Open draft' })).not.toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: 'Try again' }))

  // The same two files, so the API restarts this job instead of starting another.
  const [url, init] = fetchMock.mock.calls.find(([, options]) => options?.method === 'POST')!
  expect(url).toBe('/api/v1/clients/c1/onboarding-jobs')
  expect(JSON.parse(init!.body as string)).toEqual({
    transcript_document_id: 't1',
    intake_document_id: 'i1',
  })
  expect(await screen.findByRole('heading', { name: 'Drafting Plateau Basements' })).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
  // Following the restarted job again.
  await waitFor(() => expect(statusChecks(fetchMock)).toBeGreaterThan(1))
})

test('says so when Try again cannot reach the API, and keeps the button', async () => {
  const user = userEvent.setup()
  mockApi([[200, FAILED]], { start: new TypeError('Failed to fetch') })
  renderPage()

  await user.click(await screen.findByRole('button', { name: 'Try again' }))

  expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't restart the draft.")
  expect(screen.getByRole('button', { name: 'Try again' })).toBeEnabled()
})

test('a failed job without a reason or start time still shows the failure', async () => {
  mockApi([[200, { ...PENDING, status: 'failed' }]])
  renderPage()

  expect(await screen.findByText('The draft failed.')).toBeVisible()
  // No drafting time without a start time.
  expect(within(step('Drafting')).queryByText(/^\d+:\d\d$/)).not.toBeInTheDocument()
})

test('a running job without a start time shows no timer', async () => {
  mockApi([[200, { ...RUNNING, started_at: null }]])
  renderPage()

  await waitFor(() => expect(step('Drafting')).toHaveAttribute('aria-current', 'step'))
  expect(within(step('Drafting')).queryByText(/^\d+:\d\d$/)).not.toBeInTheDocument()
})

test('a job waiting for an automatic retry says why', async () => {
  const error = 'AI provider failed: ProviderUnavailable'
  mockApi([[200, { ...PENDING, attempts: 1, error }]])
  renderPage()

  await waitFor(() => expect(runCard()).toHaveTextContent('Retrying'))
  expect(step('Drafting')).toHaveAttribute('aria-current', 'step')
  expect(within(step('Drafting')).getByText(`Trying again soon. ${error}`)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
})

test('a job waiting for a retry without a reason still says it will try again', async () => {
  mockApi([[200, { ...PENDING, attempts: 1 }]])
  renderPage()

  expect(await screen.findByText('Trying again soon.')).toBeInTheDocument()
})

test('an unknown job says the draft was not found', async () => {
  mockApi([[404, { detail: 'Onboarding job not found' }]])
  renderPage()

  expect(await screen.findByRole('heading', { name: 'Draft not found' })).toBeInTheDocument()
})

test('keeps asking when a status check fails, and recovers', async () => {
  const fetchMock = mockApi([new TypeError('Failed to fetch'), [200, RUNNING]])
  renderPage()

  expect(await screen.findByRole('alert')).toHaveTextContent(
    "Couldn't load the draft's status. Trying again…",
  )
  await waitFor(() => expect(runCard()).toHaveTextContent('Running'))
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  expect(statusChecks(fetchMock)).toBeGreaterThan(1)
})

test('keeps the last status when a later check fails', async () => {
  mockApi([[200, RUNNING], new TypeError('Failed to fetch'), [200, RUNNING]])
  renderPage()

  expect(await screen.findByRole('alert')).toHaveTextContent(
    "Couldn't check for updates. Trying again…",
  )
  expect(runCard()).toHaveTextContent('Running')
})

test.each([
  ['the client list fails', () => Promise.reject(new TypeError('offline'))],
  ['the client is not in the list', () => reply([200, []])],
])('works without the client name when %s', async (_, clients) => {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => (url === '/api/v1/clients' ? clients() : reply([200, SUCCEEDED]))),
  )
  renderPage()

  expect(await screen.findByRole('heading', { name: 'Draft ready' })).toBeInTheDocument()
})

test.each([
  ['an answer', [200, RUNNING] as Reply],
  ['a failure', [500, { detail: 'boom' }] as Reply],
])('ignores %s that arrives after the page has closed', async (_, late) => {
  let answer: (response: Response) => void = () => {}
  const fetchMock = vi.fn((url: string) =>
    url === '/api/v1/clients'
      ? reply([200, CLIENTS])
      : new Promise<Response>((resolve) => {
          answer = resolve
        }),
  )
  vi.stubGlobal('fetch', fetchMock)
  const { unmount } = render(<DraftProgressPage clientId="c1" jobId="j1" pollMs={5} />)
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(JOB_URL))

  unmount()
  answer(await reply(late))
  await new Promise((resolve) => setTimeout(resolve, 30))

  // Nothing new was asked after the page closed.
  expect(fetchMock.mock.calls.filter(([url]) => url === JOB_URL)).toHaveLength(1)
})
