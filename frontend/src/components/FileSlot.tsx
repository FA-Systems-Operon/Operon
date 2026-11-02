import { useState, type ChangeEvent, type DragEvent } from 'react'
import { ACCEPT, formatSize } from '../sourceFiles'

type FileSlotProps = {
  title: string
  file: File | null
  error: string | null
  uploaded: boolean
  disabled: boolean
  onChoose: (file: File) => void
  onRemove: () => void
}

// One of the two file boxes on Add sources: an empty drop zone, or the chosen file.
export default function FileSlot({
  title,
  file,
  error,
  uploaded,
  disabled,
  onChoose,
  onRemove,
}: FileSlotProps) {
  const [dragging, setDragging] = useState(false)

  const errorMessage = error && (
    <p className="slot-error" role="alert">
      {error}
    </p>
  )

  if (file) {
    return (
      <div className="slot slot-filled">
        <span className="slot-check" aria-hidden="true">
          ✓
        </span>
        <h3 className="slot-title">{title}</h3>
        <p className="slot-filename">{file.name}</p>
        <div className="slot-footer">
          <span className="mono">
            {uploaded ? `Uploaded · ${formatSize(file.size)}` : formatSize(file.size)}
          </span>
          {!uploaded && (
            <button
              type="button"
              className="link-button"
              onClick={onRemove}
              disabled={disabled}
              aria-label={`Remove ${title.toLowerCase()}`}
            >
              Remove
            </button>
          )}
        </div>
        {errorMessage}
      </div>
    )
  }

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const chosen = event.target.files?.[0]
    if (chosen) {
      onChoose(chosen)
    }
    // Lets the same file be chosen again after it is removed.
    event.target.value = ''
  }

  function handleDragOver(event: DragEvent) {
    event.preventDefault()
    setDragging(true)
  }

  function handleDrop(event: DragEvent) {
    event.preventDefault()
    setDragging(false)
    const dropped = event.dataTransfer.files[0]
    if (dropped) {
      onChoose(dropped)
    }
  }

  return (
    <div
      className={dragging ? 'slot slot-empty slot-dragging' : 'slot slot-empty'}
      onDragOver={handleDragOver}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
    >
      <h3 className="slot-title">{title}</h3>
      <p className="slot-hint">
        Drop a file or{' '}
        <label className="link-button">
          browse
          <input
            className="visually-hidden"
            type="file"
            accept={ACCEPT}
            disabled={disabled}
            aria-label={`${title} file`}
            onChange={handleChange}
          />
        </label>
      </p>
      <p className="mono">TXT, MD or PDF</p>
      {errorMessage}
    </div>
  )
}
