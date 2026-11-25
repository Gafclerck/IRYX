import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  getAccessToken,
  setAccessToken,
  clearAccessToken,
  hasAccessToken,
} from '../api/auth-memory'
import { loginApi } from '../api/auth'

describe("Stockage du jeton d'accès exclusivement en mémoire vive volatile (ADR-0011)", () => {
  beforeEach(() => {
    clearAccessToken()
    vi.restoreAllMocks()
    window.localStorage.clear()
    window.sessionStorage.clear()
  })

  it('initialise le jeton à null en mémoire', () => {
    expect(getAccessToken()).toBeNull()
    expect(hasAccessToken()).toBe(false)
  })

  it('enregistre et restitue le jeton en mémoire vive volatile', () => {
    const mockToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.mock'
    setAccessToken(mockToken)

    expect(getAccessToken()).toBe(mockToken)
    expect(hasAccessToken()).toBe(true)
  })

  it('purge le jeton de la mémoire vive volatile lors de clearAccessToken', () => {
    setAccessToken('mon-jeton-temporaire')
    expect(hasAccessToken()).toBe(true)

    clearAccessToken()
    expect(getAccessToken()).toBeNull()
    expect(hasAccessToken()).toBe(false)
  })

  it("n'écrit JAMAIS le jeton dans localStorage ni sessionStorage (Règle stricte ADR-0011)", async () => {
    const localStorageSpy = vi.spyOn(window.localStorage, 'setItem')
    const sessionStorageSpy = vi.spyOn(window.sessionStorage, 'setItem')

    const mockToken = 'jwt-secret-token-in-memory-only'
    setAccessToken(mockToken)

    // Vérification que setItem n'a jamais été appelé sur aucun des stockages
    expect(localStorageSpy).not.toHaveBeenCalled()
    expect(sessionStorageSpy).not.toHaveBeenCalled()

    // Vérification que les stockages ne contiennent aucune trace
    expect(window.localStorage.getItem('access_token')).toBeNull()
    expect(window.localStorage.getItem('token')).toBeNull()
    expect(window.sessionStorage.getItem('access_token')).toBeNull()
    expect(window.sessionStorage.getItem('token')).toBeNull()
    expect(window.localStorage.length).toBe(0)
    expect(window.sessionStorage.length).toBe(0)
  })

  it("conserve le jeton uniquement en mémoire lors de l'appel de loginApi", async () => {
    const localStorageSpy = vi.spyOn(window.localStorage, 'setItem')
    const sessionStorageSpy = vi.spyOn(window.sessionStorage, 'setItem')

    const response = await loginApi({
      email: 'analyste@iryx.local',
      password: 'SecretPassword123!',
    })

    expect(response.access_token).toBeDefined()
    expect(getAccessToken()).toBe(response.access_token)

    // Interdiction absolue de persistance de l'access token
    const applicationStorageCalls = localStorageSpy.mock.calls.filter(
      ([key]) => key !== '__msw-cookie-store__',
    )
    expect(applicationStorageCalls).toHaveLength(0)
    expect(sessionStorageSpy).not.toHaveBeenCalled()

    expect(window.localStorage.getItem('access_token')).toBeNull()
    expect(window.localStorage.getItem('token')).toBeNull()
    expect(window.sessionStorage.getItem('access_token')).toBeNull()
    expect(window.sessionStorage.getItem('token')).toBeNull()
    expect(window.sessionStorage.length).toBe(0)
  })
})
