import { useSyncExternalStore } from 'react'
import { getSessionUser, onSessionChange, type SessionUser } from '../../../api/auth-memory'

/**
 * Hook d'accès réactif aux informations d'identité et d'organisation en mémoire vive.
 *
 * RÈGLE STRICTE (ADR-0011 / F1.5) :
 * Provient exclusivement de l'état volatile en mémoire vive.
 * Aucune lecture depuis localStorage ni sessionStorage.
 */
export function useSessionUser(): SessionUser | null {
  return useSyncExternalStore(onSessionChange, getSessionUser, getSessionUser)
}
