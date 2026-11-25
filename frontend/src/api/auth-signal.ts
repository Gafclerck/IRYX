/**
 * Signal interne d'authentification pour la détection du 401 et de l'état de session (Story F1.3).
 *
 * RÈGLE D'ARCHITECTURE F1.3 :
 * Une réponse HTTP 401 sur une requête protégée déclenche un signal interne
 * (événement / callback) indiquant « jeton expiré ou absent ».
 * Ce signal ne fait AUCUN renouvellement : le renouvellement silencieux est réservé à F1.4.
 * Un 401 sur la route de connexion (/api/v1/auth/login) n'émet JAMAIS ce signal (identifiants invalides).
 *
 * Emplacement réservé : Politique d'inactivité de l'analyste : à décider (C4).
 */

export type AuthSignalReason = 'jeton expiré ou absent'

export interface AuthSignalPayload {
  readonly reason: AuthSignalReason
  readonly url?: string
  readonly status: 401
  readonly timestamp: string
}

export type AuthSignalListener = (payload: AuthSignalPayload) => void

const listeners = new Set<AuthSignalListener>()

/**
 * Enregistre un écouteur sur le signal interne « jeton expiré ou absent ».
 * Retourne une fonction de désinscription.
 */
export function onAuthSignal(listener: AuthSignalListener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/**
 * Émet le signal interne « jeton expiré ou absent ».
 * Notifie l'ensemble des écouteurs actifs de manière sécurisée.
 */
export function emitAuthSignal(details?: { url?: string }): void {
  const payload: AuthSignalPayload = {
    reason: 'jeton expiré ou absent',
    url: details?.url,
    status: 401,
    timestamp: new Date().toISOString(),
  }

  listeners.forEach((listener) => {
    try {
      listener(payload)
    } catch {
      // Prévention des ruptures de notification si un écouteur lève une exception
    }
  })
}

/**
 * Réinitialise tous les écouteurs enregistrés (nettoyage entre les tests).
 */
export function clearAuthSignalListeners(): void {
  listeners.clear()
}

/**
 * Renvoie le nombre d'écouteurs actuellement enregistrés.
 */
export function getAuthSignalListenersCount(): number {
  return listeners.size
}

/**
 * Emplacement réservé pour le suivi d'inactivité de l'analyste.
 * Politique d'inactivité de l'analyste : à décider (C4).
 */
export const INACTIVITY_POLICY_C4 = 'à décider (C4)'
