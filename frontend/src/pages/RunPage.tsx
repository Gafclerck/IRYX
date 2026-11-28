import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Ban, LoaderCircle, Pause, Play } from 'lucide-react'
import { CaseSidebar } from '../features/cases/components/CaseSidebar'
import { useCaseDetail } from '../features/cases/hooks/useCaseDetail'
import { useSessionUser } from '../features/auth/hooks/useSessionUser'
import { PAUSE_REALIGNMENT_NOTE, TO_REALIGN, waitingAgentCards } from '../features/run/constants'
import { useRunControls, useRunSupervision } from '../features/run'
import {
  ActivityLog,
  AgentCard,
  RunCancelDialog,
  RunCanceledState,
  RunCompletedState,
  RunErrorState,
  RunFailedState,
  RunForbiddenState,
  RunLoadingSkeleton,
  RunNetworkCutoffState,
  RunPartialFailureBanner,
  RunPausedState,
  RunWaitingState,
} from '../features/run/components'

/**
 * Console de supervision temps réel de l'orchestration des agents (Story F4.3).
 * Route : /cases/:caseId/run (Étape 3 Plan et agents dans AuthenticatedLayout).
 *
 * RÈGLES DE CONCEPTION :
 * 1. Les cartes et le journal sont dérivés des phases du contrat ; tout champ absent
 *    est affiché « à réaligner » sans valeur inventée.
 * 2. Scrutation ADR-0008, arrêt terminal ou au départ de page, DP-05 sur coupure
 *    prolongée avec bouton « Réessayer la connexion ».
 * 3. Seule la reprise dispose d'une route contractuelle ; pause, annulation et
 *    relance d'agent sont désactivées ou signalées « à réaligner ».
 * 4. Aucune annulation n'est transmise sans confirmation explicite.
 * 5. Aucune réouverture du plan ou de la porte H1 (F4.1/F4.2), aucun résultat (F4.5),
 *    aucun écran d'audit (DP-02), aucune écriture dans localStorage/sessionStorage.
 */
