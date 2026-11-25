import { type ReactNode, useEffect, useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { hasAuthSession } from '../../../api/auth-memory'
import {
  executeSilentRefresh,
  hasAttemptedInitialRefresh,
  setAttemptedInitialRefresh,
  onAuthEviction,
  enableSilentRefresh,
} from '../../../api/auth-session'
import { LoadingFallback } from '../../../components/feedback/LoadingFallback'

interface AuthGuardProps {
  children: ReactNode
  isAuthenticated?: boolean
}

/**
 * Garde d'authentification des routes protégées (Story F1.1 et F1.4 / DP-06).
 *
 * RÈGLES D'ARCHITECTURE :
 * 1. Si `isAuthenticated` est explicitement passé (tests unitaires de présentation),
 *    la décision est immédiate et synchrone.
 * 2. Si `hasAuthSession()` est vrai (jeton en mémoire vive active) : l'accès est accordé.
 * 3. Application de DP-06 : au chargement initial sans jeton en mémoire (rechargement F5),
 *    tenter un renouvellement silencieux unique via POST /api/v1/auth/refresh avant d'afficher /login.
 * 4. Pendant ce renouvellement initial, afficher l'indicateur LoadingFallback conforme à la palette.
 * 5. Si le renouvellement réussit : l'accès est accordé sans interruption.
 * 6. Si le renouvellement échoue ou si le jeton est révoqué : redirection immédiate vers /login
 *    avec conservation de l'URL initiale dans l'état de navigation (state.from).
 * 7. Écoute continue des événements d'éviction pour réorienter l'utilisateur en cas d'expiration en cours de session.
 */
export function AuthGuard({ children, isAuthenticated }: AuthGuardProps) {
  const location = useLocation()

  // Si isAuthenticated est explicitement fourni, on l'utilise sans logique asynchrone
  if (isAuthenticated !== undefined) {
    if (!isAuthenticated) {
      return <Navigate to="/login" state={{ from: location }} replace />
    }
    return <>{children}</>
  }

  return <DynamicAuthGuard location={location}>{children}</DynamicAuthGuard>
}

interface DynamicAuthGuardProps {
  children: ReactNode
  location: ReturnType<typeof useLocation>
}

function DynamicAuthGuard({ children, location }: DynamicAuthGuardProps) {
  const [sessionActive, setSessionActive] = useState(() => hasAuthSession())
  const [isCheckingInitialSession, setIsCheckingInitialSession] = useState(() => {
    // Si aucun jeton en mémoire et tentative DP-06 non encore exécutée
    return !hasAuthSession() && !hasAttemptedInitialRefresh()
  })

  useEffect(() => {
    // S'assurer que le renouvellement silencieux est activé pour l'application
    enableSilentRefresh()

    // Écoute des évictions de session (expiration du refresh token ou déconnexion)
    const unsubscribeEviction = onAuthEviction(() => {
      setSessionActive(false)
    })

    // DP-06 : Renouvellement silencieux unique au chargement
    if (!hasAuthSession() && !hasAttemptedInitialRefresh()) {
      setAttemptedInitialRefresh(true)
      setIsCheckingInitialSession(true)

      executeSilentRefresh()
        .then(() => {
          setSessionActive(true)
        })
        .catch(() => {
          setSessionActive(false)
        })
        .finally(() => {
          setIsCheckingInitialSession(false)
        })
    }

    return () => {
      unsubscribeEviction()
    }
  }, [])

  if (isCheckingInitialSession) {
    return <LoadingFallback message="Vérification de la session en cours..." />
  }

  if (!sessionActive || !hasAuthSession()) {
    return (
      <Navigate
        to="/login"
        state={{
          from: location,
          message: hasAttemptedInitialRefresh()
            ? 'Session expirée. Veuillez vous reconnecter.'
            : undefined,
        }}
        replace
      />
    )
  }

  return <>{children}</>
}
