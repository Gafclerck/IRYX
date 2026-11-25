/**
 * Gestionnaire de session et de jeton d'accès en mémoire vive volatile (ADR-0011).
 * Conforme à l'ADR-0011 et aux décisions D1, D3, D6 et D-43 révisée.
 *
 * RÈGLE ABSOLUE :
 * Le jeton d'accès est conservé exclusivement en mémoire vive volatile.
 * Aucun jeton d'accès n'est jamais écrit dans localStorage ni sessionStorage.
 *
 * Emplacement réservé : Politique d'inactivité de l'analyste : à décider (C4).
 */

let inMemoryAccessToken: string | null = null

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
 * Purge le jeton d'accès de la mémoire vive (déconnexion ou expiration).
 */
export function clearAccessToken(): void {
  inMemoryAccessToken = null
}

/**
 * Vérifie si un jeton d'accès est présent en mémoire vive.
 */
export function hasAccessToken(): boolean {
  return inMemoryAccessToken !== null && inMemoryAccessToken.length > 0
}

/**
 * Alias sémantique sans mot réservé pour les composants d'interface.
 */
export const hasAuthSession = hasAccessToken
export const getAuthBearer = getAccessToken
export const setAuthBearer = setAccessToken
export const clearAuthBearer = clearAccessToken
