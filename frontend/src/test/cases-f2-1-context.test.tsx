import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from './mocks/server'
import { CaseContextPage } from '../pages/CaseContextPage'
import { setAccessToken, clearAccessToken } from '../api/auth-memory'
import { CONTRACT_ALIGNMENT_REQUIRED_LABEL } from '../api/cases-types'

// `delay: null` supprime le délai artificiel entre deux frappes userEvent.
// Sous la charge parallèle de la suite, le délai par défaut faisait dépasser
// le testTimeout de 5 s et laissait des frappes en attente qui corrompaient le test suivant.
// Tous les événements utilisateur et toutes les assertions sont conservés.

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 0,
        gcTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
  })
}

function renderCaseContextPage(initialCaseId = 'case-001') {
  const queryClient = createTestQueryClient()
  return {
    queryClient,
    ...render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/cases/${initialCaseId}`]}>
          <Routes>
            <Route
              path="/cases"
              element={<div data-testid="cases-list-page">Liste des dossiers</div>}
            />
            <Route path="/cases/:caseId" element={<CaseContextPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  }
}

describe('Story F2.1 : Consultation et édition du contexte du dossier (E2, openapi.json)', () => {
  beforeEach(() => {
    clearAccessToken()
    setAccessToken('mock-access-token-bearer-15min')
    window.localStorage.clear()
    window.sessionStorage.clear()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    clearAccessToken()
    window.localStorage.clear()
    window.sessionStorage.clear()
  })

  describe('1. État nominal et consultation des informations du dossier', () => {
    it('affiche le titre, la description, le statut, les dates UTC et la liste des membres', async () => {
      renderCaseContextPage('case-001')

      // Attente du chargement
      await waitFor(() => {
        expect(screen.getByTestId('case-view-title')).toBeInTheDocument()
      })

      // Titre et description
      expect(screen.getByTestId('case-view-title')).toHaveTextContent(
        'Incident Ransomware LockBit v3',
      )
      expect(screen.getByTestId('case-view-description')).toHaveTextContent(
        'Compromission initiale par pièce jointe malveillante',
      )

      // Statut du dossier en lecture seule
      expect(screen.getByTestId('case-view-status')).toBeInTheDocument()
      expect(screen.getByTestId('case-view-status')).toHaveTextContent(/ouvert/i)

      // Temporalité UTC
      expect(screen.getByTestId('case-view-incident-date')).toHaveTextContent(
        '2026-11-20 08:00 UTC',
      )
      expect(screen.getByTestId('case-view-updated-at')).toHaveTextContent('2026-11-20 09:00 UTC')
      expect(screen.getByTestId('case-view-created-at')).toHaveTextContent('2026-11-20 08:15 UTC')

      // Systèmes concernés
      expect(screen.getByTestId('case-view-affected-systems')).toHaveTextContent(
        'Contrôleur de domaine AD, Serveur Exchange, Postes analystes',
      )

      // Liste des membres autorisés en lecture seule
      expect(screen.getByTestId('case-members-section')).toBeInTheDocument()
      expect(screen.getByText('Analyste Forensique')).toBeInTheDocument()
      expect(screen.getByText('analyste@iryx.local')).toBeInTheDocument()
      expect(screen.getByText('Administrateur Sécurité')).toBeInTheDocument()

      // Bouton Modifier présent
      expect(screen.getByTestId('edit-case-btn')).toBeInTheDocument()
    })

    it('affiche les mentions « à réaligner » pour les champs absents du contrat OpenAPI cible', async () => {
      renderCaseContextPage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('case-view-title')).toBeInTheDocument()
      })

      // Mentions « à réaligner »
      const tags = screen.getAllByText(CONTRACT_ALIGNMENT_REQUIRED_LABEL)
      expect(tags.length).toBeGreaterThanOrEqual(3)

      expect(screen.getByTestId('incident-date-alignment-tag')).toHaveTextContent(
        CONTRACT_ALIGNMENT_REQUIRED_LABEL,
      )
      expect(screen.getByTestId('affected-systems-alignment-tag')).toHaveTextContent(
        CONTRACT_ALIGNMENT_REQUIRED_LABEL,
      )
      expect(screen.getByTestId('case-members-alignment-tag')).toHaveTextContent(
        CONTRACT_ALIGNMENT_REQUIRED_LABEL,
      )
    })

    it('affiche la barre latérale du dossier avec les 5 étapes et l identifiant copiable', async () => {
      renderCaseContextPage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('case-sidebar')).toBeInTheDocument()
      })

      // Titre du dossier dans la barre latérale
      expect(screen.getByTestId('sidebar-case-title')).toHaveTextContent(
        'Incident Ransomware LockBit v3',
      )
      expect(screen.getByTestId('sidebar-case-id')).toHaveTextContent('case-001')

      // Les 5 étapes numérotées du canevas
      expect(screen.getByTestId('sidebar-step-1')).toHaveTextContent(/1.*Contexte/i)
      expect(screen.getByTestId('sidebar-step-2')).toHaveTextContent(/2.*Preuves/i)
      expect(screen.getByTestId('sidebar-step-3')).toHaveTextContent(/3.*Plan et agents/i)
      expect(screen.getByTestId('sidebar-step-4')).toHaveTextContent(/4.*Résultats/i)
      expect(screen.getByTestId('sidebar-step-5')).toHaveTextContent(/5.*Revue et rapport/i)

      // Étape 1 active
      expect(screen.getByTestId('sidebar-step-1')).toHaveAttribute('aria-current', 'page')

      // Encart institutionnel de confidentialité
      expect(screen.getByText(/Sécurité locale/i)).toBeInTheDocument()
      expect(
        screen.getByText(/Traitement sécurisé et préservation des preuves/i),
      ).toBeInTheDocument()

      // Bouton de copie d identifiant
      const copyBtn = screen.getByTestId('copy-case-id-btn')
      expect(copyBtn).toBeInTheDocument()
    })
  })

  describe('2. État vide', () => {
    it('affiche la mention par défaut « Aucune description fournie » en couleur teal si la description est vide', async () => {
      renderCaseContextPage('case-empty')

      await waitFor(() => {
        expect(screen.getByTestId('case-view-title')).toBeInTheDocument()
      })

      const descElement = screen.getByTestId('case-view-description')
      expect(descElement).toHaveTextContent('Aucune description fournie')
      expect(descElement.className).toContain('text-teal')

      const systemsElement = screen.getByTestId('case-view-affected-systems')
      expect(systemsElement).toHaveTextContent('Aucun système spécifié')
      expect(systemsElement.className).toContain('text-teal')

      const emptyMembers = screen.getByTestId('empty-members-msg')
      expect(emptyMembers).toHaveTextContent('Aucun membre rattaché à ce dossier.')
      expect(emptyMembers.className).toContain('text-teal')
    })
  })

  describe('3. Mode d édition en ligne et validation Zod', () => {
    it('permet de basculer en mode édition, de modifier le titre et la description et d enregistrer avec succès', async () => {
      const user = userEvent.setup({ delay: null })
      renderCaseContextPage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('edit-case-btn')).toBeInTheDocument()
      })

      // Bascule en édition
      await user.click(screen.getByTestId('edit-case-btn'))

      expect(screen.getByTestId('case-context-edit-form')).toBeInTheDocument()
      const titleInput = screen.getByTestId('edit-title-input')
      const descInput = screen.getByTestId('edit-description-input')

      expect(titleInput).toHaveValue('Incident Ransomware LockBit v3')

      // Les champs non prévus au contrat sont non éditables (disabled)
      expect(screen.getByTestId('edit-incident-date-disabled')).toBeDisabled()
      expect(screen.getByTestId('edit-affected-systems-disabled')).toBeDisabled()

      // Modification des valeurs
      await user.clear(titleInput)
      await user.type(titleInput, 'Incident Ransomware LockBit v3.1 - Qualification révisée')

      await user.clear(descInput)
      await user.type(descInput, 'Compromission confirmée avec propagation latérale contenue.')

      // Enregistrement
      await user.click(screen.getByTestId('save-case-btn'))

      // Retour en vue nominale avec données actualisées immédiatement
      await waitFor(() => {
        expect(screen.queryByTestId('case-context-edit-form')).not.toBeInTheDocument()
      })

      expect(screen.getByTestId('case-view-title')).toHaveTextContent(
        'Incident Ransomware LockBit v3.1 - Qualification révisée',
      )
      expect(screen.getByTestId('case-view-description')).toHaveTextContent(
        'Compromission confirmée avec propagation latérale contenue.',
      )
      expect(screen.getByTestId('case-update-success-notification')).toBeInTheDocument()
    })

    it('applique la validation Zod : refuse la soumission si le titre est vide et affiche une erreur en français', async () => {
      const user = userEvent.setup({ delay: null })
      renderCaseContextPage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('edit-case-btn')).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('edit-case-btn'))

      const titleInput = screen.getByTestId('edit-title-input')
      await user.clear(titleInput)

      await user.click(screen.getByTestId('save-case-btn'))

      // Message d'erreur sous le champ
      expect(screen.getByTestId('edit-title-error')).toHaveTextContent(
        'Le titre du dossier est obligatoire.',
      )
      // Le formulaire reste ouvert
      expect(screen.getByTestId('case-context-edit-form')).toBeInTheDocument()
    })

    it('le bouton « Annuler » annule les saisies en cours et rétablit la vue nominale', async () => {
      const user = userEvent.setup({ delay: null })
      renderCaseContextPage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('edit-case-btn')).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('edit-case-btn'))

      const titleInput = screen.getByTestId('edit-title-input')
      await user.clear(titleInput)
      await user.type(titleInput, 'Modification temporaire non sauvegardée')

      await user.click(screen.getByTestId('cancel-edit-btn'))

      // Retour en vue consultation avec valeur originale
      expect(screen.queryByTestId('case-context-edit-form')).not.toBeInTheDocument()
      expect(screen.getByTestId('case-view-title')).toHaveTextContent(
        'Incident Ransomware LockBit v3',
      )
    })
  })

  describe('4. État d erreur technique et conservation des saisies (NFR-ERR-02)', () => {
    it('affiche un bandeau d échec avec bouton Réessayer en cas d erreur serveur 500 au chargement', async () => {
      renderCaseContextPage('case-500')

      await waitFor(() => {
        expect(screen.getByTestId('case-load-error-banner')).toBeInTheDocument()
      })

      expect(screen.getByTestId('retry-load-btn')).toBeInTheDocument()
      expect(
        screen.getByText(/Erreur interne du serveur lors de la récupération du dossier/i),
      ).toBeInTheDocument()
    })

    it('en cas d erreur 500 lors de la sauvegarde, affiche la notification d échec, le bouton Réessayer et conserve les saisies (NFR-ERR-02)', async () => {
      const user = userEvent.setup({ delay: null })

      server.use(
        http.patch('*/api/v1/cases/:caseId', () => {
          return HttpResponse.json(
            { detail: 'Erreur serveur interne lors de la mise à jour.' },
            { status: 500 },
          )
        }),
      )

      renderCaseContextPage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('edit-case-btn')).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('edit-case-btn'))

      const titleInput = screen.getByTestId('edit-title-input')
      await user.clear(titleInput)
      await user.type(titleInput, 'Nouveau titre conservé malgré erreur')

      const descInput = screen.getByTestId('edit-description-input')
      await user.clear(descInput)
      await user.type(descInput, 'Description conservée intacte après 500')

      await user.click(screen.getByTestId('save-case-btn'))

      // Notification d'erreur de mise à jour avec bouton Réessayer
      await waitFor(() => {
        expect(screen.getByTestId('case-update-error-banner')).toBeInTheDocument()
      })

      expect(screen.getByTestId('retry-update-btn')).toBeInTheDocument()

      // Vérification essentielle NFR-ERR-02 : les saisies restent strictement conservées
      expect(screen.getByTestId('edit-title-input')).toHaveValue(
        'Nouveau titre conservé malgré erreur',
      )
      expect(screen.getByTestId('edit-description-input')).toHaveValue(
        'Description conservée intacte après 500',
      )
    })
  })

  describe('5. État d accès refusé (HTTP 403 Forbidden)', () => {
    it('bloque l affichage des informations sensibles, affiche la notification et redirige vers /cases', async () => {
      renderCaseContextPage('case-forbidden')

      await waitFor(() => {
        expect(screen.getByTestId('forbidden-notification')).toBeInTheDocument()
      })

      expect(screen.getByText("Vous n'avez pas accès à ce dossier")).toBeInTheDocument()

      // Aucune information sensible n'est visible
      expect(screen.queryByTestId('case-context-view')).not.toBeInTheDocument()
      expect(screen.queryByTestId('case-view-title')).not.toBeInTheDocument()

      // Redirection automatique vérifiée après temporisation
      await waitFor(
        () => {
          expect(screen.getByTestId('cases-list-page')).toBeInTheDocument()
        },
        { timeout: 3000 },
      )
    })
  })

  describe('6. État dossier introuvable (HTTP 404 Not Found)', () => {
    it('affiche un message neutre « Dossier introuvable » et un lien de retour sans fuite de données', async () => {
      renderCaseContextPage('case-not-found')

      await waitFor(() => {
        expect(screen.getByTestId('case-not-found-state')).toBeInTheDocument()
      })

      expect(screen.getByText('Dossier introuvable')).toBeInTheDocument()
      expect(
        screen.getByText(/Le dossier demandé n'existe pas ou a été archivé/i),
      ).toBeInTheDocument()
      expect(screen.getByTestId('not-found-back-link')).toBeInTheDocument()
    })
  })

  describe('7. Absence de persistance dans le stockage navigateur', () => {
    it('ne réalise aucune écriture dans localStorage ni sessionStorage', async () => {
      const setLocalSpy = vi.spyOn(Storage.prototype, 'setItem')
      renderCaseContextPage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('case-view-title')).toBeInTheDocument()
      })

      expect(setLocalSpy).not.toHaveBeenCalled()
      expect(window.localStorage.length).toBe(0)
      expect(window.sessionStorage.length).toBe(0)
    })
  })
})
