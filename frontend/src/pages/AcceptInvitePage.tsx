import { useState, type SubmitEventHandler } from 'react'
import './AuthPages.css'
import {
  acceptInvite,
  MAX_PASSWORD_LENGTH,
  MIN_PASSWORD_LENGTH,
  type AuthUser,
} from '../auth'

type AcceptInvitePageProps = {
  token: string | null
  onSignedIn: (user: AuthUser) => void
}

export default function AcceptInvitePage({ token, onSignedIn }: AcceptInvitePageProps) {
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function accept(inviteToken: string) {
    setSubmitting(true)
    try {
      // The backend creates the account and signs the new user in.
      const user = await acceptInvite(inviteToken, displayName.trim(), password)
      onSignedIn(user)
      // Leaving this page also drops the one-time token from the address bar.
      window.location.hash = '#/'
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : 'Unable to accept the invitation. Please try again.',
      )
      setSubmitting(false)
    }
  }

  const handleSubmit: SubmitEventHandler<HTMLFormElement> = (event) => {
    event.preventDefault()
    if (submitting) return
    setError('')

    if (!token) {
      setError('Your invitation link is missing a token.')
      return
    }

    if (!displayName.trim()) {
      setError('Please enter your name.')
      return
    }

    if (!password || !confirmPassword) {
      setError('Please complete both password fields.')
      return
    }

    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Your password must contain at least ${MIN_PASSWORD_LENGTH} characters.`)
      return
    }

    if (password.length > MAX_PASSWORD_LENGTH) {
      setError(`Your password must contain at most ${MAX_PASSWORD_LENGTH} characters.`)
      return
    }

    if (password !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }

    void accept(token)
  }

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={handleSubmit} noValidate>
        <div className="auth-brand">Operon</div>

        <h1>Accept your invitation</h1>
        <p className="auth-subtitle">
          Choose your name and a password to set up your Operon account.
        </p>

        {!token && (
          <p className="auth-error" role="alert">
            This invitation link is invalid or incomplete.
          </p>
        )}

        <div className="auth-field">
          <label htmlFor="invite-name">Your name</label>
          <input
            id="invite-name"
            type="text"
            placeholder="Full name"
            autoComplete="name"
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            required
          />
        </div>

        <div className="auth-field">
          <label htmlFor="invite-password">Password</label>
          <input
            id="invite-password"
            type="password"
            placeholder={`At least ${MIN_PASSWORD_LENGTH} characters`}
            autoComplete="new-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </div>

        <div className="auth-field">
          <label htmlFor="invite-confirm-password">Confirm password</label>
          <input
            id="invite-confirm-password"
            type="password"
            placeholder="Confirm your password"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            required
          />
        </div>

        {error && (
          <p className="auth-error" role="alert">
            {error}
          </p>
        )}

        <button className="auth-button" type="submit" disabled={!token || submitting}>
          {submitting ? 'Creating account...' : 'Create account'}
        </button>

        <p className="auth-subtitle">
          Already have an account?{' '}
          <a href="#/login">Sign in</a>
        </p>
      </form>
    </div>
  )
}
