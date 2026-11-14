import { useEffect, useRef, useState } from 'react'
import {
  ApiError,
  getOnboardingJob,
  listClients,
  startOnboardingJob,
  type OnboardingJob,
} from '../api'
import { reviewDraftHref } from '../router'

// How often the page asks for the job's status while the draft is being made -> every 2s
const POLL_MS = 2000
// Stop asking when the status hasn't changed for this long. The backend already
// treats a job running for over 10 minutes as abandoned and restarts it.
const STALL_MS = 15 * 60 * 1000

type DraftProgressPageProps = {
  // From the link the upload page opens; null when the link is missing one.
  clientId: string | null
  jobId: string | null
  // How long to wait between status checks, and before giving up (shorter in tests).
  pollMs?: number
  stallMs?: number
}

type StepState = 'done' | 'current' | 'failed' | 'upcoming'

type Step = {
  title: string
  detail: string
  state: StepState
  at?: string | null
  duration?: string
}

// Read out before each step, since the marks are only drawn.
const STATE_LABELS: Record<StepState, string> = {
  done: 'Done',
  current: 'In progress',
  failed: 'Failed',
  upcoming: 'Not started',
}

// 24-hour clock time, like 09:14.
export function clockTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
}

// Time between two moments, like 0:38 or 12:05. -> used for draft step duration 
export function duration(fromIso: string, toMs: number): string {
  const seconds = Math.max(0, Math.floor((toMs - Date.parse(fromIso)) / 1000))
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

function isFinished(job: OnboardingJob): boolean {
  return job.status === 'succeeded' || job.status === 'failed'
}

// A pending job that has already run once is waiting for an automatic retry.
function isRetrying(job: OnboardingJob): boolean {
  return job.status === 'pending' && job.attempts > 0
}

function draftingStep(job: OnboardingJob, now: number): Step {
  const step: Step = {
    title: 'Drafting',
    detail: 'Reading both files and citing each field',
    state: 'current',
  }
  if (job.status === 'pending' && !isRetrying(job)) {
    return { ...step, state: 'upcoming' }
  }
  if (isRetrying(job)) {
    return { ...step, detail: `Trying again soon. ${job.error ?? ''}`.trim() }
  }
  if (job.status === 'running') {
    return { ...step, duration: job.started_at ? duration(job.started_at, now) : undefined }
  }
  const took =
    job.started_at && job.finished_at
      ? duration(job.started_at, Date.parse(job.finished_at))
      : undefined
  if (job.status === 'failed') {
    return { ...step, state: 'failed', detail: job.error ?? 'The draft failed.', duration: took }
  }
  return { ...step, state: 'done', duration: took }
}

function stepsFor(job: OnboardingJob, now: number): Step[] {
  const queued = job.status === 'pending' && !isRetrying(job)
  const ready = job.status === 'succeeded'
  return [
    // The job is created right after both files are saved, so it shares their time.
    {
      title: 'Files saved',
      detail: 'Transcript and intake answers, kept as uploaded',
      state: 'done',
      at: job.created_at,
    },
    {
      title: 'Queued',
      detail: 'Saved before running, so it can be retried',
      state: queued ? 'current' : 'done',
      at: job.created_at,
    },
    draftingStep(job, now),
    {
      title: 'Ready for review',
      detail: ready ? 'Waiting for a reviewer in Reviews' : '',
      state: ready ? 'done' : 'upcoming',
      at: ready ? job.finished_at : null,
    },
  ]
}

function runLabel(job: OnboardingJob): string {
  if (isRetrying(job)) return 'Retrying'
  return {
    pending: 'Queued',
    running: 'Running',
    succeeded: 'Succeeded',
    failed: 'Failed',
  }[job.status]
}

function heading(job: OnboardingJob | null, name: string | null): string {
  const forName = name ? ` for ${name}` : ''
  if (job?.status === 'succeeded') return `Draft ready${forName}`
  if (job?.status === 'failed') return `Draft failed${forName}`
  return name ? `Drafting ${name}` : 'Drafting'
}

function leadFor(job: OnboardingJob | null): string {
  if (job?.status === 'succeeded') return 'Open it to check each field against its source.'
  if (job?.status === 'failed') {
    return 'Both files are saved. Try again, or upload new files if it keeps failing.'
  }
  return 'You can leave this page. The draft will be waiting in Reviews.'
}

export default function DraftProgressPage({
  clientId,
  jobId,
  pollMs = POLL_MS,
  stallMs = STALL_MS,
}: DraftProgressPageProps) {
  const [job, setJob] = useState<OnboardingJob | null>(null)
  const [clientName, setClientName] = useState<string | null>(null)
  const [notFound, setNotFound] = useState(!clientId || !jobId)
  // A status check failed; the page keeps the last status and keeps asking.
  const [checkFailed, setCheckFailed] = useState(false)
  // Bumped after every status check, to schedule the next one.
  const [checks, setChecks] = useState(0)
  const [restarting, setRestarting] = useState(false)
  const [restartFailed, setRestartFailed] = useState(false)
  const [now, setNow] = useState(() => Date.now())
  // The status stayed the same for STALL_MS, so the page stopped asking.
  const [stalled, setStalled] = useState(false)
  // When the status last changed, and what it was. Refs: changing them doesn't redraw.
  const lastChange = useRef(Date.now())
  const lastStatus = useRef('')

  const finished = job !== null && isFinished(job)
  const running = job?.status === 'running'

  // The client's name for the title
  useEffect(() => {
    if (!clientId) return
    let active = true
    listClients()
      .then((clients) => {
        const client = clients.find(({ id }) => id === clientId)
        if (active && client) setClientName(client.name)
      })
      .catch(() => {})
    return () => {
      active = false
    }
  }, [clientId])

  // Ask for the job's status right away, then again after each answer until it finishes.
  // Paused while the tab is hidden (like the Reviews badge), and stopped when nothing
  // has changed for STALL_MS.
  useEffect(() => {
    if (!clientId || !jobId || notFound || finished || stalled) return
    // Both are set past the line above; the names keep that for the functions below.
    const client = clientId
    const id = jobId
    // Ignore an answer that arrives after the page has closed.
    let active = true
    // A check came due while the tab was hidden; showing the tab runs it.
    let paused = false

    function check() {
      if (document.hidden) {
        paused = true
        return
      }
      getOnboardingJob(client, id)
        .then((latest) => {
          if (!active) return
          const status = `${latest.status}/${latest.attempts}`
          if (status !== lastStatus.current) {
            lastStatus.current = status
            lastChange.current = Date.now()
          }
          setJob(latest)
          setCheckFailed(false)
        })
        .catch((error) => {
          if (!active) return
          if (error instanceof ApiError && error.status === 404) setNotFound(true)
          else setCheckFailed(true)
        })
        .finally(() => {
          if (!active) return
          if (Date.now() - lastChange.current >= stallMs) setStalled(true)
          else setChecks((previous) => previous + 1)
        })
    }

    function checkWhenShown() {
      if (paused && !document.hidden) {
        paused = false
        check()
      }
    }

    const timer = window.setTimeout(check, checks === 0 ? 0 : pollMs)
    document.addEventListener('visibilitychange', checkWhenShown)
    return () => {
      active = false
      window.clearTimeout(timer)
      document.removeEventListener('visibilitychange', checkWhenShown)
    }
  }, [clientId, jobId, notFound, finished, stalled, checks, pollMs, stallMs])

  // Tick the Drafting timer every second while the agent runs.
  useEffect(() => {
    if (!running) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [running])

  // Asking for the same two files again restarts a failed job. The address uses the
  // client from this page's link, not one from the reply: the API only answered
  // with this job because it belongs to that client.
  async function handleRetry(failed: OnboardingJob, owner: string) {
    setRestarting(true)
    setRestartFailed(false)
    try {
      setJob(
        await startOnboardingJob(owner, failed.transcript_document_id, failed.intake_document_id),
      )
      // A restart is a change, so the 15 minutes start again.
      lastChange.current = Date.now()
    } catch {
      setRestartFailed(true)
    }
    setRestarting(false)
  }

  function handleCheckAgain() {
    lastChange.current = Date.now()
    setStalled(false)
  }

  const back = (
    <a className="button" href="#/">
      Back to Command
    </a>
  )

  if (notFound) {
    return (
      <section className="draft-progress">
        <h1>Draft not found</h1>
        <p className="lead">This link doesn't point to a draft that was started.</p>
        <div className="draft-actions">{back}</div>
      </section>
    )
  }

  const draftHref =
    job?.status === 'succeeded' && job.result_profile_id && job.result_version_id
      ? reviewDraftHref(job.result_profile_id, job.result_version_id)
      : null

  return (
    <section className="draft-progress">
      <h1>{heading(job, clientName)}</h1>
      <p className="lead">{leadFor(job)}</p>

      {job ? (
        <>
          <ol className="draft-steps">
            {stepsFor(job, now).map((step) => (
              <li
                key={step.title}
                className="draft-step"
                data-state={step.state}
                aria-current={step.state === 'current' ? 'step' : undefined}
              >
                <span className="draft-step-mark" aria-hidden="true" />
                <div>
                  <p className="draft-step-title">
                    <span className="visually-hidden">{STATE_LABELS[step.state]}: </span>
                    {step.title}
                  </p>
                  {step.detail && <p className="draft-step-detail">{step.detail}</p>}
                </div>
                {step.duration && <span className="mono">{step.duration}</span>}
                {!step.duration && step.at && (
                  <time className="mono" dateTime={step.at}>
                    {clockTime(step.at)}
                  </time>
                )}
              </li>
            ))}
          </ol>

          <dl className="draft-summary">
            <div className="draft-summary-item">
              <dt>Run</dt>
              <dd data-status={job.status}>{runLabel(job)}</dd>
            </div>
            <div className="draft-summary-item">
              <dt>Review</dt>
              <dd>{job.status === 'succeeded' ? 'Ready to review' : 'Not started'}</dd>
            </div>
          </dl>
        </>
      ) : (
        !checkFailed && (
          <p className="field-note" role="status">
            Loading the draft's status…
          </p>
        )
      )}

      {checkFailed && (
        <p className="field-error" role="alert">
          {job
            ? "Couldn't check for updates. Trying again…"
            : "Couldn't load the draft's status. Trying again…"}
        </p>
      )}
      {restartFailed && (
        <p className="field-error" role="alert">
          Couldn't restart the draft. Try again.
        </p>
      )}
      {stalled && (
        <p className="field-note" role="status">
          No change for a while, so this page stopped checking. The draft keeps going on the
          server.
        </p>
      )}

      <div className="draft-actions">
        {draftHref && (
          <a className="button button-primary" href={draftHref}>
            Open draft
          </a>
        )}
        {job?.status === 'failed' && (
          <button
            className="button button-primary"
            type="button"
            disabled={restarting}
            // A job only loads when the link has a client, so clientId is set here.
            onClick={() => handleRetry(job, clientId!)}
          >
            Try again
          </button>
        )}
        {stalled && (
          <button className="button" type="button" onClick={handleCheckAgain}>
            Check again
          </button>
        )}
        {back}
      </div>
    </section>
  )
}
