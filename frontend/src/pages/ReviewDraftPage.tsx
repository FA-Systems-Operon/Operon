import { useEffect, useRef, useState } from 'react'
import { ApiError, getReviewDraft, saveReviewEdits, type ProfileVersion, type ReviewDraft, type ReviewStatus } from '../api'
import { editableReviewRows, reviewRows, type ReviewRow } from '../components/draftSources'
import InlineDraftField, { type PendingFieldEdit } from '../components/InlineDraftField'
import RejectDraft from '../components/RejectDraft'
import { applyEdit, createEditSession, fieldValue, isEditablePath, type EditablePath } from '../draftEdits'
import { formatGenerated } from './ReviewInboxPage'
import { draftSaveGate, type SaveStatus } from '../draftSave'
import { reviewDraftHref } from '../router'

const STATUS_LABELS: Record<ReviewStatus, string> = {
  draft: 'Draft',
  in_review: 'In review',
  approved: 'Approved',
  rejected: 'Rejected',
  stale: 'Stale',
}

const KIND_LABELS = { transcript: 'Transcript', intake: 'Intake' }

type ReviewDraftPageProps = {
  // From the inbox link; null when the link is missing one.
  profileId: string | null
  versionId: string | null
}

const quoteKey = ({ document_id, quote }: { document_id: string; quote: string }) =>
  JSON.stringify([document_id, quote])

// The quotes behind a row: its own references, then each side of a conflict. A quote
// that is both (same document and words) shows once, as the side with its value.
function evidenceFor(row: ReviewRow) {
  const sides = row.conflicts.flatMap((conflict) => conflict.alternatives)
  const sideKeys = new Set(sides.map(quoteKey))
  const evidence = [
    ...row.references
      .filter((reference) => !sideKeys.has(quoteKey(reference)))
      .map(({ document_id, quote }) => ({ document_id, quote, value: null as string | null })),
    ...sides,
  ]
  return evidence.filter(
    (item, index) => evidence.findIndex((other) => quoteKey(other) === quoteKey(item)) === index,
  )
}

export default function ReviewDraftPage({ profileId, versionId }: ReviewDraftPageProps) {
  const [draft, setDraft] = useState<ReviewDraft | null>(null)
  const [notFound, setNotFound] = useState(!profileId || !versionId)
  const [loadFailed, setLoadFailed] = useState(false)
  // Bumped by Try again to fetch the draft once more.
  const [attempt, setAttempt] = useState(0)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (!profileId || !versionId) return
    // Ignore a reply that arrives after the page has closed.
    let active = true
    getReviewDraft(profileId, versionId)
      .then((loaded) => {
        if (active) setDraft(loaded)
      })
      .catch((error) => {
        if (!active) return
        if (error instanceof ApiError && error.status === 404) setNotFound(true)
        else setLoadFailed(true)
      })
    return () => {
      active = false
    }
  }, [profileId, versionId, attempt])

  function retry() {
    setLoadFailed(false)
    setAttempt((previous) => previous + 1)
  }

  const back = (
    <a className="back-link" href="#/reviews">
      ← Review inbox
    </a>
  )

  if (notFound || loadFailed || !draft) {
    let message = <p className="field-note" role="status">Loading draft…</p>
    if (notFound) {
      message = <p className="field-note">This draft wasn't found. It may have been removed.</p>
    } else if (loadFailed) {
      message = (
        <div className="review-error">
          <p className="field-error" role="alert">
            Couldn't load this draft.
          </p>
          <button className="button" type="button" onClick={retry}>
            Try again
          </button>
        </div>
      )
    }
    return (
      <section className="review-draft">
        {back}
        <h1 className="visually-hidden">Draft review</h1>
        {message}
      </section>
    )
  }

  function onSaved(version: ProfileVersion) {
    setSaved(true)
    setDraft((previous) => previous && { ...previous, version })
    // Replacing avoids leaving a superseded draft as the reload destination.
    window.history.replaceState(null, '', reviewDraftHref(version.client_profile_id, version.id))
    // replaceState does not emit hashchange; update the router's snapshot too.
    window.dispatchEvent(new HashChangeEvent('hashchange'))
  }

  // Same version, new status: the page stays put and shows it as rejected.
  function onRejected(version: ProfileVersion) {
    setSaved(false)
    setDraft((previous) => previous && { ...previous, version })
  }

  return <LoadedDraft key={`${draft.version.client_profile_id}/${draft.version.id}`} draft={draft} back={back} saved={saved} onSaved={onSaved} onRejected={onRejected} />
}

