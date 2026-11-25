import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { clearAccessToken, setAccessToken } from '../api/auth-memory'
import { ReviewPage } from '../pages/ReviewPage'
import { server } from './mocks/server'

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0, gcTime: 0 },
      mutations: { retry: false },
    },
  })
}

function renderReviewPage(caseId = 'case-001') {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <MemoryRouter initialEntries={[`/cases/${caseId}/review`]}>
        <Routes>
          <Route path="/cases/:caseId/review" element={<ReviewPage />} />
          <Route path="/cases" element={<div>Liste des dossiers</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Story F4.8 - Arbitrage qualitatif des findings en porte H2', () => {
  let originalFetch: typeof globalThis.fetch
  let simulation: string | null
  let decisionRequests: { method: string; pathname: string }[]

  beforeEach(() => {
    setAccessToken('mock-valid-token')
    simulation = null
    decisionRequests = []
    originalFetch = globalThis.fetch
    globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
      const captured = input instanceof Request ? input.clone() : new Request(input, init)
      const url = new URL(captured.url)
      if (url.pathname.includes('/findings')) {
        if (captured.method !== 'GET')
          decisionRequests.push({ method: captured.method, pathname: url.pathname })
        if (simulation) {
          const headers = new Headers(captured.headers)
          headers.set('X-Simulation-Findings', simulation)
          return originalFetch(new Request(captured, { headers }))
        }
      }
      return originalFetch(input, init)
    }) as typeof fetch
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
    server.resetHandlers()
    clearAccessToken()
  })

  it('affiche les findings, compteurs et garde le rapport bloqué sans finding validé', async () => {
    renderReviewPage()
    expect(await screen.findByTestId('review-findings-list')).toBeInTheDocument()
    expect(screen.getByTestId('review-count-validated')).toHaveTextContent('0')
    expect(screen.getByTestId('review-count-rejected')).toHaveTextContent('0')
    expect(screen.getByTestId('review-count-pending')).toHaveTextContent('2')
    const reportLink = screen.getByTestId('review-generate-report-link')
    expect(reportLink).toBeDisabled()
    expect(screen.getByTestId('review-report-blocked-note')).toHaveTextContent(
      'Le rapport reste indisponible tant qu’aucun finding n’est validé.',
    )
  })

  it("n'envoie aucune décision H2 sans clic explicite et actions désactivées à réaligner (E6)", async () => {
    renderReviewPage()
    await screen.findByTestId('review-findings-list')
    expect(screen.getByTestId('finding-validate-finding-001')).toBeDisabled()
    expect(screen.getByTestId('finding-reject-finding-001')).toBeDisabled()
    expect(screen.getByTestId('finding-comment-finding-001')).toBeDisabled()
    expect(screen.getAllByText(/à réaligner \(E6\)/i).length).toBeGreaterThan(0)
    expect(decisionRequests).toHaveLength(0)
  })

  it('rejeter exige un motif obligatoire en français et n’envoie rien sans contrat', async () => {
    renderReviewPage()
    await screen.findByTestId('review-findings-list')
    const rejectBtn = screen.getByTestId('finding-reject-finding-001')
    expect(rejectBtn).toBeDisabled()
    // Aucun clic possible sur bouton désactivé ; aucune décision envoyée.
    expect(decisionRequests).toHaveLength(0)
  })

  it('affiche état vide', async () => {
    simulation = 'empty'
    renderReviewPage()
    expect(await screen.findByTestId('review-empty-state')).toHaveTextContent(
      'Aucun finding à examiner.',
    )
  })

  it('affiche accès refusé 403', async () => {
    simulation = 'forbidden'
    renderReviewPage()
    expect(await screen.findByTestId('review-forbidden-state')).toBeInTheDocument()
  })

  it('affiche erreur serveur avec Réessayer', async () => {
    simulation = 'server-error'
    renderReviewPage()
    const err = await screen.findByTestId('review-error-state')
    expect(within(err).getByTestId('review-retry')).toHaveTextContent('Réessayer')
  })

  it('active le lien rapport uniquement quand un finding validé est reçu du serveur', async () => {
    simulation = 'has-validated'
    renderReviewPage()
    await screen.findByTestId('review-findings-list')
    expect(screen.getByTestId('review-count-validated')).toHaveTextContent('1')
    const reportLink = screen.getByTestId('review-generate-report-link')
    expect(reportLink).not.toBeDisabled()
    expect(reportLink).toHaveAttribute('href', '/cases/case-001/report')
  })

  it('affiche un statut inconnu sans bloquer la page', async () => {
    simulation = 'unknown-status'
    renderReviewPage()
    await screen.findByTestId('review-findings-list')
    expect(screen.getByTestId('finding-status-finding-001')).toHaveTextContent(
      'État inconnu (unrecognized_finding_state)',
    )
  })
})
