import createClient, { type Middleware } from 'openapi-fetch'
import type { paths } from './schema'
import { getAccessToken } from './auth-memory'
import { emitAuthSignal } from './auth-signal'

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
 * RÈGLE D'INJECTION DU JETON D'ACCÈS ET DÉTECTION DU 401 (Story F1.3) :
 * 1. Toute requête vers une route protégée porte l'en-tête HTTP standard
 *    `Authorization: Bearer <token>` à partir du jeton actif en mémoire vive (auth-memory).
 * 2. Règle documentée pour les requêtes sans jeton : En l'absence de jeton en mémoire vive,
 *    la requête protégée est transmise sans en-tête Authorization. Le serveur répondra par
 *    un code HTTP 401 qui déclenchera la détection d'expiration/absence.
 * 3. Détection du 401 : Une réponse 401 sur une requête protégée déclenche le signal interne
 *    « jeton expiré ou absent ». Ce signal ne réalise AUCUN renouvellement (F1.4).
 * 4. La route de connexion (/api/v1/auth/login) est explicitement exclue de cette détection.
 * 5. Aucune écriture dans localStorage ni sessionStorage (règle stricte ADR-0011).
 * 6. Aucun cookie de données pour les requêtes métier.
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

  onResponse({ request, response }) {
    // Détection du 401 sur requête protégée
    if (response.status === 401) {
      if (!isLoginRoute(request.url)) {
        // Émission du signal interne sans renouvellement (F1.4 hors périmètre)
        emitAuthSignal({ url: request.url })
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
 * Doté du middleware d'interception d'authentification et de détection 401.
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
