import { Link } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowLeft,
  Database,
  LoaderCircle,
  ShieldAlert,
  WifiOff,
} from 'lucide-react'

export interface PlanLoadingSkeletonProps {
  readonly label?: string
}

/** État de chargement initial du plan et du dossier. */
export function PlanLoadingSkeleton({ label = 'Chargement du plan' }: PlanLoadingSkeletonProps) {
  return (
    <div
      className="animate-pulse space-y-4 rounded-lg border border-deep bg-deep/10 p-6"
      role="status"
      aria-label={label}
      data-testid="plan-page-loading"
    >
      <div className="h-6 w-1/3 rounded bg-deep" />
      <div className="h-24 rounded bg-deep/40" />
      <div className="h-24 rounded bg-deep/40" />
      <span className="sr-only">{label}</span>
    </div>
  )
}

export interface PlanPlanningStateProps {
  readonly isFetching?: boolean
}

/** État d'attente : le Planner élabore encore la stratégie (scrutation active). */
export function PlanPlanningState({ isFetching = false }: PlanPlanningStateProps) {
  return (
    <div
      className="flex flex-col items-center gap-3 rounded-lg border border-deep bg-deep/10 p-10 text-center"
      role="status"
      aria-live="polite"
      data-testid="plan-planning-state"
    >
      <LoaderCircle className="h-8 w-8 animate-spin text-cyan" aria-hidden="true" />
      <p className="text-sm font-semibold uppercase tracking-wider text-mist">
        Planification en cours
      </p>
      <p className="text-sm text-teal">Élaboration du plan par le Planner en cours...</p>
      {isFetching && <span className="sr-only">Scrutation en cours</span>}
    </div>
  )
}

export interface PlanEmptyStateProps {
  readonly caseId: string
}

/** État vide : aucun outil forensique applicable aux preuves disponibles. */
export function PlanEmptyState({ caseId }: PlanEmptyStateProps) {
  return (
    <div
      className="flex flex-col items-center gap-4 rounded-lg border border-deep bg-deep/10 p-10 text-center"
      data-testid="plan-empty-state"
    >
      <Database className="h-10 w-10 text-teal" aria-hidden="true" />
      <h2 className="text-base font-bold uppercase tracking-wider text-mist">
        Aucun outil applicable
      </h2>
      <p className="max-w-lg text-sm text-mist/80">
        Aucun outil forensique applicable aux preuves disponibles.
      </p>
      <Link
        to={`/cases/${caseId}/evidence`}
        className="inline-flex items-center gap-2 rounded border border-teal bg-deep px-4 py-2 text-sm font-semibold text-cyan hover:bg-deep/80 focus:outline-none focus:ring-2 focus:ring-cyan"
        data-testid="plan-empty-back-to-evidence"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        <span>Retour aux preuves</span>
      </Link>
    </div>
  )
}

export interface PlanErrorStateProps {
  readonly message: string | null
  readonly onRetry: () => void
}

/** État d'erreur de l'agent Planner ou du service, avec action de reprise. */
export function PlanErrorState({ message, onRetry }: PlanErrorStateProps) {
  return (
    <div
      className="space-y-3 rounded-lg border border-deep bg-deep/40 p-6"
      role="alert"
      data-testid="plan-error-state"
    >
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-6 w-6 flex-shrink-0 text-cyan" aria-hidden="true" />
        <div className="space-y-1">
          <h2 className="text-base font-bold uppercase tracking-wide text-mist">
            Échec de l’agent Planner
          </h2>
          <p className="text-sm text-mist/90">
            {message || "Le Planner n'a pas pu proposer de plan d'investigation."}
          </p>
        </div>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="inline-flex items-center gap-1.5 rounded border border-teal bg-deep px-3 py-1.5 text-xs font-semibold text-cyan hover:bg-deep/80 focus:outline-none focus:ring-2 focus:ring-cyan"
        aria-label="Réessayer la planification"
        data-testid="plan-retry-button"
      >
        Réessayer
      </button>
    </div>
  )
}

export interface PlanNetworkCutoffStateProps {
  readonly onRetryConnection: () => void
}

/** DP-05 : coupure réseau prolongée, scrutation arrêtée. */
export function PlanNetworkCutoffState({ onRetryConnection }: PlanNetworkCutoffStateProps) {
  return (
    <div
      className="space-y-3 rounded-lg border border-deep bg-deep/40 p-6"
      role="alert"
      data-testid="plan-network-cutoff-state"
    >
      <div className="flex items-start gap-3">
        <WifiOff className="mt-0.5 h-6 w-6 flex-shrink-0 text-cyan" aria-hidden="true" />
        <div className="space-y-1">
          <h2 className="text-base font-bold uppercase tracking-wide text-mist">
            Connexion interrompue
          </h2>
          <p className="text-sm text-mist/90">
            La scrutation a été arrêtée. Reprenez la consultation quand la connexion est rétablie.
          </p>
        </div>
      </div>
      <button
        type="button"
        onClick={onRetryConnection}
        className="inline-flex items-center gap-1.5 rounded border border-teal bg-deep px-3 py-1.5 text-xs font-semibold text-cyan hover:bg-deep/80 focus:outline-none focus:ring-2 focus:ring-cyan"
        data-testid="plan-retry-connection-button"
      >
        Réessayer la connexion
      </button>
    </div>
  )
}

/** État d'accès refusé (403) sur la route du plan. */
export function PlanForbiddenState() {
  return (
    <div
      className="flex flex-col items-start gap-3 rounded-lg border border-deep bg-deep/40 p-6"
      role="alert"
      data-testid="plan-forbidden-state"
    >
      <div className="flex items-start gap-3">
        <ShieldAlert className="mt-0.5 h-6 w-6 flex-shrink-0 text-cyan" aria-hidden="true" />
        <div className="space-y-1">
          <h2 className="text-base font-bold uppercase tracking-wide text-mist">Accès refusé</h2>
          <p className="text-sm text-mist/90">
            Vous n'avez pas accès à ce dossier ni au plan d'investigation associé.
          </p>
        </div>
      </div>
      <Link
        to="/cases"
        className="inline-flex items-center gap-2 rounded border border-teal bg-deep px-3 py-1.5 text-xs font-semibold text-cyan hover:bg-deep/80 focus:outline-none focus:ring-2 focus:ring-cyan"
        data-testid="plan-forbidden-back-to-cases"
      >
        <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
        <span>Retour aux dossiers</span>
      </Link>
    </div>
  )
}
