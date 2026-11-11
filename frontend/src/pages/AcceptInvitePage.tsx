
import { useState, type SubmitEventHandler } from 'react'
import './AuthPages.css'

type AcceptInvitePageProps = {
  token: string | null
}

export default function AcceptInvitePage({ token }: AcceptInvitePageProps) {
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')

  const handleSubmit: SubmitEventHandler<HTMLFormElement> = (event) => {
    event.preventDefault()
    setError('')

    if (!token) {
      setError('Your invitation link is missing a token.')
      return
    }

    if (!password || !confirmPassword) {
      setError('Please complete both password fields.')
      return
    }

    if (password.length < 8) {
      setError('Your password must contain at least 8 characters.')
      return
    }

    if (password !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }

    // TODO: Submit token and password to the invitation API.
    setError('Invitation acceptance is not available yet.')
  }

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={handleSubmit} noValidate>
        <div className="auth-brand">Operon</div>

        <h1>Accept your invitation</h1>
        <p className="auth-subtitle">
          Create a password to set up your Operon account.
        </p>

        {!token && (
          <p className="auth-error" role="alert">
            This invitation link is invalid or incomplete.
          </p>
        )}

        <div className="auth-field">
          <label htmlFor="invite-password">Password</label>
          <input
            id="invite-password"
            type="password"
            placeholder="Create a password"
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

        <button
          className="auth-button"
          type="submit"
          disabled={!token}
        >
          Accept invitation
        </button>

        <p className="auth-subtitle">
          Already have an account?{' '}
          <a href="#/login">Sign in</a>
        </p>
      </form>
    </div>
  )
}
