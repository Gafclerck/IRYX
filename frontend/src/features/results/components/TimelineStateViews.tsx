import { Link } from 'react-router-dom'
import { AlertTriangle, ArrowLeft, DatabaseZap, ShieldAlert } from 'lucide-react'
import { EMPTY_TIMELINE_DETAIL, EMPTY_TIMELINE_MESSAGE } from '../constants'

export interface TimelineLoadingSkeletonProps {
  readonly label?: string
}

/** État de chargement : squelettes linéaires pendant la transition de bloc. */
export function TimelineLoadingSkeleton({
  label = 'Chargement de la chronologie',
}: TimelineLoadingSkeletonProps) {
  return (
    <div
      className="animate-pulse space-y-2 rounded-lg border border-deep bg-deep/10 p-4"
      role="status"
      aria-label={label}
      data-testid="timeline-loading"
    >
      <div className="h-10 rounded bg-deep/40" />
      <div className="h-10 rounded bg-deep/40" />
      <div className="h-10 rounded bg-deep/40" />
      <span className="sr-only">{label}</span>
    </div>
  )
}

export interface TimelineEmptyStateProps {
  readonly onResetFilters: () => void
}

/** État vide : aucun événement pour les critères transmis au serveur. */
export function TimelineEmptyState({ onResetFilters }: TimelineEmptyStateProps) {
  return (
    <div
      className="flex flex-col items-center gap-3 rounded-lg border border-deep bg-deep/10 p-10 text-center"
      data-testid="timeline-empty-state"
    >
      <DatabaseZap className="h-10 w-10 text-teal" aria-hidden="true" />
      <h2 className="text-base font-bold uppercase tracking-wider text-mist">
        {EMPTY_TIMELINE_MESSAGE}
      </h2>
      <p className="text-sm text-teal">{EMPTY_TIMELINE_DETAIL}</p>
      <button
        type="button"
        onClick={onResetFilters}
        className="inline-flex items-center gap-1.5 rounded border border-teal bg-deep px-4 py-2 text-sm font-semibold text-mist hover:bg-deep/80 focus:outline-none focus:ring-2 focus:ring-cyan"
        data-testid="timeline-empty-reset"
      >
        <ArrowLeft className="h-4 w-4 text-cyan" aria-hidden="true" />
        Réinitialiser les filtres
      </button>
    </div>
  )
}

export interface TimelineErrorStateProps {
  readonly message: string | null
  readonly onRetry: () => void
}

/** État d'erreur : réactualisation explicite de la tranche courante. */
export function TimelineErrorState({ message, onRetry }: TimelineErrorStateProps) {
  return (
    <div
      className="space-y-3 rounded-lg border border-deep bg-deep/40 p-6"
      role="alert"
      data-testid="timeline-error-state"
    >
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-cyan" aria-hidden="true" />
        <div className="space-y-1">
          <h2 className="text-sm font-bold uppercase tracking-wide text-mist">
            Erreur de chargement de la chronologie
          </h2>
          <p className="text-sm text-mist/90">{message}</p>
        </div>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="rounded border border-cyan bg-cyan px-3 py-1.5 text-xs font-bold text-ink hover:bg-cyan/80 focus:outline-none focus:ring-2 focus:ring-cyan"
        data-testid="timeline-retry-button"
      >
        Réessayer
      </button>
    </div>
  )
}

/** Accès refusé (403) : la liste est masquée et aucune donnée n'est exposée. */
export function TimelineForbiddenState() {
  return (
    <div
      className="space-y-3 rounded-lg border border-deep bg-deep/40 p-6"
      role="alert"
      data-testid="timeline-forbidden-state"
    >
      <div className="flex items-start gap-3">
        <ShieldAlert className="mt-0.5 h-5 w-5 flex-shrink-0 text-cyan" aria-hidden="true" />
        <div className="space-y-1">
          <h2 className="text-sm font-bold uppercase tracking-wide text-mist">Accès refusé</h2>
          <p className="text-sm text-mist/90">
            Vous n'avez pas accès à la chronologie de ce dossier.
          </p>
        </div>
      </div>
      <Link
        to="/cases"
        className="inline-flex items-center gap-2 rounded border border-teal bg-deep px-3 py-1.5 text-xs font-semibold text-mist hover:bg-deep/80 focus:outline-none focus:ring-2 focus:ring-cyan"
        data-testid="timeline-forbidden-back"
      >
        <ArrowLeft className="h-3.5 w-3.5 text-cyan" aria-hidden="true" />
        Retour aux dossiers
      </Link>
    </div>
  )
}

export interface TimelinePartialBannerProps {
  readonly failedPhases: readonly string[]
}

/** Bandeau de résultats partiels, déclenché uniquement par une phase failed du contrat. */
export function TimelinePartialBanner({ failedPhases }: TimelinePartialBannerProps) {
  if (failedPhases.length === 0) return null

  return (
    <div
      className="flex items-start gap-3 rounded-lg border border-deep bg-deep/40 p-4"
      role="alert"
      data-testid="timeline-partial-banner"
    >
      <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-cyan" aria-hidden="true" />
      <p className="text-sm text-mist" data-testid="timeline-partial-message">
        RÉSULTATS PARTIELS : la phase « {failedPhases.join(', ')} » a échoué. Certaines observations
        peuvent manquer.
      </p>
    </div>
  )
}

export interface TimelineUnknownStateProps {
  readonly statusLabel: string
}

/** Statut non répertorié : code brut conservé, sans blocage de la consultation. */
export function TimelineUnknownState({ statusLabel }: TimelineUnknownStateProps) {
  return (
    <div
      className="rounded-lg border border-deep bg-deep/40 p-3 text-sm text-mist"
      role="status"
      data-testid="timeline-unknown-state"
    >
      {statusLabel} — la chronologie reste consultable.
    </div>
  )
}
