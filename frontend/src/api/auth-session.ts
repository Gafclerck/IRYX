/**
 * Gestionnaire de session, renouvellement silencieux et éviction (Story F1.4 / ADR-0011 / DP-06).
 *
 * RÈGLES D'ARCHITECTURE (ADR-0011, D1, D3, D6, DP-06) :
 * 1. Renouvellement silencieux via POST /api/v1/auth/refresh (simulée, contrat cible : auth-contrat-cible.yaml).
 *    Le cookie httpOnly est transmis par le navigateur ; le JavaScript ne lit ni n'écrit aucun cookie.
 * 2. Après succès du renouvellement : le nouvel access token (15 min) remplace le jeton en mémoire vive.
 *    La requête initiale est rejouée une seule fois.
 * 3. File d'attente et concurrence : pendant qu'un renouvellement est en cours, toutes les requêtes
 *    protégées concurrentes attendent le même appel ; un seul appel à /refresh part à la fois.
 * 4. DP-06 : Au chargement de l'application (F5 ou arrivée), si le jeton en mémoire est absent,
 *    tenter un renouvellement silencieux unique avant d'afficher /login.
 * 5. Échec du renouvellement (401 ou erreur réseau) : éviction du jeton en mémoire vive volatile,
 *    redirection vers /login avec préservation de l'URL demandée pour retour après connexion.
 * 6. Déconnexion explicite : appel à POST /api/v1/auth/logout (simulée, contrat cible : auth-contrat-cible.yaml),
 *    effacement du jeton en mémoire, réinitialisation de session et redirection vers /login.
 *    Aucune révocation serveur en base de données (modèle stateless D6).
 * 7. Sécurité : Aucune écriture dans localStorage ni sessionStorage (règle stricte ADR-0011).
 * 8. Politique d'inactivité de l'analyste : point C4, à décider.
 */

import { setAccessToken, clearAccessToken } from './auth-memory'
import { onAuthSignal } from './auth-signal'
import { refreshApi, logoutApi } from './auth'

let refreshPromise: Promise<string> | null = null
let silentRefreshEnabled = false
let initialRefreshAttempted = false

export interface AuthEvictionPayload {
  readonly reason: string
  readonly returnUrl?: string
  readonly timestamp: string
}

export type AuthEvictionListener = (payload: AuthEvictionPayload) => void

const evictionListeners = new Set<AuthEvictionListener>()

/**
 * Active le mécanisme de renouvellement silencieux pour le client réseau.
 */
export function enableSilentRefresh(): void {
  silentRefreshEnabled = true
}

/**
 * Désactive le mécanisme de renouvellement silencieux.
 */
export function disableSilentRefresh(): void {
  silentRefreshEnabled = false
}

/**
 * Indique si le renouvellement silencieux est actuellement actif.
 */
export function isSilentRefreshEnabled(): boolean {
  return silentRefreshEnabled
}

/**
 * Indique si la tentative initiale de renouvellement silencieux au chargement (DP-06) a déjà été effectuée.
 */
export function hasAttemptedInitialRefresh(): boolean {
  return initialRefreshAttempted
}

/**
 * Définit l'état de la tentative initiale de renouvellement silencieux au chargement (DP-06).
 */
export function setAttemptedInitialRefresh(value: boolean): void {
  initialRefreshAttempted = value
}

/**
 * Réinitialise le marqueur de tentative initiale au chargement.
 */
export function resetInitialRefreshAttempt(): void {
  initialRefreshAttempted = false
}

/**
 * Enregistre un écouteur sur l'événement d'éviction de session.
 * Retourne une fonction de désinscription.
 */
export function onAuthEviction(listener: AuthEvictionListener): () => void {
  evictionListeners.add(listener)
  return () => {
    evictionListeners.delete(listener)
  }
}

/**
 * Émet l'événement d'éviction de session et notifie tous les écouteurs enregistrés.
 * Purge immédiatement le jeton d'accès en mémoire vive volatile.
 */
export function emitAuthEviction(details?: { reason?: string; returnUrl?: string }): void {
  clearAccessToken()

  const payload: AuthEvictionPayload = {
    reason: details?.reason || 'Session expirée. Veuillez vous reconnecter.',
    returnUrl: details?.returnUrl,
    timestamp: new Date().toISOString(),
  }

  evictionListeners.forEach((listener) => {
    try {
      listener(payload)
    } catch {
      // Prévention des ruptures si un écouteur lève une exception
    }
  })
}

/**
 * Supprime tous les écouteurs d'éviction (nettoyage inter-tests).
 */
export function clearAuthEvictionListeners(): void {
  evictionListeners.clear()
}

/**
 * Exécute un renouvellement silencieux unique de l'access token.
 * Si un appel est déjà en cours d'exécution, toutes les requêtes concurrentes
 * attendent la même promesse (mutualisation stricte d'un appel unique).
 *
 * En cas de succès : enregistre le nouvel access token en mémoire vive et le retourne.
 * En cas d'échec (401 ou coupure réseau) : purge la mémoire et prononce l'éviction.
 */
export async function executeSilentRefresh(): Promise<string> {
  if (refreshPromise) {
    return refreshPromise
  }

  refreshPromise = (async () => {
    try {
      const tokenResponse = await refreshApi()
      const newToken = tokenResponse.access_token
      setAccessToken(newToken)
      return newToken
    } catch (error) {
      clearAccessToken()
      const reason =
        error instanceof Error ? error.message : 'Session expirée. Veuillez vous reconnecter.'
      emitAuthEviction({ reason })
      throw error
    } finally {
      refreshPromise = null
    }
  })()

  return refreshPromise
}

/**
 * Initialise le gestionnaire de session et attache le renouvellement silencieux
 * au signal « jeton expiré ou absent » émis par F1.3.
 *
 * Retourne une fonction de nettoyage pour désinscrire l'écouteur et désactiver le renouvellement.
 */
export function setupAuthSession(): () => void {
  enableSilentRefresh()

  const unsubscribeSignal = onAuthSignal(async () => {
    if (isSilentRefreshEnabled()) {
      try {
        await executeSilentRefresh()
      } catch {
        // L'échec d'éviction est déjà géré par executeSilentRefresh
      }
    }
  })

  return () => {
    unsubscribeSignal()
    disableSilentRefresh()
  }
}

/**
 * Exécute la déconnexion explicite de l'utilisateur (Story F1.4 / ADR-0011 / D6).
 * Émet POST /api/v1/auth/logout pour ordonner la suppression du cookie côté client,
 * purge l'access token en mémoire vive volatile et notifie l'éviction vers /login.
 * Conformément au modèle stateless D6, aucune révocation côté serveur n'est enregistrée.
 */
export async function performLogout(): Promise<void> {
  try {
    await logoutApi()
  } finally {
    clearAccessToken()
    resetInitialRefreshAttempt()
    emitAuthEviction({ reason: 'Déconnexion réussie.' })
  }
}

/**
 * Réinitialise l'ensemble de l'état de session (nettoyage complet entre les tests).
 */
export function resetAuthSession(): void {
  refreshPromise = null
  silentRefreshEnabled = false
  initialRefreshAttempted = false
  clearAuthEvictionListeners()
}
