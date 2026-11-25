import { Link } from 'react-router-dom'
import { Activity, AlertTriangle, RefreshCw, ShieldCheck, Wrench } from 'lucide-react'
import { formatInvestigationPhase, formatInvestigationStatus } from '../constants'

export interface PlanValidatedViewProps {
  readonly caseId: string
}

/** État validé (lecture seule) après confirmation et succès de la porte H1. */
export function PlanValidatedView({ caseId }: PlanValidatedViewProps) {
  return (
    <section
      className="space-y-4 rounded-lg border border-teal bg-deep/20 p-6"
      data-testid="plan-validated-view"
    >
      <div className="flex items-start gap-3">
        <ShieldCheck className="mt-0.5 h-6 w-6 flex-shrink-0 text-cyan" aria-hidden="true" />
        <div className="space-y-2">
          <h2 className="text-base font-bold uppercase tracking-wide text-mist">Validé</h2>
          <p className="text-sm text-mist/90">
            La porte H1 est franchie. Le plan est en lecture seule et ne peut plus être modifié.
          </p>
        </div>
      </div>
      <Link
        to={`/cases/${caseId}/run`}
        className="inline-flex items-center gap-2 rounded border border-cyan bg-cyan px-4 py-2 text-sm font-bold text-ink hover:bg-cyan/80 focus:outline-none focus:ring-2 focus:ring-cyan"
        data-testid="plan-see-run-link"
      >
        <Activity className="h-4 w-4" aria-hidden="true" />
        Voir le suivi
      </Link>
    </section>
  )
}

/** État de replanification après refus : aucune action de validation tant qu'un nouveau plan n'existe pas. */
export function PlanReplanificationView() {
  return (
    <section
      className="flex items-start gap-3 rounded-lg border border-deep bg-deep/20 p-6"
      role="status"
      data-testid="plan-replanification-view"
    >
      <Wrench className="mt-0.5 h-6 w-6 flex-shrink-0 text-cyan" aria-hidden="true" />
      <div className="space-y-2">
        <h2 className="text-base font-bold uppercase tracking-wide text-mist">
          REFUSÉ — REPLANIFICATION EN COURS
        </h2>
        <p className="text-sm text-mist/90">
          Le plan a été refusé et renvoyé au Planner. Aucune validation n'est disponible tant que le
          back-end n'a pas produit un nouveau plan.
        </p>
      </div>
    </section>
  )
}

export interface PlanDecisionErrorViewProps {
  readonly message: string
  readonly onRetry: () => void
}

/** Erreur serveur ou réseau pendant l'arbitrage : le plan reste prêt et la saisie est conservée. */
export function PlanDecisionErrorView({ message, onRetry }: PlanDecisionErrorViewProps) {
  return (
    <section
      className="space-y-3 rounded-lg border border-deep bg-deep/40 p-6"
      role="alert"
      data-testid="plan-decision-error"
    >
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-6 w-6 flex-shrink-0 text-cyan" aria-hidden="true" />
        <div className="space-y-1">
          <h2 className="text-base font-bold uppercase tracking-wide text-mist">
            ÉCHEC DE LA TRANSMISSION
          </h2>
          <p className="text-sm text-mist/90" data-testid="plan-decision-error-message">
            {message}
          </p>
          <p className="text-sm text-teal">
            Le plan reste prêt. Aucune validation n'a été enregistrée.
          </p>
        </div>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="inline-flex items-center gap-2 rounded border border-teal bg-deep px-3 py-1.5 text-xs font-semibold text-cyan hover:bg-deep/80 focus:outline-none focus:ring-2 focus:ring-cyan"
        data-testid="plan-decision-retry"
      >
        <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
        Réessayer
      </button>
    </section>
  )
}

export interface PlanConflictViewProps {
  readonly status: string | null
  readonly phase: string | null
  readonly message: string | null
  readonly onRefresh: () => void
}

/** Conflit 409 : l'état réel renvoyé par le serveur est affiché, sans validation locale. */
export function PlanConflictView({ status, phase, message, onRefresh }: PlanConflictViewProps) {
  return (
    <section
      className="space-y-3 rounded-lg border border-deep bg-deep/40 p-6"
      role="alert"
      data-testid="plan-conflict-view"
    >
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-6 w-6 flex-shrink-0 text-cyan" aria-hidden="true" />
        <div className="space-y-2">
          <h2 className="text-base font-bold uppercase tracking-wide text-mist">
            CONFLIT — ÉTAT RÉEL DU SERVEUR
          </h2>
          <p className="text-sm text-mist/90" data-testid="plan-conflict-status">
            Statut renvoyé : {formatInvestigationStatus(status).label}
          </p>
          {phase && (
            <p className="text-sm text-mist/90" data-testid="plan-conflict-phase">
              Phase renvoyée : {formatInvestigationPhase(phase).label}
            </p>
          )}
          {message && (
            <p className="text-sm text-teal" data-testid="plan-conflict-message">
              {message}
            </p>
          )}
          <p className="text-sm text-mist/80">
            Aucune validation n'a été enregistrée par le front.
          </p>
        </div>
      </div>
      <button
        type="button"
        onClick={onRefresh}
        className="inline-flex items-center gap-2 rounded border border-teal bg-deep px-3 py-1.5 text-xs font-semibold text-cyan hover:bg-deep/80 focus:outline-none focus:ring-2 focus:ring-cyan"
        data-testid="plan-conflict-refresh"
      >
        <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
        Actualiser le plan
      </button>
    </section>
  )
}
