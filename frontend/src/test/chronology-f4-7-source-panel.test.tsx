import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { clearAccessToken, setAccessToken, setSessionUser } from '../api/auth-memory'
import { buildSourceDownloadUrl } from '../features/results'
import { ResultsPage } from '../pages/ResultsPage'
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

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="current-path">{location.pathname}</div>
}

function renderResultsPage(caseId = 'case-001') {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <MemoryRouter initialEntries={[`/cases/${caseId}/results`]}>
        <LocationProbe />
        <Routes>
          <Route path="/cases/:caseId/results" element={<ResultsPage />} />
          <Route path="/cases" element={<div>Liste des dossiers</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Story F4.7 - Panneau latéral d’inspection de la source', () => {
  let originalFetch: typeof globalThis.fetch
  let detailRequests: URL[]
  let sourceSimulation: string | null
  let clipboardWriteText: ReturnType<typeof vi.fn>
  let originalClipboard: PropertyDescriptor | undefined
  let storageSetItem: ReturnType<typeof vi.spyOn>
  // `delay: null` évite les frappes userEvent en attente sous la charge parallèle.
  let user: ReturnType<typeof userEvent.setup>

  beforeEach(() => {
    user = userEvent.setup({ delay: null })
    setAccessToken('mock-valid-token')
    setSessionUser({ userName: 'Analyste Forensique', role: 'analyst' })
    resetMockCases()
    resetMockH1Decisions()
    resetMockRunSupervision()

    detailRequests = []
    sourceSimulation = null
    originalFetch = globalThis.fetch
    globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
      const captured = input instanceof Request ? input.clone() : new Request(input, init)
      const url = new URL(captured.url)
      if (/\/observations\/[^/]+$/.test(url.pathname)) {
        detailRequests.push(url)
        if (sourceSimulation) {
          const headers = new Headers(captured.headers)
          headers.set('X-Simulation-Source', sourceSimulation)
          return originalFetch(new Request(captured, { headers }))
        }
      }
      return originalFetch(input, init)
    }) as typeof fetch

    originalClipboard = Object.getOwnPropertyDescriptor(navigator, 'clipboard')
    clipboardWriteText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: clipboardWriteText },
      configurable: true,
      writable: true,
    })
    storageSetItem = vi.spyOn(Storage.prototype, 'setItem')
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    if (originalClipboard) {
      Object.defineProperty(navigator, 'clipboard', originalClipboard)
    } else {
      Reflect.deleteProperty(navigator, 'clipboard')
    }
    vi.restoreAllMocks()
    server.resetHandlers()
    clearAccessToken()
  })

  async function openFirstSource(simulation: string | null = null) {
    renderResultsPage()
    expect(await screen.findByTestId('timeline-list')).toBeInTheDocument()
    sourceSimulation = simulation
    const origin = screen.getAllByTestId('timeline-source-chip')[0] as HTMLButtonElement
    await user.click(origin)
    return origin
  }

  it('ouvre le tiroir depuis la source sans quitter la chronologie et restaure le focus', async () => {
    const origin = await openFirstSource()

    const drawer = await screen.findByTestId('source-detail-drawer')
    expect(drawer).toBeInTheDocument()
    expect(screen.getByTestId('current-path')).toHaveTextContent('/cases/case-001/results')
    expect(screen.getByTestId('timeline-list')).toBeInTheDocument()
    expect(screen.getByTestId('source-drawer-close')).toHaveFocus()

    expect(within(drawer).getByTestId('source-file-name')).toHaveTextContent('Security.evtx')
    expect(within(drawer).getByTestId('source-event-identifier')).toHaveTextContent('evt-001')
    expect(within(drawer).getByTestId('source-line')).toHaveTextContent('1')
    expect(within(drawer).getByTestId('source-raw-excerpt')).toHaveClass('font-mono')
    expect(within(drawer).getByTestId('source-confidentiality-note')).toHaveTextContent(
      'Original conservé en local. Aucun contenu original transmis.',
    )
    expect(within(drawer).getByTestId('source-proof-fingerprint')).toHaveTextContent(/…$/)
    expect(storageSetItem).not.toHaveBeenCalled()
    expect(window.localStorage.length).toBe(0)
    expect(window.sessionStorage.length).toBe(0)

    await user.click(within(drawer).getByTestId('source-copy-proof'))
    await waitFor(() => expect(clipboardWriteText).toHaveBeenCalledTimes(1))
    expect(clipboardWriteText).toHaveBeenCalledWith('01'.repeat(32))

    await user.click(within(drawer).getByTestId('source-drawer-close'))
    await waitFor(() =>
      expect(screen.queryByTestId('source-detail-drawer')).not.toBeInTheDocument(),
    )
    expect(origin).toHaveFocus()
    expect(detailRequests).toHaveLength(1)
  })

  it('ouvre aussi le tiroir depuis la ligne d’événement et ferme avec Échap', async () => {
    renderResultsPage()
    expect(await screen.findByTestId('timeline-list')).toBeInTheDocument()
    const origin = screen.getAllByTestId('timeline-event-open')[0] as HTMLButtonElement

    await user.click(origin)
    expect(await screen.findByTestId('source-detail-drawer')).toBeInTheDocument()

    await userEvent.keyboard('{Escape}')
    await waitFor(() =>
      expect(screen.queryByTestId('source-detail-drawer')).not.toBeInTheDocument(),
    )
    expect(origin).toHaveFocus()
  })

  it('affiche immédiatement un squelette pendant le chargement du détail', async () => {
    await openFirstSource('loading')

    expect(await screen.findByTestId('source-drawer-loading')).toBeInTheDocument()
    expect(screen.queryByTestId('source-raw-excerpt')).not.toBeInTheDocument()
    expect(
      await screen.findByTestId('source-raw-excerpt', {}, { timeout: 2000 }),
    ).toBeInTheDocument()
  })

  it('affiche le message dédié quand aucun texte complémentaire existe', async () => {
    await openFirstSource('empty')

    expect(await screen.findByTestId('source-empty-message')).toHaveTextContent(
      'Aucun détail textuel supplémentaire pour cette observation',
    )
  })

  it('affiche une erreur avec motif technique et permet de réessayer', async () => {
    await openFirstSource('error')

    const errorBlock = await screen.findByTestId('source-drawer-error')
    expect(errorBlock).toHaveTextContent('Données de source indisponibles')
    expect(within(errorBlock).getByTestId('source-error-reason')).toHaveTextContent(
      'Erreur interne lors de la récupération de l’observation.',
    )

    sourceSimulation = null
    await user.click(within(errorBlock).getByTestId('source-drawer-retry'))
    expect(await screen.findByTestId('source-raw-excerpt')).toBeInTheDocument()
    expect(detailRequests).toHaveLength(2)
  })

  it('affiche une interdiction de consultation sur 403 sans exposer l’extrait', async () => {
    await openFirstSource('forbidden')

    const forbidden = await screen.findByTestId('source-drawer-forbidden')
    expect(forbidden).toHaveTextContent('Consultation de la source interdite.')
    expect(screen.queryByTestId('source-raw-excerpt')).not.toBeInTheDocument()
  })

  it('affiche un message neutre sur 404', async () => {
    await openFirstSource('not-found')

    expect(await screen.findByTestId('source-drawer-not-found')).toHaveTextContent(
      'Source introuvable.',
    )
  })

  it('signale un statut inconnu et désactive les actions dépendantes', async () => {
    await openFirstSource('unknown-status')

    expect(await screen.findByTestId('source-unknown-status')).toHaveTextContent(
      'État inconnu (etat_non_reconnu)',
    )
    expect(screen.getByTestId('source-copy-excerpt')).toBeDisabled()
    expect(screen.getByTestId('source-copy-proof')).toBeDisabled()
    expect(screen.getByTestId('source-download-full')).toHaveAttribute('aria-disabled', 'true')
  })

  it('tronque à 500 lignes avec bannière et téléchargement direct sans charger le contenu intégral', async () => {
    await openFirstSource('truncated')

    const banner = await screen.findByTestId('source-truncation-banner')
    expect(within(banner).getByTestId('source-truncation-message')).toHaveTextContent(
      'Extrait tronqué à 500 lignes / 64 Ko',
    )
    const download = within(banner).getByTestId('source-download-full')
    expect(download).toHaveTextContent("Télécharger l'extrait complet")
    expect(download).toHaveAttribute('download')
    expect(download).toHaveAttribute('href', buildSourceDownloadUrl('case-001', 'case-001-obs-001'))

    const preview = screen.getByTestId('source-raw-excerpt')
    expect(preview.textContent?.split('\n')).toHaveLength(500)
    expect(preview).not.toHaveTextContent('ligne 501')

    // L'affichage ne charge jamais le contenu intégral : seul le lien direct le demandera.
    expect(detailRequests).toHaveLength(1)
    expect(detailRequests[0]?.searchParams.get('download')).toBeNull()
  })

  it('ne journalise aucun contenu d’extrait forensique', async () => {
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => undefined)
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined)

    await openFirstSource()
    expect(await screen.findByTestId('source-raw-excerpt')).toBeInTheDocument()

    const logged = [...logSpy.mock.calls, ...errorSpy.mock.calls]
      .map((call) => call.map(String).join(' '))
      .join('\n')
    expect(logged).not.toContain('fait technique')
    expect(logged).not.toContain('Security.evtx')
  })
}, 15000)
