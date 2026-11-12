import { useState, type SubmitEventHandler } from 'react'
import './AuthPages.css'
import { createInvite, inviteLink, type AuthUser, type Invite } from '../auth'

type InviteUserPageProps = {
  user: AuthUser | null
}

// Admin page: create an invitations, manage users/permissions, dashboards for things like audits and user details, etc
// Everyone invited starts with the same default role; roles are changed later.
export default function InviteUserPage({ user }: InviteUserPageProps) {
  const [email, setEmail] = useState('')
  const [invite, setInvite] = useState<Invite | null>(null)
  const [error, setError] = useState('')
  const [copyMessage, setCopyMessage] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // The backend enforces this too; the page just doesn't offer the form to others.
  if (user?.role !== 'admin') {
    return (
      <section className="invite-page">
        <p role="alert">Only admins can invite people.</p>
      </section>
    )
  }

  async function create() {
    setSubmitting(true)
    try {
      setInvite(await createInvite(email.trim()))
      setCopyMessage('')
    } catch (caught) {
      setInvite(null)
      setError(caught instanceof Error ? caught.message : 'Unable to create the invitation.')
    } finally {
      setSubmitting(false)
    }
  }

  const handleSubmit: SubmitEventHandler<HTMLFormElement> = (event) => {
    event.preventDefault()
    if (submitting) return
    setError('')

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setError('Enter a valid email address.')
      return
    }

    void create()
  }

  const link = invite ? inviteLink(invite.invite_token) : ''

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(link)
      setCopyMessage('Link copied.')
    } catch {
      setCopyMessage('Could not copy automatically. Select the link and copy it.')
    }
  }

  return (
    <section className="invite-page">
      <form className="auth-card" onSubmit={handleSubmit} noValidate>
        <h1>Invite someone</h1>
        <p className="auth-subtitle">
          Create a one-time link. Send it to them yourself; it works once.
        </p>

        <div className="auth-field">
          <label htmlFor="invite-email">Email address</label>
          <input
            id="invite-email"
            type="email"
            placeholder="name@company.com"
            autoComplete="off"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
        </div>

        {error && (
          <p className="auth-error" role="alert">
            {error}
          </p>
        )}

        <button className="auth-button" type="submit" disabled={submitting}>
          {submitting ? 'Creating link...' : 'Create invite link'}
        </button>

        {invite && (
          <div className="invite-result">
            <p className="auth-subtitle">
              Link for {invite.email}, valid until{' '}
              {new Date(invite.expires_at).toLocaleString()}. It is shown only once, and a new
              invite for this email replaces it.
            </p>
            <div className="auth-field">
              <label htmlFor="invite-link">Invitation link</label>
              <input id="invite-link" type="text" readOnly value={link} />
            </div>
            <button className="auth-button" type="button" onClick={() => void copyLink()}>
              Copy link
            </button>
            {copyMessage && <p role="status">{copyMessage}</p>}
          </div>
        )}
      </form>
    </section>
  )
}
