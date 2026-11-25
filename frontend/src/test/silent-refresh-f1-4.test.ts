import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from './mocks/server'
import {
  apiClient,
  getAccessToken,
  setAccessToken,
  clearAccessToken,
  enableSilentRefresh,
  disableSilentRefresh,
  isSilentRefreshEnabled,
  executeSilentRefresh,
  performLogout,
  onAuthEviction,
  clearAuthEvictionListeners,
  hasAttemptedInitialRefresh,
  setAttemptedInitialRefresh,
  resetInitialRefreshAttempt,
  resetAuthSession,
  ANALYST_INACTIVITY_POLICY,
  INACTIVITY_POLICY_C4,
} from '../api'

describe('Story F1.4 : Renouvellement silencieux et éviction', () => {
  beforeEach(() => {
    resetAuthSession()
    clearAccessToken()
    clearAuthEvictionListeners()
    enableSilentRefresh()
    vi.restoreAllMocks()
    window.localStorage.clear()
    window.sessionStorage.clear()
  })

  afterEach(() => {
    resetAuthSession()
    clearAccessToken()
    clearAuthEvictionListeners()
    vi.restoreAllMocks()
  })

  describe('1. Renouvellement silencieux unique sur 401 et rejeu de la requête', () => {
    it('un 401 sur une requête protégée déclenche exactement un appel à /refresh puis rejoue la requête avec succès', async () => {
      let refreshCallCount = 0

      server.use(
        http.post('*/api/v1/auth/refresh', () => {
          refreshCallCount++
          return HttpResponse.json(
            {
              access_token: 'mock-refreshed-token-valid-15m',
              token_type: 'bearer',
              expires_in: 900,
            },
            { status: 200 },
          )
        }),
      )

      // Jeton expiré positionné en mémoire vive
      setAccessToken('mock-expired-token')

      // Émission d'une requête protégée
      const { data, response, error } = await apiClient.GET('/api/v1/cases')

      // La requête initiale a reçu 401, a déclenché /refresh, puis a été rejouée
      expect(refreshCallCount).toBe(1)
      expect(error).toBeUndefined()
      expect(response.status).toBe(200)
      expect(data).toBeDefined()
      expect(data?.items).toEqual([])

      // Le nouveau jeton a remplacé le jeton expiré en mémoire vive volatile
      expect(getAccessToken()).toBe('mock-refreshed-token-valid-15m')
    })
  })

  describe('2. Concurrence et mutualisation des requêtes sur 401', () => {
    it('plusieurs requêtes concurrentes en 401 ne provoquent qu’un seul appel à /refresh et sont toutes rejouées avec succès', async () => {
      let refreshCallCount = 0

      server.use(
        http.post('*/api/v1/auth/refresh', async () => {
          refreshCallCount++
          // Simulation d'une latence réseau pour observer la mise en attente concurrente
          await new Promise((resolve) => setTimeout(resolve, 50))
          return HttpResponse.json(
            {
              access_token: 'mock-refreshed-concurrent-token-15m',
              token_type: 'bearer',
              expires_in: 900,
            },
            { status: 200 },
          )
        }),
      )

      setAccessToken('mock-expired-token')

      // 4 requêtes protégées émises simultanément avec le jeton expiré
      const [res1, res2, res3, res4] = await Promise.all([
        apiClient.GET('/api/v1/cases'),
        apiClient.GET('/api/v1/auth/me'),
        apiClient.GET('/api/v1/cases'),
        apiClient.GET('/api/v1/auth/me'),
      ])

      // Exactement un seul appel réseau a été émis vers /api/v1/auth/refresh
      expect(refreshCallCount).toBe(1)

      // Les 4 requêtes ont toutes abouti avec succès (code 200) après rejeu
      expect(res1.response.status).toBe(200)
      expect(res2.response.status).toBe(200)
      expect(res3.response.status).toBe(200)
      expect(res4.response.status).toBe(200)

      expect(res1.data?.items).toEqual([])
      expect(res2.data?.email).toBe('analyste@iryx.local')
      expect(res3.data?.items).toEqual([])
      expect(res4.data?.email).toBe('analyste@iryx.local')

      // Le jeton en mémoire vive a été mis à jour une seule fois
      expect(getAccessToken()).toBe('mock-refreshed-concurrent-token-15m')
    })
  })

  describe('3. Échec du renouvellement (401 ou erreur réseau) et éviction', () => {
    it('efface le jeton en mémoire vive et prononce l’éviction en cas d’échec 401 sur /refresh (cookie expiré)', async () => {
      let refreshCallCount = 0
      const evictionListener = vi.fn()
      onAuthEviction(evictionListener)

      server.use(
        http.post('*/api/v1/auth/refresh', () => {
          refreshCallCount++
          return HttpResponse.json(
            { detail: 'Session expirée. Veuillez vous reconnecter.' },
            { status: 401 },
          )
        }),
      )

      setAccessToken('mock-expired-token')

      const { response } = await apiClient.GET('/api/v1/cases')

      expect(refreshCallCount).toBe(1)
      expect(response.status).toBe(401)

      // Le jeton d'accès est immédiatement purgé de la mémoire vive volatile
      expect(getAccessToken()).toBeNull()

      // L'événement d'éviction a été notifié pour réorientation vers /login
      expect(evictionListener).toHaveBeenCalledTimes(1)
      expect(evictionListener).toHaveBeenCalledWith(
        expect.objectContaining({
          reason: expect.stringContaining('Session expirée'),
        }),
      )
    })

    it('efface le jeton en mémoire vive et prononce l’éviction en cas d’erreur réseau sur /refresh', async () => {
      let refreshCallCount = 0
      const evictionListener = vi.fn()
      onAuthEviction(evictionListener)

      server.use(
        http.post('*/api/v1/auth/refresh', () => {
          refreshCallCount++
          return HttpResponse.error()
        }),
      )

      setAccessToken('mock-expired-token')

      const { response } = await apiClient.GET('/api/v1/auth/me')

      expect(refreshCallCount).toBe(1)
      expect(response.status).toBe(401)
      expect(getAccessToken()).toBeNull()
      expect(evictionListener).toHaveBeenCalledTimes(1)
    })

    it('ne boucle pas à l’infini si la requête rejouée retourne à nouveau un code 401', async () => {
      let refreshCallCount = 0
      const evictionListener = vi.fn()
      onAuthEviction(evictionListener)

      server.use(
        http.post('*/api/v1/auth/refresh', () => {
          refreshCallCount++
          return HttpResponse.json(
            {
              access_token: 'mock-corrupted-token-401',
              token_type: 'bearer',
              expires_in: 900,
            },
            { status: 200 },
          )
        }),
        http.get('*/api/v1/cases', ({ request }) => {
          const authHeader = request.headers.get('Authorization')
          if (authHeader?.includes('corrupted')) {
            return HttpResponse.json({ detail: 'Jeton corrompu.' }, { status: 401 })
          }
          return HttpResponse.json({ detail: "Jeton d'accès expiré." }, { status: 401 })
        }),
      )

      setAccessToken('mock-expired-token')

      const { response } = await apiClient.GET('/api/v1/cases')

      // Exactement 1 appel à /refresh : pas de seconde tentative en boucle infinie
      expect(refreshCallCount).toBe(1)
      expect(response.status).toBe(401)
      expect(getAccessToken()).toBeNull()
      expect(evictionListener).toHaveBeenCalled()
    })
  })

  describe('4. Application de DP-06 : Renouvellement silencieux au chargement de page', () => {
    it('au chargement sans jeton mémoire, executeSilentRefresh tente le renouvellement une seule fois', async () => {
      let refreshCount = 0
      server.use(
        http.post('*/api/v1/auth/refresh', () => {
          refreshCount++
          return HttpResponse.json(
            {
              access_token: 'mock-token-dp06-f5',
              token_type: 'bearer',
              expires_in: 900,
            },
            { status: 200 },
          )
        }),
      )

      expect(getAccessToken()).toBeNull()
      expect(hasAttemptedInitialRefresh()).toBe(false)

      // Appel initial DP-06
      const token = await executeSilentRefresh()
      setAttemptedInitialRefresh(true)

      expect(refreshCount).toBe(1)
      expect(token).toBe('mock-token-dp06-f5')
      expect(getAccessToken()).toBe('mock-token-dp06-f5')
      expect(hasAttemptedInitialRefresh()).toBe(true)
    })

    it('en cas d’échec du renouvellement DP-06, la session reste nulle et l’éviction est émise', async () => {
      const evictionListener = vi.fn()
      onAuthEviction(evictionListener)

      server.use(
        http.post('*/api/v1/auth/refresh', () => {
          return HttpResponse.json(
            { detail: 'Session expirée. Veuillez vous reconnecter.' },
            { status: 401 },
          )
        }),
      )

      expect(getAccessToken()).toBeNull()

      await expect(executeSilentRefresh()).rejects.toThrow('Session expirée')

      expect(getAccessToken()).toBeNull()
      expect(evictionListener).toHaveBeenCalledTimes(1)
    })
  })

  describe('5. Déconnexion explicite (Logout - ADR-0011 / D6)', () => {
    it('appelle POST /api/v1/auth/logout, purge la mémoire vive et émet l’éviction', async () => {
      let logoutCalled = false
      const evictionListener = vi.fn()
      onAuthEviction(evictionListener)

      server.use(
        http.post('*/api/v1/auth/logout', () => {
          logoutCalled = true
          return HttpResponse.json({ message: 'Déconnexion réussie.' }, { status: 200 })
        }),
      )

      // Analyste connecté
      setAccessToken('mock-logged-in-token')
      expect(getAccessToken()).toBe('mock-logged-in-token')

      // Déconnexion explicite
      await performLogout()

      expect(logoutCalled).toBe(true)
      expect(getAccessToken()).toBeNull()
      expect(evictionListener).toHaveBeenCalledTimes(1)
      expect(evictionListener).toHaveBeenCalledWith(
        expect.objectContaining({
          reason: 'Déconnexion réussie.',
        }),
      )
    })

    it('purge la mémoire vive volatile même si l’appel réseau de déconnexion échoue', async () => {
      const evictionListener = vi.fn()
      onAuthEviction(evictionListener)

      server.use(
        http.post('*/api/v1/auth/logout', () => {
          return HttpResponse.error()
        }),
      )

      setAccessToken('mock-logged-in-token')

      await performLogout()

      expect(getAccessToken()).toBeNull()
      expect(evictionListener).toHaveBeenCalledTimes(1)
    })
  })

  describe('6. Sécurité absolue : interdiction de localStorage et sessionStorage (ADR-0011)', () => {
    it('aucune écriture dans localStorage ni sessionStorage lors du renouvellement et de l’éviction', async () => {
      const localStorageSpy = vi.spyOn(window.localStorage, 'setItem')
      const sessionStorageSpy = vi.spyOn(window.sessionStorage, 'setItem')

      setAccessToken('mock-expired-token')

      // Renouvellement et rejeu réussis
      await apiClient.GET('/api/v1/cases')

      // Déconnexion
      await performLogout()

      // Filtre sur d'éventuels appels internes hors application
      const appLocalStorageCalls = localStorageSpy.mock.calls.filter(
        ([key]) => key !== '__msw-cookie-store__',
      )
      expect(appLocalStorageCalls).toHaveLength(0)
      expect(sessionStorageSpy).not.toHaveBeenCalled()

      expect(window.localStorage.getItem('access_token')).toBeNull()
      expect(window.localStorage.getItem('token')).toBeNull()
      expect(window.sessionStorage.getItem('access_token')).toBeNull()
      expect(window.sessionStorage.getItem('token')).toBeNull()
      expect(window.sessionStorage.length).toBe(0)
    })
  })

  describe('7. Emplacement réservé pour la politique d’inactivité (C4)', () => {
    it('expose la mention "à décider (C4)" pour la politique d\'inactivité', () => {
      expect(ANALYST_INACTIVITY_POLICY).toBe('à décider (C4)')
      expect(INACTIVITY_POLICY_C4).toBe('à décider (C4)')
    })
  })

  describe('8. Contrôle du cycle de session et des bascules de renouvellement', () => {
    it('permet d’activer, désactiver et interroger l’état du renouvellement silencieux', () => {
      enableSilentRefresh()
      expect(isSilentRefreshEnabled()).toBe(true)

      disableSilentRefresh()
      expect(isSilentRefreshEnabled()).toBe(false)
    })

    it('permet de réinitialiser la tentative initiale au chargement', () => {
      setAttemptedInitialRefresh(true)
      expect(hasAttemptedInitialRefresh()).toBe(true)

      resetInitialRefreshAttempt()
      expect(hasAttemptedInitialRefresh()).toBe(false)
    })
  })
})
