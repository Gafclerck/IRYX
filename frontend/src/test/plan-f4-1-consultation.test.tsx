import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, renderHook, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from './mocks/server'
import { resetMockCases, resetMockPlanPolling } from './mocks/handlers'
import { PlanPage } from '../pages/PlanPage'
import { usePlan } from '../features/plan/hooks/usePlan'
import { setAccessToken, clearAccessToken, setSessionUser } from '../api/auth-memory'

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
          <Route path="/cases/:caseId/evidence" element={<div>Registre des preuves</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return queryClient
}

function renderUsePlan(caseId: string, pollIntervalMs = 5) {
  const queryClient = createTestQueryClient()
  return renderHook(() => usePlan({ caseId, pollIntervalMs }), {
    wrapper: ({ children }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    ),
  })
}

describe('Story F4.1 - Consultation du plan proposé par le Planner', () => {
  beforeEach(() => {
    setAccessToken('mock-valid-token')
    setSessionUser({ userName: 'Analyste Forensique', role: 'analyst' })
    resetMockCases()
    resetMockPlanPolling()
  })

  afterEach(() => {
    server.resetHandlers()
    clearAccessToken()
    vi.useRealTimers()
  })

  it('affiche la liste ordonnée des étapes avec les libellés de consultation et les actions F4.2', async () => {
    renderPlanPage()

    expect(await screen.findByTestId('plan-page-content')).toBeInTheDocument()
    expect(screen.getByTestId('plan-step-list')).toBeInTheDocument()
    expect(screen.getByTestId('plan-step-number-1')).toHaveTextContent('1')
    expect(screen.getByTestId('plan-step-objective-1')).toHaveTextContent(
      /événements d’authentification/,
    )
    expect(screen.getByTestId('plan-step-agent-1')).toHaveTextContent('à réaligner')
    expect(screen.getByTestId('plan-step-tool-1')).toHaveTextContent('Analyseur EVTX')
    expect(screen.getByTestId('plan-step-evidence-1')).toHaveTextContent('evi-001')
    expect(screen.getByTestId('plan-step-number-3')).toHaveTextContent('3')
    expect(screen.getByText('Pour consultation')).toBeInTheDocument()

    // Les actions d'arbitrage appartiennent désormais à F4.2 : leurs boutons ouvrent
    // un dialogue de confirmation et ne transmettent jamais directement la décision.
    expect(screen.queryByTestId('plan-decision-dialog')).not.toBeInTheDocument()
    expect(screen.getByTestId('plan-validate-button')).toHaveTextContent('Valider et lancer')
    expect(screen.getByTestId('plan-refuse-button')).toHaveTextContent('Refuser le plan')
    expect(screen.queryByRole('button', { name: /ajouter une étape/i })).not.toBeInTheDocument()
  })

  it('affiche l’attente de planification tant que le plan n’est pas disponible', async () => {
    server.use(
      http.get('*/api/v1/cases/:caseId/investigations/:runId/plan', () =>
        HttpResponse.json(
          {
            detail: 'Le plan est en cours d’élaboration par le Planner.',
            code: 'PLAN_NOT_FOUND',
          },
          { status: 404, headers: { 'Retry-After': '3' } },
        ),
      ),
    )

    renderPlanPage()

    expect(await screen.findByTestId('plan-planning-state')).toBeInTheDocument()
    expect(screen.getByText('Planification en cours')).toBeInTheDocument()
    expect(screen.getByText(/Élaboration du plan par le Planner en cours/)).toBeInTheDocument()
  })

  it('affiche l’état vide avec un retour vers les preuves', async () => {
    renderPlanPage('case-plan-empty')

    expect(await screen.findByTestId('plan-empty-state')).toBeInTheDocument()
    expect(screen.getByText('Aucun outil applicable')).toBeInTheDocument()
    expect(
      screen.getByText('Aucun outil forensique applicable aux preuves disponibles.'),
    ).toBeInTheDocument()
    expect(screen.getByTestId('plan-empty-back-to-evidence')).toHaveAttribute(
      'href',
      '/cases/case-plan-empty/evidence',
    )
  })

  it('affiche un plan validé en lecture seule avec la mention Validé', async () => {
    renderPlanPage('case-plan-validated')

    expect(await screen.findByTestId('plan-validated-badge')).toHaveTextContent('Validé')
    expect(screen.getByTestId('plan-page-content')).toBeInTheDocument()
    expect(screen.getByText('Lecture seule')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /valider|rejeter/i })).not.toBeInTheDocument()
  })

  it('affiche l’erreur de l’agent Planner avec l’action de reprise', async () => {
    renderPlanPage('case-plan-error')

    expect(await screen.findByTestId('plan-error-state')).toBeInTheDocument()
    expect(screen.getByText(/Échec de l’agent Planner/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Réessayer la planification' })).toBeInTheDocument()
    expect(screen.getByText('Réessayer')).toBeInTheDocument()
  })

  it('bloque l’accès refusé (403) et propose le retour aux dossiers', async () => {
    renderPlanPage('case-plan-forbidden')

    expect(await screen.findByTestId('plan-forbidden-state')).toBeInTheDocument()
    expect(screen.getByText('Accès refusé')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Retour aux dossiers/i })).toHaveAttribute(
      'href',
      '/cases',
    )
  })

  it('restitue un statut inconnu sans bloquer la consultation du plan', async () => {
    renderPlanPage('case-plan-unknown')

    expect(await screen.findByTestId('plan-page-content')).toBeInTheDocument()
    expect(screen.getByTestId('plan-status-badge')).toHaveTextContent(
      'État inconnu (unrecognized_state_code)',
    )
    expect(screen.getByTestId('plan-step-list')).toBeInTheDocument()
  })

  it('arrête la scrutation après une coupure prolongée (DP-05)', async () => {
    server.use(
      http.get('*/api/v1/cases/:caseId/investigations/:runId/plan', () => HttpResponse.error()),
    )

    const { result } = renderUsePlan('case-001')

    await waitFor(() => expect(result.current.isNetworkCutoff).toBe(true), { timeout: 3000 })
    expect(result.current.state).toBe('error')
    expect(result.current.errorMessage).toMatch(/DP-05/)
  })

  it('arrête la scrutation à l’état terminal et au départ de la page', async () => {
    let planCalls = 0
    server.use(
      http.get('*/api/v1/cases/:caseId/investigations/:runId/plan', () => {
        planCalls += 1
        return HttpResponse.json(
          {
            steps: [
              {
                step_id: 1,
                tool_name: 'Analyseur EVTX',
                target_evidence_id: 'evi-001',
                rationale: 'Objectif',
              },
            ],
            summary: '',
          },
          { headers: { 'Retry-After': '3' } },
        )
      }),
    )

    const { result, unmount } = renderUsePlan('case-001')

    await waitFor(() => expect(result.current.state).toBe('ready'))
    const callsAtTerminalState = planCalls
    await new Promise((resolve) => setTimeout(resolve, 40))
    expect(planCalls).toBe(callsAtTerminalState)

    unmount()
    expect(planCalls).toBe(callsAtTerminalState)
  })
})
