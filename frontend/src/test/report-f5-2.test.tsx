import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { clearAccessToken, setAccessToken } from '../api/auth-memory'
import { ReportPage } from '../pages/ReportPage'
import { MOCK_REPORT_CONTENT, resetMockReport } from './mocks/handlers'
import { server } from './mocks/server'

/** Valeur fournie par le back dans le test : le front ne la calcule jamais. */
const BACK_PROVIDED_FINGERPRINT = '0123456789abcdef'.repeat(4)
const BACK_PROVIDED_JSON_CONTENT = '{"rapport":"donnees transmises par le back-end"}'

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0, gcTime: 0 },
      mutations: { retry: false },
    },
  })
}

/** jsdom n'expose pas Blob.text() : lecture via FileReader, sans transformation. */
function readBlobAsText(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(reader.error)
    reader.readAsText(blob)
  })
}

function readBlobAsBytes(blob: Blob): Promise<Uint8Array> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(new Uint8Array(reader.result as ArrayBuffer))
    reader.onerror = () => reject(reader.error)
    reader.readAsArrayBuffer(blob)
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

describe('Story F5.2 - Téléchargement du rapport scellé', () => {
  let originalFetch: typeof globalThis.fetch
  let simulation: string | null
  let taskSimulation: string | null
  let createdBlobs: Blob[]
  let createdObjectUrls: string[]
  let clickedLinks: { readonly href: string; readonly download: string }[]
  let createObjectUrl: ReturnType<typeof vi.fn>
  let revokeObjectUrl: ReturnType<typeof vi.fn>
  let anchorClickSpy: ReturnType<typeof vi.spyOn>
  let user: ReturnType<typeof userEvent.setup>

  beforeEach(() => {
    user = userEvent.setup({ delay: null })
    setAccessToken('mock-valid-token')
    resetMockReport()
    simulation = null
    taskSimulation = null
    createdBlobs = []
    createdObjectUrls = []
    clickedLinks = []

    originalFetch = globalThis.fetch
    globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
      const captured = input instanceof Request ? input.clone() : new Request(input, init)
      const url = new URL(captured.url)
      const isReportRoute = url.pathname.includes('/report') || url.pathname.includes('/tasks/')

      if (isReportRoute) {
        const headerValue = url.pathname.includes('/tasks/')
          ? (taskSimulation ?? simulation)
          : simulation
        if (headerValue) {
          const headers = new Headers(captured.headers)
          headers.set('X-Simulation-Report', headerValue)
          return originalFetch(new Request(captured, { headers }))
        }
      }
      return originalFetch(input, init)
    }) as typeof fetch

    createObjectUrl = vi.fn((blob: Blob) => {
      createdBlobs.push(blob)
      const url = `blob:rapport-test/${createdBlobs.length}`
      createdObjectUrls.push(url)
      return url
    })
    revokeObjectUrl = vi.fn((url: string) => {
      expect(createdObjectUrls).toContain(url)
    })
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: createObjectUrl,
    })
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: revokeObjectUrl,
    })
    anchorClickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      clickedLinks.push({ href: this.href, download: this.download })
    })
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
    server.resetHandlers()
    resetMockReport()
    clearAccessToken()
  })

  it('désactive le téléchargement avec une explication quand le rapport n’est pas prêt', async () => {
    renderReportPage()

    expect(await screen.findByTestId('report-empty-state')).toBeInTheDocument()
    expect(screen.getByTestId('report-download-button')).toBeDisabled()
    expect(screen.getByTestId('report-download-explanation')).toHaveTextContent(
      'Le téléchargement est disponible uniquement lorsque le rapport est prêt.',
    )
    expect(anchorClickSpy).not.toHaveBeenCalled()
  })

  it('télécharge le contenu reçu octet pour octet via un lien Blob, sans stockage navigateur', async () => {
    const storageSetItem = vi.spyOn(Storage.prototype, 'setItem')
    simulation = 'ready'
    renderReportPage()

    await screen.findByTestId('report-preview')
    const button = screen.getByTestId('report-download-button')
    expect(button).toBeEnabled()
    expect(button).toHaveTextContent('Télécharger le rapport')

    fireEvent.click(button)
    expect(screen.getByTestId('report-download-button')).toBeDisabled()
    expect(screen.getByTestId('report-download-button')).toHaveTextContent(
      'Téléchargement en cours...',
    )

    await waitFor(() => expect(clickedLinks).toHaveLength(1))
    const clickedLink = clickedLinks[0]!
    const downloadedBlob = createdBlobs[0]!
    expect(screen.getByTestId('report-download-button')).toBeEnabled()
    expect(clickedLink.href).toBe(createdObjectUrls[0])
    expect(clickedLink.download).toBe('rapport-case-001.md')
    expect(revokeObjectUrl).toHaveBeenCalledWith(createdObjectUrls[0])

    expect(createdBlobs).toHaveLength(1)
    expect(downloadedBlob.type).toBe('text/markdown;charset=utf-8')
    expect(await readBlobAsText(downloadedBlob)).toBe(MOCK_REPORT_CONTENT)
    const receivedBytes = new TextEncoder().encode(MOCK_REPORT_CONTENT)
    const downloadedBytes = await readBlobAsBytes(downloadedBlob)
    expect(Array.from(downloadedBytes)).toEqual(Array.from(receivedBytes))
    expect(storageSetItem).not.toHaveBeenCalled()
  })

  it('utilise le format json renvoyé par le back pour le type MIME et l’extension', async () => {
    server.use(
      http.get('*/api/v1/cases/:caseId/report', () => {
        return HttpResponse.json({
          status: 'validated',
          format: 'json',
          content: BACK_PROVIDED_JSON_CONTENT,
        })
      }),
    )
    renderReportPage()

    await screen.findByTestId('report-preview')
    await user.click(screen.getByTestId('report-download-button'))

    await waitFor(() => expect(clickedLinks).toHaveLength(1))
    const downloadedBlob = createdBlobs[0]!
    expect(downloadedBlob.type).toBe('application/json;charset=utf-8')
    expect(clickedLinks[0]!.download).toBe('rapport-case-001.json')
    expect(await readBlobAsText(downloadedBlob)).toBe(BACK_PROVIDED_JSON_CONTENT)
  })

  it('affiche l’empreinte fournie par le back, tronquée et copiable intégralement', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(globalThis.navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })
    server.use(
      http.get('*/api/v1/cases/:caseId/report', () => {
        return HttpResponse.json({
          status: 'validated',
          format: 'markdown',
          content: MOCK_REPORT_CONTENT,
          sha256: BACK_PROVIDED_FINGERPRINT,
        })
      }),
    )
    renderReportPage()

    await screen.findByTestId('report-preview')
    const value = screen.getByTestId('report-fingerprint-value')
    expect(value).toHaveTextContent('0123456789ab…456789abcdef')
    expect(value).not.toHaveTextContent(BACK_PROVIDED_FINGERPRINT)
    expect(screen.getByTestId('report-fingerprint-copy')).toBeEnabled()

    await user.click(screen.getByTestId('report-fingerprint-copy'))
    expect(writeText).toHaveBeenCalledWith(BACK_PROVIDED_FINGERPRINT)
    expect(await screen.findByTestId('report-fingerprint-copied')).toHaveTextContent('Copié')
  })

  it('signale un échec de téléchargement et permet de réessayer', async () => {
    simulation = 'ready'
    renderReportPage()
    await screen.findByTestId('report-preview')

    createObjectUrl.mockImplementationOnce(() => {
      throw new Error('échec simulé du Blob')
    })
    await user.click(screen.getByTestId('report-download-button'))

    const error = await screen.findByTestId('report-download-error')
    expect(within(error).getByTestId('report-download-error-message')).toHaveTextContent(
      'Le téléchargement du rapport a échoué. Veuillez réessayer.',
    )
    const retry = within(error).getByTestId('report-download-retry')
    expect(retry).toHaveTextContent('Réessayer')

    await user.click(retry)
    await waitFor(() => expect(clickedLinks).toHaveLength(1))
    expect(screen.queryByTestId('report-download-error')).not.toBeInTheDocument()
  })

  it('cache le téléchargement en cas d’accès refusé (403)', async () => {
    simulation = 'forbidden'
    renderReportPage()

    expect(await screen.findByTestId('report-forbidden-state')).toBeInTheDocument()
    expect(screen.queryByTestId('report-download-panel')).not.toBeInTheDocument()
  })

  it('désactive le téléchargement et restitue le code brut pour un statut inconnu', async () => {
    renderReportPage()
    await screen.findByTestId('report-empty-state')
    taskSimulation = 'unknown-status'

    await user.click(screen.getByTestId('report-generate-button'))

    const unknown = await screen.findByTestId('report-unknown-state')
    expect(within(unknown).getByTestId('report-unknown-label')).toHaveTextContent(
      'État inconnu (unrecognized_state_code)',
    )
    expect(screen.getByTestId('report-download-button')).toBeDisabled()
  })
})
