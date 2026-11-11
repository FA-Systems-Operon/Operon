
export type AuthUser = {
  id: string
  email: string
  role: string
}

export type AuthStatus =
  | 'loading'
  | 'authenticated'
  | 'unauthenticated'

// Checks whether the browser has a valid server-side session.
// Max's backend will provide this endpoint.
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


export async function logout(): Promise<void> {
  const response = await fetch('/api/v1/logout', {
    method: 'POST',
    credentials: 'include',
  })

  if (!response.ok) {
    throw new Error('Unable to log out. Please try again.')
  }
}


// These routes must remain accessible without login.
export function isPublicRoute(path: string): boolean {
  return path === '/login' || path === '/accept-invite'
}
