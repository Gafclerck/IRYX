import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, LoaderCircle } from 'lucide-react'
import { CaseSidebar } from '../features/cases/components/CaseSidebar'
import { useCaseDetail } from '../features/cases/hooks/useCaseDetail'
import { useResultsStatus, useTimeline } from '../features/results'
import {
  SourceDetailDrawer,
  TimelineEmptyState,
  TimelineErrorState,
  TimelineFiltersBar,
  TimelineForbiddenState,
  TimelineList,
  TimelineLoadingSkeleton,
  TimelinePartialBanner,
  TimelineUnknownState,
} from '../features/results/components'
import type { TimelineEntry } from '../features/results/types'

/**
 * Exploration des résultats — onglet Chronologie (Story F4.6, FR-RES-02).
 * Route : /cases/:caseId/results (Étape 4 dans AuthenticatedLayout).
 *
 * RÈGLES DE CONCEPTION :
 * 1. F4.5 est sautée : seul l'onglet Chronologie est rendu ; Artefacts et
 *    hypothèses ne sont pas implémentés.
 * 2. DP-01 : pagination serveur stricte par blocs de 100 événements, un seul
 *    bloc conservé à la fois, filtres transmis au serveur et maintenus.
 * 3. Le panneau « Source » (F4.7) s'ouvre depuis la ligne ou la puce source,
 *    sans navigation ; la chronologie reste visible et le focus revient à
 *    l'élément d'origine à la fermeture.
 * 4. Résultats partiels et statuts inconnus sont dérivés du contrat sans
 *    invention ; aucune écriture dans localStorage ni sessionStorage.
 */
export function ResultsPage() {
  const { caseId } = useParams<{ caseId: string }>()
  const safeCaseId = caseId ?? ''
  const [selectedSource, setSelectedSource] = useState<TimelineEntry | null>(null)
  const sourceOriginRef = useRef<HTMLElement | null>(null)

  const { data: caseData, isLoading: isCaseLoading, error: caseError } = useCaseDetail(safeCaseId)
  const timeline = useTimeline({ caseId: safeCaseId, enabled: Boolean(safeCaseId) })
  const status = useResultsStatus({ caseId: safeCaseId, enabled: Boolean(safeCaseId) })

  const openSource = useCallback((entry: TimelineEntry, origin: HTMLElement) => {
    sourceOriginRef.current = origin
    setSelectedSource(entry)
  }, [])

  const closeSource = useCallback(() => {
    setSelectedSource(null)
  }, [])

  useEffect(() => {
    if (!selectedSource) {
      sourceOriginRef.current?.focus()
      sourceOriginRef.current = null
    }
  }, [selectedSource])

  const isForbidden = caseError?.status === 403 || timeline.state === 'forbidden'
  const isInitialLoading = isCaseLoading || (timeline.state === 'loading' && !timeline.block)
  const isTransitionLoading = timeline.isFetching && !isInitialLoading

  return (
    <div className="flex min-h-[calc(100vh-56px)] flex-col bg-ink text-mist md:flex-row">
      <CaseSidebar caseId={safeCaseId} caseTitle={caseData?.title || 'Dossier d’investigation'} />

      <div className="flex-1 overflow-y-auto p-4 md:p-8">
        <div className="mx-auto max-w-6xl space-y-6">
          <div className="flex items-center space-x-2 text-xs text-mist/70">
            <Link
              to="/cases"
              className="inline-flex items-center gap-1 rounded hover:text-cyan focus:outline-none focus:ring-2 focus:ring-cyan"
              aria-label="Retour à la liste des dossiers"
            >
              <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Dossiers</span>
            </Link>
            <span>/</span>
            <Link
              to={`/cases/${safeCaseId}`}
              className="max-w-[200px] truncate rounded hover:text-cyan focus:outline-none focus:ring-2 focus:ring-cyan"
            >
              {caseData?.title || safeCaseId}
            </Link>
            <span>/</span>
            <span className="font-medium text-teal">Résultats</span>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-deep pb-4">
            <div>
              <span className="inline-block text-xs font-semibold uppercase tracking-wider text-teal">
                Étape 4 du canevas
              </span>
              <h1 className="text-2xl font-bold tracking-tight text-mist">Résultats</h1>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {status.statusLabel && (
                <span
                  className="rounded border border-deep bg-deep/20 px-3 py-1.5 text-xs text-mist"
                  data-testid="results-status-badge"
                >
                  {status.statusLabel}
                </span>
              )}
              {timeline.isFetching && (
                <span
                  className="inline-flex items-center gap-1.5 rounded border border-deep bg-deep/20 px-3 py-1.5 text-xs font-semibold text-cyan"
                  role="status"
                  data-testid="timeline-fetching-badge"
                >
                  <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                  CHARGEMENT DU BLOC
                </span>
              )}
            </div>
          </div>

          {!isForbidden && status.isUnknown && status.statusLabel && (
            <TimelineUnknownState statusLabel={status.statusLabel} />
          )}
          {!isForbidden && <TimelinePartialBanner failedPhases={status.failedPhases} />}

          {isForbidden && <TimelineForbiddenState />}

          {!isForbidden && (
            <>
              <TimelineFiltersBar
                value={timeline.filters}
                disabled={isInitialLoading}
                isFetching={timeline.isFetching}
                onApply={timeline.applyFilters}
                onReset={timeline.resetFilters}
              />

              {isInitialLoading && <TimelineLoadingSkeleton />}
              {isTransitionLoading && (
                <TimelineLoadingSkeleton label="Chargement du bloc de chronologie suivant" />
              )}

              {!isInitialLoading && !isTransitionLoading && timeline.state === 'error' && (
                <TimelineErrorState message={timeline.errorMessage} onRetry={timeline.refetch} />
              )}

              {!isInitialLoading && !isTransitionLoading && timeline.state === 'empty' && (
                <TimelineEmptyState onResetFilters={timeline.resetFilters} />
              )}

              {!isInitialLoading && !isTransitionLoading && timeline.state === 'success' && (
                <TimelineList
                  entries={timeline.entries}
                  page={timeline.page}
                  hasMore={timeline.hasMore}
                  isFetching={timeline.isFetching}
                  onNext={timeline.goToNextBlock}
                  onPrevious={timeline.goToPreviousBlock}
                  onOpenSource={openSource}
                />
              )}
            </>
          )}
        </div>
      </div>

      <SourceDetailDrawer
        isOpen={Boolean(selectedSource)}
        caseId={safeCaseId}
        entry={selectedSource}
        onClose={closeSource}
      />
    </div>
  )
}
