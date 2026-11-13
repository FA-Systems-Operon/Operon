
import { useEffect, useRef, useState, type ReactNode } from 'react'
import './App.css'

import TopNav, { type Tab } from './components/TopNav'
import AddSourcesPage from './pages/AddSourcesPage'
import CommandPage from './pages/CommandPage'
import PlaceholderPage from './pages/PlaceholderPage'
import ReviewDraftPage from './pages/ReviewDraftPage'
import ReviewInboxPage from './pages/ReviewInboxPage'
import StatusPage from './pages/StatusPage'
import LoginPage from './pages/LoginPage'
import AcceptInvitePage from './pages/AcceptInvitePage'
import InviteUserPage from './pages/InviteUserPage'

import {
  getCurrentUser,
  isPublicRoute,
  logout,
  type AuthStatus,
  type AuthUser,
} from './auth'
import { useRoute } from './router'

type Page = {
  tab: Tab | null
  content: ReactNode
}

function pageFor(
  path: string,
  query: URLSearchParams,
  onSignedIn: (user: AuthUser) => void,
  currentUser: AuthUser | null,
): Page {
  switch (path) {
    case '/login':
      return {
        tab: null,
        content: <LoginPage next={query.get('next')} onSignedIn={onSignedIn} />,
      }

    case '/accept-invite':
      return {
        tab: null,
        content: (
          <AcceptInvitePage token={query.get('token')} onSignedIn={onSignedIn} />
        ),
      }

    case '/':
      return { tab: 'command', content: <CommandPage /> }

    case '/brain':
      return {
        tab: 'brain',
        content: <PlaceholderPage title="Brain" />,
      }

    case '/workforce':
      return {
        tab: 'workforce',
        content: <PlaceholderPage title="Workforce" />,
      }

    case '/reviews':
      return { tab: 'reviews', content: <ReviewInboxPage /> }
    case '/reviews/draft': {
      const profileId = query.get('profile')
      const versionId = query.get('version')
      // The key starts fresh (no selected field) when the link opens another draft.
      return {
        tab: 'reviews',
        content: (
          <ReviewDraftPage
            key={`${profileId}/${versionId}`}
            profileId={profileId}
            versionId={versionId}
          />
        ),
      }
    }
    case '/sources/new': {
      const clientId = query.get('client')

      return {
        tab: 'brain',
        content: (
          <AddSourcesPage
            key={clientId ?? ''}
            initialClientId={clientId}
          />
        ),
      }
    }

    case '/invite':
      return { tab: null, content: <InviteUserPage user={currentUser} /> }

    case '/status':
      return { tab: null, content: <StatusPage /> }

    default:
      return {
        tab: null,
        content: <PlaceholderPage title="Page not found" />,
      }
  }
}

export default function App() {

  const sessionCheckVersion = useRef(0)
  const [isLoggingOut, setIsLoggingOut] = useState(false)
  const [logoutError, setLogoutError] = useState('')

  const { path, query } = useRoute()

  const [authStatus, setAuthStatus] =
    useState<AuthStatus>('loading')

  const [sessionError, setSessionError] = useState('')

  // Who is signed in (role-based screens will read this).
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null)

  // Called by the login and accept-invite pages. Without this the app would still
  // think the visitor is signed out and send them straight back to /login.
 
  function handleSignedIn(user: AuthUser) {
  // Invalidate any session check started before this successful login.
  sessionCheckVersion.current += 1

  setCurrentUser(user)
  setSessionError('')
  setAuthStatus('authenticated')
}

  // Check the session once when Operon loads.
  useEffect(() => {
  let active = true
  const version = ++sessionCheckVersion.current

  async function checkSession() {
    try {
      const user = await getCurrentUser()

      if (!active || version !== sessionCheckVersion.current) return

      setCurrentUser(user)
      setAuthStatus(user ? 'authenticated' : 'unauthenticated')
    } catch {
      if (!active || version !== sessionCheckVersion.current) return

      setSessionError(
        'Unable to check your session. Please try again.',
         )
       }
      }

     void checkSession()

      return () => {
       active = false
     }
  }, [])

  async function handleLogout() {
  if (isLoggingOut) return

  setIsLoggingOut(true)
  setLogoutError('')

  try {
    await logout()

    // Only mark the user signed out if the server confirms success.
    setCurrentUser(null)
    setAuthStatus('unauthenticated')
    window.location.hash = '#/login'
  } catch {
    setLogoutError('Unable to log out. Please try again.')
  } finally {
    setIsLoggingOut(false)
  }
}

  // Keep the original destination, including query parameters.
  useEffect(() => {
    if (
      authStatus === 'unauthenticated' &&
      !isPublicRoute(path)
    ) {
      const destination =
        path + (query.toString() ? `?${query.toString()}` : '')

      window.location.hash =
        `#/login?next=${encodeURIComponent(destination)}`
    }
  }, [authStatus, path, query])

  if (isPublicRoute(path)) {
  return pageFor(path, query, handleSignedIn, currentUser).content
}

  if (sessionError) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1>Connection problem</h1>
          <p role="alert">{sessionError}</p>
          <button
            className="auth-button"
            onClick={() => window.location.reload()}
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  // Never display protected UI while the session is being checked.
  if (authStatus === 'loading') {
    return (
      <div className="auth-page">
        <p>Checking your session...</p>
      </div>
    )
  }

  // Prevent protected content from rendering during redirect.
  if (
    authStatus === 'unauthenticated' &&
    !isPublicRoute(path)
  ) {
    return null
  }

const page = pageFor(path, query, handleSignedIn, currentUser)

  return (
    <div className="app">
   <TopNav
  active={page.tab}
  path={path}
  onLogout={handleLogout}
  isAdmin={currentUser?.role === 'admin'}
  isLoggingOut={isLoggingOut}
  logoutError={logoutError}
/>
<main className="page">{page.content}</main>
</div>
  )
}
