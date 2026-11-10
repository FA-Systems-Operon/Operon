import { useEffect, useState } from 'react'
import { ApiError, getReviewDraft, type ReviewDraft, type ReviewStatus } from '../api'
import { reviewRows, type ReviewRow } from '../components/draftSources'
import { formatGenerated } from './ReviewInboxPage'

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

// The quotes behind a row: its own references, then each side of a conflict.
function evidenceFor(row: ReviewRow) {
  return [
    ...row.references.map(({ document_id, quote }) => ({ document_id, quote, value: null })),
    ...row.conflicts.flatMap((conflict) => conflict.alternatives),
  ]
}

export default function ReviewDraftPage({ profileId, versionId }: ReviewDraftPageProps) {
  const [draft, setDraft] = useState<ReviewDraft | null>(null)
  const [notFound, setNotFound] = useState(!profileId || !versionId)
  const [loadFailed, setLoadFailed] = useState(false)
  // Bumped by Try again to fetch the draft once more.
  const [attempt, setAttempt] = useState(0)
  const [selectedKey, setSelectedKey] = useState<string | null>(null)

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

  const { version, client, documents } = draft
  const { rows, unsupported } = reviewRows(version.data)
  const selected = rows.find((row) => row.key === selectedKey) ?? rows[0]

  function documentLabel(id: string) {
    const document = documents.find((candidate) => candidate.id === id)
    if (!document) return 'Unknown document'
    return document.kind
      ? `${document.original_filename} · ${KIND_LABELS[document.kind]}`
      : document.original_filename
  }

  function sourceTag(row: ReviewRow) {
    const evidence = evidenceFor(row)
    if (evidence.length > 1) return `${evidence.length} sources`
    if (evidence.length === 0) return ''
    return documents.find(({ id }) => id === evidence[0].document_id)?.kind ?? 'source'
  }

  function renderEvidence(row: ReviewRow) {
    const evidence = evidenceFor(row)
    return (
      <section className="review-evidence" aria-live="polite" aria-labelledby="evidence-title">
        {row.flag === 'conflict' && <p className="review-flag">▲ Sources disagree</p>}
        {row.flag === 'missing' && <p className="review-flag">○ Missing information</p>}
        <h2 id="evidence-title">{row.label}</h2>
        {row.conflicts.map((conflict, index) => (
          <p key={index} className="field-note">
            {conflict.explanation}
          </p>
        ))}
        {evidence.length === 0 ? (
          <p className="field-note">
            {row.flag === 'missing'
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
            {row.flag === 'conflict' && (
              <p className="field-note">
                Operon won't pick one. A reviewer decides which value to keep.
              </p>
            )}
            <p className="review-matched">✓ Quotes were matched word for word in the files.</p>
          </>
        )}
      </section>
    )
  }

  return (
    <section className="review-draft">
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

      <div className="review-draft-body">
        <div className="review-fields">
          {unsupported && (
            <p className="field-error">
              Some warnings could not be shown. Check the saved draft data.
            </p>
          )}
          <ul className="review-list">
            {rows.map((row) => (
              <li key={row.key}>
                <button
                  className="review-field"
                  type="button"
                  data-flag={row.flag ?? undefined}
                  aria-pressed={row === selected}
                  onClick={() => setSelectedKey(row.key)}
                >
                  <span className="review-field-label">
                    {row.flag === 'conflict' && <span aria-hidden="true">▲ </span>}
                    {row.flag === 'missing' && <span aria-hidden="true">○ </span>}
                    {row.label}
                  </span>
                  <span className="review-field-value">{row.value}</span>
                  <span className="mono">{sourceTag(row)}</span>
                </button>
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
