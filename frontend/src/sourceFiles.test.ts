import { expect, test } from 'vitest'
import { ApiError } from './api'
import { checkFile, describeUploadError, formatSize, MAX_UPLOAD_BYTES } from './sourceFiles'

function fileOfSize(name: string, size: number) {
  const file = new File(['x'], name)
  Object.defineProperty(file, 'size', { value: size })
  return file
}

test.each(['call.txt', 'notes.md', 'notes.markdown', 'answers.pdf', 'CALL.TXT'])(
  'checkFile accepts %s',
  (name) => {
    expect(checkFile(fileOfSize(name, 10))).toBeNull()
  },
)

test.each(['photo.png', 'answers.docx', 'README', 'archive.txt.zip'])(
  'checkFile refuses %s',
  (name) => {
    expect(checkFile(fileOfSize(name, 10))).toBe('Use a TXT, MD or PDF file.')
  },
)

test('checkFile refuses an empty file', () => {
  expect(checkFile(fileOfSize('call.txt', 0))).toBe('This file is empty.')
})

test('checkFile allows exactly the size limit and refuses one byte more', () => {
  expect(checkFile(fileOfSize('call.txt', MAX_UPLOAD_BYTES))).toBeNull()
  expect(checkFile(fileOfSize('call.txt', MAX_UPLOAD_BYTES + 1))).toBe(
    'This file is larger than 20 MB.',
  )
})

test.each([
  [404, undefined, 'This client no longer exists. Choose another one.'],
  [413, 'File is larger than 20971520 bytes', 'This file is larger than 20 MB.'],
  [415, 'Supported document formats are TXT, Markdown, and PDF', 'Use a TXT, MD or PDF file.'],
  [400, 'File is empty', 'File is empty'],
  [422, 'PDF has no extractable text', 'PDF has no extractable text'],
  [422, undefined, 'This file could not be read.'],
  [500, undefined, 'Upload failed. Try again.'],
])('describeUploadError for %i (%j)', (status, detail, message) => {
  expect(describeUploadError(new ApiError(status, detail))).toBe(message)
})

test('describeUploadError when the server could not be reached', () => {
  expect(describeUploadError(new TypeError('Failed to fetch'))).toBe(
    "Couldn't reach the server. Try again.",
  )
})

test.each([
  [512, '512 B'],
  [1024, '1 KB'],
  [12_800, '13 KB'],
  [1_572_864, '1.5 MB'],
])('formatSize(%i) is %s', (bytes, text) => {
  expect(formatSize(bytes)).toBe(text)
})
