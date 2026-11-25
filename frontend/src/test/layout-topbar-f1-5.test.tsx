import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, act, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { server } from './mocks/server'
import { TopBar } from '../components/layout/TopBar'
import { AuthenticatedLayout } from '../components/layout/AuthenticatedLayout'
import {
  setAccessToken,
  getAccessToken,
  setSessionUser,
  getSessionUser,
  clearAccessToken,
  clearSessionUser,
} from '../api/auth-memory'
import { resetAuthSession } from '../api/auth-session'
import { AuthGuard } from '../features/auth/components/AuthGuard'
import { LoginPage } from '../pages/LoginPage'
import { NotFoundPage } from '../pages/NotFoundPage'

describe('Story F1.5 : Layout permanent, TopBar et Déconnexion explicite (DP-02, ADR-0011)', () => {
  beforeEach(() => {
    resetAuthSession()
    clearAccessToken()
    clearSessionUser()
    window.localStorage.clear()
    window.sessionStorage.clear()
  })

  afterEach(() => {
    cleanup()
    resetAuthSession()
    clearAccessToken()
    clearSessionUser()
    vi.restoreAllMocks()
  })

  describe('1. Barre supérieure (TopBar) et état de session en mémoire', () => {
    it('affiche la TopBar avec 56px de hauteur, fond ink, bordure deep et logo IRYX', () => {
      render(
        <MemoryRouter>
          <TopBar />
        </MemoryRouter>,
      )

      const header = screen.getByRole('banner')
      expect(header).toBeInTheDocument()
      expect(header.className).toContain('h-14')
      expect(header.className).toContain('bg-ink')
      expect(header.className).toContain('border-deep')
      expect(screen.getByText('IRYX')).toBeInTheDocument()
    })

    it('affiche les valeurs neutres « Organisation » et « Utilisateur » quand la session est vide (sans données inventées)', () => {
      render(
        <MemoryRouter>
          <TopBar />
        </MemoryRouter>,
      )

      expect(screen.getByTestId('topbar-org')).toHaveTextContent('Organisation')
      expect(screen.getByTestId('topbar-user')).toHaveTextContent('Utilisateur')
      expect(screen.queryByTestId('topbar-role')).not.toBeInTheDocument()
    })

    it("restitue fidèlement le nom d'organisation et l'utilisateur issus de la mémoire volatile", () => {
      setSessionUser({
        organizationName: 'CERT National',
        userName: 'Alexandre Renard',
        role: 'Enquêteur DFIR',
      })

      render(
        <MemoryRouter>
          <TopBar />
        </MemoryRouter>,
      )

      expect(screen.getByTestId('topbar-org')).toHaveTextContent('CERT National')
      expect(screen.getByTestId('topbar-user')).toHaveTextContent('Alexandre Renard')
      expect(screen.getByTestId('topbar-role')).toHaveTextContent('Enquêteur DFIR')
    })

    it('actualise dynamiquement son affichage en cas de mise à jour de la session en mémoire', async () => {
      render(
        <MemoryRouter>
          <TopBar />
        </MemoryRouter>,
      )

      expect(screen.getByTestId('topbar-user')).toHaveTextContent('Utilisateur')

      await act(async () => {
        setSessionUser({
          organizationName: 'SOC Privé',
          userName: 'Camille Martin',
        })
      })

      expect(screen.getByTestId('topbar-org')).toHaveTextContent('SOC Privé')
      expect(screen.getByTestId('topbar-user')).toHaveTextContent('Camille Martin')
    })
  })

  describe('2. Déconnexion explicite (F1.4 / D6)', () => {
    it('appelle la déconnexion, purge la mémoire vive et redirige vers /login', async () => {
      const user = userEvent.setup()
      let logoutApiCalled = false

      server.use(
        http.post('*/api/v1/auth/logout', () => {
          logoutApiCalled = true
          return HttpResponse.json({ message: 'Déconnexion réussie.' }, { status: 200 })
        }),
      )

      setAccessToken('active-bearer-token')
      setSessionUser({
        organizationName: 'Agence DFIR',
        userName: 'Enquêteur 1',
      })

      render(
        <MemoryRouter initialEntries={['/cases']}>
          <Routes>
            <Route path="/cases" element={<AuthenticatedLayout />} />
            <Route path="/login" element={<div>Page de connexion /login</div>} />
          </Routes>
        </MemoryRouter>,
      )

      const logoutBtn = screen.getByRole('button', { name: 'Se déconnecter' })
      expect(logoutBtn).toBeInTheDocument()

      await user.click(logoutBtn)

      await waitFor(() => {
        expect(logoutApiCalled).toBe(true)
        expect(getAccessToken()).toBeNull()
        expect(getSessionUser()).toBeNull()
        expect(screen.getByText('Page de connexion /login')).toBeInTheDocument()
      })
    })

    it("purge la mémoire et redirige impérativement vers /login même en cas d'échec réseau de l'API", async () => {
      const user = userEvent.setup()

      server.use(
        http.post('*/api/v1/auth/logout', () => {
          return HttpResponse.error()
        }),
      )

      setAccessToken('token-to-purge')
      setSessionUser({ userName: 'Enquêteur Résilient' })

      render(
        <MemoryRouter initialEntries={['/cases']}>
          <Routes>
            <Route path="/cases" element={<AuthenticatedLayout />} />
            <Route path="/login" element={<div>Page de connexion de secours</div>} />
          </Routes>
        </MemoryRouter>,
      )

      const logoutBtn = screen.getByRole('button', { name: 'Se déconnecter' })
      await user.click(logoutBtn)

      await waitFor(() => {
        expect(getAccessToken()).toBeNull()
        expect(getSessionUser()).toBeNull()
        expect(screen.getByText('Page de connexion de secours')).toBeInTheDocument()
      })
    })
  })

  describe('3. Enveloppement des routes et étanchéité du layout', () => {
    it('les routes authentifiées sont affichées dans AuthenticatedLayout avec la TopBar', () => {
      setAccessToken('valid-bearer')

      render(
        <MemoryRouter initialEntries={['/cases']}>
          <Routes>
            <Route
              element={
                <AuthGuard>
                  <AuthenticatedLayout />
                </AuthGuard>
              }
            >
              <Route path="/cases" element={<div>Contenu de la vue des dossiers</div>} />
            </Route>
            <Route path="/login" element={<LoginPage />} />
          </Routes>
        </MemoryRouter>,
      )

      expect(screen.getByRole('banner')).toBeInTheDocument()
      expect(screen.getByText('Contenu de la vue des dossiers')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Se déconnecter' })).toBeInTheDocument()
    })

    it('la page /login est affichée hors layout (sans TopBar)', () => {
      render(
        <MemoryRouter initialEntries={['/login']}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              path="/cases"
              element={
                <AuthGuard>
                  <AuthenticatedLayout />
                </AuthGuard>
              }
            />
          </Routes>
        </MemoryRouter>,
      )

      expect(screen.queryByRole('banner')).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Se déconnecter' })).not.toBeInTheDocument()
      expect(screen.getByRole('heading', { level: 2, name: 'Connexion' })).toBeInTheDocument()
    })

    it('la page 404 est affichée hors layout (sans TopBar)', () => {
      render(
        <MemoryRouter initialEntries={['/route-inexistante']}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              element={
                <AuthGuard>
                  <AuthenticatedLayout />
                </AuthGuard>
              }
            >
              <Route path="/cases" element={<div>Espace dossiers</div>} />
            </Route>
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </MemoryRouter>,
      )

      expect(screen.queryByRole('banner')).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Se déconnecter' })).not.toBeInTheDocument()
      expect(screen.getByText('404')).toBeInTheDocument()
      expect(screen.getByText('Page non trouvée')).toBeInTheDocument()
    })
  })

  describe('4. Sécurité : Aucune écriture dans localStorage ni sessionStorage (ADR-0011)', () => {
    it('ne stocke ni ne lit aucune donnée applicative dans localStorage ou sessionStorage', async () => {
      const user = userEvent.setup()
      const localSetSpy = vi.spyOn(window.localStorage, 'setItem')
      const localGetSpy = vi.spyOn(window.localStorage, 'getItem')
      const sessionSetSpy = vi.spyOn(window.sessionStorage, 'setItem')
      const sessionGetSpy = vi.spyOn(window.sessionStorage, 'getItem')

      setAccessToken('token-test-storage')
      setSessionUser({
        organizationName: 'SecOps',
        userName: 'Analyste Strict',
      })

      render(
        <MemoryRouter initialEntries={['/cases']}>
          <Routes>
            <Route path="/cases" element={<AuthenticatedLayout />} />
            <Route path="/login" element={<div>Login</div>} />
          </Routes>
        </MemoryRouter>,
      )

      expect(screen.getByTestId('topbar-user')).toHaveTextContent('Analyste Strict')

      const logoutBtn = screen.getByRole('button', { name: 'Se déconnecter' })
      await user.click(logoutBtn)

      await waitFor(() => {
        expect(screen.getByText('Login')).toBeInTheDocument()
      })

      // Aucune écriture applicative dans le stockage
      const appLocalSetCalls = localSetSpy.mock.calls.filter(
        ([key]) => key !== '__msw-cookie-store__',
      )
      const appLocalGetCalls = localGetSpy.mock.calls.filter(
        ([key]) => key !== '__msw-cookie-store__',
      )

      expect(appLocalSetCalls).toHaveLength(0)
      expect(appLocalGetCalls).toHaveLength(0)
      expect(sessionSetSpy).not.toHaveBeenCalled()
      expect(sessionGetSpy).not.toHaveBeenCalled()

      expect(window.localStorage.getItem('access_token')).toBeNull()
      expect(window.localStorage.getItem('user')).toBeNull()
      expect(window.localStorage.getItem('session')).toBeNull()
      expect(window.sessionStorage.getItem('access_token')).toBeNull()
      expect(window.sessionStorage.getItem('user')).toBeNull()
      expect(window.sessionStorage.length).toBe(0)
    })
  })

  describe('5. Règle décisionnelle DP-02 : Aucun écran d’audit au MVP', () => {
    it("ne comporte aucun lien, bouton ou navigation vers un journal d'audit", () => {
      render(
        <MemoryRouter>
          <AuthenticatedLayout>
            <div>Zone centrale</div>
          </AuthenticatedLayout>
        </MemoryRouter>,
      )

      expect(screen.queryByText(/audit/i)).not.toBeInTheDocument()
      expect(screen.queryByRole('link', { name: /audit/i })).not.toBeInTheDocument()
    })
  })

  describe('6. Accessibilité et navigation au clavier (NFR-ACC-01, NFR-ACC-03)', () => {
    it("le bouton de déconnexion est accessible au clavier et possède l'anneau de focus cyan", async () => {
      const user = userEvent.setup()

      render(
        <MemoryRouter>
          <TopBar />
        </MemoryRouter>,
      )

      const logoutBtn = screen.getByRole('button', { name: 'Se déconnecter' })
      expect(logoutBtn.className).toContain('focus:ring-cyan')

      await user.tab()
      expect(logoutBtn).toHaveFocus()
    })
  })
})
