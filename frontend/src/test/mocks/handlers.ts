import { http, HttpResponse } from 'msw'
import type {
  LoginRequest,
  TokenResponse,
  LogoutResponse,
  ErrorResponse,
} from '../../api/auth-types'

/**
 * Handlers MSW simulant les routes réseau de l'application IRYX.
 *
 * Routes d'authentification simulées d'après le contrat cible (Story F1.2) :
 * - POST /api/v1/auth/login (simulée, contrat cible : auth-contrat-cible.yaml)
 * - POST /api/v1/auth/refresh (simulée, contrat cible : auth-contrat-cible.yaml)
 * - POST /api/v1/auth/logout (simulée, contrat cible : auth-contrat-cible.yaml)
 *
 * Routes protégées simulées d'après le contrat OpenAPI (Story F1.3) :
 * - GET /api/v1/auth/me (simulée, contrat cible : openapi.json)
 * - GET /api/v1/cases (simulée, contrat cible : openapi.json)
 */
export const handlers = [
  http.get('*/api/test-simulation', () => {
    return HttpResponse.json({ status: 'ok', simulation: true })
  }),

  http.get('*/api/health', () => {
    return HttpResponse.json({ status: 'healthy' })
  }),

  // POST /api/v1/auth/login (simulée, contrat cible : auth-contrat-cible.yaml)
  http.post('*/api/v1/auth/login', async ({ request }) => {
    try {
      const body = (await request.json()) as Partial<LoginRequest>
      const { email, password } = body

      if (!email || !password) {
        return HttpResponse.json<ErrorResponse>(
          { detail: 'Champs obligatoires manquants.' },
          { status: 400 },
        )
      }

      // Simulation compte inactif / révoqué (403)
      if (email === 'bloque@iryx.local') {
        return HttpResponse.json<ErrorResponse>(
          { detail: 'Compte inactif ou accès révoqué. Contactez votre administrateur.' },
          { status: 403 },
        )
      }

      // Simulation erreur serveur 500
      if (email === 'serveur-erreur@iryx.local') {
        return HttpResponse.json<ErrorResponse>(
          { detail: 'Erreur interne du serveur.' },
          { status: 500 },
        )
      }

      // Simulation identifiants incorrects (401)
      if (
        password === 'mauvaismdp' ||
        password === 'wrong-password' ||
        email === 'inconnu@iryx.local'
      ) {
        return HttpResponse.json<ErrorResponse>(
          { detail: 'Identifiants incorrects.' },
          { status: 401 },
        )
      }

      // Cas nominal (200) : délivrance de l'access token (15 min) et positionnement du cookie refresh (7 j)
      const tokenResponse: TokenResponse = {
        access_token: 'mock-access-token-bearer-15min',
        token_type: 'bearer',
        expires_in: 900,
      }

      return HttpResponse.json(tokenResponse, {
        status: 200,
        headers: {
          'Set-Cookie':
            'refresh_token=mock-refresh-token-jwt-7d; Path=/api/v1/auth/refresh; Max-Age=604800; HttpOnly; Secure; SameSite=Strict',
        },
      })
    } catch {
      return HttpResponse.json<ErrorResponse>({ detail: 'Requête malformée.' }, { status: 400 })
    }
  }),

  // POST /api/v1/auth/refresh (simulée, contrat cible : auth-contrat-cible.yaml)
  http.post('*/api/v1/auth/refresh', async ({ request }) => {
    const origin = request.headers.get('Origin')
    // Simulation rejet anti-CSRF
    if (origin === 'http://malicious-site.local') {
      return HttpResponse.json<ErrorResponse>({ detail: 'Origine non autorisée.' }, { status: 403 })
    }

    const cookieHeader = request.headers.get('Cookie')
    if (cookieHeader?.includes('expired') || cookieHeader?.includes('invalid')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Session expirée. Veuillez vous reconnecter.' },
        { status: 401 },
      )
    }

    const tokenResponse: TokenResponse = {
      access_token: 'mock-refreshed-access-token-bearer-15min',
      token_type: 'bearer',
      expires_in: 900,
    }

    return HttpResponse.json(tokenResponse, { status: 200 })
  }),

  // POST /api/v1/auth/logout (simulée, contrat cible : auth-contrat-cible.yaml)
  http.post('*/api/v1/auth/logout', async () => {
    const logoutResponse: LogoutResponse = {
      message: 'Déconnexion réussie.',
    }

    return HttpResponse.json(logoutResponse, {
      status: 200,
      headers: {
        'Set-Cookie':
          'refresh_token=; Path=/api/v1/auth/refresh; Max-Age=0; HttpOnly; Secure; SameSite=Strict; Expires=Thu, 01 Jan 1970 00:00:00 GMT',
      },
    })
  }),

  // GET /api/v1/auth/me (simulée, contrat cible : openapi.json - Story F1.3)
  http.get('*/api/v1/auth/me', ({ request }) => {
    const authHeader = request.headers.get('Authorization')

    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Jeton d'accès expiré ou absent." },
        { status: 401 },
      )
    }

    const token = authHeader.replace('Bearer ', '').trim()

    if (token === 'mock-expired-token' || token.includes('expired')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Jeton d'accès expiré ou absent." },
        { status: 401 },
      )
    }

    if (token === 'mock-server-error-token' || token.includes('server-error')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Erreur interne du serveur.' },
        { status: 500 },
      )
    }

    return HttpResponse.json(
      {
        id: '00000000-0000-0000-0000-000000000001',
        email: 'analyste@iryx.local',
        is_active: true,
        created_at: '2026-11-25T00:00:00Z',
        updated_at: '2026-11-25T00:00:00Z',
      },
      { status: 200 },
    )
  }),

  // GET /api/v1/cases (simulée, contrat cible : openapi.json - Story F1.3)
  http.get('*/api/v1/cases', ({ request }) => {
    const authHeader = request.headers.get('Authorization')

    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Jeton d'accès expiré ou absent." },
        { status: 401 },
      )
    }

    const token = authHeader.replace('Bearer ', '').trim()

    if (token === 'mock-expired-token' || token.includes('expired')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Jeton d'accès expiré ou absent." },
        { status: 401 },
      )
    }

    if (token === 'mock-server-error-token' || token.includes('server-error')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Erreur interne du serveur.' },
        { status: 500 },
      )
    }

    return HttpResponse.json(
      {
        items: [],
        total: 0,
        limit: 20,
        offset: 0,
      },
      { status: 200 },
    )
  }),
]
