import type { ReactNode } from 'react'
import './App.css'
import TopNav, { type Tab } from './components/TopNav'
import AddSourcesPage from './pages/AddSourcesPage'
import CommandPage from './pages/CommandPage'
import PlaceholderPage from './pages/PlaceholderPage'
import ReviewDraftPage from './pages/ReviewDraftPage'
import ReviewInboxPage from './pages/ReviewInboxPage'
import StatusPage from './pages/StatusPage'
import { useRoute } from './router'

type Page = {
  tab: Tab | null
  content: ReactNode
}

// To add a page: add a case here, and a tab in TopNav if it belongs in the menu.
function pageFor(path: string, query: URLSearchParams): Page {
  switch (path) {
    case '/':
      return { tab: 'command', content: <CommandPage /> }
    case '/brain':
      return { tab: 'brain', content: <PlaceholderPage title="Brain" /> }
    case '/workforce':
      return { tab: 'workforce', content: <PlaceholderPage title="Workforce" /> }
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
      // The key starts a fresh form when the chosen client in the link changes.
      return {
        tab: 'brain',
        content: <AddSourcesPage key={clientId ?? ''} initialClientId={clientId} />,
      }
    }
    case '/status':
      return { tab: null, content: <StatusPage /> }
    default:
      return { tab: null, content: <PlaceholderPage title="Page not found" /> }
  }
}

export default function App() {
  const { path, query } = useRoute()
  const page = pageFor(path, query)

  return (
    <div className="app">
      <TopNav active={page.tab} path={path} />
      <main className="page">{page.content}</main>
    </div>
  )
}
