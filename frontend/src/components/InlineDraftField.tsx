import { useId, useLayoutEffect, useRef, useState } from 'react'
import { validateEdit, type EditablePath } from '../draftEdits'
import './InlineDraftField.css'

export type PendingFieldEdit = { text: string; error: string | null }

type Props = {
  path: EditablePath
  label: string
  value: unknown
  displayValue: string
  onSelect: () => void
  onApply: (path: EditablePath, text: string) => void
  // Separate unapplied/invalid typing from the applied session for the future save flow.
  onPendingChange: (path: EditablePath, pending: PendingFieldEdit | null) => void
  disabled?: boolean
}

export default function InlineDraftField({ path, label, value, displayValue, onSelect, onApply, onPendingChange, disabled }: Props) {
  const [pending, setPending] = useState<PendingFieldEdit | null>(null)
  const button = useRef<HTMLButtonElement>(null)
  const errorId = useId()
  const valueId = useId()
  const restoreFocus = useRef(false)
  useLayoutEffect(() => {
    if (!pending && restoreFocus.current) {
      restoreFocus.current = false
      button.current?.focus()
    }
  }, [pending])

  function finish(cancel: boolean, focusButton: boolean) {
    if (!pending) return
    const error = cancel ? null : validateEdit(path, pending.text).error
    if (error) {
      const next = { ...pending, error }
      setPending(next)
      onPendingChange(path, next)
      return
    }
    if (!cancel) onApply(path, pending.text)
    restoreFocus.current = focusButton
    setPending(null)
    onPendingChange(path, null)
  }

  return (
    <span className="inline-draft-field">
      <button
        ref={button}
        type="button"
        disabled={disabled}
        className="review-field-value inline-draft-value"
        aria-label={`Edit ${label}`}
        aria-describedby={valueId}
        hidden={pending !== null}
        onClick={() => {
          onSelect()
          const next = { text: typeof value === 'string' ? value : '', error: null }
          setPending(next)
          onPendingChange(path, next)
        }}
      ><span id={valueId}>{displayValue}</span></button>
      {pending && (
        <>
          <input
            disabled={disabled}
            autoFocus
            aria-label={label}
            aria-invalid={!!pending.error}
            aria-describedby={pending.error ? errorId : undefined}
            value={pending.text}
            onFocus={onSelect}
            onChange={(event) => {
              const text = event.target.value
              const next = { text, error: pending.error ? validateEdit(path, text).error : null }
              setPending(next)
              onPendingChange(path, next)
            }}
            onBlur={() => finish(false, false)}
            onKeyDown={(event) => {
              if (event.nativeEvent.isComposing) return
              if (event.key === 'Enter' || event.key === 'Escape') {
                event.preventDefault()
                finish(event.key === 'Escape', true)
              }
            }}
          />
          {pending.error && <span id={errorId} className="field-error" role="alert">{pending.error}</span>}
        </>
      )}
    </span>
  )
}
