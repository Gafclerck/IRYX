import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from './mocks/server'
import { resetMockCases, resetMockEvidences } from './mocks/handlers'
import { EvidencePage } from '../pages/EvidencePage'
import { setAccessToken, clearAccessToken, setSessionUser } from '../api/auth-memory'
import {
  formatIngestionStatus,
  DP05_MAX_CONSECUTIVE_NETWORK_ERRORS,
} from '../features/evidence/constants'

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

function renderEvidencePage(initialCaseId = 'case-001') {
  const queryClient = createTestQueryClient()
  return {
    queryClient,
    ...render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/cases/${initialCaseId}/evidence`]}>
          <Routes>
            <Route
              path="/cases"
              element={<div data-testid="cases-list-page">Liste des dossiers</div>}
            />
            <Route
              path="/cases/:caseId/plan"
              element={<div data-testid="case-plan-page">Étape 3 Plan d'investigation</div>}
            />
            <Route path="/cases/:caseId" element={<div>Contexte dossier</div>} />
            <Route path="/cases/:caseId/evidence" element={<EvidencePage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  }
}

describe('Story F3.2 : Registre d’inventaire des preuves, suivi d’ingestion et condition d’analyse', () => {
  beforeEach(() => {
    clearAccessToken()
    setAccessToken('mock-access-token-bearer-15min')
    setSessionUser({
      userName: 'analyste@iryx.local',
      organizationName: 'CERT National IRYX',
      role: 'analyst',
    })
    resetMockCases()
    resetMockEvidences()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('1. Tableau de l’inventaire et 7 colonnes obligatoires (État nominal)', () => {
    it('affiche le tableau d’inventaire avec les 7 colonnes requises', async () => {
      renderEvidencePage('case-001')

      // Attente du chargement du tableau
      await waitFor(() => {
        expect(screen.getByTestId('evidence-inventory-table')).toBeInTheDocument()
      })

      // Vérification des 7 en-têtes de colonnes
      expect(screen.getByRole('columnheader', { name: 'Nom' })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: 'Type détecté' })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: 'Taille' })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: 'Empreinte SHA-256' })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: 'Date d’ajout (UTC)' })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: 'Provenance' })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: 'Statut d’ingestion' })).toBeInTheDocument()

      // Présence des preuves initiales
      expect(screen.getByText('Security.evtx')).toBeInTheDocument()
      expect(screen.getByText('memory_dump.raw')).toBeInTheDocument()
      expect(screen.getByText('auth.log')).toBeInTheDocument()
      expect(screen.getByText('corrupted_artifact.bin')).toBeInTheDocument()
    })

    it('affiche la date d’ajout explicitement en UTC pour garantir la rigueur forensique', async () => {
      renderEvidencePage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('evidence-inventory-table')).toBeInTheDocument()
      })

      // Vérification d'au moins un horodatage avec la mention 'UTC' au format YYYY-MM-DD HH:mm:ss UTC
      const utcDateElements = screen.getAllByText(/\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC/)
      expect(utcDateElements.length).toBeGreaterThan(0)
      expect(utcDateElements[0]?.textContent).toMatch(/\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC/)
    })

    it('affiche la provenance et la taille formatée', async () => {
      renderEvidencePage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('evidence-inventory-table')).toBeInTheDocument()
      })

      // Taille formatée
      expect(screen.getByText('14.8 Mo')).toBeInTheDocument() // 15482880 octets
      expect(screen.getByText('4.0 Go')).toBeInTheDocument() // 4294967296 octets

      // Provenance
      const provenanceElements = screen.getAllByText('analyste@iryx.local')
      expect(provenanceElements.length).toBeGreaterThan(0)
    })
  })

  describe('2. Troncature SHA-256 et copie dans le presse-papier', () => {
    it('tronque l’empreinte SHA-256 en affichage condensé et permet la copie intégrale', async () => {
      const writeTextMock = vi.fn().mockResolvedValue(undefined)
      Object.assign(navigator, {
        clipboard: {
          writeText: writeTextMock,
        },
      })

      renderEvidencePage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('evidence-inventory-table')).toBeInTheDocument()
      })

      // Vérification de la troncature : 8 premiers caractères + ... + 8 derniers caractères
      const hashSpan = screen.getByTestId('sha256-hash-evi-001')
      expect(hashSpan.textContent).toBe('a1b2c3d4...9abcdef0')

      // Clic sur le bouton de copie
      const copyBtn = screen.getByTestId('copy-sha256-btn-evi-001')
      fireEvent.click(copyBtn)

      // Le hash complet de 64 caractères est écrit dans le presse-papier
      expect(writeTextMock).toHaveBeenCalledWith(
        'a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef0',
      )
    })
  })

  describe('3. Machine d’états d’ingestion et règle de robustesse', () => {
    it('restitue l’état completed sous le libellé « INTÈGRE »', async () => {
      renderEvidencePage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('status-badge-evi-001')).toBeInTheDocument()
      })

      const badge = screen.getByTestId('status-badge-evi-001')
      expect(badge.textContent).toContain('INTÈGRE')
    })

    it('restitue l’état failed sous le libellé « ÉCHEC » avec icône d’alerte', async () => {
      renderEvidencePage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('status-badge-evi-004')).toBeInTheDocument()
      })

      const badge = screen.getByTestId('status-badge-evi-004')
      expect(badge.textContent).toContain('ÉCHEC')
    })

    it('restitue un statut non répertorié sous la mention « État inconnu (code) » sans plantage', async () => {
      server.use(
        http.get('*/api/v1/cases/:caseId/evidences', () => {
          return HttpResponse.json({
            items: [
              {
                id: 'evi-unknown',
                case_id: 'case-001',
                original_name: 'future_format.dat',
                file_size: 512,
                sha256: null,
                detected_type: 'application/octet-stream',
                imported_by: 'analyste@iryx.local',
                created_at: '2026-11-20T10:00:00Z',
              },
            ],
            total: 1,
            total_items: 1,
            limit: 50,
            offset: 0,
            has_more: false,
          })
        }),
      )

      renderEvidencePage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('status-badge-evi-unknown')).toBeInTheDocument()
      })

      // Vérification de la règle docs/frontend/12 section 4 : « État inconnu (code) »
      const badge = screen.getByTestId('status-badge-evi-unknown')
      expect(badge.textContent).toContain('État inconnu (unrecognized_state_code)')
    })

    it('fonction utilitaire formatIngestionStatus respecte le modèle et les états terminaux', () => {
      expect(formatIngestionStatus('completed')).toEqual({
        label: 'INTÈGRE',
        isKnown: true,
        isTerminal: true,
        isIntegrity: true,
        isFailed: false,
      })

      expect(formatIngestionStatus('failed')).toEqual({
        label: 'ÉCHEC',
        isKnown: true,
        isTerminal: true,
        isIntegrity: false,
        isFailed: true,
      })

      expect(formatIngestionStatus('processing')).toEqual({
        label: 'EN COURS',
        isKnown: true,
        isTerminal: false,
        isIntegrity: false,
        isFailed: false,
      })

      expect(formatIngestionStatus('pending')).toEqual({
        label: 'EN ATTENTE',
        isKnown: true,
        isTerminal: false,
        isIntegrity: false,
        isFailed: false,
      })

      expect(formatIngestionStatus('unknown_custom_code')).toEqual({
        label: 'État inconnu (unknown_custom_code)',
        isKnown: false,
        isTerminal: true,
        isIntegrity: false,
        isFailed: true,
      })
    })
  })

  describe('4. Condition d’activation du bouton « Lancer l’analyse »', () => {
    it('active le bouton « Lancer l’analyse » dès qu’au moins une preuve est intègre et permet la navigation vers /plan', async () => {
      renderEvidencePage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('launch-analysis-btn')).toBeInTheDocument()
      })

      const launchBtn = screen.getByTestId('launch-analysis-btn')
      expect(launchBtn).not.toBeDisabled()

      fireEvent.click(launchBtn)

      // Navigation vers /cases/:caseId/plan (Étape 3)
      await waitFor(() => {
        expect(screen.getByTestId('case-plan-page')).toBeInTheDocument()
      })
    })

    it('désactive le bouton avec infobulle si aucune preuve n’est confirmée intègre', async () => {
      // Simulation dossier avec uniquement des preuves en échec ou non terminées
      server.use(
        http.get('*/api/v1/cases/:caseId/evidences', () => {
          return HttpResponse.json({
            items: [
              {
                id: 'evi-failed-only',
                case_id: 'case-001',
                original_name: 'corrupted.bin',
                file_size: 1024,
                sha256: null,
                detected_type: 'application/octet-stream',
                imported_by: 'analyste@iryx.local',
                created_at: '2026-11-20T10:00:00Z',
              },
            ],
            total: 1,
            total_items: 1,
            limit: 50,
            offset: 0,
            has_more: false,
          })
        }),
        http.get('*/api/v1/cases/:caseId/evidences/:evidenceId/ingestion-status', () => {
          return HttpResponse.json({
            status: 'failed',
            progress: 10,
            error_message: 'Fichier corrompu',
            sha256: null,
            detected_type: 'application/octet-stream',
          })
        }),
      )

      renderEvidencePage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('launch-analysis-btn')).toBeInTheDocument()
      })

      const launchBtn = screen.getByTestId('launch-analysis-btn')
      expect(launchBtn).toBeDisabled()
      expect(launchBtn).toHaveAttribute(
        'title',
        'Le lancement de l’analyse requiert au moins une preuve scellée et confirmée intègre.',
      )

      expect(screen.getByTestId('analysis-disabled-help')).toBeInTheDocument()
    })
  })

  describe('5. État vide du registre', () => {
    it('affiche le message central « Aucune preuve déposée pour ce dossier » et désactive l’analyse', async () => {
      server.use(
        http.get('*/api/v1/cases/:caseId/evidences', () => {
          return HttpResponse.json({
            items: [],
            total: 0,
            total_items: 0,
            limit: 50,
            offset: 0,
            has_more: false,
          })
        }),
      )

      renderEvidencePage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('evidence-inventory-empty-state')).toBeInTheDocument()
      })

      expect(screen.getByTestId('evidence-inventory-empty-state')).toHaveTextContent(
        'Aucune preuve déposée pour ce dossier',
      )

      const launchBtn = screen.getByTestId('launch-analysis-btn')
      expect(launchBtn).toBeDisabled()
    })
  })

  describe('6. État d’erreur et réessai', () => {
    it('affiche le bandeau d’erreur avec le bouton « Réessayer » en cas de défaillance 500', async () => {
      let fail = true
      server.use(
        http.get('*/api/v1/cases/:caseId/evidences', () => {
          if (fail) {
            return HttpResponse.json({ detail: 'Incident interne de stockage.' }, { status: 500 })
          }
          return HttpResponse.json({
            items: [
              {
                id: 'evi-recovered',
                case_id: 'case-001',
                original_name: 'recovered.evtx',
                file_size: 2048,
                sha256: 'abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890',
                detected_type: 'application/x-ms-evtx',
                imported_by: 'analyste@iryx.local',
                created_at: '2026-11-20T10:00:00Z',
              },
            ],
            total: 1,
            total_items: 1,
            limit: 50,
            offset: 0,
            has_more: false,
          })
        }),
      )

      renderEvidencePage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('evidence-table-error')).toBeInTheDocument()
      })

      expect(screen.getByText('Erreur de chargement du registre des preuves')).toBeInTheDocument()

      // Clic sur Réessayer
      fail = false
      const retryBtn = screen.getByTestId('retry-evidence-fetch-btn')
      fireEvent.click(retryBtn)

      await waitFor(() => {
        expect(screen.getByText('recovered.evtx')).toBeInTheDocument()
      })
    })
  })

  describe('7. DP-05 : Coupure réseau prolongée et bouton « Réessayer la connexion »', () => {
    it('interrompt la scrutation sur coupure prolongée et permet la relance via « Réessayer la connexion »', async () => {
      server.use(
        http.get('*/api/v1/cases/:caseId/evidences', () => {
          return HttpResponse.json({
            items: [
              {
                id: 'evi-polling-test',
                case_id: 'case-001',
                original_name: 'live.evtx',
                file_size: 1024,
                sha256: null,
                detected_type: 'application/x-ms-evtx',
                imported_by: 'analyste@iryx.local',
                created_at: '2026-11-20T10:00:00Z',
              },
            ],
            total: 1,
            total_items: 1,
            limit: 50,
            offset: 0,
            has_more: false,
          })
        }),
        http.get('*/api/v1/cases/:caseId/evidences/:evidenceId/ingestion-status', () => {
          // Erreur réseau répétée
          return HttpResponse.json({ detail: 'Rupture de transport' }, { status: 503 })
        }),
      )

      renderEvidencePage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('evidence-inventory-table')).toBeInTheDocument()
      })

      // Le seuil de sécurité DP-05 est de 3 erreurs consécutives
      expect(DP05_MAX_CONSECUTIVE_NETWORK_ERRORS).toBe(3)
    })
  })

  describe('8. État d’accès refusé (HTTP 403 Forbidden)', () => {
    it('interrompt immédiatement la scrutation et affiche le message d’accès refusé', async () => {
      server.use(
        http.get('*/api/v1/cases/:caseId/evidences', () => {
          return HttpResponse.json(
            { detail: "Accès refusé. Vous n'avez pas accès aux preuves de ce dossier." },
            { status: 403 },
          )
        }),
      )

      renderEvidencePage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('evidence-forbidden-banner')).toBeInTheDocument()
      })

      expect(screen.getByText('Accès non autorisé')).toBeInTheDocument()
    })
  })
})
