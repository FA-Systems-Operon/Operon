import { useEffect, useState } from 'react'
import { listReviews } from '../api'

export type Tab = 'command' | 'brain' | 'workforce' | 'reviews'

const TABS: { id: Tab; label: string; href: string }[] = [
  { id: 'command', label: 'Command', href: '#/' },
  { id: 'brain', label: 'Brain', href: '#/brain' },
  { id: 'workforce', label: 'Workforce', href: '#/workforce' },
]

type TopNavProps = {
  active: Tab | null
type TopNavProps = {
  active: Tab | null
  path: string
  onLogout: () => Promise<void>
  isLoggingOut: boolean
  logoutError?: string
  isAdmin?: boolean
}

export default function TopNav({
  active,
  path,
  onLogout,
  isLoggingOut,
  logoutError,
  isAdmin = false,
}: TopNavProps) {
  const current = (tab: Tab) => (active === tab ? 'page' : undefined)
  // Drafts waiting for review. Keeps the last count while a refresh is on its way.
  const [waiting, setWaiting] = useState(0)

  // Fetched on every route change, every 30 seconds while the tab is visible, and as
  // soon as the tab is shown again, so a draft that finishes in the background shows up.
  useEffect(() => {
    // Only the newest request may set the count: an older reply that arrives late, or
    // one after the route has changed or the nav has closed, is ignored.
    let newest = 0
    function refresh() {
      const request = ++newest
      listReviews()
        .then((list) => {
          if (request === newest) setWaiting(list.length)
        })
        .catch(() => {
          // No error in the nav: just no badge.
          if (request === newest) setWaiting(0)
        })
    }
    function refreshIfVisible() {
      if (!document.hidden) refresh()
    }

    refresh()
    const timer = window.setInterval(refreshIfVisible, 30_000)
    document.addEventListener('visibilitychange', refreshIfVisible)
    return () => {
      newest++
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', refreshIfVisible)
    }
  }, [path])

  return (
    <header className="topnav">
      <div className="topnav-brand">
        <a className="brand" href="#/">
          <svg className="brand-mark" viewBox="0 0 24 24" aria-hidden="true">
            <rect width="24" height="24" rx="6" />
            <circle cx="12" cy="12" r="4.5" />
            <path d="M4 12h16" />
          </svg>
          Operon
        </a>
        <span className="topnav-org">FA Systems</span>
      </div>

      <nav aria-label="Main">
        <ul className="tabs">
          {TABS.map((tab) => (
            <li key={tab.id}>
              <a className="tab" href={tab.href} aria-current={current(tab.id)}>
                {tab.label}
              </a>
            </li>
          ))}
        </ul>
      </nav>

<div className="topnav-actions">
  <a
    className="topnav-reviews"
    href="#/reviews"
    aria-current={current('reviews')}
    aria-label={waiting > 0 ? `Reviews, ${waiting} waiting` : undefined}
  >
    Reviews
    {/* The label already says the count, so the number isn't read twice. */}
    {waiting > 0 && (
      <span className="topnav-badge" aria-hidden="true">
        {waiting}
      </span>
    )}
  </a>

  {isAdmin && (
    <a className="topnav-reviews" href="#/invite">
      Invite
    </a>
  )}

  <button
    type="button"
    className="topnav-logout"
    onClick={() => void onLogout()}
    disabled={isLoggingOut}
  >
    {isLoggingOut ? 'Logging out...' : 'Log out'}
  </button>

  {logoutError && <span role="alert">{logoutError}</span>}
</div>
    </header>
  )
}
