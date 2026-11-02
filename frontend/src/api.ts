export type Client = {
  id: string
  name: string
  created_at: string
}

export type DocumentKind = 'transcript' | 'intake'

export type SourceDocument = {
  id: string
  client_id: string
  original_filename: string
  content_type: string
  size_bytes: number
  sha256: string
  kind: DocumentKind | null
  uploaded_at: string
}

// A response the API answered with an error status (as opposed to no answer at all).
export class ApiError extends Error {
  status: number
  detail: string | undefined

  constructor(status: number, detail: string | undefined) {
    super(detail ?? `Request failed with status ${status}`)
    this.status = status
    this.detail = detail
  }
}

// FastAPI puts the reason in "detail". It is a plain string for errors we raise,
// and a list for automatic validation errors, which we don't show as-is.
async function readDetail(response: Response): Promise<string | undefined> {
  try {
    const body = await response.json()
    return typeof body.detail === 'string' ? body.detail : undefined
  } catch {
    return undefined
  }
}

export async function listClients(): Promise<Client[]> {
  const response = await fetch('/api/v1/clients')
  if (!response.ok) {
    throw new ApiError(response.status, await readDetail(response))
  }
  return response.json()
}

// FormData is an empty box that can carry files over the internet. We can append files to it, and then send it in a POST request.
export async function uploadDocument(
  clientId: string,
  file: File,
  kind: DocumentKind,
): Promise<SourceDocument> {
  const body = new FormData()
  body.append('file', file)
  body.append('kind', kind)

  const response = await fetch(`/api/v1/clients/${encodeURIComponent(clientId)}/documents`, {
    method: 'POST',
    body,
  })
  if (!response.ok) {
    throw new ApiError(response.status, await readDetail(response))
  }
  return response.json()
}
