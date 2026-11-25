import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from './mocks/server'
import { resetMockCases } from './mocks/handlers'
import { CasesPage } from '../pages/CasesPage'
import { setAccessToken, clearAccessToken } from '../api/auth-memory'
import { INCIDENT_TYPE_POLICY, INCIDENT_TYPE_OPTIONS } from '../api/cases-types'

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

function renderCasesPage(initialRoute = '/cases') {
  const queryClient = createTestQueryClient()
  return {
    queryClient,
    ...render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[initialRoute]}>
          <Routes>
            <Route path="/cases" element={<CasesPage />} />
            <Route
              path="/cases/:caseId"
              element={
                <div data-testid="case-detail-mock">
                  <h1>Détail du dossier</h1>
                </div>
              }
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  }
}

describe('Story F1.7 : Création d un nouveau dossier d investigation en modale (E2, openapi.json)', () => {
  beforeEach(() => {
    clearAccessToken()
    setAccessToken('mock-access-token-bearer-15min')
    window.localStorage.clear()
    window.sessionStorage.clear()
    resetMockCases()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    cleanup()
    clearAccessToken()
    resetMockCases()
    vi.restoreAllMocks()
  })

  describe('1. Ouverture, initialisation et accessibilité de la modale', () => {
    it('affiche le bouton « Nouveau dossier » sur la vue /cases', async () => {
      renderCasesPage()

      await waitFor(() => {
        expect(screen.getByTestId('create-case-button')).toBeInTheDocument()
      })

      const createButton = screen.getByTestId('create-case-button')
      expect(createButton).toHaveTextContent('Nouveau dossier')
    })

    it('ouvre la modale au clic avec focus sur le titre et date courante pré-remplie', async () => {
      const user = userEvent.setup({ delay: null })
      renderCasesPage()

      await waitFor(() => {
        expect(screen.getByTestId('create-case-button')).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('create-case-button'))

      expect(screen.getByTestId('create-case-modal')).toBeInTheDocument()
      expect(screen.getByRole('dialog')).toBeInTheDocument()
      expect(screen.getByTestId('create-case-modal-title')).toHaveTextContent(
        "Nouveau dossier d'investigation",
      )

      // Champs textuels initialement vides
      const titleInput = screen.getByLabelText(/Titre du dossier/i)
      expect(titleInput).toHaveValue('')

      const affectedInput = screen.getByLabelText(/Systèmes concernés/i)
      expect(affectedInput).toHaveValue('')

      const descInput = screen.getByLabelText(/Description factuelle/i)
      expect(descInput).toHaveValue('')

      // Date de l'incident pré-remplie par défaut
      const dateInput = screen.getByLabelText(/Date de l'incident/i) as HTMLInputElement
      expect(dateInput.value).not.toBe('')

      // Focus automatique sur le champ titre
      await waitFor(() => {
        expect(document.activeElement).toBe(titleInput)
      })
    })

    it('ferme la modale au clic sur le bouton Annuler ou la croix de fermeture', async () => {
      const user = userEvent.setup({ delay: null })
      renderCasesPage()

      await waitFor(() => {
        expect(screen.getByTestId('create-case-button')).toBeInTheDocument()
      })

      // Ouverture
      await user.click(screen.getByTestId('create-case-button'))
      expect(screen.getByTestId('create-case-modal')).toBeInTheDocument()

      // Fermeture via le bouton Annuler
      const cancelButton = screen.getByTestId('create-case-cancel-button')
      await user.click(cancelButton)

      await waitFor(() => {
        expect(screen.queryByTestId('create-case-modal')).not.toBeInTheDocument()
      })

      // Réouverture puis fermeture via la croix
      await user.click(screen.getByTestId('create-case-button'))
      expect(screen.getByTestId('create-case-modal')).toBeInTheDocument()

      const closeButton = screen.getByTestId('create-case-close-button')
      await user.click(closeButton)

      await waitFor(() => {
        expect(screen.queryByTestId('create-case-modal')).not.toBeInTheDocument()
      })
    })
  })

  describe('2. Validation des champs avant envoi (Zod, en français)', () => {
    it('affiche les erreurs de validation obligatoires sans émettre de requête réseau si les champs sont vides', async () => {
      const postSpy = vi.fn()
      server.use(
        http.post('*/api/v1/cases', async () => {
          postSpy()
          return HttpResponse.json({}, { status: 201 })
        }),
      )

      const user = userEvent.setup({ delay: null })
      renderCasesPage()

      await waitFor(() => {
        expect(screen.getByTestId('create-case-button')).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('create-case-button'))

      // Effacer la date pré-remplie pour tester l'absence de date
      const dateInput = screen.getByLabelText(/Date de l'incident/i)
      await user.clear(dateInput)

      // Clic sur Créer le dossier sans saisir les champs obligatoires
      const submitButton = screen.getByTestId('create-case-submit-button')
      await user.click(submitButton)

      // Messages d'erreur en français
      await waitFor(() => {
        expect(screen.getByTestId('create-case-title-error')).toHaveTextContent(
          'Le titre du dossier est obligatoire.',
        )
      })

      expect(screen.getByTestId('create-case-affected-systems-error')).toHaveTextContent(
        'Les systèmes concernés sont obligatoires.',
      )
      expect(screen.getByTestId('create-case-description-error')).toHaveTextContent(
        'La description est obligatoire.',
      )

      // Aucune requête réseau émise
      expect(postSpy).not.toHaveBeenCalled()

      // Modale maintenue ouverte
      expect(screen.getByTestId('create-case-modal')).toBeInTheDocument()
    })
  })

  describe('3. Succès nominal de création, rafraîchissement et retour page 1', () => {
    it('crée le dossier avec succès, ferme la modale, réinitialise la page à 1 et affiche la notification', async () => {
      const user = userEvent.setup({ delay: null })
      renderCasesPage()

      await waitFor(() => {
        expect(screen.getByTestId('case-row-case-001')).toBeInTheDocument()
      })

      // Naviguer d'abord à la page 2 pour vérifier le retour à la page 1
      const nextButton = screen.getByRole('button', { name: 'Page suivante' })
      await user.click(nextButton)

      await waitFor(() => {
        expect(screen.getByTestId('pagination-page-indicator')).toHaveTextContent('Page 2')
      })

      // Ouvrir la modale
      await user.click(screen.getByTestId('create-case-button'))
      expect(screen.getByTestId('create-case-modal')).toBeInTheDocument()

      // Remplir les champs du formulaire
      const titleInput = screen.getByLabelText(/Titre du dossier/i)
      await user.type(titleInput, 'Nouvelle Intrusion APT découverte')

      const affectedInput = screen.getByLabelText(/Systèmes concernés/i)
      await user.type(affectedInput, 'Serveurs DMZ et Contrôleurs de domaine')

      const descInput = screen.getByLabelText(/Description factuelle/i)
      await user.type(
        descInput,
        'Mouvements latéraux identifiés sur le segment DMZ avec exploitation de vulnérabilité.',
      )

      // Soumission du formulaire
      const submitButton = screen.getByTestId('create-case-submit-button')
      await user.click(submitButton)

      // Vérification 1 : La modale se ferme
      await waitFor(() => {
        expect(screen.queryByTestId('create-case-modal')).not.toBeInTheDocument()
      })

      // Vérification 2 : Notification de confirmation affichée
      expect(screen.getByTestId('cases-success-notification')).toBeInTheDocument()
      expect(screen.getByTestId('cases-success-notification')).toHaveTextContent(
        "Dossier d'investigation créé avec succès.",
      )

      // Vérification 3 : Retour à la page 1 de la pagination
      expect(screen.getByTestId('pagination-page-indicator')).toHaveTextContent('Page 1')

      // Vérification 4 : Le nouveau dossier est présent dans la liste
      await waitFor(() => {
        expect(screen.getByText('Nouvelle Intrusion APT découverte')).toBeInTheDocument()
      })
    })
  })

  describe('4. Échec de validation serveur 400 avec erreurs sur les champs', () => {
    it('affiche les erreurs renvoyées par l API sous les champs et conserve les saisies dans la modale ouverte', async () => {
      server.use(
        http.post('*/api/v1/cases', () => {
          return HttpResponse.json(
            {
              detail: 'Données de dossier invalides.',
              errors: {
                title: 'Ce titre de dossier est déjà utilisé dans votre organisation.',
              },
            },
            { status: 400 },
          )
        }),
      )

      const user = userEvent.setup({ delay: null })
      renderCasesPage()

      await waitFor(() => {
        expect(screen.getByTestId('create-case-button')).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('create-case-button'))

      // Saisie des données
      const titleInput = screen.getByLabelText(/Titre du dossier/i)
      await user.type(titleInput, 'Titre Existant Doublon')

      const affectedInput = screen.getByLabelText(/Systèmes concernés/i)
      await user.type(affectedInput, 'Serveur AD Principal')

      const descInput = screen.getByLabelText(/Description factuelle/i)
      await user.type(descInput, 'Description détaillée conservée sans perte.')

      await user.click(screen.getByTestId('create-case-submit-button'))

      // La modale doit rester ouverte
      expect(screen.getByTestId('create-case-modal')).toBeInTheDocument()

      // Erreur affichée sous le champ titre
      await waitFor(() => {
        expect(screen.getByTestId('create-case-title-error')).toHaveTextContent(
          'Ce titre de dossier est déjà utilisé dans votre organisation.',
        )
      })

      // Règle NFR-ERR-02 : Les textes saisis restent rigoureusement conservés
      expect(titleInput).toHaveValue('Titre Existant Doublon')
      expect(affectedInput).toHaveValue('Serveur AD Principal')
      expect(descInput).toHaveValue('Description détaillée conservée sans perte.')
    })
  })

  describe('5. Erreur réseau ou HTTP 5xx avec bouton Réessayer et conservation de saisie', () => {
    it('affiche le message d échec 500, propose le bouton Réessayer et permet la relance sans perte de saisie', async () => {
      let failCount = 1
      server.use(
        http.post('*/api/v1/cases', () => {
          if (failCount > 0) {
            failCount--
            return HttpResponse.json(
              { detail: 'Erreur interne du serveur lors de la création du dossier.' },
              { status: 500 },
            )
          }
          return HttpResponse.json(
            {
              id: 'case-recovered-500',
              organization_id: 'org-001',
              title: 'Dossier créé après réessai 500',
              description: 'Données conservées intactes.',
              status: 'open',
              created_by: 'analyste@iryx.local',
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
              evidence_count: 0,
            },
            { status: 201 },
          )
        }),
      )

      const user = userEvent.setup({ delay: null })
      renderCasesPage()

      await waitFor(() => {
        expect(screen.getByTestId('create-case-button')).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('create-case-button'))

      const titleInput = screen.getByLabelText(/Titre du dossier/i)
      await user.type(titleInput, 'Dossier créé après réessai 500')

      const affectedInput = screen.getByLabelText(/Systèmes concernés/i)
      await user.type(affectedInput, 'Serveurs de bases de données')

      const descInput = screen.getByLabelText(/Description factuelle/i)
      await user.type(descInput, 'Données conservées intactes.')

      // Première tentative
      await user.click(screen.getByTestId('create-case-submit-button'))

      // Échec 500 : Bannière affichée, modale reste ouverte
      await waitFor(() => {
        expect(screen.getByTestId('create-case-server-error')).toBeInTheDocument()
      })
      expect(screen.getByTestId('create-case-server-error')).toHaveTextContent(
        'Erreur interne du serveur lors de la création du dossier.',
      )

      // Bouton « Réessayer » présent
      const retryButton = screen.getByTestId('create-case-retry-button')
      expect(retryButton).toBeInTheDocument()
      expect(retryButton).toHaveTextContent('Réessayer')

      // Saisies conservées (NFR-ERR-02)
      expect(titleInput).toHaveValue('Dossier créé après réessai 500')
      expect(affectedInput).toHaveValue('Serveurs de bases de données')
      expect(descInput).toHaveValue('Données conservées intactes.')

      // Clic sur Réessayer
      await user.click(retryButton)

      // Succès post-réessai : modale fermée et notification affichée
      await waitFor(() => {
        expect(screen.queryByTestId('create-case-modal')).not.toBeInTheDocument()
      })
      expect(screen.getByTestId('cases-success-notification')).toBeInTheDocument()
    })

    it('gère une erreur réseau avec message clair, bouton Réessayer et conservation des données', async () => {
      let isNetworkDown = true
      server.use(
        http.post('*/api/v1/cases', () => {
          if (isNetworkDown) {
            return HttpResponse.error()
          }
          return HttpResponse.json(
            {
              id: 'case-recovered-network',
              organization_id: 'org-001',
              title: 'Dossier créé après rétablissement réseau',
              description: 'Données conservées.',
              status: 'open',
              created_by: 'analyste@iryx.local',
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
              evidence_count: 0,
            },
            { status: 201 },
          )
        }),
      )

      const user = userEvent.setup({ delay: null })
      renderCasesPage()

      await waitFor(() => {
        expect(screen.getByTestId('create-case-button')).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('create-case-button'))

      const titleInput = screen.getByLabelText(/Titre du dossier/i)
      await user.type(titleInput, 'Dossier créé après rétablissement réseau')

      const affectedInput = screen.getByLabelText(/Systèmes concernés/i)
      await user.type(affectedInput, 'Routeurs VPN')

      const descInput = screen.getByLabelText(/Description factuelle/i)
      await user.type(descInput, 'Données conservées.')

      await user.click(screen.getByTestId('create-case-submit-button'))

      // Échec réseau : affichage de l'erreur avec bouton Réessayer
      await waitFor(() => {
        expect(screen.getByTestId('create-case-server-error')).toBeInTheDocument()
      })
      expect(screen.getByTestId('create-case-retry-button')).toBeInTheDocument()

      // Saisie conservée
      expect(titleInput).toHaveValue('Dossier créé après rétablissement réseau')

      // Rétablissement du réseau et réessai
      isNetworkDown = false
      await user.click(screen.getByTestId('create-case-retry-button'))

      await waitFor(() => {
        expect(screen.queryByTestId('create-case-modal')).not.toBeInTheDocument()
      })
      expect(screen.getByTestId('cases-success-notification')).toBeInTheDocument()
    })
  })

  describe('6. Accès refusé HTTP 403', () => {
    it('affiche la notification d interdiction sans fermer la modale et conserve les saisies', async () => {
      server.use(
        http.post('*/api/v1/cases', () => {
          return HttpResponse.json(
            {
              detail:
                "Vous n'avez pas les autorisations nécessaires pour créer un dossier dans cette organisation.",
            },
            { status: 403 },
          )
        }),
      )

      const user = userEvent.setup({ delay: null })
      renderCasesPage()

      await waitFor(() => {
        expect(screen.getByTestId('create-case-button')).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('create-case-button'))

      const titleInput = screen.getByLabelText(/Titre du dossier/i)
      await user.type(titleInput, 'Tentative non autorisée')

      const affectedInput = screen.getByLabelText(/Systèmes concernés/i)
      await user.type(affectedInput, 'Cluster Kubernetes')

      const descInput = screen.getByLabelText(/Description factuelle/i)
      await user.type(descInput, 'Détails saisis conservés.')

      await user.click(screen.getByTestId('create-case-submit-button'))

      await waitFor(() => {
        expect(screen.getByTestId('create-case-server-error')).toBeInTheDocument()
      })
      expect(screen.getByTestId('create-case-server-error')).toHaveTextContent(
        "Vous n'avez pas les autorisations nécessaires pour créer un dossier dans cette organisation.",
      )

      // La modale reste ouverte et les saisies sont conservées
      expect(screen.getByTestId('create-case-modal')).toBeInTheDocument()
      expect(titleInput).toHaveValue('Tentative non autorisée')
      expect(affectedInput).toHaveValue('Cluster Kubernetes')
      expect(descInput).toHaveValue('Détails saisis conservés.')
    })
  })

  describe('7. Règles d architecture, non-invention et absence de stockage', () => {
    it('marque explicitement la politique de typologie d incident comme « à décider »', () => {
      expect(INCIDENT_TYPE_POLICY).toBe('à décider')
      expect(INCIDENT_TYPE_OPTIONS.length).toBeGreaterThan(0)
      expect(INCIDENT_TYPE_OPTIONS[0]?.label.toLowerCase()).toContain('à décider')
    })

    it('n effectue aucune écriture dans localStorage ni sessionStorage', async () => {
      const setLocalStorageSpy = vi.spyOn(Storage.prototype, 'setItem')
      const user = userEvent.setup({ delay: null })
      renderCasesPage()

      await waitFor(() => {
        expect(screen.getByTestId('create-case-button')).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('create-case-button'))

      const titleInput = screen.getByLabelText(/Titre du dossier/i)
      await user.type(titleInput, 'Contrôle absence stockage')

      const affectedInput = screen.getByLabelText(/Systèmes concernés/i)
      await user.type(affectedInput, 'Système vérifié')

      const descInput = screen.getByLabelText(/Description factuelle/i)
      await user.type(descInput, 'Vérification absence totale d appel à localStorage.')

      await user.click(screen.getByTestId('create-case-submit-button'))

      await waitFor(() => {
        expect(screen.queryByTestId('create-case-modal')).not.toBeInTheDocument()
      })

      const appStorageCalls = setLocalStorageSpy.mock.calls.filter(
        ([key]) => key !== '__msw-cookie-store__',
      )
      expect(appStorageCalls.length).toBe(0)
    })
  })
})
