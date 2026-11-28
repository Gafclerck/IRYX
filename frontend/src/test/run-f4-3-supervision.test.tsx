import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { render, renderHook, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from './mocks/server'
import {
  resetMockCases,
  resetMockH1Decisions,
  resetMockPlanPolling,
  resetMockRunSupervision,
} from './mocks/handlers'
import { clearAccessToken, setAccessToken, setSessionUser } from '../api/auth-memory'
import { RunPage } from '../pages/RunPage'
import { useRunSupervision } from '../features/run/hooks/useRunSupervision'

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0, gcTime: 0 },
      mutations: { retry: false },
    },
  })
}

function renderRunPage(caseId = 'case-001') {
  const queryClient = createTestQueryClient()
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/cases/${caseId}/run`]}>
        <Routes>
          <Route path="/cases/:caseId/run" element={<RunPage />} />
          <Route path="/cases/:caseId/results" element={<div>Résultats</div>} />
          <Route path="/cases" element={<div>Liste des dossiers</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function renderUseRunSupervision(caseId: string, pollIntervalMs = 5) {
  return renderHook(() => useRunSupervision({ caseId, pollIntervalMs }))
}

const AGENT_KEYS = ['planner', 'executor', 'analyst', 'verifier', 'correlator', 'reporter'] as const

describe('Story F4.3 - Console de supervision temps réel de l’orchestration', () => {
  let originalFetch: typeof globalThis.fetch
  let detailCalls: number
  let resumeCalls: number
  let cancellationRequests: Request[]

  beforeEach(() => {
    setAccessToken('mock-valid-token')
    setSessionUser({ userName: 'Analyste Forensique', role: 'analyst' })
    resetMockCases()
    resetMockPlanPolling()
    resetMockH1Decisions()
    resetMockRunSupervision()

    detailCalls = 0
    resumeCalls = 0
    cancellationRequests = []
    originalFetch = globalThis.fetch
    globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
      const captured = input instanceof Request ? input.clone() : new Request(input, init)
      const url = captured.url
      if (captured.method === 'GET' && url.includes('/investigations/') && !url.includes('/plan')) {
        detailCalls += 1
      }
      if (captured.method === 'POST' && url.includes('/resume')) resumeCalls += 1
      if (captured.method === 'POST' && (url.includes('/cancel') || url.includes('/control'))) {
        cancellationRequests.push(captured)
      }
      return originalFetch(input, init)
    }) as typeof fetch
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    server.resetHandlers()
    clearAccessToken()
  })

  it('affiche les cartes d’agents dérivées du contrat et un journal UTC mono en lecture seule', async () => {
    renderRunPage()

    expect(await screen.findByTestId('run-status-badge')).toHaveTextContent('EN COURS')
    for (const key of AGENT_KEYS) {
      expect(screen.getByTestId(`run-agent-card-${key}`)).toBeInTheDocument()
    }
    expect(screen.getByTestId('run-agent-status-planner')).toHaveTextContent('TERMINÉ')
    expect(screen.getByTestId('run-agent-elapsed-planner')).toHaveTextContent('2 min')
    expect(screen.getByTestId('run-agent-status-executor')).toHaveTextContent('EN COURS')
    expect(screen.getByTestId('run-agent-status-correlator')).toHaveTextContent('à réaligner')

    // Progression, dernier message et diagnostic absents du contrat : aucune valeur inventée.
    expect(screen.getByTestId('run-agent-progress-executor')).toHaveTextContent('à réaligner')
    expect(screen.getByTestId('run-agent-message-executor')).toHaveTextContent('à réaligner')

    const log = screen.getByTestId('run-activity-log')
    expect(log).toHaveClass('font-mono')
    expect(log).toHaveTextContent('Lecture seule')
    expect(screen.getByTestId('run-activity-entries')).toBeInTheDocument()
    expect(log).toHaveTextContent(/2026-11-20T09:02:00\.000Z \(UTC\)/)
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()

    // Commandes présentes ; pause sans route contractuelle désactivée.
    expect(screen.getByTestId('run-pause-button')).toBeDisabled()
    expect(screen.getByTestId('run-pause-button')).toHaveTextContent('à réaligner')
    expect(screen.getByTestId('run-resume-button')).toBeDisabled()
    expect(screen.getByTestId('run-cancel-button')).toBeEnabled()
    expect(window.localStorage.length).toBe(0)
    expect(window.sessionStorage.length).toBe(0)
  })

  it('affiche l’attente des agents et l’initialisation du flux quand aucune session n’existe', async () => {
    renderRunPage('case-plan-pending')

    expect(await screen.findByTestId('run-waiting-state')).toBeInTheDocument()
    expect(screen.getByTestId('run-activity-empty')).toHaveTextContent(
      "Initialisation du flux d'activité...",
    )
    for (const key of AGENT_KEYS) {
      expect(screen.getByTestId(`run-agent-status-${key}`)).toHaveTextContent('EN ATTENTE')
    }
  })

  it('signale un agent en échec sans interrompre les autres agents', async () => {
    renderRunPage('case-run-partial')

    expect(await screen.findByTestId('run-partial-failure-banner')).toBeInTheDocument()
    expect(screen.getByTestId('run-agent-failed-icon-executor')).toBeInTheDocument()
    expect(screen.getByTestId('run-agent-status-executor')).toHaveTextContent('ÉCHEC')
    expect(screen.getByTestId('run-agent-diagnostic-executor')).toHaveTextContent('à réaligner')
    const retryAgent = screen.getByTestId('run-agent-retry-executor')
    expect(retryAgent).toHaveTextContent('Réessayer cet agent')
    expect(retryAgent).toBeDisabled()
    expect(retryAgent).toHaveTextContent('à réaligner')
    expect(screen.getByTestId('run-agent-status-analyst')).toHaveTextContent('EN COURS')
  })

  it('arrête la scrutation à l’état terminé et met en avant les résultats', async () => {
    renderRunPage('case-run-completed')

    expect(await screen.findByTestId('run-status-badge')).toHaveTextContent('TERMINÉ')
    expect(screen.getByTestId('run-see-results-link')).toHaveTextContent('Voir les résultats')
    expect(screen.getByTestId('run-see-results-link')).toHaveAttribute(
      'href',
      '/cases/case-run-completed/results',
    )

    const callsAtTerminalState = detailCalls
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(detailCalls).toBe(callsAtTerminalState)
  })

  it('restitue une session annulée avec la mention « à réaligner »', async () => {
    renderRunPage('case-run-canceled')

    expect(await screen.findByTestId('run-status-badge')).toHaveTextContent('ANNULÉ')
    expect(screen.getByTestId('run-canceled-state')).toHaveTextContent('à réaligner')
  })

  it('appelle la route de reprise contractuelle uniquement depuis l’état en pause', async () => {
    const user = userEvent.setup()
    renderRunPage('case-run-paused')

    expect(await screen.findByTestId('run-status-badge')).toHaveTextContent('EN PAUSE')
    expect(screen.getByTestId('run-resume-button')).toBeEnabled()
    expect(screen.getByTestId('run-pause-button')).toBeDisabled()

    await user.click(screen.getByTestId('run-resume-button'))

    await waitFor(() => expect(resumeCalls).toBe(1))
    expect(await screen.findByTestId('run-status-badge')).toHaveTextContent('EN COURS')
    expect(screen.getByTestId('run-control-outcome')).toHaveTextContent('Session reprise.')
  })

  it("n'envoie aucune annulation sans confirmation explicite", async () => {
    const user = userEvent.setup()
    renderRunPage()

    expect(await screen.findByTestId('run-status-badge')).toHaveTextContent('EN COURS')
    await user.click(screen.getByTestId('run-cancel-button'))

    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('Confirmation explicite requise')
    expect(screen.getByTestId('run-cancel-summary')).toHaveTextContent(
      "Aucune annulation n'est transmise sans confirmation explicite.",
    )
    // Aucun appel réseau d'annulation/contrôle avant la confirmation.
    expect(cancellationRequests).toHaveLength(0)

    await user.click(screen.getByTestId('run-cancel-confirm'))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    // Le contrat ne déclare aucune route d'annulation : aucun appel n'est émis,
    // même après confirmation, et l'écart est signalé à l'utilisateur.
    expect(cancellationRequests).toHaveLength(0)
    expect(screen.getByTestId('run-control-outcome')).toHaveTextContent('à réaligner')
  })

  it('arrête la scrutation après une coupure prolongée (DP-05)', async () => {
    server.use(http.get('*/api/v1/cases/:caseId/investigations/:runId', () => HttpResponse.error()))

    const { result, unmount } = renderUseRunSupervision('case-001')

    await waitFor(() => expect(result.current.isNetworkCutoff).toBe(true), { timeout: 3000 })
    expect(result.current.state).toBe('networkCutoff')
    expect(result.current.errorMessage).toMatch(/DP-05/)
    unmount()
  })

  it('affiche l’erreur de consultation avec un bouton « Réessayer »', async () => {
    renderRunPage('case-run-error')

    expect(await screen.findByTestId('run-error-state')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Réessayer' })).toBeInTheDocument()
    expect(screen.getByTestId('run-retry-button')).toBeInTheDocument()
  })

  it('bloque l’accès refusé (403) puis redirige vers les dossiers', async () => {
    renderRunPage('case-forbidden')

    expect(await screen.findByTestId('run-forbidden-state')).toBeInTheDocument()
    expect(screen.getByTestId('run-forbidden-back-to-cases')).toHaveAttribute('href', '/cases')
    expect(await screen.findByText('Liste des dossiers', {}, { timeout: 2500 })).toBeInTheDocument()
  })

  it('restitue un statut inconnu avec son code brut sans activer les commandes', async () => {
    renderRunPage('case-run-unknown')

    expect(await screen.findByTestId('run-status-badge')).toHaveTextContent(
      'État inconnu (unrecognized_run_code)',
    )
    expect(screen.getByTestId('run-unknown-state')).toBeInTheDocument()
    expect(screen.queryByTestId('run-control-actions')).not.toBeInTheDocument()
  })

  it('arrête la scrutation à l’état terminal et au départ de la page', async () => {
    let localDetailCalls = 0
    server.use(
      http.get('*/api/v1/cases/:caseId/investigations/:runId', () => {
        localDetailCalls += 1
        return HttpResponse.json(
          {
            id: 'run-plan-001',
            case_id: 'case-001',
            status: 'completed',
            current_phase: 'reporting',
            validated_plan: {},
            iteration_count: 0,
            error_count: 0,
            started_at: '2026-11-20T09:00:00Z',
            updated_at: '2026-11-20T09:12:00Z',
            phases: [],
          },
          { headers: { 'Retry-After': '3' } },
        )
      }),
    )

    const { result, unmount } = renderUseRunSupervision('case-001')

    await waitFor(() => expect(result.current.state).toBe('completed'))
    const callsAtTerminalState = localDetailCalls
    await new Promise((resolve) => setTimeout(resolve, 40))
    expect(localDetailCalls).toBe(callsAtTerminalState)

    unmount()
    await new Promise((resolve) => setTimeout(resolve, 40))
    expect(localDetailCalls).toBe(callsAtTerminalState)
  })
})