function LoadedDraft({ draft, back, saved, onSaved, onRejected }: {
  draft: ReviewDraft; back: React.ReactNode; saved: boolean
  onSaved: (version: ProfileVersion) => void; onRejected: (version: ProfileVersion) => void
}) {
  const [session, setSession] = useState(() => createEditSession(draft))
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const [pendingFields, setPendingFields] = useState<Partial<Record<EditablePath, PendingFieldEdit>>>({})
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle')
  const [saveError, setSaveError] = useState('')
  // A reject request in flight: Save and Approve wait so its result can't be hidden.
  const [rejecting, setRejecting] = useState(false)
  const saving = useRef(false)
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])
  const dirty = Object.keys(session.changes).length > 0
  const { version, client, documents } = draft
  const editable = version.status === 'draft' || version.status === 'in_review'
  const pending = Object.keys(pendingFields).length > 0
  const gate = draftSaveGate(version.status, dirty, pending, saveStatus)
  const historicalEvidence = dirty || version.data.assessment === null
  // Evidence always comes from the original version, even after a correction.
  const { rows, unsupported } = (editable ? editableReviewRows : reviewRows)(version.data)
  const selected = rows.find((row) => row.key === selectedKey) ?? rows[0]
  async function save() {
    if (!gate.canSave || rejecting || saving.current) return
    saving.current = true
    setSaveStatus('saving')
    setSaveError('')
    const changes = Object.fromEntries(Object.entries(session.changes).map(([path, change]) => [path, change!.currentValue]))
    try {
      const version = await saveReviewEdits(session.base.profileId, session.base.versionId, changes)
      if (!mounted.current) return
      setSession(createEditSession({ ...draft, version }))
      setSaveStatus('saved')
      onSaved(version)
    } catch (error) {
      if (!mounted.current) return
      const stale = error instanceof ApiError && error.status === 409
      setSaveStatus(stale ? 'stale' : 'error')
      setSaveError(stale
        ? 'This draft changed or is no longer editable. Your edits are still here. Open the latest draft from the review inbox before continuing.'
        : error instanceof ApiError && error.status === 422
          ? "Couldn't save these edits. Check the field values and try saving again."
          : "Couldn't confirm that your edits were saved. Your edits are still here. Try saving again.")
    } finally {
      saving.current = false
    }
  }
  function rejected(version: ProfileVersion) {
    // Rejecting drops unsaved edits; the rejected version is read-only.
    setSession(createEditSession({ ...draft, version }))
    setPendingFields({})
    setSaveStatus('idle')
    setSaveError('')
    onRejected(version)
  }
  function pendingChange(path: EditablePath, pending: PendingFieldEdit | null) {
    setPendingFields((previous) => {
      const next = { ...previous }
      if (pending) next[path] = pending
      else delete next[path]
      return next
    })
  }
  function documentLabel(id: string) {
    const document = documents.find((candidate) => candidate.id === id)
    if (!document) return 'Unknown document'
    return document.kind
      ? `${document.original_filename} · ${KIND_LABELS[document.kind]}`
      : document.original_filename
  }

  function sourceTag(row: ReviewRow) {
    const evidence = evidenceFor(row)
    if (evidence.length > 1) return `${evidence.length} ${historicalEvidence ? 'original sources' : 'sources'}`
    if (evidence.length === 0) return ''
    return documents.find(({ id }) => id === evidence[0].document_id)?.kind ?? 'source'
  }

  const originalDisplayValue = (row: ReviewRow) =>
    historicalEvidence && row.flag === 'conflict' && fieldValue(session.currentData, row.key as EditablePath) == null
      ? `Original proposal: ${row.value}` : row.value

  function renderEvidence(row: ReviewRow) {
    const evidence = evidenceFor(row)
    return (
      <section className="review-evidence" aria-live="polite" aria-labelledby="evidence-title">
        {!historicalEvidence && row.flag === 'conflict' && <p className="review-flag">▲ Sources disagree</p>}
        {!historicalEvidence && row.flag === 'missing' && <p className="review-flag">○ Missing information</p>}
        <h2 id="evidence-title">{row.label}</h2>
        {dirty && <p className="field-note">Original version evidence. These sources do not verify local corrections.</p>}
        {!dirty && historicalEvidence && <p className="field-note">Original source evidence is retained as history and does not verify reviewer corrections. {(version.data.conflicts?.length ?? 0) > 0 && 'Conflicts remain unresolved.'}</p>}
        {row.conflicts.map((conflict, index) => (
          <p key={index} className="field-note">
            {conflict.explanation}
          </p>
        ))}
        {evidence.length === 0 ? (
          <p className="field-note">
            {!historicalEvidence && row.flag === 'missing'
              ? 'Not found in the transcript or intake answers.'
              : 'No source linked to this field.'}
          </p>
        ) : (
          <>
            <ul className="review-list review-quotes">
              {evidence.map((item, index) => (
                <li key={index}>
                  <span className="review-quote-source">{documentLabel(item.document_id)}</span>
                  {item.value && <strong>{item.value}</strong>}
                  <q>{item.quote}</q>
                </li>
              ))}
            </ul>
            {!historicalEvidence && row.flag === 'conflict' && (
              <p className="field-note">
                Operon won't pick one. A reviewer decides which value to keep.
              </p>
            )}
          </>
        )}
      </section>
    )
  }

  return (
    <section className="review-draft" data-approval-blocked={gate.blocksApproval}>
      {back}
      <header className="review-draft-head">
        <div>
          <h1>{client.name}</h1>
          <p className="lead">Draft from the sales call and intake answers</p>
        </div>
        <p className="review-draft-meta">
          <span className="review-pill">{STATUS_LABELS[version.status]}</span>
          <span>Version {version.version_number}</span>
          <time dateTime={version.created_at}>{formatGenerated(version.created_at)}</time>
        </p>
      </header>

      {dirty && <p role="status" className="field-note">Unsaved local changes. Information checks apply to the original version.</p>}
      {!dirty && saved && saveStatus !== 'error' && saveStatus !== 'stale' && <p role="status" className="field-note">Draft edits saved.</p>}
      {version.status === 'rejected' && (
        <div className="review-rejected" role="status">
          <p><strong>Rejected</strong>{version.rejected_at && <> · <time dateTime={version.rejected_at}>{formatGenerated(version.rejected_at)}</time></>}</p>
          {version.rejection_reason && <p className="field-note">Reason: {version.rejection_reason}</p>}
        </div>
      )}
      {version.data.assessment === null && <p className="field-note">Information checks have not been recomputed for this version.</p>}
      {editable && (
        <div className="review-save">
          <button className="button" type="button" disabled={!gate.canSave || rejecting} onClick={save}>
            {saveStatus === 'saving' ? 'Saving…' : saveStatus === 'error' ? 'Try saving again' : 'Save changes'}
          </button>
          {pending && <p className="field-note">Finish or cancel the current edit before saving.</p>}
          {gate.blocksApproval && <p className="field-note">Approval requires saved edits with no pending input or save errors.</p>}
          {saveError && <p className="field-error" role="alert">{saveError}</p>}
          <RejectDraft
            profileId={version.client_profile_id}
            versionId={version.id}
            disabled={saveStatus === 'saving' || saveStatus === 'stale'}
            hasUnsavedEdits={dirty || pending}
            onRejected={rejected}
            onRejectingChange={setRejecting}
          />
        </div>
      )}
      {Object.values(pendingFields).some((pending) => pending?.error) && (
        <p className="field-error">Some edits have not been applied. Correct them or press Escape to cancel.</p>
      )}
      <div className="review-draft-body">
        <div className="review-fields">
          {unsupported && (
            <p className="field-error">
              {dirty ? 'Some original-version warnings could not be shown. Check the saved draft data.'
                : 'Some warnings could not be shown. Check the saved draft data.'}
            </p>
          )}
          <ul className="review-list">
            {rows.map((row) => (
              <li key={row.key}>
                <div
                  className="review-field review-field-row"
                  data-flag={!historicalEvidence ? row.flag ?? undefined : undefined}
                  data-selected={row === selected}
                >
                  <button
                    className="review-field-label review-field-selector"
                    type="button"
                    aria-pressed={row === selected}
                    onClick={() => setSelectedKey(row.key)}
                  >
                    {!historicalEvidence && row.flag === 'conflict' && <span aria-hidden="true">▲ </span>}
                    {!historicalEvidence && row.flag === 'missing' && <span aria-hidden="true">○ </span>}
                    {row.label}
                  </button>
                  {editable && isEditablePath(session.originalData, row.key) ? (
                    <InlineDraftField
                      disabled={saveStatus === 'saving' || saveStatus === 'stale'}
                      path={row.key}
                      label={row.label}
                      value={fieldValue(session.currentData, row.key)}
                      displayValue={session.changes[row.key]
                        ? session.changes[row.key]!.currentValue ?? 'Not mentioned' : originalDisplayValue(row)}
                      onSelect={() => setSelectedKey(row.key)}
                      onApply={(path, text) => setSession((previous) => applyEdit(previous, path, text))}
                      onPendingChange={pendingChange}
                    />
                  ) : <span className="review-field-value">{originalDisplayValue(row)}</span>}
                  <span className="mono">
                    {sourceTag(row)}
                    {isEditablePath(session.originalData, row.key) && session.changes[row.key] && (
                      <span className="review-edited">Reviewer-edited</span>
                    )}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </div>
        {selected ? (
          renderEvidence(selected)
        ) : (
          <p className="review-evidence field-note">This version has no proposed fields.</p>
        )}
      </div>
    </section>
  )
}
