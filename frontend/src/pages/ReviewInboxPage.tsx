import { useEffect, useState } from 'react'
import { listReviews, type ReviewInboxItem } from '../api'
import { reviewDraftHref } from '../router'

const STATUS_LABELS: Record<ReviewInboxItem['status'], string> = {
  draft: 'Draft',
  in_review: 'In review',
}

// In the reviewer's own locale and time zone, e.g. "Nov 9, 2026, 2:03 PM".
export function formatGenerated(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export default function ReviewInboxPage() {
  const [items, setItems] = useState<ReviewInboxItem[] | null>(null)
  const [loadFailed, setLoadFailed] = useState(false)
  // Bumped by Try again to fetch the list once more.
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    // Ignore a reply that arrives after the page has closed.
    let active = true
    listReviews()
      .then((list) => {
        if (active) setItems(list)
      })
      .catch(() => {
        if (active) setLoadFailed(true)
      })
    return () => {
      active = false
    }
  }, [attempt])

  function retry() {
    setLoadFailed(false)
    setAttempt((previous) => previous + 1)
  }

  let content
  if (loadFailed) {
    content = (
      <div className="review-error">
        <p className="field-error" role="alert">
          Couldn't load the drafts waiting for review.
        </p>
        <button className="button" type="button" onClick={retry}>
          Try again
        </button>
      </div>
    )
  } else if (items === null) {
    content = <p className="field-note" role="status">Loading drafts…</p>
  } else if (items.length === 0) {
    content = <p className="field-note">No drafts waiting for review.</p>
  } else {
    // Already newest first from the API. One row per profile, so key by version.
    content = (
      <div className="review-card">
        {/* Each row link reads on its own, so the headers are only visual. */}
        <div className="review-row review-head" aria-hidden="true">
          <span>Client</span>
          <span>Generated</span>
          <span>Version</span>
          <span>Status</span>
        </div>
        <ul className="review-list">
          {items.map((item) => (
            <li key={item.version_id}>
              <a
                className="review-row"
                href={reviewDraftHref(item.client_profile_id, item.version_id)}
              >
                <span className="review-client">{item.client_name}</span>
                <time dateTime={item.created_at}>{formatGenerated(item.created_at)}</time>
                <span>v{item.version_number}</span>
                <span className="review-status" data-status={item.status}>
                  {STATUS_LABELS[item.status]}
                </span>
              </a>
            </li>
          ))}
        </ul>
      </div>
    )
  }

  return (
    <section className="review-inbox">
      <h1>Review inbox</h1>
      <p className="lead">Drafts waiting for a reviewer, newest first.</p>
      {content}
    </section>
  )
}
