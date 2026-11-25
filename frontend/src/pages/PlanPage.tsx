import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Ban, LoaderCircle, ShieldCheck } from 'lucide-react'
import { useCaseDetail } from '../features/cases/hooks/useCaseDetail'
import { CaseSidebar } from '../features/cases/components/CaseSidebar'
import { useSessionUser } from '../features/auth/hooks/useSessionUser'
import { usePlan } from '../features/plan/hooks/usePlan'
import { useH1Decision } from '../features/plan/hooks/useH1Decision'
import {
  PlanConflictView,
  PlanDecisionDialog,
  PlanDecisionErrorView,
  PlanEmptyState,
  PlanErrorState,
  PlanForbiddenState,
  PlanLoadingSkeleton,
  PlanNetworkCutoffState,
  PlanPlanningState,
  PlanReplanificationView,
  PlanStepList,
  PlanValidatedView,
  type PlanDecisionDialogKind,
} from '../features/plan/components'
import type { H1DecisionRequest } from '../features/plan/types'

interface PendingDecision {
  readonly kind: PlanDecisionDialogKind
  readonly payload: H1DecisionRequest
}

function kindFromDecision(decision: H1DecisionRequest['decision']): PlanDecisionDialogKind {
  return decision === 'reject' ? 'reject' : decision === 'modify' ? 'modify' : 'approve'
}

/**
 * Revue du plan et arbitrage formel de la porte H1 (Stories F4.1 et F4.2).
 * Route : /cases/:caseId/plan (Étape 3 Plan et agents dans AuthenticatedLayout).
 *
 * RÈGLES DE CONCEPTION :
 * 1. Aucun envoi H1 n'est déclenché par un bouton de l'écran principal : les boutons
 *    ouvrent un dialogue qui résume le nombre d'étapes retenues et exige une confirmation.
 * 2. Le motif de refus est validé par Zod avec un message en français.
 * 3. Une garde référentielle interdit deux envois concurrents ; les boutons sont désactivés
 *    pendant l'envoi et le plan reste « prêt » sur erreur réseau ou serveur.
 * 4. Un 409 affiche l'état réel renvoyé par le serveur sans valider côté front.
 * 5. Après succès : lecture seule avec mention « Validé » et lien « Voir le suivi » (F4.3).
 * 6. Après refus : état de replanification, sans action de validation tant qu'un nouveau
 *    plan n'a pas été produit par le back-end.
 * 7. Aucun ajout d'étape, aucun suivi d'agents (F4.3), aucun écran d'audit (DP-02),
 *    aucune écriture dans localStorage ni sessionStorage, palette stricte sans couleur en dur.
 */
