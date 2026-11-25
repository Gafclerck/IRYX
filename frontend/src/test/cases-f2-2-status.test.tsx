import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from './mocks/server'
import { MOCK_CASES } from './mocks/handlers'
import { CaseContextPage } from '../pages/CaseContextPage'
import { CaseStatusSelector } from '../features/cases/components/CaseStatusSelector'
import { CasesStatusBadge } from '../features/cases/components/CasesStatusBadge'
import { setAccessToken, clearAccessToken, setSessionUser } from '../api/auth-memory'
import {
  VALID_CASE_STATUS_TRANSITIONS,
  CASE_STATUS_UPPERCASE_LABELS,
  CASE_STATUS_UNDEFINED_LABEL,
} from '../api/cases-types'
import { updateCaseStatusSchema } from '../features/cases/schemas/updateCaseStatusSchema'

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

describe('Story F2.2 : Évolution du statut global du dossier (E2, openapi.json)', () => {
  beforeEach(() => {
    clearAccessToken()
    setAccessToken('mock-access-token-bearer-15min')
    setSessionUser({
      userName: 'analyste@iryx.local',
      organizationName: 'CERT National IRYX',
      role: 'analyst',
    })

    // Réinitialisation de l'état simulé en mémoire des dossiers
    const case001 = MOCK_CASES.find((c) => c.id === 'case-001')
    if (case001) case001.status = 'open'
    const case002 = MOCK_CASES.find((c) => c.id === 'case-002')
    if (case002) case002.status = 'in_progress'
    const case003 = MOCK_CASES.find((c) => c.id === 'case-003')
    if (case003) case003.status = 'review'
    const case005 = MOCK_CASES.find((c) => c.id === 'case-005')
    if (case005) case005.status = 'closed'

    window.localStorage.clear()
    window.sessionStorage.clear()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    clearAccessToken()
    window.localStorage.clear()
    window.sessionStorage.clear()
  })

  describe('1. Validation Zod et matrice stricte des transitions', () => {
    it('valide uniquement les 4 statuts officiels du contrat OpenAPI via le schéma Zod', () => {
      expect(updateCaseStatusSchema.safeParse({ status: 'open' }).success).toBe(true)
      expect(updateCaseStatusSchema.safeParse({ status: 'in_progress' }).success).toBe(true)
      expect(updateCaseStatusSchema.safeParse({ status: 'review' }).success).toBe(true)
      expect(updateCaseStatusSchema.safeParse({ status: 'closed' }).success).toBe(true)

      // Rejet des valeurs inventées ou non conformes
      expect(updateCaseStatusSchema.safeParse({ status: 'archived' }).success).toBe(false)
      expect(updateCaseStatusSchema.safeParse({ status: 'pending' }).success).toBe(false)
      expect(updateCaseStatusSchema.safeParse({ status: 'draft' }).success).toBe(false)
      expect(updateCaseStatusSchema.safeParse({}).success).toBe(false)
    })

    it('définit rigoureusement la matrice des transitions de cycle de vie sans transitions inventées', () => {
      // open -> in_progress, closed
      expect(VALID_CASE_STATUS_TRANSITIONS.open).toEqual(['in_progress', 'closed'])
      // in_progress -> review, open, closed
      expect(VALID_CASE_STATUS_TRANSITIONS.in_progress).toEqual(['review', 'open', 'closed'])
      // review -> closed, in_progress
      expect(VALID_CASE_STATUS_TRANSITIONS.review).toEqual(['closed', 'in_progress'])
      // closed -> aucun (état terminal)
      expect(VALID_CASE_STATUS_TRANSITIONS.closed).toEqual([])
    })
  })

  describe('2. État nominal et mise à jour réussie du statut', () => {
    it('affiche le badge d état en majuscules dans l en-tête et propose uniquement les transitions autorisées', async () => {
      renderCaseContextPage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('case-view-title')).toBeInTheDocument()
      })

      // Badge d'en-tête en majuscules avec icône
      const statusBadge = screen.getByTestId('case-view-status')
      expect(statusBadge).toHaveTextContent(CASE_STATUS_UPPERCASE_LABELS.open) // 'OUVERT'

      // Sélecteur de statut contrôlé
      const select = screen.getByTestId('case-status-select') as HTMLSelectElement
      expect(select).toBeInTheDocument()
      expect(select).not.toBeDisabled()

      // Options disponibles depuis 'open' : uniquement 'in_progress' et 'closed'
      const options = Array.from(select.options).map((o) => o.value)
      expect(options).toContain('in_progress')
      expect(options).toContain('closed')
      expect(options).not.toContain('review') // 'review' n'est pas autorisée depuis 'open'
    })

    it('exécute la mutation PATCH /status, met à jour le badge en majuscules et affiche la notification de confirmation', async () => {
      const user = userEvent.setup()
      const { queryClient } = renderCaseContextPage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('case-view-title')).toBeInTheDocument()
      })

      const select = screen.getByTestId('case-status-select')
      const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

      // Sélection de "Passer à : En cours"
      await user.selectOptions(select, 'in_progress')

      // Validation serveur et mise à jour de l'affichage
      await waitFor(() => {
        const badge = screen.getByTestId('case-view-status')
        expect(badge).toHaveTextContent(CASE_STATUS_UPPERCASE_LABELS.in_progress) // 'EN COURS'
      })

      // Notification de confirmation présente
      expect(screen.getByTestId('case-update-success-notification')).toHaveTextContent(
        /Statut du dossier mis à jour avec succès : EN COURS/i,
      )

      // Invalidation des requêtes du cache TanStack Query
      expect(invalidateSpy).toHaveBeenCalledWith(expect.objectContaining({ queryKey: ['cases'] }))
    })
  })

  describe('3. État de chargement et synchronisation', () => {
    it('désactive le sélecteur avec un indicateur discret de synchronisation pendant la mutation', async () => {
      // 1. Vérification unitaire du composant en mode synchronisation
      const { unmount } = render(
        <CaseStatusSelector currentStatus="open" onStatusChange={vi.fn()} isUpdating={true} />,
      )
      const directSelect = screen.getByTestId('case-status-select')
      expect(directSelect).toBeDisabled()
      expect(screen.getByTestId('status-sync-indicator')).toBeInTheDocument()
      expect(screen.getByTestId('status-sync-indicator')).toHaveTextContent(/synchronisation/i)
      unmount()

      // 2. Vérification d'intégration lors d'un appel réseau asynchrone
      server.use(
        http.patch('*/api/v1/cases/:caseId/status', async () => {
          await new Promise((resolve) => setTimeout(resolve, 80))
          const case001 = MOCK_CASES.find((c) => c.id === 'case-001')
          if (case001) case001.status = 'in_progress'
          return HttpResponse.json(
            {
              id: 'case-001',
              organization_id: 'org-001',
              title: 'Incident Ransomware LockBit v3',
              description: 'Compromission initiale',
              status: 'in_progress',
              created_by: 'analyste@iryx.local',
              created_at: '2026-11-20T08:15:00Z',
              updated_at: '2026-11-25T10:00:00Z',
              evidence_count: 4,
            },
            { status: 200 },
          )
        }),
      )

      renderCaseContextPage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('case-status-select')).toBeInTheDocument()
      })

      const select = screen.getByTestId('case-status-select')
      fireEvent.change(select, { target: { value: 'in_progress' } })

      // Pendant la synchronisation
      expect(select).toBeDisabled()
      expect(screen.getByTestId('status-sync-indicator')).toBeInTheDocument()

      // Après résolution
      await waitFor(() => {
        expect(screen.queryByTestId('status-sync-indicator')).not.toBeInTheDocument()
        expect(screen.getByTestId('case-view-status')).toHaveTextContent(
          CASE_STATUS_UPPERCASE_LABELS.in_progress,
        )
      })
    })
  })

  describe('4. État vide / Statut non défini', () => {
    it('affiche la mention « NON DÉFINI » avec icône neutre si le statut n est pas défini au chargement', async () => {
      // Mock d'un dossier dont le statut est nul ou non défini
      server.use(
        http.get('*/api/v1/cases/:caseId', () => {
          return HttpResponse.json(
            {
              id: 'case-undefined-status',
              organization_id: 'org-001',
              title: 'Dossier statut non défini',
              description: 'Incident en cours de qualification',
              status: null,
              created_by: 'analyste@iryx.local',
              created_at: '2026-11-20T08:15:00Z',
              updated_at: '2026-11-20T09:00:00Z',
              evidence_count: 0,
            },
            { status: 200 },
          )
        }),
      )

      renderCaseContextPage('case-undefined-status')

      await waitFor(() => {
        expect(screen.getByTestId('case-view-title')).toBeInTheDocument()
      })

      // Badge affiche NON DÉFINI
      const undefinedBadge = screen.getByTestId('case-status-undefined')
      expect(undefinedBadge).toBeInTheDocument()
      expect(undefinedBadge).toHaveTextContent(CASE_STATUS_UNDEFINED_LABEL)

      // Sélecteur affiche la mention non défini
      expect(screen.getByTestId('case-status-undefined-selector')).toHaveTextContent(
        CASE_STATUS_UNDEFINED_LABEL,
      )
    })

    it('le composant CasesStatusBadge restitue l état vide de manière isolée sans crash', () => {
      const { unmount } = render(<CasesStatusBadge status={undefined} />)
      expect(screen.getByTestId('case-status-undefined')).toHaveTextContent(
        CASE_STATUS_UNDEFINED_LABEL,
      )
      unmount()

      render(<CasesStatusBadge status={null} />)
      expect(screen.getByTestId('case-status-undefined')).toHaveTextContent(
        CASE_STATUS_UNDEFINED_LABEL,
      )
    })
  })

  describe('5. Statut terminal (dossier clôturé)', () => {
    it('désactive le sélecteur lorsqu un dossier est au statut closed (aucune transition)', async () => {
      renderCaseContextPage('case-005') // case-005 a le statut 'closed' dans MOCK_CASES

      await waitFor(() => {
        expect(screen.getByTestId('case-view-title')).toBeInTheDocument()
      })

      expect(screen.getByTestId('case-view-status')).toHaveTextContent(
        CASE_STATUS_UPPERCASE_LABELS.closed,
      )

      const select = screen.getByTestId('case-status-select') as HTMLSelectElement
      expect(select).toBeDisabled()
      expect(select).toHaveTextContent(/aucune transition/i)
    })
  })

  describe('6. Rejet de transition par le serveur (HTTP 400 ou 409) et conservation de saisie', () => {
    it('affiche un message clair lors d un refus HTTP 400, restaure le statut initial et ne perd aucune saisie', async () => {
      const user = userEvent.setup()

      server.use(
        http.patch('*/api/v1/cases/:caseId/status', () => {
          return HttpResponse.json(
            { detail: "Transition non autorisée du statut 'open' vers 'in_progress'." },
            { status: 400 },
          )
        }),
      )

      renderCaseContextPage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('case-status-select')).toBeInTheDocument()
      })

      const select = screen.getByTestId('case-status-select') as HTMLSelectElement
      await user.selectOptions(select, 'in_progress')

      // Notification d'erreur affichée avec le message clair renvoyé par le serveur
      await waitFor(() => {
        expect(screen.getByTestId('case-status-error-notification')).toBeInTheDocument()
      })
      expect(screen.getByTestId('case-status-error-notification')).toHaveTextContent(
        /Transition non autorisée/i,
      )

      // Le statut précédent reste restauré sur le badge d'en-tête
      expect(screen.getByTestId('case-view-status')).toHaveTextContent(
        CASE_STATUS_UPPERCASE_LABELS.open,
      )
      // La description et le contexte ne sont pas altérés
      expect(screen.getByTestId('case-view-description')).toHaveTextContent(
        'Compromission initiale par pièce jointe malveillante',
      )
    })

    it('affiche un message clair lors d un conflit HTTP 409 et restaure le statut précédent', async () => {
      const user = userEvent.setup()

      server.use(
        http.patch('*/api/v1/cases/:caseId/status', () => {
          return HttpResponse.json(
            { detail: 'Conflit de version : transition concurrente détectée.' },
            { status: 409 },
          )
        }),
      )

      renderCaseContextPage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('case-status-select')).toBeInTheDocument()
      })

      const select = screen.getByTestId('case-status-select')
      await user.selectOptions(select, 'in_progress')

      await waitFor(() => {
        expect(screen.getByTestId('case-status-error-notification')).toBeInTheDocument()
      })
      expect(screen.getByTestId('case-status-error-notification')).toHaveTextContent(
        /Conflit de version/i,
      )

      // Statut initial préservé
      expect(screen.getByTestId('case-view-status')).toHaveTextContent(
        CASE_STATUS_UPPERCASE_LABELS.open,
      )
    })

    it('gère une erreur réseau ou 500 avec message clair et statut précédent conservé', async () => {
      const user = userEvent.setup()

      server.use(
        http.patch('*/api/v1/cases/:caseId/status', () => {
          return HttpResponse.json(
            { detail: 'Erreur interne du serveur lors de la mise à jour du statut.' },
            { status: 500 },
          )
        }),
      )

      renderCaseContextPage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('case-status-select')).toBeInTheDocument()
      })

      const select = screen.getByTestId('case-status-select')
      await user.selectOptions(select, 'in_progress')

      await waitFor(() => {
        expect(screen.getByTestId('case-status-error-notification')).toBeInTheDocument()
      })
      expect(screen.getByTestId('case-status-error-notification')).toHaveTextContent(
        /Erreur interne du serveur/i,
      )
      expect(screen.getByTestId('case-view-status')).toHaveTextContent(
        CASE_STATUS_UPPERCASE_LABELS.open,
      )
    })
  })

  describe('7. État d accès refusé / Profil en lecture seule (viewer)', () => {
    it('rend le sélecteur en mode texte non modifiable sans contrôle interactif pour un utilisateur viewer', async () => {
      // Configuration de session pour un utilisateur en lecture seule
      setSessionUser({
        userName: 'lecteur@iryx.local',
        organizationName: 'CERT National IRYX',
        role: 'viewer',
      })

      renderCaseContextPage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('case-view-title')).toBeInTheDocument()
      })

      // Le sélecteur est rendu en mode texte non modifiable (lecture seule)
      expect(screen.getByTestId('case-status-readonly')).toBeInTheDocument()
      expect(screen.getByTestId('case-status-readonly')).toHaveTextContent(/lecture seule/i)

      // Aucun contrôle <select> interactif n'est disponible
      expect(screen.queryByTestId('case-status-select')).not.toBeInTheDocument()
    })

    it('le composant CaseStatusSelector avec isReadOnly=true affiche le badge lecture seule sans contrôle interactif', () => {
      render(<CaseStatusSelector currentStatus="open" onStatusChange={vi.fn()} isReadOnly={true} />)

      expect(screen.getByTestId('case-status-readonly')).toBeInTheDocument()
      expect(screen.getByTestId('case-status-readonly')).toHaveTextContent(/lecture seule/i)
      expect(screen.queryByTestId('case-status-select')).not.toBeInTheDocument()
    })
  })

  describe('8. Respect des règles architecturales : absence de stockage local et palette stricte', () => {
    it('n effectue aucune écriture dans localStorage ni sessionStorage lors de l évolution de statut', async () => {
      const user = userEvent.setup()
      renderCaseContextPage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('case-status-select')).toBeInTheDocument()
      })

      const setItemLocalSpy = vi.spyOn(Storage.prototype, 'setItem')

      const select = screen.getByTestId('case-status-select')
      await user.selectOptions(select, 'in_progress')

      await waitFor(() => {
        expect(screen.getByTestId('case-view-status')).toHaveTextContent(
          CASE_STATUS_UPPERCASE_LABELS.in_progress,
        )
      })

      expect(setItemLocalSpy).not.toHaveBeenCalled()
      expect(window.localStorage.length).toBe(0)
      expect(window.sessionStorage.length).toBe(0)
    })
  })
})
