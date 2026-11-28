import { AlertTriangle, FileSearch, LoaderCircle, ShieldAlert, WifiOff } from 'lucide-react'
import { Link } from 'react-router-dom'
import {
  REVIEW_EMPTY_MESSAGE,
  REVIEW_ERROR_FALLBACK_MESSAGE,
  REVIEW_FORBIDDEN_MESSAGE,
  REVIEW_NETWORK_CUTOFF_MESSAGE,
  REVIEW_RETRY_CONNECTION_LABEL,
  REVIEW_RETRY_LABEL,
  REVIEW_UNKNOWN_DISABLED_NOTE,
} from '../constants'

export function ReviewLoadingState() {
  return (
    <div
      className="animate-pulse space-y-3 rounded-lg border border-deep bg-deep/10 p-6"
      role="status"
      aria-label="Chargement des findings"
      data-testid="review-loading"
    >
      <div className="h-8 w-1/3 rounded bg-deep" />
      <div className="h-24 rounded bg-deep/40" />
      <div className="h-24 rounded bg-deep/40" />
    </div>
  )
}

export function ReviewEmptyState() {
  return (
    <div
      className="flex flex-col items-center gap-3 rounded-lg border border-deep bg-deep/10 p-10 text-center"
      data-testid="review-empty-state"
    >
      <FileSearch className="h-10 w-10 text-teal" aria-hidden="true" />
      <p className="text-sm text-teal">{REVIEW_EMPTY_MESSAGE}</p>
    </div>
  )
}

export function ReviewForbiddenState() {
  return (
    <div
      className="space-y-3 rounded-lg border border-deep bg-deep/40 p-6"
      role="alert"
      data-testid="review-forbidden-state"
    >
      <div className="flex items-start gap-3">
        <ShieldAlert className="mt-0.5 h-5 w-5 flex-shrink-0 text-cyan" aria-hidden="true" />
        <div className="space-y-1">
          <h2 className="text-sm font-bold uppercase tracking-wide text-mist">Accès refusé</h2>
          <p className="text-sm text-mist/90">{REVIEW_FORBIDDEN_MESSAGE}</p>
        </div>
      </div>
      <Link
        to="/cases"
        className="inline-flex items-center gap-2 rounded border border-teal bg-deep px-3 py-1.5 text-xs font-semibold text-mist hover:bg-deep/80 focus:outline-none focus:ring-2 focus:ring-cyan"
      >
        Retour aux dossiers
      </Link>
    </div>
  )
}

export function ReviewErrorState({
  message,
  onRetry,
  isNetworkCutoff,
}: {
  readonly message: string | null
  readonly onRetry: () => void
  readonly isNetworkCutoff: boolean
}) {
  const Icon = isNetworkCutoff ? WifiOff : AlertTriangle
  return (
    <div
      className="space-y-3 rounded-lg border border-deep bg-deep/40 p-6"
      role="alert"
      data-testid="review-error-state"
    >
      <div className="flex items-start gap-3">
        <Icon className="mt-0.5 h-5 w-5 flex-shrink-0 text-cyan" aria-hidden="true" />
        <p className="text-sm text-mist" data-testid="review-error-message">
          {message ||
            (isNetworkCutoff ? REVIEW_NETWORK_CUTOFF_MESSAGE : REVIEW_ERROR_FALLBACK_MESSAGE)}
        </p>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="rounded border border-cyan bg-cyan px-3 py-1.5 text-xs font-bold text-ink hover:bg-cyan/80 focus:outline-none focus:ring-2 focus:ring-cyan"
        data-testid="review-retry"
      >
        {isNetworkCutoff ? REVIEW_RETRY_CONNECTION_LABEL : REVIEW_RETRY_LABEL}
      </button>
    </div>
  )
}

export function ReviewUnknownState({ statusLabel }: { readonly statusLabel: string }) {
  return (
    <div
      className="space-y-1 rounded-lg border border-deep bg-deep/40 p-4"
      role="status"
      data-testid="review-unknown-state"
    >
      <p className="text-sm font-semibold text-mist">{statusLabel}</p>
      <p className="text-xs text-teal">{REVIEW_UNKNOWN_DISABLED_NOTE}</p>
    </div>
  )
}

export function ReviewFetchingBadge() {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded border border-deep bg-deep/20 px-3 py-1.5 text-xs font-semibold text-cyan"
      role="status"
      data-testid="review-fetching-badge"
    >
      <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
      CHARGEMENT
    </span>
  )
}
