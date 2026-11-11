
import { useEffect, useState, type ReactNode } from 'react'
import './App.css'

import TopNav, { type Tab } from './components/TopNav'
import AddSourcesPage from './pages/AddSourcesPage'
import CommandPage from './pages/CommandPage'
import PlaceholderPage from './pages/PlaceholderPage'
import StatusPage from './pages/StatusPage'
import LoginPage from './pages/LoginPage'
import AcceptInvitePage from './pages/AcceptInvitePage'

import {
  getCurrentUser,
  isPublicRoute,
  logout,
  type AuthStatus,
} from './auth'
import { useRoute } from './router'

type Page = {
  tab: Tab | null
  content: ReactNode
}

function pageFor(path: string, query: URLSearchParams): Page {
  switch (path) {
    case '/login':
      return { tab: null, content: <LoginPage /> }

    case '/accept-invite':
      return {
        tab: null,
        content: <AcceptInvitePage token={query.get('token')} />,
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
      return {
        tab: 'reviews',
        content: <PlaceholderPage title="Reviews" />,
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
  const [isLoggingOut, setIsLoggingOut] = useState(false)
  const [logoutError, setLogoutError] = useState('')

  const { path, query } = useRoute()

  const [authStatus, setAuthStatus] =
    useState<AuthStatus>('loading')

  const [sessionError, setSessionError] = useState('')

  // Check the session once when Operon loads.
  useEffect(() => {
    let active = true

    async function checkSession() {
      try {
        const user = await getCurrentUser()

        if (!active) return

        setAuthStatus(user ? 'authenticated' : 'unauthenticated')
      } catch {
        if (!active) return

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
  return pageFor(path, query).content
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

const page = pageFor(path, query)

  return (
    <div className="app">
      <TopNav
        active={page.tab}
        onLogout={handleLogout}
        isLoggingOut={isLoggingOut}
       logoutError={logoutError}
      />
      <main className="page">{page.content}</main>
    </div>
  )
}