export function RunPage() {
  const { caseId } = useParams<{ caseId: string }>()
  const navigate = useNavigate()
  const safeCaseId = caseId || ''
  const sessionUser = useSessionUser()
  const isViewer = sessionUser?.role?.toUpperCase() === 'VIEWER'

  const { data: caseData, isLoading: isCaseLoading, error: caseError } = useCaseDetail(safeCaseId)
  const caseForbidden = caseError?.status === 403

  const supervision = useRunSupervision({
    caseId: safeCaseId,
    enabled: Boolean(safeCaseId && !isCaseLoading && !caseForbidden),
  })
  const {
    state,
    run,
    statusLabel,
    errorMessage,
    isFetching,
    isNetworkCutoff,
    agentCards,
    activityEntries,
    refetch,
    retryConnection,
  } = supervision

  const controls = useRunControls({ caseId: safeCaseId, runId: run?.id ?? '', onResumed: refetch })
  const { outcome, isSubmitting, resume, confirmCancel, reset: resetControls } = controls
  const [isCancelDialogOpen, setCancelDialogOpen] = useState(false)

  useEffect(() => {
    setCancelDialogOpen(false)
    resetControls()
  }, [caseId, resetControls, run?.id])

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
  const showConsole = !isForbidden && !isNetworkCutoff && state !== 'error' && state !== 'loading'
  const controlsAvailable =
    Boolean(run) && showConsole && !isViewer && state !== 'unknown' && !isSubmitting
  const canResume = controlsAvailable && state === 'paused'
  const canCancel = controlsAvailable

  const displayedCards = useMemo(
    () => (state === 'waiting' && !run ? waitingAgentCards() : agentCards),
    [agentCards, run, state],
  )

  const handleConfirmCancel = useCallback(async () => {
    await confirmCancel()
    setCancelDialogOpen(false)
  }, [confirmCancel])

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
            <span className="font-medium text-teal">Suivi des agents</span>
          </div>

          <div className="border-b border-deep pb-4">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <span className="inline-block text-xs font-semibold uppercase tracking-wider text-teal">
                  Étape 3 du canevas
                </span>
                <h1 className="text-2xl font-bold tracking-tight text-mist">
                  Console d’exécution des agents
                </h1>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {statusLabel && (
                  <span
                    className="rounded border border-deep bg-deep/20 px-3 py-1.5 text-xs text-mist"
                    data-testid="run-status-badge"
                  >
                    {statusLabel}
                  </span>
                )}
                {isFetching && !isForbidden && (
                  <span
                    className="inline-flex items-center gap-1.5 rounded border border-deep bg-deep/20 px-3 py-1.5 text-xs font-semibold text-cyan"
                    role="status"
                    data-testid="run-fetching-badge"
                  >
                    <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                    SCRUTATION EN COURS
                  </span>
                )}
              </div>
            </div>
            <p className="mt-2 text-sm text-mist/80">
              Supervision par scrutation ADR-0008. Progression, messages et diagnostic d’agent :{' '}
              {TO_REALIGN}.
            </p>
          </div>

          {showSkeleton && <RunLoadingSkeleton />}
          {isForbidden && <RunForbiddenState />}
          {!isForbidden && isNetworkCutoff && (
            <RunNetworkCutoffState onRetryConnection={retryConnection} />
          )}
          {!isForbidden && !isNetworkCutoff && state === 'error' && (
            <RunErrorState message={errorMessage} onRetry={refetch} />
          )}
          {!isForbidden && !isNetworkCutoff && state === 'waiting' && (
            <RunWaitingState isFetching={isFetching} />
          )}
          {!isForbidden && !isNetworkCutoff && state === 'paused' && <RunPausedState />}
          {!isForbidden && !isNetworkCutoff && state === 'partialFailure' && (
            <RunPartialFailureBanner />
          )}
          {!isForbidden && !isNetworkCutoff && state === 'completed' && (
            <RunCompletedState caseId={safeCaseId} />
          )}
          {!isForbidden && !isNetworkCutoff && state === 'canceled' && <RunCanceledState />}
          {!isForbidden && !isNetworkCutoff && state === 'failed' && <RunFailedState />}
          {!isForbidden && !isNetworkCutoff && state === 'unknown' && (
            <div
              className="rounded-lg border border-deep bg-deep/40 p-4 text-xs text-mist"
              role="status"
              data-testid="run-unknown-state"
            >
              État inconnu reçu du serveur : {statusLabel}. Les commandes sont désactivées —{' '}
              {TO_REALIGN}.
            </div>
          )}

          {controlsAvailable && (
            <section
              className="space-y-3 rounded-lg border border-deep bg-deep/10 p-4"
              aria-labelledby="run-controls-heading"
              data-testid="run-control-actions"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2
                    id="run-controls-heading"
                    className="text-sm font-bold uppercase tracking-wide text-mist"
                  >
                    Commandes de session
                  </h2>
                  <p className="mt-1 text-xs text-teal">{PAUSE_REALIGNMENT_NOTE}</p>
                </div>
                <div className="flex flex-wrap gap-3">
                  <button
                    type="button"
                    disabled
                    title={PAUSE_REALIGNMENT_NOTE}
                    className="inline-flex items-center gap-1.5 rounded border border-deep bg-deep px-4 py-2 text-sm font-semibold text-cyan disabled:cursor-not-allowed disabled:opacity-60"
                    data-testid="run-pause-button"
                  >
                    <Pause className="h-4 w-4" aria-hidden="true" />
                    Suspendre la session — {TO_REALIGN}
                  </button>
                  <button
                    type="button"
                    onClick={() => void resume()}
                    disabled={!canResume}
                    title={canResume ? undefined : 'Reprise disponible uniquement en pause'}
                    className="inline-flex items-center gap-1.5 rounded border border-teal bg-deep px-4 py-2 text-sm font-semibold text-mist hover:bg-deep/80 focus:outline-none focus:ring-2 focus:ring-cyan disabled:cursor-not-allowed disabled:opacity-60"
                    data-testid="run-resume-button"
                  >
                    <Play className="h-4 w-4" aria-hidden="true" />
                    {isSubmitting ? 'Reprise en cours...' : 'Reprendre'}
                  </button>
                  <button
                    type="button"
                    onClick={() => setCancelDialogOpen(true)}
                    disabled={!canCancel}
                    className="inline-flex items-center gap-1.5 rounded border border-deep bg-deep px-4 py-2 text-sm font-semibold text-mist hover:bg-deep/80 focus:outline-none focus:ring-2 focus:ring-cyan disabled:cursor-not-allowed disabled:opacity-60"
                    data-testid="run-cancel-button"
                  >
                    <Ban className="h-4 w-4" aria-hidden="true" />
                    Annuler la session
                  </button>
                </div>
              </div>
              {outcome.kind !== 'idle' && (
                <p className="text-xs text-cyan" role="status" data-testid="run-control-outcome">
                  {outcome.message}
                </p>
              )}
            </section>
          )}

          {showConsole && (
            <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
              <section className="space-y-4" aria-labelledby="run-agents-heading">
                <div>
                  <h2
                    id="run-agents-heading"
                    className="text-sm font-bold uppercase tracking-wide text-mist"
                  >
                    Agents spécialisés
                  </h2>
                  <p className="mt-1 text-xs text-teal">États dérivés des phases du contrat</p>
                </div>
                <div className="grid gap-4 sm:grid-cols-2" data-testid="run-agent-grid">
                  {displayedCards.map((agent) => (
                    <AgentCard key={agent.key} agent={agent} />
                  ))}
                </div>
              </section>
              <ActivityLog entries={activityEntries} />
            </div>
          )}

          {isCancelDialogOpen && (
            <RunCancelDialog
              isSubmitting={isSubmitting}
              onCancel={() => setCancelDialogOpen(false)}
              onConfirm={() => void handleConfirmCancel()}
            />
          )}
        </div>
      </div>
    </div>
  )
}
