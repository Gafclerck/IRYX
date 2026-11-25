import type { LoginRequest, TokenResponse, LogoutResponse, ErrorResponse } from './auth-types'
import { setAccessToken, clearAccessToken } from './auth-memory'

/**
 * Erreur spécifique liée à l'authentification.
 */
export class AuthError extends Error {
  readonly status: number

  constructor(message: string, status: number = 0) {
    super(message)
    this.name = 'AuthError'
    this.status = status
  }
}

/**
 * Endpoint de connexion utilisateur.
 * Route cible : POST /api/v1/auth/login
 * Contrat cible : docs/contrat/auth-contrat-cible.yaml (simulée)
 */
export async function loginApi(credentials: LoginRequest): Promise<TokenResponse> {
  try {
    const response = await fetch('/api/v1/auth/login', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(credentials),
    })

    if (!response.ok) {
      if (response.status === 403) {
        let detail = 'Compte inactif ou accès révoqué. Contactez votre administrateur.'
        try {
          const errData = (await response.json()) as ErrorResponse
          if (errData?.detail) {
            detail = errData.detail
          }
        } catch {
          // ignore parsing error
        }
        throw new AuthError(detail, 403)
      }

      if (response.status === 401 || response.status >= 500) {
        throw new AuthError('Identifiants incorrects.', response.status)
      }

      let detail = 'Identifiants incorrects.'
      try {
        const errData = (await response.json()) as ErrorResponse
        if (errData?.detail) {
          detail = errData.detail
        }
      } catch {
        // ignore parsing error
      }
      throw new AuthError(detail, response.status)
    }

    const data = (await response.json()) as TokenResponse

    // Enregistrement exclusivement en mémoire vive volatile (ADR-0011)
    setAccessToken(data.access_token)

    return data
  } catch (error) {
    if (error instanceof AuthError) {
      throw error
    }
    // Erreur réseau ou serveur injoignable
    throw new AuthError('Serveur injoignable. Veuillez vérifier votre connexion.', 0)
  }
}

/**
 * Endpoint de renouvellement silencieux de la session.
 * Route cible : POST /api/v1/auth/refresh
 * Contrat cible : docs/contrat/auth-contrat-cible.yaml (simulée)
 */
export async function refreshApi(): Promise<TokenResponse> {
  try {
    const response = await fetch('/api/v1/auth/refresh', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    })

    if (!response.ok) {
      clearAccessToken()
      throw new AuthError('Session expirée. Veuillez vous reconnecter.', response.status)
    }

    const data = (await response.json()) as TokenResponse
    setAccessToken(data.access_token)
    return data
  } catch (error) {
    clearAccessToken()
    if (error instanceof AuthError) {
      throw error
    }
    throw new AuthError('Serveur injoignable. Veuillez vérifier votre connexion.', 0)
  }
}

/**
 * Endpoint de déconnexion explicite.
 * Route cible : POST /api/v1/auth/logout
 * Contrat cible : docs/contrat/auth-contrat-cible.yaml (simulée)
 */
export async function logoutApi(): Promise<LogoutResponse> {
  try {
    const response = await fetch('/api/v1/auth/logout', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    })

    clearAccessToken()

    if (!response.ok) {
      return { message: 'Déconnexion effectuée.' }
    }

    return (await response.json()) as LogoutResponse
  } catch {
    clearAccessToken()
    return { message: 'Déconnexion effectuée.' }
  }
}
