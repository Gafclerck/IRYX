import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, ShieldCheck } from 'lucide-react'
import { CaseSidebar } from '../features/cases/components/CaseSidebar'
import { useCaseDetail } from '../features/cases/hooks/useCaseDetail'
import { useSessionUser } from '../features/auth/hooks/useSessionUser'
import {
  FindingCard,
  ReviewEmptyState,
  ReviewErrorState,
  ReviewFetchingBadge,
  ReviewForbiddenState,
  ReviewLoadingState,
} from '../features/review/components'
import { useReview } from '../features/review/hooks/useReview'
import {
  REVIEW_REPORT_LINK_BLOCKED_NOTE,
  REVIEW_REPORT_LINK_LABEL,
  isKnownFindingStatus,
} from '../features/review/constants'

/**
 * Revue H2 des findings (Story F4.8, FR-REV-01).
 * Route : /cases/:caseId/review, dans AuthenticatedLayout, étape 5 (partie 1).
 *
 * RÈGLES :
 * 1. Aucune décision calculée côté front. Route de décision absente du contrat :
 *    actions désactivées avec "à réaligner (E6)", jamais simulées comme acquises.
 * 2. Rejet : motif obligatoire (Zod, FR) validé localement ; aucune requête envoyée.
 * 3. "Générer le rapport" (lien vers F5.1) actif seulement si au moins un finding
 *    est validé selon l'état reçu du serveur. Le front reflète l'état reçu.
 * 4. États : chargement, vide, nominal, erreur/réessayer, accès refusé 403, inconnu.
 * 5. Aucune écriture localStorage/sessionStorage. Palette stricte, texte FR.
 */
export function ReviewPage() {
  const { caseId } = useParams<{ caseId: string }>()
  const safeCaseId = caseId ?? ''
  const sessionUser = useSessionUser()
  const isAnalyst =
    sessionUser?.role?.toUpperCase() === 'ANALYST' || sessionUser?.role?.toUpperCase() === 'ADMIN'

  const { data: caseData, error: caseError } = useCaseDetail(safeCaseId)
  const review = useReview({ caseId: safeCaseId, enabled: Boolean(safeCaseId) })

  const isForbidden = caseError?.status === 403 || review.state === 'forbidden'
  const findings = review.findings
  const validatedCount = findings.filter((f) => f.status === 'validated').length
  const rejectedCount = findings.filter((f) => f.status === 'rejected').length
  const pendingCount = findings.filter((f) => f.status === 'proposed').length
  const unknownCount = findings.filter((f) => !isKnownFindingStatus(f.status)).length
  const hasValidatedFinding = validatedCount > 0

  return (
    <div className="flex min-h-[calc(100vh-56px)] flex-col bg-ink text-mist md:flex-row">
      <CaseSidebar caseId={safeCaseId} caseTitle={caseData?.title || "Dossier d'investigation"} />

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
            <span className="font-medium text-teal">Revue</span>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-deep pb-4">
            <div>
              <span className="inline-block text-xs font-semibold uppercase tracking-wider text-teal">
                Étape 5 du canevas — Porte H2
              </span>
              <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-mist">
                <ShieldCheck className="h-6 w-6 text-cyan" aria-hidden="true" />
                Revue des findings
              </h1>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {review.isFetching && <ReviewFetchingBadge />}
              {hasValidatedFinding ? (
                <Link
                  to={`/cases/${safeCaseId}/report`}
                  className="rounded border border-cyan bg-cyan px-4 py-2 text-sm font-bold text-ink hover:bg-cyan/80 focus:outline-none focus:ring-2 focus:ring-cyan"
                  data-testid="review-generate-report-link"
                >
                  {REVIEW_REPORT_LINK_LABEL}
                </Link>
              ) : (
                <button
                  type="button"
                  disabled
                  title={REVIEW_REPORT_LINK_BLOCKED_NOTE}
                  className="rounded border border-deep bg-deep/40 px-4 py-2 text-sm font-bold text-mist/60 disabled:cursor-not-allowed"
                  data-testid="review-generate-report-link"
                >
                  {REVIEW_REPORT_LINK_LABEL}
                </button>
              )}
            </div>
          </div>

          <div
            className="rounded-lg border border-deep bg-deep/10 p-3 text-xs text-teal"
            data-testid="review-h2-note"
          >
            Décision H2 : chaque action est une requête distincte au back. La route de décision est
            absente du contrat — actions désactivées, à réaligner (E6). Aucune décision n’est
            simulée comme acquise.
          </div>

          {!isForbidden && review.state === 'ready' && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4" data-testid="review-counters">
              <div className="rounded border border-deep bg-deep/10 p-3">
                <p className="text-xs uppercase tracking-wider text-teal">Validés</p>
                <p className="text-xl font-bold text-mist" data-testid="review-count-validated">
                  {validatedCount}
                </p>
              </div>
              <div className="rounded border border-deep bg-deep/10 p-3">
                <p className="text-xs uppercase tracking-wider text-teal">Rejetés</p>
                <p className="text-xl font-bold text-mist" data-testid="review-count-rejected">
                  {rejectedCount}
                </p>
              </div>
              <div className="rounded border border-deep bg-deep/10 p-3">
                <p className="text-xs uppercase tracking-wider text-teal">À examiner</p>
                <p className="text-xl font-bold text-mist" data-testid="review-count-pending">
                  {pendingCount}
                </p>
              </div>
              <div className="rounded border border-deep bg-deep/10 p-3">
                <p className="text-xs uppercase tracking-wider text-teal">Inconnu</p>
                <p className="text-xl font-bold text-mist" data-testid="review-count-unknown">
                  {unknownCount}
                </p>
              </div>
            </div>
          )}

          {!hasValidatedFinding && !isForbidden && review.state !== 'loading' && (
            <p className="text-xs text-teal" data-testid="review-report-blocked-note">
              {REVIEW_REPORT_LINK_BLOCKED_NOTE}
            </p>
          )}

          {review.state === 'loading' && <ReviewLoadingState />}
          {isForbidden && <ReviewForbiddenState />}
          {!isForbidden && review.state === 'empty' && <ReviewEmptyState />}
          {!isForbidden && review.state === 'error' && (
            <ReviewErrorState
              message={review.errorMessage}
              onRetry={review.isNetworkCutoff ? review.retryConnection : review.refetch}
              isNetworkCutoff={review.isNetworkCutoff}
            />
          )}
          {!isForbidden && review.state === 'ready' && (
            <div className="space-y-4" data-testid="review-findings-list">
              {findings.map((finding) => (
                <FindingCard key={finding.id} finding={finding} />
              ))}
            </div>
          )}

          {!isForbidden && !isAnalyst && review.state === 'ready' && (
            <p className="text-xs text-teal" data-testid="review-readonly-note">
              Profil non analyste : les actions d’arbitrage sont désactivées (lecture seule).
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
