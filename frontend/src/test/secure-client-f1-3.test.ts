import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import {
  apiClient,
  isLoginRoute,
  getAccessToken,
  setAccessToken,
  clearAccessToken,
  onAuthSignal,
  clearAuthSignalListeners,
  getAuthSignalListenersCount,
  ANALYST_INACTIVITY_POLICY,
  INACTIVITY_POLICY_C4,
} from '../api'
import { loginApi } from '../api/auth'

describe('Story F1.3 : Client réseau sécurisé et détection du 401', () => {
  beforeEach(() => {
    clearAccessToken()
    clearAuthSignalListeners()
    vi.restoreAllMocks()
    window.localStorage.clear()
    window.sessionStorage.clear()
  })

  afterEach(() => {
    clearAccessToken()
    clearAuthSignalListeners()
    vi.restoreAllMocks()
  })

  describe("1. Injection de l'en-tête Authorization: Bearer <token> sur requêtes protégées", () => {
    it("injecte l'en-tête Authorization: Bearer avec le jeton en mémoire vive volatile", async () => {
      const activeToken = 'mock-access-token-bearer-15min'
      setAccessToken(activeToken)

      const signalListener = vi.fn()
      onAuthSignal(signalListener)

      const { data, error, response } = await apiClient.GET('/api/v1/auth/me')

      expect(error).toBeUndefined()
      expect(response.status).toBe(200)
      expect(data).toBeDefined()
      expect(data?.email).toBe('analyste@iryx.local')
      expect(data?.id).toBe('00000000-0000-0000-0000-000000000001')
      expect(signalListener).not.toHaveBeenCalled()
    })

    it('transmet les requêtes protégées sans altération de la charge utile', async () => {
      setAccessToken('mock-access-token-bearer-15min')

      const { data, response } = await apiClient.GET('/api/v1/cases')

      expect(response.status).toBe(200)
      expect(data).toBeDefined()
      expect(data?.items).toEqual([])
      expect(data?.total).toBe(0)
    })
  })

  describe('2. Requête protégée sans jeton (Règle documentée F1.3)', () => {
    it('transmet la requête sans en-tête Authorization, reçoit un 401 et émet le signal interne', async () => {
      clearAccessToken()
      expect(getAccessToken()).toBeNull()

      const signalListener = vi.fn()
      onAuthSignal(signalListener)

      const { response, error } = await apiClient.GET('/api/v1/auth/me')

      expect(response.status).toBe(401)
      expect(error).toBeDefined()
      expect(signalListener).toHaveBeenCalledTimes(1)
      expect(signalListener).toHaveBeenCalledWith(
        expect.objectContaining({
          reason: 'jeton expiré ou absent',
          status: 401,
          url: expect.stringContaining('/api/v1/auth/me'),
        }),
      )
    })
  })

  describe('3. Détection du code HTTP 401 sur requête protégée', () => {
    it('émet le signal « jeton expiré ou absent » sur un 401 avec jeton expiré', async () => {
      setAccessToken('mock-expired-token')

      const signalListener = vi.fn()
      onAuthSignal(signalListener)

      const { response, error } = await apiClient.GET('/api/v1/cases')

      expect(response.status).toBe(401)
      expect(error).toBeDefined()
      expect(signalListener).toHaveBeenCalledTimes(1)
      const payload = signalListener.mock.calls[0]?.[0]
      expect(payload).toBeDefined()
      expect(payload?.reason).toBe('jeton expiré ou absent')
      expect(payload?.status).toBe(401)
      expect(payload?.timestamp).toBeDefined()
      expect(payload?.url).toContain('/api/v1/cases')
    })

    it('ne réalise AUCUN renouvellement silencieux de jeton (réservé à F1.4)', async () => {
      setAccessToken('mock-expired-token')

      const signalListener = vi.fn()
      onAuthSignal(signalListener)

      // Le jeton reste tel quel en F1.3 : pas de tentative d'appel automatique à /refresh
      await apiClient.GET('/api/v1/auth/me')

      expect(getAccessToken()).toBe('mock-expired-token')
      expect(signalListener).toHaveBeenCalledTimes(1)
    })
  })

  describe('4. Exclusion formelle de la route de connexion (/api/v1/auth/login)', () => {
    it("n'émet PAS le signal d'expiration lors d'un échec 401 sur /api/v1/auth/login via loginApi", async () => {
      const signalListener = vi.fn()
      onAuthSignal(signalListener)

      await expect(
        loginApi({
          email: 'inconnu@iryx.local',
          password: 'SecretPassword123!',
        }),
      ).rejects.toThrow('Identifiants incorrects.')

      expect(signalListener).not.toHaveBeenCalled()
    })

    it("n'émet PAS le signal d'expiration lors d'un 401 direct sur /api/v1/auth/login via apiClient", async () => {
      const signalListener = vi.fn()
      onAuthSignal(signalListener)

      const { response } = await apiClient.POST('/api/v1/auth/login', {
        body: {
          email: 'inconnu@iryx.local',
          password: 'mauvaismdp',
        },
      })

      expect(response.status).toBe(401)
      expect(signalListener).not.toHaveBeenCalled()
    })

    it('identifie correctement les variantes de chemin pour la route de connexion', () => {
      expect(isLoginRoute('/api/v1/auth/login')).toBe(true)
      expect(isLoginRoute('http://localhost:3000/api/v1/auth/login')).toBe(true)
      expect(isLoginRoute('/api/v1/auth/login?param=1')).toBe(true)
      expect(isLoginRoute('/api/v1/auth/me')).toBe(false)
      expect(isLoginRoute('/api/v1/cases')).toBe(false)
      expect(isLoginRoute('/api/v1/organizations')).toBe(false)
    })
  })

  describe("5. Comportement sur erreurs 5xx et absence d'invalidation intempestive", () => {
    it("propage l'erreur 500 sans émettre le signal d'expiration ni purger le jeton", async () => {
      const token = 'mock-server-error-token'
      setAccessToken(token)

      const signalListener = vi.fn()
      onAuthSignal(signalListener)

      const { response, error } = await apiClient.GET('/api/v1/auth/me')

      expect(response.status).toBe(500)
      expect(error).toBeDefined()
      // Aucun signal d'expiration ne doit être émis pour une erreur 5xx
      expect(signalListener).not.toHaveBeenCalled()
      // Le jeton reste intact en mémoire vive
      expect(getAccessToken()).toBe(token)
    })
  })

  describe("6. Respect strict de l'interdiction de localStorage et sessionStorage (ADR-0011)", () => {
    it("n'écrit JAMAIS de jeton dans localStorage ni sessionStorage lors des appels API", async () => {
      const localStorageSpy = vi.spyOn(window.localStorage, 'setItem')
      const sessionStorageSpy = vi.spyOn(window.sessionStorage, 'setItem')

      setAccessToken('token-test-security-f1-3')

      // Appel réussi
      await apiClient.GET('/api/v1/auth/me')

      // Appel rejeté 401
      setAccessToken('mock-expired-token')
      await apiClient.GET('/api/v1/cases')

      // Vérification des appels de stockage applicatif
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

  describe('7. Gestion du cycle de vie des écouteurs de signal', () => {
    it("permet la désinscription unitaire d'un écouteur via la fonction retournée", async () => {
      const signalListener = vi.fn()
      const unsubscribe = onAuthSignal(signalListener)

      expect(getAuthSignalListenersCount()).toBe(1)

      // Désinscription
      unsubscribe()
      expect(getAuthSignalListenersCount()).toBe(0)

      // Requête 401 après désinscription
      setAccessToken('mock-expired-token')
      await apiClient.GET('/api/v1/cases')

      expect(signalListener).not.toHaveBeenCalled()
    })

    it('permet la purge globale de tous les écouteurs', () => {
      const l1 = vi.fn()
      const l2 = vi.fn()
      onAuthSignal(l1)
      onAuthSignal(l2)
      expect(getAuthSignalListenersCount()).toBe(2)

      clearAuthSignalListeners()
      expect(getAuthSignalListenersCount()).toBe(0)
    })
  })

  describe("8. Emplacement réservé pour la politique d'inactivité (C4)", () => {
    it('expose la mention "à décider (C4)" pour la politique d\'inactivité', () => {
      expect(ANALYST_INACTIVITY_POLICY).toBe('à décider (C4)')
      expect(INACTIVITY_POLICY_C4).toBe('à décider (C4)')
    })
  })
})
