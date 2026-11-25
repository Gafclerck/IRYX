import { useEffect } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, ShieldCheck } from 'lucide-react'
import { useCaseDetail } from '../features/cases/hooks/useCaseDetail'
import { CaseSidebar } from '../features/cases/components/CaseSidebar'
import { usePlan } from '../features/plan/hooks/usePlan'
import {
  PlanEmptyState,
  PlanErrorState,
  PlanForbiddenState,
  PlanLoadingSkeleton,
  PlanNetworkCutoffState,
  PlanPlanningState,
  PlanStepList,
} from '../features/plan/components'

/**
 * Consultation de la séquence d'investigation proposée par le Planner (Story F4.1).
 * Route : /cases/:caseId/plan (Étape 3 Plan et agents dans AuthenticatedLayout).
 *
 * RÈGLES DE CONCEPTION :
 * 1. Lecture seule stricte : aucune action de validation, de retrait ou de refus (F4.2 / H1),
 *    aucun suivi d'agents (F4.3), aucun ajout d'étape.
 * 2. Scrutation de l'élaboration selon Retry-After: 3 (ADR-0008), arrêt à état terminal et
 *    au départ de la page ; coupure prolongée -> DP-05 (« Réessayer la connexion »).
 * 3. Plan validé : consultation en lecture seule avec mention « Validé ».
 * 4. Statut non répertorié : « État inconnu (code_brut) » sans blocage de l'affichage.
 * 5. Aucune écriture dans localStorage ni sessionStorage ; palette stricte sans couleur en dur.
 * 6. Les champs absents du contrat (agent assigné) sont marqués « à réaligner » plutôt
 *    que d'être inventés (docs/frontend/14).
 */
export function PlanPage() {
  const { caseId } = useParams<{ caseId: string }>()
  const navigate = useNavigate()
  const safeCaseId = caseId || ''

  const { data: caseData, isLoading: isCaseLoading, error: caseError } = useCaseDetail(safeCaseId)
  const caseForbidden = caseError?.status === 403

  const {
    state,
    plan,
    statusLabel,
    errorMessage,
    isFetching,
    isNetworkCutoff,
    refetch,
    retryConnection,
  } = usePlan({
    caseId: safeCaseId,
    enabled: Boolean(safeCaseId && !isCaseLoading && !caseForbidden),
  })

  // Conformément à la story F4.1, un accès refusé sur le dossier ou sur le plan
  // bloque l'affichage puis redirige vers la liste des dossiers.
  useEffect(() => {
    if (!caseForbidden && state !== 'forbidden') return
    const timer = setTimeout(() => {
      navigate('/cases', {
        replace: true,
        state: { forbiddenError: "Vous n'avez pas accès à ce dossier" },
      })
    }, 1200)
    return () => clearTimeout(timer)
  }, [caseForbidden, navigate, state])

  const isForbidden = caseForbidden || state === 'forbidden'
  const showSkeleton = state === 'loading' && isCaseLoading

  return (
    <div className="flex min-h-[calc(100vh-56px)] flex-col bg-ink text-mist md:flex-row">
      <CaseSidebar caseId={safeCaseId} caseTitle={caseData?.title || 'Dossier d’investigation'} />

      <div className="flex-1 overflow-y-auto p-4 md:p-8">
        <div className="mx-auto max-w-5xl space-y-6">
          {/* Fil d'Ariane */}
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
            <span className="font-medium text-teal">Plan</span>
          </div>

          {/* En-tête de l'étape 3 */}
          <div className="border-b border-deep pb-4">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <span className="inline-block text-xs font-semibold uppercase tracking-wider text-teal">
                  Étape 3 du canevas
                </span>
                <h1 className="text-2xl font-bold tracking-tight text-mist">
                  Plan d’investigation proposé
                </h1>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {statusLabel && (
                  <span
                    className="rounded border border-deep bg-deep/20 px-3 py-1.5 text-xs text-mist"
                    data-testid="plan-status-badge"
                  >
                    {statusLabel}
                  </span>
                )}
                {state === 'validated' && (
                  <span
                    className="inline-flex items-center gap-1.5 rounded border border-teal bg-deep px-3 py-1.5 text-xs font-semibold text-cyan"
                    data-testid="plan-validated-badge"
                  >
                    <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
                    Validé
                  </span>
                )}
              </div>
            </div>
            <p className="mt-2 text-sm text-mist/80">
              Séquence forensique élaborée par le Planner, consultable en lecture seule avant toute
              décision d’arbitrage.
            </p>
          </div>

          {/* Chargement initial */}
          {showSkeleton && <PlanLoadingSkeleton />}

          {/* Accès refusé (403) */}
          {isForbidden && <PlanForbiddenState />}

          {/* Coupure réseau prolongée (DP-05) */}
          {!isForbidden && isNetworkCutoff && (
            <PlanNetworkCutoffState onRetryConnection={retryConnection} />
          )}

          {/* Erreur de l'agent Planner ou du service */}
          {!isForbidden && !isNetworkCutoff && state === 'error' && (
            <PlanErrorState message={errorMessage} onRetry={refetch} />
          )}

          {/* Planification en cours : scrutation active */}
          {!isForbidden && state === 'planning' && <PlanPlanningState isFetching={isFetching} />}

          {/* Aucun outil applicable */}
          {!isForbidden && state === 'empty' && <PlanEmptyState caseId={safeCaseId} />}

          {/* État nominal ou plan validé : lecture seule stricte */}
          {!isForbidden && (state === 'ready' || state === 'validated') && plan && (
            <div className="space-y-6" data-testid="plan-page-content">
              {plan.summary.trim() !== '' && (
                <section
                  aria-labelledby="plan-summary-heading"
                  className="rounded-lg border border-deep bg-deep/10 p-4"
                >
                  <h2
                    id="plan-summary-heading"
                    className="text-xs font-semibold uppercase tracking-wider text-teal"
                  >
                    Synthèse du plan
                  </h2>
                  <p className="mt-2 text-sm text-mist" data-testid="plan-summary">
                    {plan.summary}
                  </p>
                </section>
              )}
              <PlanStepList steps={plan.steps} readOnly />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
