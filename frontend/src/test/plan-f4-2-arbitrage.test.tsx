import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from './mocks/server'
import { resetMockCases, resetMockH1Decisions, resetMockPlanPolling } from './mocks/handlers'
import { PlanPage } from '../pages/PlanPage'
import { clearAccessToken, setAccessToken, setSessionUser } from '../api/auth-memory'

const H1_ROUTE = '*/api/v1/cases/:caseId/investigations/:runId/gates/h1'

const SUCCESS_RESPONSE = {
  run_id: 'run-plan-001',
  case_id: 'case-001',
  status: 'running',
  current_phase: 'executor',
  decision: 'approve',
  message: 'Plan validé. Session d’exécution lancée.',
  phases: [],
}

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0, gcTime: 0 },
      mutations: { retry: false },
    },
  })
}

function renderPlanPage(caseId = 'case-001') {
  const queryClient = createTestQueryClient()
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/cases/${caseId}/plan`]}>
        <Routes>
          <Route path="/cases/:caseId/plan" element={<PlanPage />} />
          <Route path="/cases" element={<div>Liste des dossiers</div>} />
          <Route path="/cases/:caseId/run" element={<div>Console d’exécution</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Story F4.2 - Arbitrage et validation formelle de la porte H1', () => {
  let originalFetch: typeof globalThis.fetch
  let h1Requests: Request[]

  beforeEach(() => {
    setAccessToken('mock-valid-token')
    setSessionUser({ userName: 'Analyste Forensique', role: 'analyst' })
    resetMockCases()
    resetMockPlanPolling()
    resetMockH1Decisions()

    originalFetch = globalThis.fetch
    h1Requests = []
    globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
      const captured = input instanceof Request ? input.clone() : new Request(input, init)
      if (captured.method === 'POST' && captured.url.includes('/gates/h1')) {
        h1Requests.push(captured)
      }
      return originalFetch(input, init)
    }) as typeof fetch
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    server.resetHandlers()
    clearAccessToken()
  })

  async function waitForReadyPlan() {
    expect(await screen.findByTestId('plan-validate-button')).toBeEnabled()
  }

  it("n'envoie aucune validation sans confirmation et scelle le plan après accord explicite", async () => {
    const user = userEvent.setup()
    renderPlanPage()
    await waitForReadyPlan()

    await user.click(screen.getByTestId('plan-validate-button'))

    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(screen.getByTestId('plan-confirmation-summary')).toHaveTextContent(
      '3 étapes retenues seront soumises à la porte H1.',
    )
    // Aucun appel réseau tant que la confirmation explicite n'a pas été donnée.
    expect(h1Requests).toHaveLength(0)

    await user.click(screen.getByTestId('plan-decision-confirm'))

    await waitFor(() => expect(h1Requests).toHaveLength(1))
    const body = (await h1Requests[0]!.json()) as Record<string, unknown>
    expect(body).toMatchObject({ decision: 'approve', return_to_planner: false })

    expect(await screen.findByTestId('plan-validated-badge')).toHaveTextContent('Validé')
    expect(screen.getByTestId('plan-see-run-link')).toHaveAttribute('href', '/cases/case-001/run')
    expect(screen.queryByTestId('plan-validate-button')).not.toBeInTheDocument()
    expect(screen.queryByTestId('plan-refuse-button')).not.toBeInTheDocument()
    expect(screen.queryByTestId('plan-remove-step-1')).not.toBeInTheDocument()
    expect(window.localStorage.length).toBe(0)
    expect(window.sessionStorage.length).toBe(0)
  })

  it('impose un motif de refus valide (Zod, message français) puis passe en replanification', async () => {
    const user = userEvent.setup()
    renderPlanPage()
    await waitForReadyPlan()

    await user.click(screen.getByTestId('plan-refuse-button'))
    await user.click(screen.getByTestId('plan-decision-confirm'))

    expect(await screen.findByTestId('plan-reject-reason-error')).toHaveTextContent(
      'Le motif du refus est obligatoire.',
    )
    expect(h1Requests).toHaveLength(0)

    await user.type(
      screen.getByTestId('plan-reject-reason'),
      'Outil non pertinent pour les preuves disponibles.',
    )
    await user.click(screen.getByTestId('plan-decision-confirm'))

    await waitFor(() => expect(h1Requests).toHaveLength(1))
    const body = (await h1Requests[0]!.json()) as Record<string, unknown>
    expect(body).toMatchObject({
      decision: 'reject',
      feedback: 'Outil non pertinent pour les preuves disponibles.',
      return_to_planner: true,
    })

    expect(await screen.findByTestId('plan-replanification-view')).toHaveTextContent(
      /REPLANIFICATION EN COURS/,
    )
    expect(screen.queryByTestId('plan-validate-button')).not.toBeInTheDocument()
    expect(screen.queryByTestId('plan-refuse-button')).not.toBeInTheDocument()
    expect(window.localStorage.length).toBe(0)
    expect(window.sessionStorage.length).toBe(0)
  })

  it('transmet les étapes retenues après retrait unitaire, sans ajout', async () => {
    const user = userEvent.setup()
    renderPlanPage()
    await waitForReadyPlan()

    await user.click(screen.getByTestId('plan-remove-step-2'))

    expect(screen.queryByTestId('plan-step-2')).not.toBeInTheDocument()
    expect(screen.getByTestId('plan-step-1')).toBeInTheDocument()
    expect(screen.getByTestId('plan-step-3')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /ajouter une étape/i })).not.toBeInTheDocument()

    await user.click(screen.getByTestId('plan-validate-button'))
    expect(screen.getByTestId('plan-confirmation-summary')).toHaveTextContent(
      '2 étapes retenues seront soumises à la porte H1.',
    )
    await user.click(screen.getByTestId('plan-decision-confirm'))

    await waitFor(() => expect(h1Requests).toHaveLength(1))
    const body = (await h1Requests[0]!.json()) as {
      decision: string
      modified_plan: { steps: { step_id: number }[] }
    }
    expect(body.decision).toBe('modify')
    expect(body.modified_plan.steps.map((step) => step.step_id)).toEqual([1, 3])
  })

  it('désactive les actions pendant l’envoi et n’envoie qu’une seule validation', async () => {
    const user = userEvent.setup()
    let release: (() => void) | null = null
    server.use(
      http.post(H1_ROUTE, async () => {
        await new Promise<void>((resolve) => {
          release = resolve
        })
        return HttpResponse.json(SUCCESS_RESPONSE, { status: 200 })
      }),
    )

    renderPlanPage()
    await waitForReadyPlan()

    await user.click(screen.getByTestId('plan-validate-button'))
    await user.click(screen.getByTestId('plan-decision-confirm'))

    await waitFor(() => expect(h1Requests).toHaveLength(1))
    expect(screen.getByTestId('plan-submitting-badge')).toBeInTheDocument()
    expect(screen.getByTestId('plan-decision-confirm')).toBeDisabled()
    expect(screen.getByTestId('plan-validate-button')).toBeDisabled()
    expect(screen.getByTestId('plan-refuse-button')).toBeDisabled()
    expect(screen.getByTestId('plan-remove-step-1')).toBeDisabled()

    await user.click(screen.getByTestId('plan-decision-confirm'))
    expect(h1Requests).toHaveLength(1)

    expect(release).not.toBeNull()
    const resolveRequest = release as unknown as () => void
    resolveRequest()
    expect(await screen.findByTestId('plan-validated-badge')).toHaveTextContent('Validé')
    expect(h1Requests).toHaveLength(1)
  })

  it('garde le plan prêt sur erreur serveur et propose un Réessayer confirmé', async () => {
    const user = userEvent.setup()
    let attempts = 0
    server.use(
      http.post(H1_ROUTE, () => {
        attempts += 1
        if (attempts === 1) {
          return HttpResponse.json({ detail: 'Erreur interne du serveur.' }, { status: 500 })
        }
        return HttpResponse.json(SUCCESS_RESPONSE, { status: 200 })
      }),
    )

    renderPlanPage()
    await waitForReadyPlan()

    await user.click(screen.getByTestId('plan-validate-button'))
    await user.click(screen.getByTestId('plan-decision-confirm'))

    expect(await screen.findByTestId('plan-decision-error')).toHaveTextContent(
      /Erreur interne du serveur\./,
    )
    expect(screen.queryByTestId('plan-validated-badge')).not.toBeInTheDocument()
    expect(screen.getByTestId('plan-page-content')).toBeInTheDocument()
    expect(screen.getByTestId('plan-validate-button')).toBeEnabled()

    await user.click(screen.getByTestId('plan-decision-retry'))

    expect(await screen.findByTestId('plan-decision-dialog')).toBeInTheDocument()
    expect(h1Requests).toHaveLength(1)

    await user.click(screen.getByTestId('plan-decision-confirm'))
    await waitFor(() => expect(h1Requests).toHaveLength(2))
    expect(await screen.findByTestId('plan-validated-badge')).toHaveTextContent('Validé')
  })

  it('affiche l’état réel renvoyé sur 409 sans valider côté front', async () => {
    const user = userEvent.setup()
    renderPlanPage('case-h1-conflict')
    await waitForReadyPlan()

    await user.click(screen.getByTestId('plan-validate-button'))
    await user.click(screen.getByTestId('plan-decision-confirm'))

    expect(await screen.findByTestId('plan-conflict-view')).toBeInTheDocument()
    expect(screen.getByTestId('plan-conflict-status')).toHaveTextContent('TERMINÉ')
    expect(screen.getByTestId('plan-conflict-message')).toHaveTextContent(/déjà été validé/)
    expect(screen.queryByTestId('plan-validated-badge')).not.toBeInTheDocument()
    expect(screen.queryByTestId('plan-validate-button')).not.toBeInTheDocument()

    await user.click(screen.getByTestId('plan-conflict-refresh'))
    expect(await screen.findByTestId('plan-validated-badge')).toHaveTextContent('Validé')
  })

  it('masque les actions d’arbitrage pour un profil en consultation seule', async () => {
    setSessionUser({ userName: 'Observateur', role: 'viewer' })
    renderPlanPage()

    expect(await screen.findByTestId('plan-page-content')).toBeInTheDocument()
    expect(screen.queryByTestId('plan-validate-button')).not.toBeInTheDocument()
    expect(screen.queryByTestId('plan-refuse-button')).not.toBeInTheDocument()
    expect(screen.queryByTestId('plan-remove-step-1')).not.toBeInTheDocument()
    expect(h1Requests).toHaveLength(0)
  })

  it('restitue un statut inconnu avec son code brut sans bloquer l’arbitrage', async () => {
    server.use(
      http.get('*/api/v1/cases/:caseId/investigations', () =>
        HttpResponse.json(
          [
            {
              id: 'run-plan-001',
              case_id: 'case-001',
              status: 'unrecognized_state_code',
              current_phase: 'unrecognized_phase_code',
              validated_plan: null,
              iteration_count: 0,
              error_count: 0,
              started_at: '2026-11-20T09:00:00Z',
              updated_at: '2026-11-20T09:05:00Z',
            },
          ],
          { headers: { 'Retry-After': '3' } },
        ),
      ),
    )

    renderPlanPage()

    expect(await screen.findByTestId('plan-status-badge')).toHaveTextContent(
      'État inconnu (unrecognized_state_code)',
    )
    expect(await screen.findByTestId('plan-validate-button')).toBeEnabled()
  })
})
