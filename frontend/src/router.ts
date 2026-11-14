import { useSyncExternalStore } from 'react'

export type Route = {
  path: string
  query: URLSearchParams
}

// Pages live after the # (for example /#/sources/new). The production server only
// serves static files, so refreshing a real path such as /brain would return 404.
// The part after # never reaches the server, so every page survives a refresh.
export function parseHash(hash: string): Route {
  const withoutHash = hash.replace(/^#/, '')
  const queryStart = withoutHash.indexOf('?')
  const path = queryStart === -1 ? withoutHash : withoutHash.slice(0, queryStart)
  const search = queryStart === -1 ? '' : withoutHash.slice(queryStart + 1)
  return { path: path || '/', query: new URLSearchParams(search) }
}

function subscribe(onChange: () => void) {
  window.addEventListener('hashchange', onChange)
  return () => window.removeEventListener('hashchange', onChange)
}

// window.location.hash is the part after the # (for example #/brain) for the app to read.
export function useRoute(): Route {
  const hash = useSyncExternalStore(subscribe, () => window.location.hash)
  return parseHash(hash)
}

// Link to Add sources. Pass a client ID to open it with that client already chosen
// (the client's Brain page); leave it out for a new intake (Command).
export function addSourcesHref(clientId?: string): string {
  return clientId ? `#/sources/new?client=${encodeURIComponent(clientId)}` : '#/sources/new'
}

// Link to one draft in the review inbox (#57 builds the page). Versions are scoped
// to their profile in the API, so the link carries both IDs.
export function reviewDraftHref(profileId: string, versionId: string): string {
  const query = new URLSearchParams({ profile: profileId, version: versionId })
  return `#/reviews/draft?${query}`
}
