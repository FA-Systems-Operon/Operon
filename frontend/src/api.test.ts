import { afterEach, expect, test, vi } from 'vitest'
import { ApiError, listClients, listReviews, startOnboardingJob, uploadDocument } from './api'

function response(status: number, body: unknown) {
  return {
    ok: status < 400,
    status,
    json: () => (body instanceof Error ? Promise.reject(body) : Promise.resolve(body)),
  } as Response
}

afterEach(() => {
  vi.unstubAllGlobals()
})

test('listClients returns the clients from the API', async () => {
  const clients = [{ id: 'c1', name: 'Acme', created_at: '2026-10-29T00:00:00Z' }]
  const fetchMock = vi.fn().mockResolvedValue(response(200, clients))
  vi.stubGlobal('fetch', fetchMock)

  await expect(listClients()).resolves.toEqual(clients)
  expect(fetchMock).toHaveBeenCalledWith('/api/v1/clients')
})

test('listClients throws an ApiError with the status on failure', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(500, new Error('not JSON'))))

  const error = await listClients().catch((caught) => caught)

  expect(error).toBeInstanceOf(ApiError)
  expect(error.status).toBe(500)
  expect(error.detail).toBeUndefined()
  expect(error.message).toBe('Request failed with status 500')
})

test('listReviews returns the drafts from the API', async () => {
  const drafts = [{ version_id: 'v2', client_name: 'Acme', status: 'draft' }]
  const fetchMock = vi.fn().mockResolvedValue(response(200, drafts))
  vi.stubGlobal('fetch', fetchMock)

  await expect(listReviews()).resolves.toEqual(drafts)
  expect(fetchMock).toHaveBeenCalledWith('/api/v1/reviews')
})

test('listReviews throws an ApiError with the status on failure', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(503, { detail: 'Database down' })))

  const error = await listReviews().catch((caught) => caught)

  expect(error).toBeInstanceOf(ApiError)
  expect(error.status).toBe(503)
  expect(error.detail).toBe('Database down')
})

test('uploadDocument posts the file and its kind as a form', async () => {
  const saved = { id: 'd1', kind: 'intake' }
  const fetchMock = vi.fn().mockResolvedValue(response(201, saved))
  vi.stubGlobal('fetch', fetchMock)
  const file = new File(['Q: Goals?'], 'answers.txt', { type: 'text/plain' })

  await expect(uploadDocument('c1', file, 'intake')).resolves.toEqual(saved)

  const [url, init] = fetchMock.mock.calls[0]
  expect(url).toBe('/api/v1/clients/c1/documents')
  expect(init.method).toBe('POST')
  expect(init.body.get('kind')).toBe('intake')
  expect((init.body.get('file') as File).name).toBe('answers.txt')
})

test('uploadDocument keeps the reason the API gave', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(400, { detail: 'File is empty' })))

  const error = await uploadDocument('c1', new File(['x'], 'a.txt'), 'transcript').catch(
    (caught) => caught,
  )

  expect(error.status).toBe(400)
  expect(error.detail).toBe('File is empty')
  expect(error.message).toBe('File is empty')
})

test('uploadDocument ignores validation details that are not a sentence', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(response(422, { detail: [{ loc: ['body', 'kind'] }] })),
  )

  const error = await uploadDocument('c1', new File(['x'], 'a.txt'), 'transcript').catch(
    (caught) => caught,
  )

  expect(error.status).toBe(422)
  expect(error.detail).toBeUndefined()
})

test('startOnboardingJob posts both document IDs as JSON', async () => {
  const job = { id: 'j1', status: 'pending' }
  const fetchMock = vi.fn().mockResolvedValue(response(201, job))
  vi.stubGlobal('fetch', fetchMock)

  await expect(startOnboardingJob('c1', 'd1', 'd2')).resolves.toEqual(job)

  const [url, init] = fetchMock.mock.calls[0]
  expect(url).toBe('/api/v1/clients/c1/onboarding-jobs')
  expect(init.method).toBe('POST')
  expect(init.headers).toEqual({ 'Content-Type': 'application/json' })
  expect(JSON.parse(init.body)).toEqual({ transcript_document_id: 'd1', intake_document_id: 'd2' })
})

test('startOnboardingJob throws an ApiError with the reason on failure', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(404, { detail: 'Intake not found' })))

  const error = await startOnboardingJob('c1', 'd1', 'd2').catch((caught) => caught)

  expect(error).toBeInstanceOf(ApiError)
  expect(error.status).toBe(404)
  expect(error.detail).toBe('Intake not found')
})
