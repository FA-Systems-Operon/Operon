import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import AddSourcesPage, { initials } from './AddSourcesPage'

const CLIENTS = [
  { id: 'c1', name: 'Plateau Basements', created_at: '2026-10-28T00:00:00Z' },
  { id: 'c2', name: 'acme plumbing', created_at: '2026-10-29T00:00:00Z' },
]

const TRANSCRIPT_BOX = 'Sales call transcript'
const INTAKE_BOX = 'Intake answers'

type Reply = [status: number, body: unknown]

function reply([status, body]: Reply) {
  return Promise.resolve({
    ok: status < 400,
    status,
    json: () => Promise.resolve(body),
  } as Response)
}

// Fakes the three endpoints the page calls. `upload` can return a reply (or a promise
// of one) to override the normal "201 Created" for a given kind, and `start` does the
// same for starting the draft.
function mockApi(
  options: {
    clients?: Reply
    upload?: (kind: string) => Reply | Promise<Response> | undefined
    start?: () => Reply | undefined
  } = {},
) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url === '/api/v1/clients') {
      return reply(options.clients ?? [200, CLIENTS])
    }
    if (url.endsWith('/onboarding-jobs')) {
      return reply(options.start?.() ?? [201, { id: 'job1', status: 'pending' }])
    }
    const form = init!.body as FormData
    const kind = form.get('kind') as string
    const override = options.upload?.(kind)
    if (override instanceof Promise) {
      return override
    }
    const clientId = url.split('/')[4]
    return reply(override ?? [201, { id: `${clientId}-${kind}`, client_id: clientId, kind }])
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

// The uploads sent so far, as [client, kind, file name].
function uploadsSent(fetchMock: ReturnType<typeof mockApi>) {
  return fetchMock.mock.calls
    .filter(([url]) => url.endsWith('/documents'))
    .map(([url, init]) => {
      const form = init!.body as FormData
      return [url.split('/')[4], form.get('kind'), (form.get('file') as File).name]
    })
}

// The draft starts asked for so far, as [client, transcript ID, intake ID].
function startsSent(fetchMock: ReturnType<typeof mockApi>) {
  return fetchMock.mock.calls
    .filter(([url]) => url.endsWith('/onboarding-jobs'))
    .map(([url, init]) => {
      const body = JSON.parse(init!.body as string)
      return [url.split('/')[4], body.transcript_document_id, body.intake_document_id]
    })
}

function textFile(name: string, text = 'Rep: Hi, thanks for joining.') {
  return new File([text], name, { type: 'text/plain' })
}

function box(title: string) {
  return within(screen.getByRole('heading', { name: title }).closest('.slot') as HTMLElement)
}

function submitButton() {
  return screen.getByRole('button', { name: 'Upload and draft' })
}

function status() {
  return screen.getByRole('status')
}

async function renderPage(initialClientId: string | null = null, onDraftStarted = vi.fn()) {
  render(<AddSourcesPage initialClientId={initialClientId} onDraftStarted={onDraftStarted} />)
  const picker = screen.getByRole('combobox', { name: 'Client' })
  await waitFor(() => expect(picker).toBeEnabled())
  return { picker, onDraftStarted }
}

async function chooseEverything(clientId = 'c1') {
  const user = userEvent.setup()
  await user.selectOptions(screen.getByRole('combobox', { name: 'Client' }), clientId)
  await user.upload(screen.getByLabelText(`${TRANSCRIPT_BOX} file`), textFile('call.txt'))
  await user.upload(screen.getByLabelText(`${INTAKE_BOX} file`), textFile('answers.md'))
  return user
}

afterEach(() => {
  vi.unstubAllGlobals()
})

test('initials uses the first letter of the first two words', () => {
  expect(initials('Plateau Basements Inc')).toBe('PB')
  expect(initials('acme plumbing')).toBe('AP')
  expect(initials('  Solo  ')).toBe('S')
})

