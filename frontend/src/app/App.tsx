import { useEffect } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from 'react-router-dom'
import { queryClient } from './queryClient'
import { router } from './router'
import { ErrorBoundary } from '../components/feedback/ErrorBoundary'
import { setupAuthSession, onAuthEviction } from '../api/auth-session'

export function App() {
  useEffect(() => {
    // Initialise le renouvellement silencieux F1.4 et attache l'écouteur au signal F1.3
    const cleanupSession = setupAuthSession()

    // À chaque éviction (expiration du refresh token ou déconnexion) : purge du cache TanStack Query
    const unsubscribeEviction = onAuthEviction(() => {
      queryClient.clear()
    })

    return () => {
      cleanupSession()
      unsubscribeEviction()
    }
  }, [])

  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </ErrorBoundary>
  )
}
