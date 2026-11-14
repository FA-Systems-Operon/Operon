import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import App from './App'

// AT 3.1 (#47): a staff member on the upload screen uploads a transcript and intake
// answers for a client, and the draft starts with no other step. This checks what the
// page sends; tests/test_upload_acceptance.py sends the same requests to the real API
// and checks the job is saved as pending and the draft is generated.
const CLIENT = '0b7d3c1e-0000-4000-8000-000000000001'
const TRANSCRIPT = '0b7d3c1e-0000-4000-8000-000000000002'
const INTAKE = '0b7d3c1e-0000-4000-8000-000000000003'

type Request = { method: string; url: string; body: unknown }

// A fake API that answers like the backend and records every request it gets.

function fakeApi() {
  const requests: Request[] = []

  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
  // Simulate an authenticated user for the session check.
  if (url === '/api/v1/me') {
    return {
      ok: true,
      status: 200,
      json: async () => ({
        id: 'test-user',
        email: 'staff@example.com',
        display_name: 'Test User',
        role: 'reviewer',
      }),
    } as Response
  }

  // The nav's waiting-review count isn't part of the upload flow.
  if (url === '/api/v1/reviews') {
    return {
      ok: true,
      json: async () => [],
    } as Response
  }

  const method = init?.method ?? 'GET'
    let body: unknown = null
    let answer: unknown = [
      { id: CLIENT, name: 'Plateau Basements', created_at: '' },
    ]

    if (init?.body instanceof FormData) {
      const kind = init.body.get('kind')
      body = {
        kind,
        file: (init.body.get('file') as File).name,
      }

      answer = {
        id: kind === 'transcript' ? TRANSCRIPT : INTAKE,
        client_id: CLIENT,
        kind,
      }
    } else if (typeof init?.body === 'string') {
      body = JSON.parse(init.body)
      answer = { id: 'job-1', status: 'pending' }
    }

    requests.push({ method, url, body })

    return {
      ok: true,
      status: method === 'POST' ? 201 : 200,
      json: async () => answer,
    } as Response
  })

  vi.stubGlobal('fetch', fetchMock)
  return requests
}


afterEach(() => {
  vi.unstubAllGlobals()
  window.location.hash = ''
})

test('uploading both files from New intake starts the draft with no other step', async () => {
  const requests = fakeApi()
  const user = userEvent.setup()
  render(<App />)

  await user.click(
    await screen.findByRole('link', { name: 'New intake' }),
  )
  expect(await screen.findByRole('heading', { name: 'Add sources' })).toBeInTheDocument()
  await user.selectOptions(await screen.findByRole('combobox', { name: 'Client' }), CLIENT)
  await user.upload(
    screen.getByLabelText('Sales call transcript file'),
    new File(['Rep: Thanks for joining.'], 'call.txt', { type: 'text/plain' }),
  )
  await user.upload(
    screen.getByLabelText('Intake answers file'),
    new File(['Contact name: Maya Chen'], 'answers.md', { type: 'text/markdown' }),
  )
  await user.click(screen.getByRole('button', { name: 'Upload and draft' }))

  expect(
    await screen.findByText('Draft started for Plateau Basements. It takes about a minute.'),
  ).toBeInTheDocument()
  // One click sent both files, then started the draft from the two saved documents.
  expect(requests).toEqual([
    { method: 'GET', url: '/api/v1/clients', body: null },
    {
      method: 'POST',
      url: `/api/v1/clients/${CLIENT}/documents`,
      body: { kind: 'transcript', file: 'call.txt' },
    },
    {
      method: 'POST',
      url: `/api/v1/clients/${CLIENT}/documents`,
      body: { kind: 'intake', file: 'answers.md' },
    },
    {
      method: 'POST',
      url: `/api/v1/clients/${CLIENT}/onboarding-jobs`,
      body: { transcript_document_id: TRANSCRIPT, intake_document_id: INTAKE },
    },
  ])
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})