test('asks for a client and both files before it can upload', async () => {
  mockApi()
  const { picker } = await renderPage()

  expect(picker).toHaveValue('')
  expect(screen.getByText('?')).toBeInTheDocument()
  expect(within(picker).getAllByRole('option').map((option) => option.textContent)).toEqual([
    'Choose a client',
    'Plateau Basements',
    'acme plumbing',
  ])
  expect(submitButton()).toBeDisabled()
  expect(status()).toHaveTextContent(
    'Choose a client and add the sales call transcript and the intake answers to continue. ' +
      'The draft takes about a minute.',
  )
})

test('opens with the client from the Brain page already chosen', async () => {
  mockApi()
  const { picker } = await renderPage('c1')

  expect(picker).toHaveValue('c1')
  expect(screen.getByText('PB')).toBeInTheDocument()
  expect(status()).toHaveTextContent(
    'Add the sales call transcript and the intake answers to continue.',
  )
})

test('says so when the client in the link does not exist', async () => {
  mockApi()
  const { picker } = await renderPage('deleted-client')

  expect(picker).toHaveValue('')
  expect(screen.getByRole('alert')).toHaveTextContent("That client wasn't found.")
})

test('shows loading, then an error when clients cannot be loaded', async () => {
  mockApi({ clients: [500, { detail: 'boom' }] })
  render(<AddSourcesPage initialClientId={null} />)

  expect(screen.getByRole('option', { name: 'Loading clients…' })).toBeInTheDocument()
  expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't load clients.")
  expect(screen.getByRole('combobox', { name: 'Client' })).toBeDisabled()
  expect(screen.getByRole('option', { name: 'Choose a client' })).toBeInTheDocument()
})

test('says when there are no clients yet', async () => {
  mockApi({ clients: [200, []] })
  render(<AddSourcesPage initialClientId={null} />)

  expect(await screen.findByText('No clients yet.')).toBeInTheDocument()
  expect(screen.getByRole('combobox', { name: 'Client' })).toBeDisabled()
})

// The first request (for c1) is still waiting when the link changes to c2. When it
// finally answers, it must not undo the newer page.
async function openThenSwitchToC2(firstRequest: Promise<Response>) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockReturnValueOnce(firstRequest).mockImplementationOnce(() => reply([200, CLIENTS])),
  )
  const { rerender } = render(<AddSourcesPage initialClientId="c1" />)
  rerender(<AddSourcesPage initialClientId="c2" />)
  const picker = screen.getByRole('combobox', { name: 'Client' })
  await waitFor(() => expect(picker).toHaveValue('c2'))
  return picker
}

test('ignores a client list from an earlier link that arrives late', async () => {
  let answer!: (response: Response) => void
  const picker = await openThenSwitchToC2(new Promise((resolve) => (answer = resolve)))

  await act(async () => {
    answer({ ok: true, status: 200, json: () => Promise.resolve(CLIENTS) } as Response)
  })

  expect(picker).toHaveValue('c2')
})

