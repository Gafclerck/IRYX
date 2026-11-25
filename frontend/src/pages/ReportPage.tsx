import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, LoaderCircle } from 'lucide-react'
import { CaseSidebar } from '../features/cases/components/CaseSidebar'
import { useCaseDetail } from '../features/cases/hooks/useCaseDetail'
import { REPORT_GENERATE_LABEL, REPORT_H2_H3_GAP_NOTE } from '../features/report/constants'
import {
  ReportEmptyState,
  ReportErrorState,
  ReportForbiddenState,
  ReportGenerationFailedState,
  ReportGeneratingState,
  ReportLoadingState,
  ReportNetworkCutoffState,
  ReportPreview,
  ReportUnknownState,
} from '../features/report/components'
import { useReport } from '../features/report/hooks/useReport'

export interface ReportPageProps {
  /** Réservé aux tests : raccourcit la cadence de scrutation ADR-0008. */
  readonly pollIntervalMs?: number
}

/**
 * Génération et consultation du rapport — étape 5 (Story F5.1, FR-REP-01).
 * Route : /cases/:caseId/report, dans AuthenticatedLayout.
 *
 * RÈGLES DE CONCEPTION :
 * 1. DP-03 : le bouton demande la compilation au back ; le front n'assemble
 *    aucun chapitre et affiche le document reçu sans modification.
 * 2. ADR-0008 / DP-05 : scrutation pilotée par Retry-After, arrêt à l'état
 *    terminal ou au départ de la page, et « Réessayer la connexion » en cas
 *    de coupure prolongée.
 * 3. F4.8 / F4.9 non implémentées : aucun contrôle H2/H3 n'est appliqué ;
 *    l'écart est signalé dans l'interface, à réaligner.
 * 4. Aucune écriture dans localStorage ni sessionStorage ; palette stricte,
 *    aperçu sur fond mist avec texte ink.
 */
export function ReportPage({ pollIntervalMs }: ReportPageProps) {
  const { caseId } = useParams<{ caseId: string }>()
  const safeCaseId = caseId ?? ''
  const { data: caseData, error: caseError } = useCaseDetail(safeCaseId)
  const report = useReport({
    caseId: safeCaseId,
    enabled: Boolean(safeCaseId),
    pollIntervalMs,
  })

  const isForbidden = caseError?.status === 403 || report.state === 'forbidden'
  const canGenerate =
    report.state === 'empty' ||
    report.state === 'error' ||
    report.state === 'generationFailed' ||
    (report.state === 'generating' && report.document?.status === 'draft')
  const showPreview = !isForbidden && Boolean(report.document?.content)

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
            <span className="font-medium text-teal">Rapport</span>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-deep pb-4">
            <div>
              <span className="inline-block text-xs font-semibold uppercase tracking-wider text-teal">
                Étape 5 du canevas
              </span>
              <h1 className="text-2xl font-bold tracking-tight text-mist">Rapport d'incident</h1>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {report.statusLabel && (
                <span
                  className="rounded border border-deep bg-deep/20 px-3 py-1.5 text-xs text-mist"
                  data-testid="report-status-badge"
                >
                  {report.statusLabel}
                </span>
              )}
              {report.isFetching && (
                <span
                  className="inline-flex items-center gap-1.5 rounded border border-deep bg-deep/20 px-3 py-1.5 text-xs font-semibold text-cyan"
                  role="status"
                  data-testid="report-fetching-badge"
                >
                  <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                  CHARGEMENT
                </span>
              )}
              <button
                type="button"
                onClick={report.generate}
                disabled={!canGenerate}
                className="rounded border border-cyan bg-cyan px-4 py-2 text-sm font-bold text-ink hover:bg-cyan/80 focus:outline-none focus:ring-2 focus:ring-cyan disabled:cursor-not-allowed disabled:border-deep disabled:bg-deep/40 disabled:text-mist/60"
                data-testid="report-generate-button"
              >
                {REPORT_GENERATE_LABEL}
              </button>
            </div>
          </div>

          <div
            className="rounded-lg border border-deep bg-deep/10 p-3 text-xs text-teal"
            data-testid="report-h2-h3-gap-note"
          >
            {REPORT_H2_H3_GAP_NOTE}
          </div>

          {report.state === 'loading' && <ReportLoadingState />}

          {isForbidden && <ReportForbiddenState />}

          {!isForbidden && report.state === 'empty' && <ReportEmptyState />}

          {!isForbidden && report.state === 'generating' && (
            <ReportGeneratingState isFetching={report.isFetching} />
          )}

          {!isForbidden && report.state === 'generationFailed' && (
            <ReportGenerationFailedState
              message={report.errorMessage}
              onRetry={report.retryGeneration}
            />
          )}

          {!isForbidden && report.state === 'error' && (
            <ReportErrorState message={report.errorMessage} onRetry={report.refetch} />
          )}

          {!isForbidden && report.state === 'networkCutoff' && (
            <ReportNetworkCutoffState onRetry={report.retryConnection} />
          )}

          {!isForbidden && report.state === 'unknown' && report.statusLabel && (
            <ReportUnknownState statusLabel={report.statusLabel} />
          )}

          {showPreview && report.document && <ReportPreview document={report.document} />}
        </div>
      </div>
    </div>
  )
}
