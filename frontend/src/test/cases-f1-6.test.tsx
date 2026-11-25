import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, act, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from './mocks/server'
import { CasesPage } from '../pages/CasesPage'
import { setAccessToken, clearAccessToken } from '../api/auth-memory'
import {
  SEARCH_DEBOUNCE_DELAY_MS,
  SEARCH_DEBOUNCE_POLICY,
  DEFAULT_PAGE_SIZE,
  PAGE_SIZE_POLICY,
} from '../api/cases-types'
import { formatUtcDateTime } from '../lib/date'

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 0,
        gcTime: 0,
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

describe('Story F1.6 : Consultation paginée et recherche des dossiers (E2, openapi.json)', () => {
  beforeEach(() => {
    clearAccessToken()
    setAccessToken('mock-access-token-bearer-15min')
    window.localStorage.clear()
    window.sessionStorage.clear()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    cleanup()
    clearAccessToken()
    vi.restoreAllMocks()
  })

  describe('1. État nominal et tableau récapitulatif paginé', () => {
    it('affiche le titre de la section, la barre de recherche et le tableau avec les colonnes requises', async () => {
      renderCasesPage()

      expect(screen.getByRole('heading', { name: "Dossiers d'investigation" })).toBeInTheDocument()
      expect(screen.getByPlaceholderText('Rechercher par titre...')).toBeInTheDocument()

      await waitFor(() => {
        expect(screen.getByRole('table')).toBeInTheDocument()
      })

      // Vérification des 4 colonnes requises
      expect(screen.getByText('Titre du dossier')).toBeInTheDocument()
      expect(screen.getByText('Statut')).toBeInTheDocument()
      expect(screen.getByText('Date de détection UTC')).toBeInTheDocument()
      expect(screen.getByText('Preuves scellées')).toBeInTheDocument()
    })

    it('affiche exclusivement les dossiers de la page courante (10 dossiers par défaut sur 25) sans charger la liste complète', async () => {
      renderCasesPage()

      await waitFor(() => {
        expect(screen.getByTestId('case-row-case-001')).toBeInTheDocument()
      })

      const rows = screen.getAllByRole('row')
      // 1 ligne thead + 10 lignes tbody = 11 rows
      expect(rows.length).toBe(11)

      // Le premier dossier de la page 1 est présent
      expect(screen.getByText('Incident Ransomware LockBit v3')).toBeInTheDocument()
      // Le 10e dossier de la page 1 est présent
      expect(screen.getByText('Détection malware Cobalt Strike balise')).toBeInTheDocument()
      // Le 11e dossier (page 2) ne doit PAS être affiché sur la page 1
      expect(screen.queryByText('Élévation de privilèges CVE-2026-1337')).not.toBeInTheDocument()
    })

    it('affiche les métadonnées obligatoires : statut en français non chromatique, date UTC et nombre de preuves', async () => {
      renderCasesPage()

      await waitFor(() => {
        expect(screen.getByTestId('case-row-case-001')).toBeInTheDocument()
      })

      // Statut non-chromatique avec libellé en français (NFR-ACC-02)
      const openBadges = screen.getAllByTestId('case-status-open')
      expect(openBadges.length).toBeGreaterThan(0)
      expect(openBadges[0]).toHaveTextContent('Ouvert')

      // Date de création en UTC
      expect(screen.getByText(formatUtcDateTime('2026-11-20T08:15:00Z'))).toBeInTheDocument()

      // Nombre de preuves scellées
      const evidenceCount = screen.getByTestId('case-evidence-count-case-001')
      expect(evidenceCount).toHaveTextContent('4')
    })

    it('navigue vers /cases/:caseId lors du clic sur une ligne du tableau', async () => {
      const user = userEvent.setup()
      renderCasesPage()

      await waitFor(() => {
        expect(screen.getByTestId('case-row-case-001')).toBeInTheDocument()
      })

      const row = screen.getByTestId('case-row-case-001')
      await user.click(row)

      await waitFor(() => {
        expect(screen.getByTestId('case-detail-mock')).toBeInTheDocument()
      })
    })

    it('permet la navigation au clavier avec la touche Entrée vers /cases/:caseId', async () => {
      renderCasesPage()

      await waitFor(() => {
        expect(screen.getByTestId('case-row-case-001')).toBeInTheDocument()
      })

      const row = screen.getByTestId('case-row-case-001')
      row.focus()
      expect(row).toHaveFocus()

      await act(async () => {
        row.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
      })

      await waitFor(() => {
        expect(screen.getByTestId('case-detail-mock')).toBeInTheDocument()
      })
    })
  })

  describe('2. Pagination côté serveur', () => {
    it('permet de naviguer de page en page avec désactivation des boutons aux limites', async () => {
      const user = userEvent.setup()
      renderCasesPage()

      await waitFor(() => {
        expect(screen.getByTestId('cases-pagination')).toBeInTheDocument()
      })

      // Page 1
      expect(screen.getByTestId('pagination-page-indicator')).toHaveTextContent('Page 1 / 3')
      expect(screen.getByTestId('pagination-summary')).toHaveTextContent(
        'Affichage de 1 à 10 sur 25 dossiers',
      )

      // Sur page 1, Précédent est désactivé
      expect(screen.getByTestId('pagination-prev')).toBeDisabled()
      expect(screen.getByTestId('pagination-next')).toBeEnabled()

      // Passage en page 2
      await user.click(screen.getByTestId('pagination-next'))

      await waitFor(() => {
        expect(screen.getByTestId('pagination-page-indicator')).toHaveTextContent('Page 2 / 3')
        expect(screen.getByText('Élévation de privilèges CVE-2026-1337')).toBeInTheDocument()
        expect(screen.getByTestId('pagination-prev')).toBeEnabled()
        expect(screen.getByTestId('pagination-next')).toBeEnabled()
      })
      expect(screen.getByTestId('pagination-summary')).toHaveTextContent(
        'Affichage de 11 à 20 sur 25 dossiers',
      )

      // Passage en page 3 (dernière page)
      await user.click(screen.getByTestId('pagination-next'))

      await waitFor(() => {
        expect(screen.getByTestId('pagination-page-indicator')).toHaveTextContent('Page 3 / 3')
        expect(screen.getByTestId('pagination-prev')).toBeEnabled()
        expect(screen.getByTestId('pagination-next')).toBeDisabled()
      })
      expect(screen.getByTestId('pagination-summary')).toHaveTextContent(
        'Affichage de 21 à 25 sur 25 dossiers',
      )

      // Retour en page 2
      await user.click(screen.getByTestId('pagination-prev'))

      await waitFor(() => {
        expect(screen.getByTestId('pagination-page-indicator')).toHaveTextContent('Page 2 / 3')
        expect(screen.getByTestId('pagination-prev')).toBeEnabled()
        expect(screen.getByTestId('pagination-next')).toBeEnabled()
      })
    })
  })

  describe('3. Recherche par titre avec saisie différée et réinitialisation de page', () => {
    it('actualise la saisie immédiatement (principe C2) et déclenche la requête filtrée après temporisation', async () => {
      const user = userEvent.setup()
      renderCasesPage()

      await waitFor(() => {
        expect(screen.getByTestId('case-row-case-001')).toBeInTheDocument()
      })

      const searchInput = screen.getByTestId('cases-search-input') as HTMLInputElement

      // Saisie immédiate dans l'input
      await user.type(searchInput, 'LockBit')
      expect(searchInput.value).toBe('LockBit')

      // Après temporisation (debounce), la liste est filtrée
      await waitFor(
        () => {
          expect(screen.getByText('Incident Ransomware LockBit v3')).toBeInTheDocument()
          expect(screen.queryByText('Fuite de données confidentielles RH')).not.toBeInTheDocument()
        },
        { timeout: 2000 },
      )

      expect(screen.getByTestId('pagination-summary')).toHaveTextContent(
        'Affichage de 1 à 1 sur 1 dossier',
      )
    })

    it('revient systématiquement à la page 1 lors d un changement dans la recherche', async () => {
      const user = userEvent.setup()
      renderCasesPage()

      await waitFor(() => {
        expect(screen.getByTestId('pagination-next')).toBeInTheDocument()
      })

      // Naviguer vers la page 2
      await user.click(screen.getByTestId('pagination-next'))
      await waitFor(() => {
        expect(screen.getByTestId('pagination-page-indicator')).toHaveTextContent('Page 2 / 3')
      })

      // Taper une recherche
      const searchInput = screen.getByTestId('cases-search-input')
      await user.type(searchInput, 'Attaque')

      // La pagination est revenue immédiatement à la page 1
      await waitFor(() => {
        expect(screen.getByTestId('pagination-page-indicator')).toHaveTextContent('Page 1 /')
      })
    })
  })

  describe('4. Les cinq états obligatoires', () => {
    it('État de chargement : affiche des lignes de squelettes animées pendant la requête', () => {
      // Configuration d'un délai réseau MSW
      server.use(
        http.get('*/api/v1/cases', async () => {
          await new Promise((res) => setTimeout(res, 300))
          return HttpResponse.json({
            items: [],
            total: 0,
            total_items: 0,
            limit: 10,
            offset: 0,
            has_more: false,
          })
        }),
      )

      renderCasesPage()

      const skeleton = screen.getByTestId('cases-loading-skeleton')
      expect(skeleton).toBeInTheDocument()
      expect(skeleton).toHaveAttribute('role', 'status')
    })

    it('État vide : affiche le message explicite « Aucun dossier. Créez le premier. » sans bouton de création (F1.7)', async () => {
      server.use(
        http.get('*/api/v1/cases', () => {
          return HttpResponse.json({
            items: [],
            total: 0,
            total_items: 0,
            limit: 10,
            offset: 0,
            has_more: false,
          })
        }),
      )

      renderCasesPage()

      await waitFor(() => {
        expect(screen.getByTestId('cases-empty-state')).toBeInTheDocument()
      })

      const emptyMessage = screen.getByTestId('cases-empty-message')
      expect(emptyMessage).toHaveTextContent('Aucun dossier. Créez le premier.')

      // Règle stricte F1.6 : aucun bouton de création affiché pour l'instant
      expect(screen.queryByRole('button', { name: /Nouveau dossier/i })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /Créer un dossier/i })).not.toBeInTheDocument()
    })

    it('État d erreur 5xx : affiche la bannière d alerte avec le bouton « Réessayer » qui relance la requête', async () => {
      let shouldFail = true
      server.use(
        http.get('*/api/v1/cases', () => {
          if (shouldFail) {
            return HttpResponse.json({ detail: 'Erreur interne du serveur.' }, { status: 500 })
          }
          return HttpResponse.json({
            items: [
              {
                id: 'case-recovered',
                organization_id: 'org-001',
                title: 'Dossier récupéré après réessai',
                description: null,
                status: 'open',
                created_by: null,
                created_at: '2026-11-20T08:00:00Z',
                updated_at: '2026-11-20T08:00:00Z',
                evidence_count: 1,
              },
            ],
            total: 1,
            total_items: 1,
            limit: 10,
            offset: 0,
            has_more: false,
          })
        }),
      )

      const user = userEvent.setup()
      renderCasesPage()

      await waitFor(() => {
        expect(screen.getByTestId('cases-error-banner')).toBeInTheDocument()
      })

      expect(screen.getByRole('alert')).toBeInTheDocument()
      expect(screen.getByText('Erreur interne du serveur.')).toBeInTheDocument()

      const retryButton = screen.getByTestId('cases-retry-button')
      expect(retryButton).toBeInTheDocument()
      expect(retryButton).toHaveTextContent('Réessayer')

      // Clic sur Réessayer après rétablissement du service
      shouldFail = false
      await user.click(retryButton)

      await waitFor(() => {
        expect(screen.getByText('Dossier récupéré après réessai')).toBeInTheDocument()
      })
    })

    it('État d accès refusé 403 : affiche le message d interdiction invitant à contacter l administrateur sans exposer de données', async () => {
      server.use(
        http.get('*/api/v1/cases', () => {
          return HttpResponse.json(
            {
              detail:
                "Accès refusé. Vous n'avez pas accès aux dossiers de cette organisation. Veuillez contacter votre administrateur.",
            },
            { status: 403 },
          )
        }),
      )

      renderCasesPage()

      await waitFor(() => {
        expect(screen.getByTestId('cases-forbidden-banner')).toBeInTheDocument()
      })

      expect(screen.getByRole('alert')).toBeInTheDocument()
      expect(screen.getByText('Accès refusé')).toBeInTheDocument()
      expect(
        screen.getByText(
          "Vous n'avez pas accès aux dossiers de cette organisation. Veuillez contacter votre administrateur.",
        ),
      ).toBeInTheDocument()

      // Aucune donnée ni tableau affiché
      expect(screen.queryByRole('table')).not.toBeInTheDocument()
    })
  })

  describe('5. Règle d absence de stockage et points d architecture', () => {
    it('n effectue aucune écriture dans localStorage ni sessionStorage', async () => {
      const setLocalStorageSpy = vi.spyOn(Storage.prototype, 'setItem')
      renderCasesPage()

      await waitFor(() => {
        expect(screen.getByTestId('case-row-case-001')).toBeInTheDocument()
      })

      const appStorageCalls = setLocalStorageSpy.mock.calls.filter(
        ([key]) => key !== '__msw-cookie-store__',
      )
      expect(appStorageCalls.length).toBe(0)
    })

    it('expose les mentions explicites « à décider » pour la pause de frappe et la taille de page', () => {
      expect(SEARCH_DEBOUNCE_POLICY).toBe('à décider')
      expect(SEARCH_DEBOUNCE_DELAY_MS).toBeGreaterThan(0)
      expect(PAGE_SIZE_POLICY).toBe('à décider')
      expect(DEFAULT_PAGE_SIZE).toBeGreaterThan(0)
    })
  })
})
