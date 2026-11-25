/**
 * Types du module d'authentification IRYX.
 * Source cible : docs/contrat/auth-contrat-cible.yaml
 * Mention : simulée, contrat cible : auth-contrat-cible.yaml
 */

export interface LoginRequest {
  email: string
  password: string
}

export interface TokenResponse {
  access_token: string
  token_type: 'bearer'
  expires_in: number
}

export interface LogoutResponse {
  message: string
}

export interface ErrorResponse {
  detail: string
}
