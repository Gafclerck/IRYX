import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse, delay } from 'msw'
import { server } from './mocks/server'
import { resetMockCases, resetMockEvidences } from './mocks/handlers'
import { EvidencePage } from '../pages/EvidencePage'
import { setAccessToken, clearAccessToken, setSessionUser } from '../api/auth-memory'
import { truncateObservationContent, DP04_MAX_PREVIEW_LINES } from '../features/evidence'

const EVI_001_SHA256 = 'a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef0'

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="current-path">{location.pathname}</div>
}

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

function renderEvidencePage(initialPath = '/cases/case-001/evidence') {
  const queryClient = createTestQueryClient()
  return {
    queryClient,
    ...render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[initialPath]}>
          <Routes>
            <Route path="/cases" element={<div data-testid="cases-list-page">Liste</div>} />
            <Route path="/cases/:caseId/plan" element={<div>Plan</div>} />
            <Route path="/cases/:caseId" element={<div>Contexte dossier</div>} />
            <Route path="/cases/:caseId/evidence" element={<EvidencePage />} />
            <Route path="/cases/:caseId/evidence/:evidenceId" element={<EvidencePage />} />
          </Routes>
          <LocationProbe />
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  }
}

async function openDrawerFor(evidenceId: string) {
  const row = await screen.findByTestId(`evidence-row-${evidenceId}`)
  fireEvent.click(row)
  return screen.findByTestId('evidence-detail-drawer')
}

