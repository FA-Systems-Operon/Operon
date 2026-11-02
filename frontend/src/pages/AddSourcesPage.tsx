import { useEffect, useState, type FormEvent } from 'react'
import {
  listClients,
  uploadDocument,
  type Client,
  type DocumentKind,
  type SourceDocument,
} from '../api'
import FileSlot from '../components/FileSlot'
import { checkFile, describeUploadError } from '../sourceFiles'

type Slot = {
  file: File | null
  error: string | null
  // Set once the file is saved on the server, as a receipt so a retry doesn't upload it twice.
  document: SourceDocument | null
}

const EMPTY_SLOT: Slot = { file: null, error: null, document: null }

// The two files the Onboarding agent drafts a profile from, in upload order.
const SLOTS: { kind: DocumentKind; title: string; missing: string }[] = [
  { kind: 'transcript', title: 'Sales call transcript', missing: 'the sales call transcript' },
  { kind: 'intake', title: 'Intake answers', missing: 'the intake answers' },
]

type AddSourcesPageProps = {
  // Already chosen when opened from a client's Brain page; null from Command.
  initialClientId: string | null
  // Called once both files are saved.
  onUploaded?: (clientId: string, documents: SourceDocument[]) => void
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0].toUpperCase())
    .join('')
}

function nextStep(clientChosen: boolean, missingFiles: string[]): string {
  const steps = []
  if (!clientChosen) {
    steps.push('choose a client')
  }
  if (missingFiles.length > 0) {
    steps.push(`add ${missingFiles.join(' and ')}`)
  }
  if (steps.length === 0) {
    return 'The draft takes about a minute.'
  }
  const sentence = steps.join(' and ')
  const capitalized = sentence[0].toUpperCase() + sentence.slice(1)
  return `${capitalized} to continue. The draft takes about a minute.`
}

export default function AddSourcesPage({ initialClientId, onUploaded }: AddSourcesPageProps) {
  const [clients, setClients] = useState<Client[] | null>(null)
  const [loadFailed, setLoadFailed] = useState(false)
  const [clientId, setClientId] = useState('')
  const [slots, setSlots] = useState<Record<DocumentKind, Slot>>({
    transcript: EMPTY_SLOT,
    intake: EMPTY_SLOT,
  })
  const [uploading, setUploading] = useState(false)

  useEffect(() => {
    // Ignore a reply that arrives after the page has closed.
    let active = true
    listClients()
      .then((list) => {
        if (!active) return
        setClients(list)
        if (initialClientId && list.some((client) => client.id === initialClientId)) {
          setClientId(initialClientId)
        }
      })
      .catch(() => {
        if (active) setLoadFailed(true)
      })
    return () => {
      active = false
    }
  }, [initialClientId])

  function updateSlot(kind: DocumentKind, change: Partial<Slot>) {
    setSlots((previous) => ({ ...previous, [kind]: { ...previous[kind], ...change } }))
  }

  function handleClientChange(id: string) {
    setClientId(id)
    // Files already saved belong to the previous client, so upload them again.
    setSlots((previous) => ({
      transcript: { ...previous.transcript, document: null, error: null },
      intake: { ...previous.intake, document: null, error: null },
    }))
  }

  function handleChoose(kind: DocumentKind, file: File) {
    const error = checkFile(file)
    updateSlot(kind, error ? { ...EMPTY_SLOT, error } : { ...EMPTY_SLOT, file })
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setUploading(true)
    const documents: SourceDocument[] = []
    for (const { kind } of SLOTS) {
      const slot = slots[kind]
      if (slot.document) {
        documents.push(slot.document)
        continue
      }
      try {
        const document = await uploadDocument(clientId, slot.file!, kind)
        documents.push(document)
        updateSlot(kind, { document, error: null })
      } catch (error) {
        updateSlot(kind, { error: describeUploadError(error) })
      }
    }
    setUploading(false)
    if (documents.length === SLOTS.length) {
      onUploaded?.(clientId, documents)
    }
  }

  const selected = clients?.find((client) => client.id === clientId)
  const initialMissing =
    clients !== null &&
    initialClientId !== null &&
    !clients.some((client) => client.id === initialClientId)
  const missingFiles = SLOTS.filter(({ kind }) => !slots[kind].file).map(({ missing }) => missing)
  const allUploaded = SLOTS.every(({ kind }) => slots[kind].document)
  const ready = Boolean(selected) && missingFiles.length === 0 && !allUploaded

  let status = nextStep(Boolean(selected), missingFiles)
  if (uploading) {
    status = 'Uploading…'
  } else if (allUploaded && selected) {
    status = `Both files are uploaded to ${selected.name}.`
  }

  return (
    <form className="add-sources" onSubmit={handleSubmit}>
      <h1>Add sources</h1>
      <p className="lead">
        The Onboarding agent drafts a profile from these two files. A reviewer checks it before
        anything is used.
      </p>

      <label className="field-label" htmlFor="client">
        Client
      </label>
      <div className="picker">
        <span className="avatar" aria-hidden="true">
          {selected ? initials(selected.name) : '?'}
        </span>
        <select
          id="client"
          value={clientId}
          disabled={uploading || !clients?.length}
          onChange={(event) => handleClientChange(event.target.value)}
        >
          <option value="" disabled>
            {clients === null && !loadFailed ? 'Loading clients…' : 'Choose a client'}
          </option>
          {clients?.map((client) => (
            <option key={client.id} value={client.id}>
              {client.name}
            </option>
          ))}
        </select>
        <svg className="chevron" viewBox="0 0 16 16" aria-hidden="true">
          <path d="M4 6l4 4 4-4" />
        </svg>
      </div>
      {loadFailed && (
        <p className="field-error" role="alert">
          Couldn't load clients. Refresh the page to try again.
        </p>
      )}
      {clients?.length === 0 && <p className="field-note">No clients yet.</p>}
      {initialMissing && (
        <p className="field-error" role="alert">
          That client wasn't found. Choose one from the list.
        </p>
      )}

      <h2 className="field-label">Files</h2>
      <div className="slots">
        {SLOTS.map(({ kind, title }) => (
          <FileSlot
            key={kind}
            title={title}
            file={slots[kind].file}
            error={slots[kind].error}
            uploaded={slots[kind].document !== null}
            disabled={uploading}
            onChoose={(file) => handleChoose(kind, file)}
            onRemove={() => updateSlot(kind, EMPTY_SLOT)}
          />
        ))}
      </div>

      <div className="submit-row">
        <button className="button button-primary" type="submit" disabled={!ready || uploading}>
          Upload and draft
        </button>
        <p className="submit-status" role="status">
          {status}
        </p>
      </div>
    </form>
  )
}
