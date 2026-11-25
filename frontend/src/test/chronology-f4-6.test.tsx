import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { HttpResponse, http } from 'msw'
import { apiClient } from '../api/client'
import { clearAccessToken, setAccessToken, setSessionUser } from '../api/auth-memory'
import { ResultsPage } from '../pages/ResultsPage'
import { TIMELINE_PAGE_SIZE } from '../features/results/constants'
import { server } from './mocks/server'
import { resetMockCases, resetMockH1Decisions, resetMockRunSupervision } from './mocks/handlers'

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0, gcTime: 0 },
      mutations: { retry: false },
    },
  })
}

function renderResultsPage(caseId = 'case-001') {
  const queryClient = createTestQueryClient()
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/cases/${caseId}/results`]}>
        <Routes>
          <Route path="/cases/:caseId/results" element={<ResultsPage />} />
          <Route path="/cases" element={<div>Liste des dossiers</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Story F4.6 - Chronologie unifiée des faits techniques', () => {
  let originalFetch: typeof globalThis.fetch
  let observationRequests: URL[]
  let timelineSimulation: string | null

  beforeEach(() => {
    setAccessToken('mock-valid-token')
    setSessionUser({ userName: 'Analyste Forensique', role: 'analyst' })
    resetMockCases()
    resetMockH1Decisions()
    resetMockRunSupervision()

    observationRequests = []
    timelineSimulation = null
    originalFetch = globalThis.fetch
    globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
      const captured = input instanceof Request ? input.clone() : new Request(input, init)
      const url = new URL(captured.url)
      if (url.pathname.includes('/observations')) observationRequests.push(url)

      if (timelineSimulation && url.pathname.includes('/observations')) {
        const headers = new Headers(captured.headers)
        headers.set('X-Simulation-Timeline', timelineSimulation)
        return originalFetch(new Request(captured, { headers }))
      }
      return originalFetch(input, init)
    }) as typeof fetch
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    server.resetHandlers()
    clearAccessToken()
  })

  it('affiche un seul bloc de 100 événements UTC avec source désactivée et aucun stockage local', async () => {
    renderResultsPage()

    expect(await screen.findByTestId('timeline-list')).toBeInTheDocument()
    expect(screen.getAllByTestId('timeline-event-row')).toHaveLength(TIMELINE_PAGE_SIZE)
    expect(screen.getAllByRole('tab')).toHaveLength(1)
    expect(screen.getByRole('tab')).toHaveTextContent('Chronologie')

    const firstDate = screen.getAllByTestId('timeline-event-date')[0]!
    expect(firstDate).toHaveClass('font-mono')
    expect(firstDate).toHaveTextContent(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC$/)

    const firstSource = screen.getAllByTestId('timeline-source-label')[0]!
    expect(firstSource).toHaveTextContent(/Security\.evtx · evt-001 · ligne 1/)
    expect(screen.getAllByTestId('timeline-source-chip')[0]).toBeEnabled()
    expect(screen.getAllByTestId('timeline-event-open')[0]).toBeEnabled()
    expect(screen.getByTestId('source-panel-placeholder')).toHaveTextContent(
      'Panneau « Source » actif',
    )
    expect(screen.queryByTestId('source-detail-drawer')).not.toBeInTheDocument()

    expect(observationRequests).toHaveLength(1)
    expect(observationRequests[0]!.searchParams.get('limit')).toBe('100')
    expect(observationRequests[0]!.searchParams.get('offset')).toBe('0')
    expect(window.localStorage.length).toBe(0)
    expect(window.sessionStorage.length).toBe(0)
  })

  it('charge le bloc suivant côté serveur sans jamais accumuler plus de 100 événements', async () => {
    const user = userEvent.setup()
    renderResultsPage()

    expect(await screen.findByTestId('timeline-list')).toBeInTheDocument()
    expect(screen.getAllByTestId('timeline-event-row')).toHaveLength(TIMELINE_PAGE_SIZE)

    await user.click(screen.getByTestId('timeline-next-block'))

    await waitFor(() =>
      expect(screen.getByTestId('timeline-page-label')).toHaveTextContent('Bloc 2'),
    )
    expect(screen.getAllByTestId('timeline-event-row')).toHaveLength(TIMELINE_PAGE_SIZE)
    expect(observationRequests).toHaveLength(2)
    expect(observationRequests[1]!.searchParams.get('limit')).toBe('100')
    expect(observationRequests[1]!.searchParams.get('offset')).toBe('100')
    expect(observationRequests.every((url) => url.searchParams.get('limit') === '100')).toBe(true)

    await user.click(screen.getByTestId('timeline-previous-block'))
    await waitFor(() =>
      expect(screen.getByTestId('timeline-page-label')).toHaveTextContent('Bloc 1'),
    )
    expect(observationRequests).toHaveLength(3)
    expect(observationRequests[2]!.searchParams.get('offset')).toBe('0')
    expect(screen.getAllByTestId('timeline-event-row')).toHaveLength(TIMELINE_PAGE_SIZE)
  })

  it('transmet les filtres de source et de plage UTC au serveur et les maintient entre les blocs', async () => {
    const user = userEvent.setup()
    renderResultsPage()

    expect(await screen.findByTestId('timeline-list')).toBeInTheDocument()

    fireEvent.change(screen.getByTestId('timeline-source-filter'), {
      target: { value: 'evi-001' },
    })
    fireEvent.change(screen.getByTestId('timeline-start-filter'), {
      target: { value: '2026-11-20T09:00' },
    })
    fireEvent.change(screen.getByTestId('timeline-end-filter'), {
      target: { value: '2026-11-20T09:30' },
    })
    await user.click(screen.getByTestId('timeline-apply-filters'))

    await waitFor(() => expect(observationRequests).toHaveLength(2))
    expect(observationRequests[1]!.searchParams.get('source_id')).toBe('evi-001')
    expect(observationRequests[1]!.searchParams.get('start_date')).toBe('2026-11-20T09:00:00Z')
    expect(observationRequests[1]!.searchParams.get('end_date')).toBe('2026-11-20T09:30:00Z')
    expect(observationRequests[1]!.searchParams.get('offset')).toBe('0')

    // La liste filtrée est revenue après la transition avant de changer de bloc.
    await waitFor(() => expect(screen.getByTestId('timeline-next-block')).toBeEnabled())
    await user.click(screen.getByTestId('timeline-next-block'))
    await waitFor(() => expect(observationRequests).toHaveLength(3))
    expect(observationRequests[2]!.searchParams.get('source_id')).toBe('evi-001')
    expect(observationRequests[2]!.searchParams.get('start_date')).toBe('2026-11-20T09:00:00Z')
    expect(observationRequests[2]!.searchParams.get('end_date')).toBe('2026-11-20T09:30:00Z')
    expect(observationRequests[2]!.searchParams.get('offset')).toBe('100')
    expect(screen.getAllByTestId('timeline-event-row').length).toBeLessThanOrEqual(
      TIMELINE_PAGE_SIZE,
    )
  })

  it('affiche l’état vide avec réinitialisation des filtres', async () => {
    renderResultsPage('case-timeline-empty')

    expect(await screen.findByTestId('timeline-empty-state')).toBeInTheDocument()
    expect(screen.getByText('Aucun événement chronologique.')).toBeInTheDocument()
    expect(
      screen.getByText('Aucun événement chronologique ne correspond aux critères sélectionnés.'),
    ).toBeInTheDocument()
    expect(screen.getByTestId('timeline-empty-reset')).toHaveTextContent(
      'Réinitialiser les filtres',
    )
  })

  it('affiche l’erreur avec Réessayer et rejoue la même tranche', async () => {
    const user = userEvent.setup()
    renderResultsPage('case-timeline-error')

    expect(await screen.findByTestId('timeline-error-state')).toBeInTheDocument()
    expect(screen.getByTestId('timeline-retry-button')).toHaveTextContent('Réessayer')

    await user.click(screen.getByTestId('timeline-retry-button'))

    await waitFor(() => expect(observationRequests).toHaveLength(2))
    expect(observationRequests[1]!.searchParams.get('offset')).toBe('0')
  })

  it('masque la chronologie en cas d’accès refusé (403)', async () => {
    renderResultsPage('case-timeline-forbidden')

    expect(await screen.findByTestId('timeline-forbidden-state')).toBeInTheDocument()
    expect(screen.queryByTestId('timeline-list')).not.toBeInTheDocument()
    expect(screen.getByTestId('timeline-forbidden-back')).toHaveAttribute('href', '/cases')
  })

  it('affiche le bandeau de résultats partiels signalé par une phase failed du contrat', async () => {
    renderResultsPage('case-results-partial')

    expect(await screen.findByTestId('timeline-partial-banner')).toBeInTheDocument()
    expect(screen.getByTestId('timeline-partial-message')).toHaveTextContent('RÉSULTATS PARTIELS')
    expect(screen.getByTestId('timeline-partial-message')).toHaveTextContent('executor')
  })

  it('restitue un statut inconnu avec son code brut sans bloquer la chronologie', async () => {
    renderResultsPage('case-timeline-unknown')

    expect(await screen.findByTestId('timeline-unknown-state')).toHaveTextContent(
      'État inconnu (unrecognized_state_code)',
    )
    expect(await screen.findByTestId('timeline-list')).toBeInTheDocument()
  })

  it('simule la route de détail d’observation pour le futur panneau Source (F4.7)', async () => {
    const { data, response } = await apiClient.GET(
      '/api/v1/cases/{case_id}/observations/{observation_id}',
      {
        params: {
          path: { case_id: 'case-001', observation_id: 'case-001-obs-001' },
        },
      },
    )

    expect(response.status).toBe(200)
    expect(data).toMatchObject({
      id: 'case-001-obs-001',
      case_id: 'case-001',
      tool_name: 'Analyseur EVTX',
      source_id: 'evi-001',
    })
    expect(window.localStorage.length).toBe(0)
    expect(window.sessionStorage.length).toBe(0)
  })

  it('affiche des squelettes linéaires pendant la transition de bloc', async () => {
    const user = userEvent.setup()
    let deferResponse = false
    const deferred: { release: (() => void) | null } = { release: null }

    const emptyResponse = () =>
      HttpResponse.json({
        items: [],
        total: 0,
        total_items: 0,
        limit: TIMELINE_PAGE_SIZE,
        offset: 0,
        has_more: false,
      })

    server.use(
      http.get('*/api/v1/cases/:caseId/observations', () =>
        deferResponse
          ? new Promise((resolve) => {
              deferred.release = () => resolve(emptyResponse())
            })
          : emptyResponse(),
      ),
    )

    renderResultsPage('case-timeline-empty')
    expect(await screen.findByTestId('timeline-empty-state')).toBeInTheDocument()

    // La transition est pilotée par l'état de la requête, sans délai arbitraire.
    deferResponse = true
    await user.click(screen.getByTestId('timeline-empty-reset'))
    expect(await screen.findByTestId('timeline-loading')).toBeInTheDocument()

    deferred.release?.()
    deferred.release = null
    await waitFor(() => expect(screen.queryByTestId('timeline-loading')).not.toBeInTheDocument())
  })
})
