import createClient, { type Middleware } from 'openapi-fetch'
import type { paths } from './schema'
import { getAccessToken, clearAccessToken } from './auth-memory'
import { emitAuthSignal } from './auth-signal'
import { executeSilentRefresh, isSilentRefreshEnabled, emitAuthEviction } from './auth-session'

/**
 * Détermine si une URL cible correspond à la route de connexion utilisateur.
 * Un code HTTP 401 sur cette route correspond à un échec d'identifiants (F1.2)
 * et ne doit jamais être interprété comme une expiration de session.
 */
export function isLoginRoute(url: string): boolean {
  try {
    const parsed = new URL(url, 'http://localhost')
    return parsed.pathname === '/api/v1/auth/login' || parsed.pathname.endsWith('/auth/login')
  } catch {
    return url.includes('/api/v1/auth/login') || url.includes('/auth/login')
  }
}

/**
 * Détermine si une URL cible correspond à une route d'authentification directe
 * (/login, /refresh, /logout) pour éviter toute boucle ou récursion infinie.
 */
export function isAuthEndpoint(url: string): boolean {
  try {
    const parsed = new URL(url, 'http://localhost')
    const pathname = parsed.pathname
    return (
      pathname === '/api/v1/auth/login' ||
      pathname === '/api/v1/auth/refresh' ||
      pathname === '/api/v1/auth/logout' ||
      pathname.endsWith('/auth/login') ||
      pathname.endsWith('/auth/refresh') ||
      pathname.endsWith('/auth/logout')
    )
  } catch {
    return (
      url.includes('/api/v1/auth/login') ||
      url.includes('/api/v1/auth/refresh') ||
      url.includes('/api/v1/auth/logout')
    )
  }
}

/**
 * RÈGLE D'INJECTION DU JETON D'ACCÈS ET RENOUVELLEMENT SILENCIEUX (Stories F1.3 et F1.4) :
 * 1. Toute requête vers une route protégée porte l'en-tête HTTP standard
 *    `Authorization: Bearer <token>` à partir du jeton actif en mémoire vive (auth-memory).
 * 2. Règle documentée pour les requêtes sans jeton : En l'absence de jeton en mémoire vive,
 *    la requête protégée est transmise sans en-tête Authorization. Le serveur répondra par
 *    un code HTTP 401 qui déclenchera la détection d'expiration/absence.
 * 3. Détection du 401 : Une réponse 401 sur une requête protégée déclenche le signal interne
 *    « jeton expiré ou absent » (Story F1.3).
 * 4. Renouvellement silencieux et rejeu (Story F1.4) :
 *    - Si le renouvellement silencieux est activé, un appel unique à POST /api/v1/auth/refresh est exécuté.
 *    - Les requêtes concurrentes en 401 attendent ce même appel sans multiplier les requêtes /refresh.
 *    - Après succès, le nouvel access token remplace le jeton en mémoire et la requête initiale est rejouée une fois.
 *    - Si la requête a déjà été rejouée (en-tête X-Retry: 1) et reçoit à nouveau 401, elle n'est pas rejouée à l'infini.
 *    - En cas d'échec du renouvellement (401 ou erreur réseau), le jeton est purgé et l'éviction est prononcée.
 * 5. Aucune écriture dans localStorage ni sessionStorage (règle stricte ADR-0011).
 * 6. Aucun cookie lu par JavaScript (seul le navigateur transmet le cookie httpOnly).
 * 7. Politique d'inactivité de l'analyste : à décider (C4).
 */
export const authMiddleware: Middleware = {
  onRequest({ request }) {
    const token = getAccessToken()
    if (token) {
      request.headers.set('Authorization', `Bearer ${token}`)
    }
    // Règle documentée : Si aucun jeton n'est présent, la requête part sans en-tête Authorization
    return request
  },

  async onResponse({ request, response }) {
    // Détection du code HTTP 401
    if (response.status === 401) {
      // La route de connexion est explicitement exclue (identifiants incorrects, F1.2)
      if (isLoginRoute(request.url)) {
        return response
      }

      // Émission systématique du signal interne F1.3 « jeton expiré ou absent »
      emitAuthSignal({ url: request.url })

      // Les endpoints d'authentification directs ne déclenchent pas de sous-renouvellement
      if (isAuthEndpoint(request.url)) {
        return response
      }

      // Si le renouvellement silencieux F1.4 est activé
      if (isSilentRefreshEnabled()) {
        const isRetry = request.headers.get('X-Retry') === '1'

        // Si la requête a déjà été rejouée une fois : interruption immédiate pour prévenir toute boucle infinie
        if (isRetry) {
          clearAccessToken()
          emitAuthEviction({
            reason: 'Session expirée après réessai',
            returnUrl: request.url,
          })
          return response
        }

        try {
          // Attente du renouvellement silencieux unique (mutualisé pour toutes les requêtes concurrentes)
          const newToken = await executeSilentRefresh()

          if (newToken) {
            // Rejouer la requête initiale une seule fois avec le nouvel access token
            const retryHeaders = new Headers(request.headers)
            retryHeaders.set('Authorization', `Bearer ${newToken}`)
            retryHeaders.set('X-Retry', '1')

            const retryRequest = new Request(request.url, {
              method: request.method,
              headers: retryHeaders,
              body:
                request.method !== 'GET' && request.method !== 'HEAD' ? request.body : undefined,
              // @ts-expect-error duplex option for node environment
              duplex: 'half',
            })

            const retriedResponse = await globalThis.fetch(retryRequest)

            // Si la requête rejouée retourne à nouveau un code 401, prononcer l'éviction immédiate
            if (retriedResponse.status === 401) {
              clearAccessToken()
              emitAuthEviction({
                reason: 'Session expirée après réessai',
                returnUrl: request.url,
              })
            }

            return retriedResponse
          }
        } catch {
          // Échec du renouvellement silencieux (401 sur /refresh ou coupure réseau)
          // L'éviction et la purge mémoire ont été exécutées par executeSilentRefresh
          return response
        }
      }
    }

    return response
  },
}

/**
 * Détermine l'URL de base pour openapi-fetch (nécessite une origine valide dans l'environnement Node/Request).
 */
const resolveBaseUrl = (): string => {
  if (typeof window !== 'undefined' && window.location?.origin) {
    return window.location.origin
  }
  return 'http://localhost'
}

/**
 * Client réseau HTTP typé d'après le contrat OpenAPI.
 * Doté du middleware d'interception d'authentification, de détection 401 et de renouvellement silencieux.
 * Délégué dynamiquement à globalThis.fetch pour supporter l'interception MSW et les environnements de test.
 */
export const apiClient = createClient<paths>({
  baseUrl: resolveBaseUrl(),
  fetch: (input: Request): Promise<Response> => globalThis.fetch(input),
})

apiClient.use(authMiddleware)

/**
 * Emplacement réservé pour le suivi d'inactivité de l'analyste.
 * Politique d'inactivité de l'analyste : à décider (C4).
 */
export const ANALYST_INACTIVITY_POLICY = 'à décider (C4)'
