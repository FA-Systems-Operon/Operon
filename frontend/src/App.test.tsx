import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, test, vi } from 'vitest'
import App from './App'

afterEach(() => {
  vi.unstubAllGlobals()
})

function jsonResponse(body: unknown, ok = true) {
  return Promise.resolve({
    ok,
    json: () => Promise.resolve(body),
  } as Response)
}

test('renders checking then the mocked /api/v1/status payload', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      jsonResponse({
        api: 'ok',
        db: 'ok',
        ollama: {
          status: 'ok',
          url: 'http://status.test:11434',
          models: ['fixture-model'],
          configured_model: 'fixture-model',
        },
      }),
    ),
  )

  render(<App />)
  expect(screen.getByText('checking...')).toBeInTheDocument()

expect(await screen.findByText('Configured model:')).toBeInTheDocument()
expect(screen.getByText('Configured model:').closest('p')).toHaveTextContent(
  'Configured model: fixture-model',
)
expect(screen.getByText('Ollama URL:').closest('p')).toHaveTextContent(
  'http://status.test:11434',
)
expect(screen.getByText('Installed on host:').closest('p')).toHaveTextContent(
  'fixture-model',
)
})

test('renders fallbacks when the status payload has no ollama fields', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ api: 'ok' })))

  render(<App />)

  expect(await screen.findByText(/not set/)).toBeInTheDocument()
  expect(screen.getAllByText(/unknown/).length).toBeGreaterThan(0)
  expect(screen.getByText(/none reported/)).toBeInTheDocument()
})

test('renders API unreachable when /api/v1/status fails', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network down')))

  render(<App />)

  expect(await screen.findByText('API unreachable')).toBeInTheDocument()
})
test('shows a waiting message while the model request is pending', async () => {
  let resolveModel!: (r: Response) => void
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ api: 'ok', ollama: {} }))
      .mockReturnValueOnce(
        new Promise<Response>((resolve) => {
          resolveModel = resolve
        }),
      ),
  )
  render(<App />)

  fireEvent.click(screen.getByRole('button', { name: 'Test the model via the API' }))
  expect(await screen.findByText('Waiting for the model...')).toBeInTheDocument()

  resolveModel({
    ok: true,
    json: () => Promise.resolve({ model: 'm', response: 'r' }),
  } as Response)
  expect(await screen.findByText('m: r')).toBeInTheDocument()
  expect(screen.queryByText('Waiting for the model...')).not.toBeInTheDocument()
})
test('test button displays whatever /api/v1/ollama/test returns', async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(jsonResponse({ api: 'ok', ollama: {} }))
    .mockResolvedValueOnce(
      jsonResponse({
        model: 'from-api',
        response: 'from-api-body',
      }),
    )
    .mockResolvedValueOnce(jsonResponse({ detail: 'from-api-error' }, false))
    .mockResolvedValueOnce(jsonResponse({}, false))
    .mockRejectedValueOnce(new Error('network down'))

  vi.stubGlobal('fetch', fetchMock)
  render(<App />)
  await screen.findByRole('button', { name: 'Test the model via the API' })

  fireEvent.click(screen.getByRole('button', { name: 'Test the model via the API' }))
  expect(await screen.findByText('from-api: from-api-body')).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: 'Test the model via the API' }))
  expect(await screen.findByText('from-api-error')).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: 'Test the model via the API' }))
  expect(await screen.findByText('Request failed')).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: 'Test the model via the API' }))
  await waitFor(() => {
    expect(screen.getByText('API unreachable')).toBeInTheDocument()
  })
})
