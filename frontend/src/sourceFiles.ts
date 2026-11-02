import { ApiError } from './api'

// Same default as the API's MAX_UPLOAD_BYTES. The server still checks every file;
// checking here first just saves uploading something that will be refused.
export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024

// The formats the API can extract text from (backend/src/document_extraction.py).
const EXTENSIONS = ['.txt', '.md', '.markdown', '.pdf']

export const ACCEPT = EXTENSIONS.join(',')

const WRONG_TYPE = 'Use a TXT, MD or PDF file.'
const TOO_LARGE = 'This file is larger than 20 MB.'

// Returns why a file can't be used, or null if it looks fine.
export function checkFile(file: File): string | null {
  const dot = file.name.lastIndexOf('.')
  const extension = dot === -1 ? '' : file.name.slice(dot).toLowerCase()
  if (!EXTENSIONS.includes(extension)) {
    return WRONG_TYPE
  }
  if (file.size === 0) {
    return 'This file is empty.'
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return TOO_LARGE
  }
  return null
}

// Turns a failed upload into a sentence for the file's card.
export function describeUploadError(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "Couldn't reach the server. Try again."
  }
  switch (error.status) {
    case 404:
      return 'This client no longer exists. Choose another one.'
    case 413:
      return TOO_LARGE
    case 415:
      return WRONG_TYPE
    case 400:
    case 422:
      // For example "File is empty" or a PDF with no readable text.
      return error.detail ?? 'This file could not be read.'
    default:
      return 'Upload failed. Try again.'
  }
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`
  }
  if (bytes < 1024 * 1024) {
    return `${Math.round(bytes / 1024)} KB`
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