test('ignores a failure from an earlier link that arrives late', async () => {
  let fail!: (error: Error) => void
  await openThenSwitchToC2(new Promise((_, reject) => (fail = reject)))

  await act(async () => {
    fail(new Error('network down'))
  })

  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

test('shows a chosen file with its name and size, and Remove takes it out', async () => {
  mockApi()
  await renderPage('c1')
  const user = userEvent.setup()

  await user.upload(screen.getByLabelText(`${TRANSCRIPT_BOX} file`), textFile('call.txt', 'abc'))

  expect(box(TRANSCRIPT_BOX).getByText('call.txt')).toBeInTheDocument()
  expect(box(TRANSCRIPT_BOX).getByText('3 B')).toBeInTheDocument()
  expect(status()).toHaveTextContent('Add the intake answers to continue.')

  await user.click(screen.getByRole('button', { name: 'Remove sales call transcript' }))

  expect(screen.queryByText('call.txt')).not.toBeInTheDocument()
  expect(screen.getByLabelText(`${TRANSCRIPT_BOX} file`)).toBeInTheDocument()
})

test('closing the file dialog without a file leaves the box empty', async () => {
  mockApi()
  await renderPage('c1')

  fireEvent.change(screen.getByLabelText(`${INTAKE_BOX} file`), { target: { files: [] } })

  expect(screen.getByLabelText(`${INTAKE_BOX} file`)).toBeInTheDocument()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

test('refuses a file the API cannot read and keeps the box empty', async () => {
  mockApi()
  await renderPage('c1')
  const user = userEvent.setup({ applyAccept: false })

  await user.upload(screen.getByLabelText(`${INTAKE_BOX} file`), textFile('answers.docx'))

  expect(box(INTAKE_BOX).getByRole('alert')).toHaveTextContent('Use a TXT, MD or PDF file.')
  expect(screen.getByLabelText(`${INTAKE_BOX} file`)).toBeInTheDocument()
  expect(screen.queryByText('answers.docx')).not.toBeInTheDocument()

  // Choosing a good file clears the message.
  await user.upload(screen.getByLabelText(`${INTAKE_BOX} file`), textFile('answers.txt'))
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

test('accepts a file dropped on its box', async () => {
  mockApi()
  await renderPage('c1')
  const zone = screen.getByRole('heading', { name: INTAKE_BOX }).closest('.slot')!

  fireEvent.dragOver(zone)
  expect(zone).toHaveClass('slot-dragging')
  fireEvent.dragLeave(zone)
  expect(zone).not.toHaveClass('slot-dragging')

  fireEvent.drop(zone, { dataTransfer: { files: [] } })
  expect(screen.getByLabelText(`${INTAKE_BOX} file`)).toBeInTheDocument()

  fireEvent.drop(zone, { dataTransfer: { files: [textFile('answers.pdf')] } })
  expect(box(INTAKE_BOX).getByText('answers.pdf')).toBeInTheDocument()
})

test('uploads both files with their kinds, then starts the draft from both', async () => {
  const fetchMock = mockApi()
  const { onDraftStarted } = await renderPage()
  const user = await chooseEverything('c2')

  expect(screen.getByText('AP')).toBeInTheDocument()
  expect(status()).toHaveTextContent(/^The draft takes about a minute\.$/)
  expect(submitButton()).toBeEnabled()

  await user.click(submitButton())

  expect(
    await screen.findByText('Draft started for acme plumbing. It takes about a minute.'),
  ).toBeInTheDocument()
  expect(uploadsSent(fetchMock)).toEqual([
    ['c2', 'transcript', 'call.txt'],
    ['c2', 'intake', 'answers.md'],
  ])
  expect(startsSent(fetchMock)).toEqual([['c2', 'c2-transcript', 'c2-intake']])
  expect(onDraftStarted).toHaveBeenCalledWith({ id: 'job1', status: 'pending' })
  expect(submitButton()).toBeDisabled()
  expect(screen.getAllByText(/^Uploaded · /)).toHaveLength(2)
  expect(screen.queryByRole('button', { name: /^Remove/ })).not.toBeInTheDocument()
})

test('locks the form while the files are being sent', async () => {
  let finish!: (response: Response) => void
  const pending = new Promise<Response>((resolve) => (finish = resolve))
  mockApi({ upload: (kind) => (kind === 'transcript' ? pending : undefined) })
  await renderPage('c1')
  const user = await chooseEverything('c1')

  await user.click(submitButton())

  expect(status()).toHaveTextContent('Uploading…')
  expect(submitButton()).toBeDisabled()
  expect(screen.getByRole('combobox', { name: 'Client' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Remove intake answers' })).toBeDisabled()

  finish({ ok: true, status: 201, json: () => Promise.resolve({ id: 't' }) } as Response)
  expect(
    await screen.findByText('Draft started for Plateau Basements. It takes about a minute.'),
  ).toBeInTheDocument()
})

test('shows a failed upload on its file and retries only that file', async () => {
  let intakeFails = true
  const fetchMock = mockApi({
    upload: (kind) =>
      kind === 'intake' && intakeFails ? [415, { detail: 'Unsupported' }] : undefined,
  })
  const { onDraftStarted } = await renderPage('c1')
  const user = await chooseEverything('c1')

  await user.click(submitButton())

  expect(await box(INTAKE_BOX).findByRole('alert')).toHaveTextContent(
    'Use a TXT, MD or PDF file.',
  )
  expect(box(TRANSCRIPT_BOX).getByText(/^Uploaded · /)).toBeInTheDocument()
  expect(startsSent(fetchMock)).toEqual([])
  expect(onDraftStarted).not.toHaveBeenCalled()
  expect(submitButton()).toBeEnabled()

  intakeFails = false
  await user.click(submitButton())

  expect(
    await screen.findByText('Draft started for Plateau Basements. It takes about a minute.'),
  ).toBeInTheDocument()
  expect(uploadsSent(fetchMock)).toEqual([
    ['c1', 'transcript', 'call.txt'],
    ['c1', 'intake', 'answers.md'],
    ['c1', 'intake', 'answers.md'],
  ])
  expect(startsSent(fetchMock)).toHaveLength(1)
  expect(onDraftStarted).toHaveBeenCalledTimes(1)
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

test('switching client after a partial upload sends both files to the new client', async () => {
  const fetchMock = mockApi({
    upload: (kind) => (kind === 'intake' ? [404, { detail: 'Client not found' }] : undefined),
  })
  await renderPage('c1')
  const user = await chooseEverything('c1')
  await user.click(submitButton())
  expect(await box(INTAKE_BOX).findByRole('alert')).toHaveTextContent(
    'This client no longer exists.',
  )

  await user.selectOptions(screen.getByRole('combobox', { name: 'Client' }), 'c2')

  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  expect(screen.queryByText(/^Uploaded · /)).not.toBeInTheDocument()
  expect(box(TRANSCRIPT_BOX).getByText('call.txt')).toBeInTheDocument()

  await user.click(submitButton())
  await waitFor(() => expect(uploadsSent(fetchMock)).toHaveLength(4))
  expect(uploadsSent(fetchMock).slice(2)).toEqual([
    ['c2', 'transcript', 'call.txt'],
    ['c2', 'intake', 'answers.md'],
  ])
})

test('works without an onDraftStarted handler', async () => {
  mockApi()
  render(<AddSourcesPage initialClientId="c1" />)
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'Client' })).toHaveValue('c1'))
  const user = await chooseEverything('c1')

  await user.click(submitButton())

  expect(
    await screen.findByText('Draft started for Plateau Basements. It takes about a minute.'),
  ).toBeInTheDocument()
})

test('if the draft cannot start, keeps the files and retries only the start', async () => {
  let startFails = true
  const fetchMock = mockApi({ start: () => (startFails ? [500, { detail: 'boom' }] : undefined) })
  const { onDraftStarted } = await renderPage('c1')
  const user = await chooseEverything('c1')

  await user.click(submitButton())

  expect(await screen.findByRole('alert')).toHaveTextContent(
    "Both files are saved, but the draft couldn't start. Try again.",
  )
  expect(screen.getAllByText(/^Uploaded · /)).toHaveLength(2)
  expect(onDraftStarted).not.toHaveBeenCalled()
  expect(submitButton()).toBeEnabled()

  startFails = false
  await user.click(submitButton())

  expect(
    await screen.findByText('Draft started for Plateau Basements. It takes about a minute.'),
  ).toBeInTheDocument()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  expect(uploadsSent(fetchMock)).toHaveLength(2)
  expect(startsSent(fetchMock)).toEqual([
    ['c1', 'c1-transcript', 'c1-intake'],
    ['c1', 'c1-transcript', 'c1-intake'],
  ])
})

test('switching client after the draft started allows a new upload', async () => {
  const fetchMock = mockApi()
  await renderPage('c1')
  const user = await chooseEverything('c1')
  await user.click(submitButton())
  expect(await screen.findByText(/^Draft started for Plateau Basements/)).toBeInTheDocument()
  expect(submitButton()).toBeDisabled()

  await user.selectOptions(screen.getByRole('combobox', { name: 'Client' }), 'c2')

  expect(status()).toHaveTextContent(/^The draft takes about a minute\.$/)
  await user.click(submitButton())
  expect(await screen.findByText(/^Draft started for acme plumbing/)).toBeInTheDocument()
  expect(startsSent(fetchMock)).toEqual([
    ['c1', 'c1-transcript', 'c1-intake'],
    ['c2', 'c2-transcript', 'c2-intake'],
  ])
})
