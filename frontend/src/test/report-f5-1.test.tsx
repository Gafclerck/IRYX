import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { clearAccessToken, setAccessToken } from '../api/auth-memory'
import { ReportPage } from '../pages/ReportPage'
import { MOCK_REPORT_CONTENT, resetMockReport } from './mocks/handlers'
import { server } from './mocks/server'

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0, gcTime: 0 },
      mutations: { retry: false },
    },
  })
}

function renderReportPage(caseId = 'case-001') {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <MemoryRouter initialEntries={[`/cases/${caseId}/report`]}>
        <Routes>
          <Route path="/cases/:caseId/report" element={<ReportPage pollIntervalMs={10} />} />
          <Route path="/cases" element={<div>Liste des dossiers</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Story F5.1 - Compilation et visualisation du rapport', () => {
  let originalFetch: typeof globalThis.fetch
  let simulation: string | null
  let taskSimulation: string | null
  let reportRequests: { readonly method: string; readonly pathname: string }[]
  let storageSetItem: ReturnType<typeof vi.spyOn>
  let user: ReturnType<typeof userEvent.setup>

  beforeEach(() => {
    user = userEvent.setup({ delay: null })
    setAccessToken('mock-valid-token')
    resetMockReport()

    simulation = null
    taskSimulation = null
    reportRequests = []
    originalFetch = globalThis.fetch
    globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
      const captured = input instanceof Request ? input.clone() : new Request(input, init)
      const url = new URL(captured.url)
      const isReportRoute = url.pathname.includes('/report') || url.pathname.includes('/tasks/')
      const isFindingsRoute = url.pathname.includes('/findings')

      if (isReportRoute) {
        reportRequests.push({ method: captured.method, pathname: url.pathname })
        const headerValue = url.pathname.includes('/tasks/')
          ? (taskSimulation ?? simulation)
          : simulation
        if (headerValue) {
          const headers = new Headers(captured.headers)
          headers.set('X-Simulation-Report', headerValue)
          return originalFetch(new Request(captured, { headers }))
        }
      }
      if (isFindingsRoute) {
        const headers = new Headers(captured.headers)
        headers.set(
          'X-Simulation-Findings',
          simulation === 'forbidden' ? 'forbidden' : 'has-validated',
        )
        return originalFetch(new Request(captured, { headers }))
      }
      return originalFetch(input, init)
    }) as typeof fetch

    storageSetItem = vi.spyOn(Storage.prototype, 'setItem')
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
    server.resetHandlers()
    resetMockReport()
    clearAccessToken()
  })

  it("affiche l'état vide avec un bouton Générer actif, demande la compilation au back et restitue le document reçu", async () => {
    renderReportPage()

    expect(await screen.findByTestId('report-empty-state')).toBeInTheDocument()
    const generateButton = screen.getByTestId('report-generate-button')
    expect(generateButton).toBeEnabled()
    expect(generateButton).toHaveTextContent('Générer le rapport')

    await user.click(generateButton)
    simulation = 'ready'

    expect(await screen.findByTestId('report-generating-state')).toHaveTextContent(
      'Compilation et scellement du rapport en cours...',
    )
    const preview = await screen.findByTestId('report-preview')
    const content = within(preview).getByTestId('report-content')
    expect(content.textContent).toBe(MOCK_REPORT_CONTENT)
    expect(preview).toHaveClass('bg-mist', 'text-ink')
    expect(content).toHaveClass('text-ink')

    expect(
      reportRequests.some(
        (request) => request.method === 'POST' && request.pathname.endsWith('/report/generate'),
      ),
    ).toBe(true)
    expect(storageSetItem).not.toHaveBeenCalled()
  })

  it('affiche les huit chapitres tels que renvoyés et signale les findings non validés sans masquer la prévisualisation', async () => {
    simulation = 'no-findings'
    renderReportPage()

    const preview = await screen.findByTestId('report-preview')
    const content = within(preview).getByTestId('report-content')
    const text = content.textContent ?? ''
    expect(text.match(/^## /gm)).toHaveLength(8)
    expect(text).toContain('Aucun finding validé en porte H2.')
    expect(screen.getByTestId('report-read-only-note')).toHaveTextContent(
      'Aucune modification côté front (DP-03)',
    )
    expect(screen.getByTestId('report-h2-h3-gap-note')).toHaveTextContent(
      "Porte H2 reflétée depuis l'état reçu du serveur (F4.8)",
    )
  })

  it('affiche le motif de la compilation en échec et permet de réessayer', async () => {
    renderReportPage()
    await screen.findByTestId('report-empty-state')
    taskSimulation = 'generation-failed'

    await user.click(screen.getByTestId('report-generate-button'))

    const failure = await screen.findByTestId('report-generation-failed')
    expect(within(failure).getByTestId('report-failure-detail')).toHaveTextContent(
      'Le service de compilation du rapport a signalé une erreur interne.',
    )
    expect(within(failure).getByTestId('report-retry-generation')).toHaveTextContent(
      'Réessayer la compilation',
    )
  })

  it('masque le rapport en cas accès refusé (403)', async () => {
    simulation = 'forbidden'
    renderReportPage()

    expect(await screen.findByTestId('report-forbidden-state')).toBeInTheDocument()
    expect(screen.queryByTestId('report-preview')).not.toBeInTheDocument()
    expect(screen.getByTestId('report-generate-button')).toBeDisabled()
  })

  it('affiche une erreur serveur avec une action Réessayer', async () => {
    simulation = 'server-error'
    renderReportPage()

    const error = await screen.findByTestId('report-error-state')
    expect(within(error).getByTestId('report-error-message')).toHaveTextContent(
      'Échec de la consultation du rapport.',
    )
    expect(within(error).getByTestId('report-retry')).toHaveTextContent('Réessayer')
  })

  it('arrête la scrutation après une coupure prolongée (DP-05) et propose Réessayer la connexion', async () => {
    renderReportPage()
    await screen.findByTestId('report-empty-state')
    taskSimulation = 'network-error'

    await user.click(screen.getByTestId('report-generate-button'))

    const cutoff = await screen.findByTestId('report-network-cutoff', {}, { timeout: 3000 })
    expect(within(cutoff).getByTestId('report-retry-connection')).toHaveTextContent(
      'Réessayer la connexion',
    )

    const attempts = reportRequests.filter((request) => request.pathname.includes('/tasks/')).length
    expect(attempts).toBeGreaterThanOrEqual(3)
    await new Promise((resolve) => setTimeout(resolve, 80))
    const attemptsAfterWait = reportRequests.filter((request) =>
      request.pathname.includes('/tasks/'),
    ).length
    expect(attemptsAfterWait).toBe(attempts)
  })

  it('restitue un statut non répertorié avec son code brut et désactive la génération', async () => {
    renderReportPage()
    await screen.findByTestId('report-empty-state')
    taskSimulation = 'unknown-status'

    await user.click(screen.getByTestId('report-generate-button'))

    const unknown = await screen.findByTestId('report-unknown-state')
    expect(within(unknown).getByTestId('report-unknown-label')).toHaveTextContent(
      'État inconnu (unrecognized_state_code)',
    )
    expect(screen.getByTestId('report-generate-button')).toBeDisabled()
  })

  it('arrête toute scrutation au départ de la page', async () => {
    const view = renderReportPage()
    await screen.findByTestId('report-empty-state')

    await user.click(screen.getByTestId('report-generate-button'))
    await screen.findByTestId('report-generating-state')

    const attemptsBeforeUnmount = reportRequests.filter((request) =>
      request.pathname.includes('/tasks/'),
    ).length
    view.unmount()
    await new Promise((resolve) => setTimeout(resolve, 80))

    await waitFor(() => {
      expect(reportRequests.filter((request) => request.pathname.includes('/tasks/')).length).toBe(
        attemptsBeforeUnmount,
      )
    })
  })
})
