import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { server } from './mocks/server'
import { AuthGuard } from '../features/auth/components/AuthGuard'
import {
  clearAccessToken,
  setAccessToken,
  resetAuthSession,
  setAttemptedInitialRefresh,
} from '../api'

describe('AuthGuard (Story F1.1 et F1.4 / DP-06)', () => {
  beforeEach(() => {
    resetAuthSession()
    clearAccessToken()
    window.localStorage.clear()
    window.sessionStorage.clear()
  })

  afterEach(() => {
    resetAuthSession()
    clearAccessToken()
  })

  describe('1. Mode synchrone avec paramètre isAuthenticated explicite (F1.1)', () => {
    it('redirige vers /login si lutilisateur nest pas authentifié', () => {
      render(
        <MemoryRouter initialEntries={['/cases']}>
          <Routes>
            <Route path="/login" element={<div>Page de connexion</div>} />
            <Route
              path="/cases"
              element={
                <AuthGuard isAuthenticated={false}>
                  <div>Espace protégé</div>
                </AuthGuard>
              }
            />
          </Routes>
        </MemoryRouter>,
      )

      expect(screen.getByText('Page de connexion')).toBeInTheDocument()
      expect(screen.queryByText('Espace protégé')).not.toBeInTheDocument()
    })

    it('rend les enfants si lutilisateur est authentifié', () => {
      render(
        <MemoryRouter initialEntries={['/cases']}>
          <Routes>
            <Route
              path="/cases"
              element={
                <AuthGuard isAuthenticated={true}>
                  <div>Espace protégé</div>
                </AuthGuard>
              }
            />
          </Routes>
        </MemoryRouter>,
      )

      expect(screen.getByText('Espace protégé')).toBeInTheDocument()
    })
  })

  describe('2. Mode dynamique avec jeton en mémoire vive (F1.4)', () => {
    it('rend directement les enfants si un jeton actif est déjà présent en mémoire', () => {
      setAccessToken('mock-active-token')

      render(
        <MemoryRouter initialEntries={['/cases']}>
          <Routes>
            <Route path="/login" element={<div>Page de connexion</div>} />
            <Route
              path="/cases"
              element={
                <AuthGuard>
                  <div>Espace protégé avec jeton</div>
                </AuthGuard>
              }
            />
          </Routes>
        </MemoryRouter>,
      )

      expect(screen.getByText('Espace protégé avec jeton')).toBeInTheDocument()
    })
  })

  describe('3. Application de DP-06 : Renouvellement silencieux unique au chargement', () => {
    it('au chargement sans jeton, tente un renouvellement silencieux unique qui donne accès à l’espace protégé si réussi', async () => {
      server.use(
        http.post('*/api/v1/auth/refresh', () => {
          return HttpResponse.json(
            {
              access_token: 'mock-refreshed-dp06-token',
              token_type: 'bearer',
              expires_in: 900,
            },
            { status: 200 },
          )
        }),
      )

      render(
        <MemoryRouter initialEntries={['/cases']}>
          <Routes>
            <Route path="/login" element={<div>Page de connexion</div>} />
            <Route
              path="/cases"
              element={
                <AuthGuard>
                  <div>Espace protégé après DP-06</div>
                </AuthGuard>
              }
            />
          </Routes>
        </MemoryRouter>,
      )

      // Indicateur de chargement affiché pendant le renouvellement
      expect(screen.getByRole('status')).toBeInTheDocument()
      expect(screen.getByText('Vérification de la session en cours...')).toBeInTheDocument()

      // Après succès du renouvellement, l'espace protégé s'affiche sans redirection /login
      await waitFor(() => {
        expect(screen.getByText('Espace protégé après DP-06')).toBeInTheDocument()
      })
      expect(screen.queryByText('Page de connexion')).not.toBeInTheDocument()
    })

    it('au chargement sans jeton, si le renouvellement échoue, redirige vers /login', async () => {
      server.use(
        http.post('*/api/v1/auth/refresh', () => {
          return HttpResponse.json(
            { detail: 'Session expirée. Veuillez vous reconnecter.' },
            { status: 401 },
          )
        }),
      )

      render(
        <MemoryRouter initialEntries={['/cases']}>
          <Routes>
            <Route path="/login" element={<div>Page de connexion</div>} />
            <Route
              path="/cases"
              element={
                <AuthGuard>
                  <div>Espace protégé</div>
                </AuthGuard>
              }
            />
          </Routes>
        </MemoryRouter>,
      )

      await waitFor(() => {
        expect(screen.getByText('Page de connexion')).toBeInTheDocument()
      })
      expect(screen.queryByText('Espace protégé')).not.toBeInTheDocument()
    })

    it('si le renouvellement initial a déjà été tenté, redirige immédiatement vers /login sans relancer /refresh', () => {
      let refreshCallCount = 0
      server.use(
        http.post('*/api/v1/auth/refresh', () => {
          refreshCallCount++
          return HttpResponse.json({ detail: 'Session expirée.' }, { status: 401 })
        }),
      )

      setAttemptedInitialRefresh(true)

      render(
        <MemoryRouter initialEntries={['/cases']}>
          <Routes>
            <Route path="/login" element={<div>Page de connexion</div>} />
            <Route
              path="/cases"
              element={
                <AuthGuard>
                  <div>Espace protégé</div>
                </AuthGuard>
              }
            />
          </Routes>
        </MemoryRouter>,
      )

      expect(screen.getByText('Page de connexion')).toBeInTheDocument()
      expect(refreshCallCount).toBe(0)
    })
  })
})
