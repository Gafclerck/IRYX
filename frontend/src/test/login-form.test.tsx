import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { LoginPage } from '../pages/LoginPage'
import { getAccessToken, clearAccessToken } from '../api/auth-memory'

function renderLoginPage(initialRoute = '/login') {
  return render(
    <MemoryRouter initialEntries={[initialRoute]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/cases"
          element={
            <div data-testid="cases-page">
              <h1>Espace dossiers d'investigation</h1>
            </div>
          }
        />
      </Routes>
    </MemoryRouter>,
  )
}

describe('Écran /login et Formulaire de connexion (Story F1.2)', () => {
  beforeEach(() => {
    clearAccessToken()
    vi.restoreAllMocks()
    window.localStorage.clear()
    window.sessionStorage.clear()
  })

  describe('État vide et affichage initial', () => {
    it('affiche le formulaire avec champs vierges, libellés en français et bouton interactif', () => {
      renderLoginPage()

      expect(screen.getByRole('heading', { name: 'Connexion' })).toBeInTheDocument()
      expect(screen.getByLabelText('Adresse électronique')).toBeInTheDocument()
      expect(screen.getByLabelText('Mot de passe')).toBeInTheDocument()

      const emailInput = screen.getByLabelText('Adresse électronique') as HTMLInputElement
      const passwordInput = screen.getByLabelText('Mot de passe') as HTMLInputElement
      const submitButton = screen.getByRole('button', { name: 'Se connecter' })

      expect(emailInput.value).toBe('')
      expect(passwordInput.value).toBe('')
      expect(submitButton).toBeEnabled()
    })

    it('positionne le focus initial sur le champ adresse électronique', () => {
      renderLoginPage()
      const emailInput = screen.getByLabelText('Adresse électronique')
      expect(emailInput).toHaveFocus()
    })
  })

  describe('Validation des champs avant envoi (Zod)', () => {
    it('bloque la soumission et affiche les erreurs requises lorsque les champs sont vides', async () => {
      const user = userEvent.setup()
      renderLoginPage()

      const submitButton = screen.getByRole('button', { name: 'Se connecter' })
      await user.click(submitButton)

      expect(await screen.findByText("L'adresse électronique est requise.")).toBeInTheDocument()
      expect(await screen.findByText('Le mot de passe est requis.')).toBeInTheDocument()
      expect(getAccessToken()).toBeNull()
    })

    it("affiche un message d'erreur si le format de l'adresse électronique est invalide", async () => {
      const user = userEvent.setup()
      renderLoginPage()

      const emailInput = screen.getByLabelText('Adresse électronique')
      const passwordInput = screen.getByLabelText('Mot de passe')
      const submitButton = screen.getByRole('button', { name: 'Se connecter' })

      await user.type(emailInput, 'adresse-invalide')
      await user.type(passwordInput, 'MotDePasse123!')
      await user.click(submitButton)

      expect(await screen.findByText("Format d'adresse électronique invalide.")).toBeInTheDocument()
      expect(getAccessToken()).toBeNull()
    })
  })

  describe("État d'erreur et rejet d'authentification", () => {
    it('affiche "Identifiants incorrects." et conserve l\'identifiant saisi en cas d\'échec 401', async () => {
      const user = userEvent.setup()
      renderLoginPage()

      const emailInput = screen.getByLabelText('Adresse électronique') as HTMLInputElement
      const passwordInput = screen.getByLabelText('Mot de passe') as HTMLInputElement
      const submitButton = screen.getByRole('button', { name: 'Se connecter' })

      await user.type(emailInput, 'analyste@iryx.local')
      await user.type(passwordInput, 'wrong-password')
      await user.click(submitButton)

      expect(await screen.findByRole('alert')).toBeInTheDocument()
      expect(screen.getByText('Identifiants incorrects.')).toBeInTheDocument()

      // L'adresse électronique saisie n'est pas vidée
      expect(emailInput.value).toBe('analyste@iryx.local')
      expect(getAccessToken()).toBeNull()
    })

    it('affiche "Compte inactif ou accès révoqué. Contactez votre administrateur." en cas de statut 403', async () => {
      const user = userEvent.setup()
      renderLoginPage()

      const emailInput = screen.getByLabelText('Adresse électronique')
      const passwordInput = screen.getByLabelText('Mot de passe')
      const submitButton = screen.getByRole('button', { name: 'Se connecter' })

      await user.type(emailInput, 'bloque@iryx.local')
      await user.type(passwordInput, 'SecretPassword123!')
      await user.click(submitButton)

      expect(await screen.findByRole('alert')).toBeInTheDocument()
      expect(
        screen.getByText('Compte inactif ou accès révoqué. Contactez votre administrateur.'),
      ).toBeInTheDocument()
      expect(getAccessToken()).toBeNull()
    })
  })

  describe('État nominal et redirection /cases', () => {
    it('enregistre le jeton en mémoire vive uniquement et redirige vers /cases après succès', async () => {
      const user = userEvent.setup()
      const localStorageSpy = vi.spyOn(window.localStorage, 'setItem')
      const sessionStorageSpy = vi.spyOn(window.sessionStorage, 'setItem')

      renderLoginPage()

      const emailInput = screen.getByLabelText('Adresse électronique')
      const passwordInput = screen.getByLabelText('Mot de passe')
      const submitButton = screen.getByRole('button', { name: 'Se connecter' })

      await user.type(emailInput, 'analyste@iryx.local')
      await user.type(passwordInput, 'SecretPassword123!')
      await user.click(submitButton)

      // Redirection automatique vers /cases
      await waitFor(() => {
        expect(screen.getByTestId('cases-page')).toBeInTheDocument()
      })

      // Jeton d'accès détenu exclusivement en mémoire vive
      expect(getAccessToken()).toBe('mock-access-token-bearer-15min')

      // Aucune écriture du jeton dans localStorage ni sessionStorage par l'application
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
})
