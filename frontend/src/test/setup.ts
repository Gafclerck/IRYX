import '@testing-library/jest-dom/vitest'
import { afterAll, afterEach, beforeAll } from 'vitest'
import { server } from './mocks/server'
import {
  resetMockCases,
  resetMockEvidences,
  resetMockH1Decisions,
  resetMockPlanPolling,
  resetMockRunSupervision,
} from './mocks/handlers'
import { clearAccessToken, clearSessionListeners } from '../api/auth-memory'
import { clearAuthSignalListeners } from '../api/auth-signal'

// Polyfill pour Storage en environnement jsdom / Node 22+
class MockStorage implements Storage {
  private store = new Map<string, string>()

  get length(): number {
    return this.store.size
  }

  clear(): void {
    this.store.clear()
  }

  getItem(key: string): string | null {
    return this.store.get(key) ?? null
  }

  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null
  }

  removeItem(key: string): void {
    this.store.delete(key)
  }

  setItem(key: string, value: string): void {
    this.store.set(key, String(value))
  }
}

const mockLocalStorage = new MockStorage()
const mockSessionStorage = new MockStorage()

if (typeof window !== 'undefined') {
  Object.defineProperty(window, 'localStorage', {
    value: mockLocalStorage,
    writable: true,
    configurable: true,
  })
  Object.defineProperty(window, 'sessionStorage', {
    value: mockSessionStorage,
    writable: true,
    configurable: true,
  })
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))

/**
 * Isolation globale entre deux tests : handlers MSW, données simulées mutables,
 * jeton/identité en mémoire, écouteurs de session et de signal d'authentification,
 * et stockage navigateur simulé.
 *
 * Le cache TanStack Query reste isolé par render (un QueryClient neuf est créé
 * dans chaque fonction de rendu des tests), il n'existe donc pas de cache global
 * à purger ici.
 */
afterEach(() => {
  server.resetHandlers()
  resetMockCases()
  resetMockEvidences()
  resetMockPlanPolling()
  resetMockH1Decisions()
  resetMockRunSupervision()
  clearAccessToken()
  clearSessionListeners()
  clearAuthSignalListeners()
  mockLocalStorage.clear()
  mockSessionStorage.clear()
})

afterAll(() => server.close())
