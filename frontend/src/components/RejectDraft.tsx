import { useEffect, useId, useRef, useState } from 'react'
import { ApiError, REJECTION_REASON_MAX_LENGTH, rejectReviewDraft, type ProfileVersion } from '../api'

type RejectDraftProps = {
  profileId: string
  versionId: string
  // True while something else (such as saving edits) must finish first.
  disabled: boolean
  // Unsaved edits are dropped by rejecting, so the form says so.
  hasUnsavedEdits: boolean
  onRejected: (version: ProfileVersion) => void
  // Told when a reject request starts and ends, so Approve can wait for it.
  onRejectingChange?: (rejecting: boolean) => void
}

type Status = 'idle' | 'rejecting' | 'error' | 'stale'

// #63: Reject asks for a short reason, then marks the draft rejected. It never approves.
export default function RejectDraft({
  profileId, versionId, disabled, hasUnsavedEdits, onRejected, onRejectingChange,
}: RejectDraftProps) {
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [touched, setTouched] = useState(false)
  const [status, setStatus] = useState<Status>('idle')
  const [error, setError] = useState('')
  const mounted = useRef(true)
  const busy = useRef(false)
  const textarea = useRef<HTMLTextAreaElement>(null)
  const id = useId()
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])
  useEffect(() => {
    if (open) textarea.current?.focus()
  }, [open])

  const trimmed = reason.trim()
  const reasonError = trimmed ? '' : 'Enter a reason for rejecting this draft.'

  function cancel() {
    setOpen(false)
    setReason('')
    setTouched(false)
    setStatus('idle')
    setError('')
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setTouched(true)
    if (reasonError || busy.current || status === 'stale') return
    busy.current = true
    onRejectingChange?.(true)
    setStatus('rejecting')
    setError('')
    try {
      const version = await rejectReviewDraft(profileId, versionId, trimmed)
      if (!mounted.current) return
      onRejected(version)
    } catch (caught) {
      if (!mounted.current) return
      const code = caught instanceof ApiError ? caught.status : 0
      setStatus(code === 409 ? 'stale' : 'error')
      setError(code === 409
        ? 'This draft changed or was already reviewed. Open the latest draft from the review inbox.'
        : code === 422 ? 'Couldn\'t reject with that reason. Keep it short and not blank.'
          : code === 401 ? 'Your session has ended. Sign in again to reject.'
            : code === 403 ? 'Your role cannot reject drafts.'
              : 'Couldn\'t confirm the draft was rejected. Try again.')
    } finally {
      busy.current = false
      onRejectingChange?.(false)
    }
  }

  if (!open) {
    return (
      <div className="review-reject">
        <button className="button" type="button" disabled={disabled} onClick={() => setOpen(true)}>
          Reject
        </button>
      </div>
    )
  }

  const rejecting = status === 'rejecting'
  return (
    <form className="review-reject review-reject-form" onSubmit={submit} noValidate>
      <label className="field-label" htmlFor={`${id}-reason`}>Reason for rejecting</label>
      <textarea
        ref={textarea}
        id={`${id}-reason`}
        className="review-reject-reason"
        rows={3}
        maxLength={REJECTION_REASON_MAX_LENGTH}
        value={reason}
        disabled={rejecting || status === 'stale'}
        aria-invalid={touched && !!reasonError}
        aria-describedby={`${id}-hint`}
        onChange={(event) => setReason(event.target.value)}
        onKeyDown={(event) => { if (event.key === 'Escape' && !rejecting) cancel() }}
      />
      <p id={`${id}-hint`} className="field-note">
        Short and specific, up to {REJECTION_REASON_MAX_LENGTH} characters. The draft won't be approved.
        {hasUnsavedEdits && ' Unsaved edits will be discarded.'}
      </p>
      {touched && reasonError && <p className="field-error" role="alert">{reasonError}</p>}
      {error && <p className="field-error" role="alert">{error}</p>}
      <div className="review-reject-actions">
        <button className="button button-primary" type="submit" disabled={disabled || rejecting || status === 'stale'}>
          {rejecting ? 'Rejecting…' : status === 'error' ? 'Try rejecting again' : 'Reject draft'}
        </button>
        <button className="button" type="button" disabled={rejecting} onClick={cancel}>
          Cancel
        </button>
      </div>
    </form>
  )
}