export function PlanPage() {
  const { caseId } = useParams<{ caseId: string }>()
  const navigate = useNavigate()
  const safeCaseId = caseId || ''
  const sessionUser = useSessionUser()
  const isViewer = sessionUser?.role?.toUpperCase() === 'VIEWER'

  const { data: caseData, isLoading: isCaseLoading, error: caseError } = useCaseDetail(safeCaseId)
  const caseForbidden = caseError?.status === 403

  const {
    state,
    plan,
    run,
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

  const decision = useH1Decision({ caseId: safeCaseId, runId: run?.id ?? '' })
  const { outcome, isSubmitting, reset: resetDecision } = decision

  const [removedStepIds, setRemovedStepIds] = useState<readonly number[]>([])
  const [pendingDecision, setPendingDecision] = useState<PendingDecision | null>(null)

  const retainedSteps = useMemo(
    () => (plan?.steps ?? []).filter((step) => !removedStepIds.includes(step.step_id)),
    [plan, removedStepIds],
  )

  // Un nouveau plan (ou un autre dossier) réinitialise l'arbitrage local et les retraits.
  useEffect(() => {
    setRemovedStepIds([])
    setPendingDecision(null)
    resetDecision()
  }, [caseId, plan, resetDecision])

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
  const isValidated = state === 'validated' || outcome.kind === 'validated'
  const isRefused = outcome.kind === 'refused'
  const isConflict = outcome.kind === 'conflict'

  const actionsVisible =
    state === 'ready' &&
    !isForbidden &&
    !isNetworkCutoff &&
    !isViewer &&
    !isValidated &&
    !isRefused &&
    !isConflict &&
    plan !== null
  const actionsEnabled = actionsVisible && !isSubmitting && retainedSteps.length > 0

  const openDialog = useCallback(
    (kind: PlanDecisionDialogKind) => {
      if (!actionsEnabled && kind !== 'reject') return
      if (!actionsVisible) return

      let payload: H1DecisionRequest
      if (kind === 'approve') {
        // Dès qu'une étape a été retirée, le contrat exige la décision « modify »
        // avec le plan retenu : aucune étape n'est ajoutée côté client.
        payload =
          removedStepIds.length > 0
            ? {
                decision: 'modify',
                modified_plan: { ...plan!, steps: [...retainedSteps] },
                feedback: null,
                return_to_planner: false,
              }
            : { decision: 'approve', feedback: null, return_to_planner: false }
      } else if (kind === 'modify') {
        payload = {
          decision: 'modify',
          modified_plan: { ...plan!, steps: [...retainedSteps] },
          feedback: null,
          return_to_planner: false,
        }
      } else {
        payload = { decision: 'reject', feedback: '', return_to_planner: true }
      }

      setPendingDecision({ kind, payload })
    },
    [actionsEnabled, actionsVisible, plan, retainedSteps, removedStepIds],
  )

  const handleConfirm = useCallback(
    async (reason?: string) => {
      if (!pendingDecision || isSubmitting) return
      const payload: H1DecisionRequest = {
        ...pendingDecision.payload,
        ...(reason !== undefined ? { feedback: reason } : {}),
      }
      await decision.submit(payload)
      setPendingDecision(null)
    },
    [decision, isSubmitting, pendingDecision],
  )

  const handleRetryDecision = useCallback(() => {
    if (outcome.kind !== 'error') return
    decision.reset()
    setPendingDecision({
      kind: kindFromDecision(outcome.payload.decision),
      payload: outcome.payload,
    })
  }, [decision, outcome])

  const handleRefreshAfterConflict = useCallback(() => {
    decision.reset()
    refetch()
  }, [decision, refetch])

  const removeStep = useCallback(
    (stepId: number) => {
      if (isSubmitting || !actionsVisible) return
      setRemovedStepIds((current) => [...current, stepId])
    },
    [actionsVisible, isSubmitting],
  )

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
                {isSubmitting && (
                  <span
                    className="inline-flex items-center gap-1.5 rounded border border-deep bg-deep/20 px-3 py-1.5 text-xs font-semibold text-cyan"
                    role="status"
                    data-testid="plan-submitting-badge"
                  >
                    <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                    VALIDATION EN COURS
                  </span>
                )}
                {isValidated && (
                  <span
                    className="inline-flex items-center gap-1.5 rounded border border-teal bg-deep px-3 py-1.5 text-xs font-semibold text-cyan"
                    data-testid="plan-validated-badge"
                  >
                    <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
                    Validé
                  </span>
                )}
                {isRefused && (
                  <span
                    className="inline-flex items-center gap-1.5 rounded border border-deep bg-deep px-3 py-1.5 text-xs font-semibold text-cyan"
                    data-testid="plan-refused-badge"
                  >
                    <Ban className="h-3.5 w-3.5" aria-hidden="true" />
                    REFUSÉ
                  </span>
                )}
              </div>
            </div>
            <p className="mt-2 text-sm text-mist/80">
              Séquence forensique élaborée par le Planner. L’arbitrage de la porte H1 est soumis à
              confirmation explicite.
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

          {/* Conflit 409 : état réel du serveur, sans validation locale */}
          {!isForbidden && isConflict && outcome.kind === 'conflict' && (
            <PlanConflictView
              status={outcome.status}
              phase={outcome.phase}
              message={outcome.message}
              onRefresh={handleRefreshAfterConflict}
            />
          )}

          {/* Erreur réseau ou serveur sur la décision : le plan reste prêt */}
          {!isForbidden && !isNetworkCutoff && state === 'ready' && outcome.kind === 'error' && (
            <PlanDecisionErrorView message={outcome.message} onRetry={handleRetryDecision} />
          )}

          {/* Refus : replanification sans action de validation */}
          {!isForbidden && isRefused && <PlanReplanificationView />}

          {/* Validation réussie : lecture seule et accès au suivi */}
          {!isForbidden && isValidated && <PlanValidatedView caseId={safeCaseId} />}

          {/* Actions d'arbitrage (jamais d'envoi direct sans confirmation) */}
          {actionsVisible && (
            <section
              className="space-y-3 rounded-lg border border-deep bg-deep/10 p-4"
              aria-labelledby="plan-arbitration-heading"
              data-testid="plan-arbitration-actions"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2
                    id="plan-arbitration-heading"
                    className="text-sm font-bold uppercase tracking-wide text-mist"
                  >
                    Arbitrage de la porte H1
                  </h2>
                  <p className="mt-1 text-xs text-teal">
                    {retainedSteps.length > 1
                      ? `${retainedSteps.length} étapes retenues`
                      : `${retainedSteps.length} étape retenue`}
                  </p>
                </div>
                <div className="flex flex-wrap gap-3">
                  <button
                    type="button"
                    onClick={() => openDialog('approve')}
                    disabled={!actionsEnabled}
                    className="rounded border border-cyan bg-cyan px-4 py-2 text-sm font-bold text-ink hover:bg-cyan/80 focus:outline-none focus:ring-2 focus:ring-cyan disabled:cursor-not-allowed disabled:opacity-50"
                    data-testid="plan-validate-button"
                  >
                    Valider et lancer
                  </button>
                  <button
                    type="button"
                    onClick={() => openDialog('reject')}
                    disabled={isSubmitting}
                    className="rounded border border-teal bg-deep px-4 py-2 text-sm font-semibold text-mist hover:bg-deep/80 focus:outline-none focus:ring-2 focus:ring-cyan disabled:cursor-not-allowed disabled:opacity-50"
                    data-testid="plan-refuse-button"
                  >
                    Refuser le plan
                  </button>
                </div>
              </div>
              {retainedSteps.length === 0 && (
                <p className="text-sm text-cyan" data-testid="plan-no-retained-steps">
                  Aucune étape retenue. La validation est désactivée.
                </p>
              )}
            </section>
          )}

          {/* Plan prêt, validé ou en conflit : lecture seule sauf arbitrage autorisé */}
          {!isForbidden && !isRefused && (state === 'ready' || isValidated) && plan && (
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
              <PlanStepList
                steps={retainedSteps}
                readOnly={!actionsVisible}
                onRemove={actionsVisible ? removeStep : undefined}
                removeDisabled={isSubmitting}
              />
            </div>
          )}

          {pendingDecision && (
            <PlanDecisionDialog
              kind={pendingDecision.kind}
              stepCount={retainedSteps.length}
              initialReason={pendingDecision.payload.feedback}
              isSubmitting={isSubmitting}
              onCancel={() => setPendingDecision(null)}
              onConfirm={handleConfirm}
            />
          )}
        </div>
      </div>
    </div>
  )
}
