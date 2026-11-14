import type { SourceLinkedDraft } from './components/draftSources'

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

// One run of the Onboarding agent on a client's transcript and intake answers.
export type OnboardingJob = {
  id: string
  client_id: string
  transcript_document_id: string
  intake_document_id: string
  status: 'pending' | 'running' | 'succeeded' | 'failed'
  error: string | null
  result_version_id: string | null
  created_at: string
}

// A profile draft waiting for a reviewer. One per profile, so a client can appear twice.
export type ReviewInboxItem = {
  version_id: string
  client_profile_id: string
  version_number: number
  client_id: string
  client_name: string
  // When the draft was generated (saved).
  created_at: string
  status: 'draft' | 'in_review'
}

export type ReviewStatus = 'draft' | 'in_review' | 'approved' | 'rejected' | 'stale'

// One saved version of a client profile. Generated drafts keep the agent's output in data.
export type ProfileVersion = {
  id: string
  client_profile_id: string
  version_number: number
  status: ReviewStatus
  data: Partial<SourceLinkedDraft>
  created_at: string
  approved_by: string | null
  approved_at: string | null
}

// Everything the review page needs to open one draft, in one call (#57).
export type ReviewDraft = {
  version: ProfileVersion
  client: Client
  // The client's source documents, to name the file each quote came from.
  documents: SourceDocument[]
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

// Newest first, as the API sends them.
export async function listReviews(): Promise<ReviewInboxItem[]> {
  const response = await fetch('/api/v1/reviews')
  if (!response.ok) {
    throw new ApiError(response.status, await readDetail(response))
  }
  return response.json()
}

export async function getReviewDraft(profileId: string, versionId: string): Promise<ReviewDraft> {
  const response = await fetch(
    `/api/v1/reviews/profiles/${encodeURIComponent(profileId)}/versions/${encodeURIComponent(versionId)}`,
  )
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

// Uploading only saves the files. This tells the backend to start the draft from
// both of them. Asking again for the same pair returns the same job.
export async function startOnboardingJob(
  clientId: string,
  transcriptDocumentId: string,
  intakeDocumentId: string,
): Promise<OnboardingJob> {
  const response = await fetch(`/api/v1/clients/${encodeURIComponent(clientId)}/onboarding-jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      transcript_document_id: transcriptDocumentId,
      intake_document_id: intakeDocumentId,
    }),
  })
  if (!response.ok) {
    throw new ApiError(response.status, await readDetail(response))
  }
  return response.json()
}
