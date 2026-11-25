import createClient from 'openapi-fetch'
import type { paths } from './schema'
import { getAccessToken } from './auth-memory'

/**
 * Client réseau HTTP typé d'après le contrat OpenAPI.
 * Injecte l'en-tête Authorization: Bearer <token> présent en mémoire vive.
 */
export const apiClient = createClient<paths>({
  baseUrl: '',
})

apiClient.use({
  onRequest({ request }) {
    const token = getAccessToken()
    if (token) {
      request.headers.set('Authorization', `Bearer ${token}`)
    }
    return request
  },
})