describe('Story F3.3 : Panneau d’inspection détaillée d’une preuve', () => {
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

  describe('1. État nominal', () => {
    it('ouvre le tiroir sans quitter la page et affiche l’empreinte intégrale, les métadonnées et l’historique', async () => {
      renderEvidencePage()

      await openDrawerFor('evi-001')

      // La liste reste visible derrière le tiroir et l'URL est synchronisée
      expect(screen.getByTestId('evidence-inventory-table')).toBeInTheDocument()
      expect(screen.getByTestId('current-path')).toHaveTextContent(
        '/cases/case-001/evidence/evi-001',
      )

      // Empreinte SHA-256 complète en chasse fixe
      const sha256 = await screen.findByTestId('evidence-drawer-full-sha256')
      expect(sha256).toHaveTextContent(EVI_001_SHA256)
      expect(sha256.className).toContain('font-mono')
      expect(screen.getByTestId('copy-full-sha256-btn')).toBeInTheDocument()

      // Métadonnées forensiques
      expect(screen.getByTestId('drawer-meta-name')).toHaveTextContent('Security.evtx')
      expect(screen.getByTestId('drawer-meta-type')).toHaveTextContent('application/x-ms-evtx')
      expect(screen.getByTestId('drawer-meta-size')).toHaveTextContent('14.8 Mo')
      expect(screen.getByTestId('drawer-meta-date')).toHaveTextContent('2026-11-20 08:30:00 UTC')
      expect(screen.getByTestId('drawer-meta-importer')).toHaveTextContent('analyste@iryx.local')
      expect(screen.getByTestId('drawer-meta-provenance')).toHaveTextContent(
        'Non renseignée par le contrat',
      )

      // Historique des exécutions d'ingestion et erreur éventuelle
      expect(screen.getByTestId('ingestion-run-item-run-001')).toBeInTheDocument()
      expect(screen.getByTestId('drawer-ingestion-error-message')).toHaveTextContent(
        'Format binaire invalide ou corruption de fichier.',
      )

      // Décompte d'observations
      expect(screen.getByTestId('evidence-drawer-observation-count')).toHaveTextContent(
        '2 observations',
      )

      // Troncature DP-04 de l'observation volumineuse avec téléchargement direct
      expect(screen.getByTestId('dp04-truncation-notice')).toBeInTheDocument()
      expect(screen.getByTestId('download-full-observation-btn')).toHaveTextContent(
        /Télécharger l.observation intégrale/,
      )
    })

    it('copie l’empreinte SHA-256 intégrale dans le presse-papier', async () => {
      const writeText = vi.fn().mockResolvedValue(undefined)
      Object.defineProperty(navigator, 'clipboard', {
        value: { writeText },
        configurable: true,
      })

      renderEvidencePage()
      await openDrawerFor('evi-001')

      fireEvent.click(await screen.findByTestId('copy-full-sha256-btn'))

      await waitFor(() => {
        expect(writeText).toHaveBeenCalledWith(EVI_001_SHA256)
      })
      expect(await screen.findByText('Copié !')).toBeInTheDocument()
    })
  })

  describe('2. État de chargement', () => {
    it('affiche des squelettes animés pendant le chargement des métadonnées', async () => {
      server.use(
        http.get('*/api/v1/cases/:caseId/evidences/:evidenceId', async () => {
          await delay(150)
          return HttpResponse.json({
            id: 'evi-001',
            case_id: 'case-001',
            original_name: 'Security.evtx',
            file_size: 15482880,
            sha256: EVI_001_SHA256,
            detected_type: 'application/x-ms-evtx',
            imported_by: 'analyste@iryx.local',
            created_at: '2026-11-20T08:30:00Z',
            observation_count: 0,
            observations: [],
            ingestion_runs: [],
          })
        }),
      )

      renderEvidencePage()
      const row = await screen.findByTestId('evidence-row-evi-001')
      fireEvent.click(row)

      expect(await screen.findByTestId('evidence-drawer-loading')).toBeInTheDocument()
      expect(await screen.findByTestId('evidence-drawer-full-sha256')).toHaveTextContent(
        EVI_001_SHA256,
      )
    })
  })

  describe('3. État vide', () => {
    it('affiche la mention « Aucune observation extraite pour cette preuve »', async () => {
      renderEvidencePage()
      await openDrawerFor('evi-003')

      expect(await screen.findByTestId('evidence-drawer-no-observations')).toHaveTextContent(
        'Aucune observation extraite pour cette preuve',
      )
      expect(screen.getByTestId('evidence-drawer-observation-count')).toHaveTextContent(
        '0 observation',
      )
    })
  })

  describe('4. État d’erreur', () => {
    it('affiche le message d’échec et permet de réessayer', async () => {
      server.use(
        http.get('*/api/v1/cases/:caseId/evidences/:evidenceId', () =>
          HttpResponse.json(
            { detail: 'Erreur interne lors de la consultation des détails de la preuve.' },
            { status: 500 },
          ),
        ),
      )

      renderEvidencePage()
      await openDrawerFor('evi-001')

      expect(await screen.findByTestId('evidence-drawer-error')).toHaveTextContent(
        'Erreur de chargement des détails de la preuve',
      )

      server.resetHandlers()
      fireEvent.click(screen.getByTestId('retry-evidence-detail-btn'))

      expect(await screen.findByTestId('evidence-drawer-full-sha256')).toHaveTextContent(
        EVI_001_SHA256,
      )
    })
  })

  describe('5. État 404 introuvable', () => {
    it('affiche un message neutre sans fuite de données', async () => {
      renderEvidencePage('/cases/case-001/evidence/evi-inexistante')

      expect(await screen.findByTestId('evidence-drawer-not-found')).toHaveTextContent(
        'Cette preuve numérique est introuvable ou n’existe pas dans ce dossier d’investigation.',
      )
      expect(screen.queryByTestId('evidence-drawer-full-sha256')).not.toBeInTheDocument()
      expect(screen.getByTestId('current-path')).toHaveTextContent(
        '/cases/case-001/evidence/evi-inexistante',
      )
    })
  })

  describe('6. État d’accès refusé (403)', () => {
    it('ferme le tiroir, affiche un toast et revient à la liste autorisée', async () => {
      server.use(
        http.get('*/api/v1/cases/:caseId/evidences/:evidenceId', () =>
          HttpResponse.json(
            { detail: "Accès refusé. Vous n'avez pas accès aux détails de cette preuve." },
            { status: 403 },
          ),
        ),
      )

      renderEvidencePage()
      await openDrawerFor('evi-001')

      expect(await screen.findByTestId('evidence-access-denied-toast')).toHaveTextContent(
        "Accès refusé. Vous n'avez pas accès aux détails de cette preuve.",
      )
      await waitFor(() => {
        expect(screen.queryByTestId('evidence-detail-drawer')).not.toBeInTheDocument()
      })
      expect(screen.getByTestId('current-path')).toHaveTextContent('/cases/case-001/evidence')
    })
  })

  describe('7. Fermeture et restitution du focus', () => {
    it('ferme par Échap, réoriente l’URL et rend le focus à la ligne d’origine', async () => {
      renderEvidencePage()
      await openDrawerFor('evi-001')

      fireEvent.keyDown(window, { key: 'Escape' })

      await waitFor(() => {
        expect(screen.queryByTestId('evidence-detail-drawer')).not.toBeInTheDocument()
      })
      expect(screen.getByTestId('current-path')).toHaveTextContent('/cases/case-001/evidence')
      await waitFor(() => {
        expect(screen.getByTestId('evidence-row-evi-001')).toHaveFocus()
      })
    })

    it('ferme par le bouton de fermeture', async () => {
      renderEvidencePage()
      await openDrawerFor('evi-001')

      fireEvent.click(screen.getByTestId('evidence-drawer-close-btn'))

      await waitFor(() => {
        expect(screen.queryByTestId('evidence-detail-drawer')).not.toBeInTheDocument()
      })
      expect(screen.getByTestId('current-path')).toHaveTextContent('/cases/case-001/evidence')
    })
  })

  describe('8. Troncature volumétrique DP-04', () => {
    it('ne tronque pas un contenu sous les seuils', () => {
      const result = truncateObservationContent('ligne 1\nligne 2')
      expect(result.isTruncated).toBe(false)
      expect(result.totalLines).toBe(2)
    })

    it('tronque à 500 lignes avec motif « lines »', () => {
      const content = Array.from(
        { length: DP04_MAX_PREVIEW_LINES + 1 },
        (_, index) => `ligne ${index + 1}`,
      ).join('\n')
      const result = truncateObservationContent(content)
      expect(result.isTruncated).toBe(true)
      expect(result.truncationReason).toBe('lines')
      expect(result.previewText.split('\n')).toHaveLength(DP04_MAX_PREVIEW_LINES)
    })

    it('tronque au-delà de 64 Ko avec motif « bytes »', () => {
      const content = 'a'.repeat(64 * 1024 + 1)
      const result = truncateObservationContent(content)
      expect(result.isTruncated).toBe(true)
      expect(result.truncationReason).toBe('bytes')
      expect(result.previewText.length).toBe(64 * 1024)
      expect(result.fullText.length).toBe(content.length)
    })
  })
})
