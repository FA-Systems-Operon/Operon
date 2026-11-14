export type Role = 'admin' | 'reviewer' | 'viewer'

export type AuthUser = {
  id: string
  email: string
  display_name: string
  role: Role
}

export type AuthStatus =
  | 'loading'
  | 'authenticated'
  | 'unauthenticated'

// Must match the backend (SESSION_COOKIE / CSRF_COOKIE rules in backend/src/auth.py).
const CSRF_COOKIE = 'operon_csrf'
export const MIN_PASSWORD_LENGTH = 12
export const MAX_PASSWORD_LENGTH = 128

// The backend sets this cookie at login. JavaScript can read it on purpose: every
// request that changes data (POST, PUT, PATCH, DELETE) sends it back in this header.
export function getCsrfToken(): string {
  const prefix = `${CSRF_COOKIE}=`
  const entry = document.cookie.split('; ').find((c) => c.startsWith(prefix))
  return entry ? entry.slice(prefix.length) : ''
}

// FastAPI puts a readable reason in "detail" for errors we raise (a list for automatic
// validation errors, which we don't show as-is).
async function errorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json()
    if (typeof body.detail === 'string') return body.detail
  } catch {
    // No JSON body: use the fallback.
  }
  return fallback
}

// Checks whether the browser has a valid server-side session.
export async function getCurrentUser(): Promise<AuthUser | null> {
  const response = await fetch('/api/v1/me', {
    method: 'GET',
    credentials: 'include',
  })

  // No valid session exists.
  if (response.status === 401) {
    return null
  }

  if (!response.ok) {
    throw new Error('Unable to verify your session.')
  }

  return response.json() as Promise<AuthUser>
}

export async function login(email: string, password: string): Promise<AuthUser> {
  const response = await fetch('/api/v1/auth/login', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })

  // Too many failed attempts for this email; Retry-After is in seconds.
  if (response.status === 429) {
    const minutes = Math.max(1, Math.ceil((Number(response.headers.get('Retry-After')) || 0) / 60))
    throw new Error(
      `Too many failed attempts. Try again in ${minutes} minute${minutes === 1 ? '' : 's'}.`,
    )
  }

  if (!response.ok) {
    throw new Error(await errorMessage(response, 'Unable to sign in. Please try again.'))
  }

  const body = (await response.json()) as { user: AuthUser }
  return body.user
}

// Creates the account from an invitation link, then signs the new user in. The backend's
// accept-invite only creates the account, so we log in with the same details.
export async function acceptInvite(
  token: string,
  displayName: string,
  password: string,
): Promise<AuthUser> {
  const response = await fetch('/api/v1/auth/accept-invite', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, display_name: displayName, password }),
  })

  if (!response.ok) {
    throw new Error(
      await errorMessage(response, 'Unable to accept the invitation. Please try again.'),
    )
  }

  const created = (await response.json()) as AuthUser
  try {
    return await login(created.email, password)
  } catch {
    // The account exists now and the link is used up, so don't send them back to retry it.
    throw new Error('Your account is ready, but we could not sign you in. Please sign in.')
  }
}

// What the backend returns when an admin creates an invitation.
export type Invite = {
  id: string
  email: string
  role: Role
  expires_at: string
  // Shown once, never stored by the backend: build the link from it right away.
  invite_token: string
}

// Admin only. Creates a generic invitation (the backend gives the new account the
// default role; roles are changed later).
export async function createInvite(email: string): Promise<Invite> {
  const response = await fetch('/api/v1/users/invite', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrfToken() },
    body: JSON.stringify({ email }),
  })

  if (response.status === 403) throw new Error('Only admins can invite people.')
  if (response.status === 422) throw new Error('Enter a valid email address.')
  if (!response.ok) {
    throw new Error(await errorMessage(response, 'Unable to create the invitation.'))
  }
  return response.json() as Promise<Invite>
}

// The link the admin sends. The token sits after the # so it never reaches server logs.
export function inviteLink(token: string): string {
  return `${window.location.origin}/#/accept-invite?token=${encodeURIComponent(token)}`
}

export async function logout(): Promise<void> {
  const response = await fetch('/api/v1/auth/logout', {
    method: 'POST',
    credentials: 'include',
    headers: { 'X-CSRF-Token': getCsrfToken() },
  })

  // A 401 means the session has already expired.
  // Treat this as a successful sign-out.
  if (response.status === 401) {
    return
  }

  // Network errors still reject at fetch(), and server errors
  // must continue to show the retry message.
  if (!response.ok) {
    throw new Error('Unable to log out. Please try again.')
  }
}

// These routes must remain accessible without login.
export function isPublicRoute(path: string): boolean {
  return path === '/login' || path === '/accept-invite'
}

// Where to go after signing in: only paths inside the app, never another site.
export function safeNext(next: string | null): string {
  return next && next.startsWith('/') && !next.startsWith('//') ? next : '/'
}
const EMAIL_PATTERN = /^[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+$/

export function isValidEmail(value: string): boolean {
  return EMAIL_PATTERN.test(value.trim())
}