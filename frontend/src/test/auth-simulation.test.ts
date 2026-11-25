import { describe, it, expect, beforeEach } from 'vitest'
import { loginApi, refreshApi, logoutApi } from '../api/auth'
import { getAccessToken, clearAccessToken } from '../api/auth-memory'

describe("Simulation des routes d'authentification (contrat cible : auth-contrat-cible.yaml)", () => {
  beforeEach(() => {
    clearAccessToken()
  })

  describe('POST /api/v1/auth/login', () => {
    it('renvoie un access_token de 15 minutes et place le jeton en mémoire en cas de succès', async () => {
      const response = await loginApi({
        email: 'analyste@iryx.local',
        password: 'SecretPassword123!',
      })

      expect(response.access_token).toBe('mock-access-token-bearer-15min')
      expect(response.token_type).toBe('bearer')
      expect(response.expires_in).toBe(900) // 15 minutes = 900 s
      expect(getAccessToken()).toBe('mock-access-token-bearer-15min')
    })

    it('rejette avec "Identifiants incorrects." sur mauvais mot de passe (401)', async () => {
      await expect(
        loginApi({
          email: 'analyste@iryx.local',
          password: 'wrong-password',
        }),
      ).rejects.toThrow('Identifiants incorrects.')

      expect(getAccessToken()).toBeNull()
    })

    it('rejette avec "Identifiants incorrects." sur utilisateur inconnu (401)', async () => {
      await expect(
        loginApi({
          email: 'inconnu@iryx.local',
          password: 'SecretPassword123!',
        }),
      ).rejects.toThrow('Identifiants incorrects.')

      expect(getAccessToken()).toBeNull()
    })

    it('rejette avec message explicite de révocation sur compte inactif (403)', async () => {
      await expect(
        loginApi({
          email: 'bloque@iryx.local',
          password: 'SecretPassword123!',
        }),
      ).rejects.toThrow('Compte inactif ou accès révoqué. Contactez votre administrateur.')

      expect(getAccessToken()).toBeNull()
    })

    it('rejette avec "Identifiants incorrects." en cas d\'erreur serveur 500', async () => {
      await expect(
        loginApi({
          email: 'serveur-erreur@iryx.local',
          password: 'SecretPassword123!',
        }),
      ).rejects.toThrow('Identifiants incorrects.')

      expect(getAccessToken()).toBeNull()
    })
  })

  describe('POST /api/v1/auth/refresh', () => {
    it('délivre un nouvel access token de 15 minutes lors du renouvellement', async () => {
      const response = await refreshApi()

      expect(response.access_token).toBe('mock-refreshed-access-token-bearer-15min')
      expect(response.token_type).toBe('bearer')
      expect(response.expires_in).toBe(900)
      expect(getAccessToken()).toBe('mock-refreshed-access-token-bearer-15min')
    })
  })

  describe('POST /api/v1/auth/logout', () => {
    it("purge le jeton d'accès en mémoire vive volatile lors de la déconnexion", async () => {
      // Prépositionnement d'un jeton en mémoire
      await loginApi({
        email: 'analyste@iryx.local',
        password: 'SecretPassword123!',
      })
      expect(getAccessToken()).not.toBeNull()

      // Déconnexion
      const response = await logoutApi()
      expect(response.message).toBe('Déconnexion réussie.')
      expect(getAccessToken()).toBeNull()
    })
  })
})
