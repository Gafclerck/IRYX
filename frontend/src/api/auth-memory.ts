/**
 * Gestionnaire de session et de jeton d'accès en mémoire vive volatile (ADR-0011).
 * Conforme à l'ADR-0011 et aux décisions D1, D3, D6 et D-43 révisée.
 *
 * RÈGLE ABSOLUE :
 * Le jeton d'accès et les informations de session sont conservés exclusivement en mémoire vive volatile.
 * Aucun jeton d'accès ni donnée d'identité n'est jamais écrit dans localStorage ni sessionStorage.
 *
 * Emplacement réservé : Politique d'inactivité de l'analyste : à décider (C4).
 */

export interface SessionUser {
  readonly organizationName?: string
  readonly userName?: string
  readonly role?: string
}

let inMemoryAccessToken: string | null = null
let inMemorySessionUser: SessionUser | null = null
const sessionListeners = new Set<() => void>()

/**
 * Récupère le jeton d'accès Bearer en mémoire vive volatile.
 */
export function getAccessToken(): string | null {
  return inMemoryAccessToken
}

/**
 * Enregistre le jeton d'accès Bearer exclusivement en mémoire vive.
 */
export function setAccessToken(token: string | null): void {
  inMemoryAccessToken = token
}

/**
 * Purge le jeton d'accès et l'état de session utilisateur de la mémoire vive (déconnexion ou expiration).
 */
export function clearAccessToken(): void {
  inMemoryAccessToken = null
  clearSessionUser()
}

/**
 * Vérifie si un jeton d'accès est présent en mémoire vive.
 */
export function hasAccessToken(): boolean {
  return inMemoryAccessToken !== null && inMemoryAccessToken.length > 0
}

/**
 * Récupère les informations d'utilisateur et d'organisation en mémoire vive.
 */
export function getSessionUser(): SessionUser | null {
  return inMemorySessionUser
}

/**
 * Enregistre les informations d'utilisateur et d'organisation en mémoire vive.
 */
export function setSessionUser(user: SessionUser | null): void {
  inMemorySessionUser = user
  sessionListeners.forEach((listener) => {
    try {
      listener()
    } catch {
      // Prévention des ruptures si un écouteur lève une exception
    }
  })
}

/**
 * Purge les informations de session utilisateur en mémoire vive.
 */
export function clearSessionUser(): void {
  inMemorySessionUser = null
  sessionListeners.forEach((listener) => {
    try {
      listener()
    } catch {
      // Prévention des ruptures si un écouteur lève une exception
    }
  })
}

/**
 * S'abonne aux modifications de l'état de session en mémoire.
 */
export function onSessionChange(listener: () => void): () => void {
  sessionListeners.add(listener)
  return () => {
    sessionListeners.delete(listener)
  }
}

/**
 * Supprime tous les écouteurs de session (nettoyage inter-tests).
 */
export function clearSessionListeners(): void {
  sessionListeners.clear()
}

/**
 * Alias sémantique sans mot réservé pour les composants d'interface.
 */
export const hasAuthSession = hasAccessToken
export const getAuthBearer = getAccessToken
export const setAuthBearer = setAccessToken
export const clearAuthBearer = clearAccessToken
export const getSessionInfo = getSessionUser
export const setSessionInfo = setSessionUser
export const clearSessionInfo = clearSessionUser
