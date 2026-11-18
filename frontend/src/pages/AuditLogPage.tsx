import { useEffect, useState } from 'react'
import { ApiError, listAuditEvents, type AuditAction, type AuditEvent } from '../api'
import type { AuthUser } from '../auth'

type AuditLogPageProps = {
  user: AuthUser | null
}

const ACTION_LABELS: Record<AuditAction, string> = {
  upload: 'Uploaded',
  job_started: 'Started draft',
  job_requeued: 'Restarted draft',
  draft_created: 'Draft created',
  edit: 'Edited',
  approve: 'Approved',
  reject: 'Rejected',
}

// An action this page doesn't know yet is shown as recorded, e.g. "job_requeued".
export function actionLabel(action: string): string {
  return ACTION_LABELS[action as AuditAction] ?? action
}

// In the admin's own locale and time zone, with seconds: events can be close together.
export function formatWhen(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'medium' })
}

// What the action was done to, in words. The ID is the fallback when the object is gone.
export function describeObject(event: AuditEvent): string {
  switch (event.object_type) {
    case 'client_profile':
      return event.version_number === null ? 'Profile' : `Profile v${event.version_number}`
    case 'source_document':
      return event.document_filename ?? 'Document'
    case 'onboarding_job':
      return 'Onboarding job'
    default:
      return event.object_type
  }
}

// Admin page: every recorded upload, job, draft, edit, approval and rejection, newest first.
export default function AuditLogPage({ user }: AuditLogPageProps) {
  const isAdmin = user?.role === 'admin'
  const [events, setEvents] = useState<AuditEvent[] | null>(null)
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  // The cursor of the page being fetched: undefined when idle, null for the first page.
  const [loading, setLoading] = useState<string | null | undefined>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!isAdmin || loading === undefined) return
    // Ignore a reply that arrives after the page has closed.
    let active = true
    listAuditEvents(loading)
      .then((page) => {
        if (!active) return
        setEvents((previous) => (loading === null ? page.items : [...(previous ?? []), ...page.items]))
        setNextCursor(page.next_cursor)
        setLoading(undefined)
      })
      .catch((caught: unknown) => {
        if (!active) return
        setError(
          caught instanceof ApiError && caught.status === 403
            ? 'Only admins can view the audit log.'
            : "Couldn't load the audit log.",
        )
        setLoading(undefined)
      })
    return () => {
      active = false
    }
  }, [isAdmin, loading])

  // The backend enforces this too; the page just doesn't ask for the log.
  if (!isAdmin) {
    return (
      <section className="audit-log">
        <p role="alert">Only admins can view the audit log.</p>
      </section>
    )
  }

  // Try again repeats whichever page failed; the rows already shown stay.
  function retry() {
    setError('')
    setLoading(events === null ? null : nextCursor)
  }

  const loadingMore = loading !== undefined && events !== null

  return (
    <section className="audit-log">
      <h1>Audit log</h1>
      <p className="lead">
        Every upload, draft, edit, approval and rejection, with who did it. Newest first.
      </p>

      {events === null && loading !== undefined && (
        <p className="field-note" role="status">
          Loading audit events…
        </p>
      )}

      {events !== null && events.length === 0 && (
        <p className="field-note">No audit events recorded yet.</p>
      )}

      {events !== null && events.length > 0 && (
        <div className="review-card audit-card">
          <table className="audit-table">
            <thead>
              <tr>
                <th scope="col">When</th>
                <th scope="col">Who</th>
                <th scope="col">Action</th>
                <th scope="col">What</th>
                <th scope="col">Client</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <tr key={event.id}>
                  <td>
                    <time dateTime={event.created_at}>{formatWhen(event.created_at)}</time>
                  </td>
                  <td title={event.actor_email}>{event.actor_name}</td>
                  <td className="audit-action" data-action={event.action}>
                    {actionLabel(event.action)}
                  </td>
                  <td>
                    <span className="audit-object">{describeObject(event)}</span>
                    <code className="audit-id" title={event.version_id ?? event.object_id}>
                      {(event.version_id ?? event.object_id).slice(0, 8)}
                    </code>
                  </td>
                  <td>{event.client_name ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {error && (
        <div className="review-error">
          <p className="field-error" role="alert">
            {error}
          </p>
          <button className="button" type="button" onClick={retry}>
            Try again
          </button>
        </div>
      )}

      {!error && nextCursor && (
        <button
          className="button audit-more"
          type="button"
          disabled={loadingMore}
          onClick={() => setLoading(nextCursor)}
        >
          {loadingMore ? 'Loading…' : 'Load older events'}
        </button>
      )}
    </section>
  )
}
