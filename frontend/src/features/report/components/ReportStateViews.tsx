import { Link } from 'react-router-dom'
import { AlertTriangle, ArrowLeft, FileX2, LoaderCircle, ShieldAlert, WifiOff } from 'lucide-react'
import {
  REPORT_EMPTY_MESSAGE,
  REPORT_ERROR_FALLBACK_MESSAGE,
  REPORT_FORBIDDEN_MESSAGE,
  REPORT_GENERATING_MESSAGE,
  REPORT_NETWORK_CUTOFF_MESSAGE,
  REPORT_RETRY_CONNECTION_LABEL,
  REPORT_RETRY_GENERATION_LABEL,
  REPORT_UNKNOWN_DISABLED_NOTE,
} from '../constants'

/** État de chargement initial : récupération du rapport courant. */
export function ReportLoadingState() {
  return (
    <div
      className="animate-pulse space-y-3 rounded-lg border border-deep bg-deep/10 p-6"
      role="status"
      aria-label="Chargement du rapport"
      data-testid="report-loading"
    >
      <div className="h-8 w-1/3 rounded bg-deep" />
      <div className="h-48 rounded bg-deep/40" />
      <span className="sr-only">Chargement du rapport</span>
    </div>
  )
}

/** État vide : aucun rapport finalisé, le bouton principal reste actif. */
export function ReportEmptyState() {
  return (
    <div
      className="flex flex-col items-center gap-3 rounded-lg border border-deep bg-deep/10 p-10 text-center"
      data-testid="report-empty-state"
    >
      <FileX2 className="h-10 w-10 text-teal" aria-hidden="true" />
      <h2 className="text-base font-bold uppercase tracking-wider text-mist">
        Aucun rapport finalisé
      </h2>
      <p className="max-w-lg text-sm text-teal">{REPORT_EMPTY_MESSAGE}</p>
    </div>
  )
}

/** Génération en cours : l'avancement est actualisé par scrutation (ADR-0008). */
export function ReportGeneratingState({ isFetching }: { readonly isFetching?: boolean }) {
  return (
    <div
      className="flex flex-col items-center gap-3 rounded-lg border border-deep bg-deep/10 p-10 text-center"
      role="status"
      aria-live="polite"
      data-testid="report-generating-state"
    >
      <LoaderCircle className="h-8 w-8 animate-spin text-cyan" aria-hidden="true" />
      <p className="text-sm font-semibold uppercase tracking-wider text-mist">
        Génération du rapport
      </p>
      <p className="text-sm text-teal">{REPORT_GENERATING_MESSAGE}</p>
      {isFetching && <span className="sr-only">Scrutation en cours</span>}
    </div>
  )
}

export interface ReportFailureStateProps {
  readonly message: string | null
  readonly onRetry: () => void
}

/** Échec signalé par le back-end : motif renvoyé et relance immédiate. */
export function ReportGenerationFailedState({ message, onRetry }: ReportFailureStateProps) {
  return (
    <div
      className="space-y-3 rounded-lg border border-deep bg-deep/40 p-6"
      role="alert"
      data-testid="report-generation-failed"
    >
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-cyan" aria-hidden="true" />
        <div className="space-y-1">
          <h2 className="text-sm font-bold uppercase tracking-wide text-mist">
            Échec de génération du rapport
          </h2>
          <p className="text-sm text-mist/90" data-testid="report-failure-detail">
            {message || REPORT_ERROR_FALLBACK_MESSAGE}
          </p>
        </div>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="rounded border border-cyan bg-cyan px-3 py-1.5 text-xs font-bold text-ink hover:bg-cyan/80 focus:outline-none focus:ring-2 focus:ring-cyan"
        data-testid="report-retry-generation"
      >
        {REPORT_RETRY_GENERATION_LABEL}
      </button>
    </div>
  )
}

/** Erreur technique de consultation ou de demande de compilation. */
export function ReportErrorState({ message, onRetry }: ReportFailureStateProps) {
  return (
    <div
      className="space-y-3 rounded-lg border border-deep bg-deep/40 p-6"
      role="alert"
      data-testid="report-error-state"
    >
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-cyan" aria-hidden="true" />
        <p className="text-sm text-mist" data-testid="report-error-message">
          {message || REPORT_ERROR_FALLBACK_MESSAGE}
        </p>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="rounded border border-cyan bg-cyan px-3 py-1.5 text-xs font-bold text-ink hover:bg-cyan/80 focus:outline-none focus:ring-2 focus:ring-cyan"
        data-testid="report-retry"
      >
        Réessayer
      </button>
    </div>
  )
}

/** Accès refusé (403) : aucune donnée de rapport n'est exposée. */
export function ReportForbiddenState() {
  return (
    <div
      className="space-y-3 rounded-lg border border-deep bg-deep/40 p-6"
      role="alert"
      data-testid="report-forbidden-state"
    >
      <div className="flex items-start gap-3">
        <ShieldAlert className="mt-0.5 h-5 w-5 flex-shrink-0 text-cyan" aria-hidden="true" />
        <div className="space-y-1">
          <h2 className="text-sm font-bold uppercase tracking-wide text-mist">Accès refusé</h2>
          <p className="text-sm text-mist/90">{REPORT_FORBIDDEN_MESSAGE}</p>
        </div>
      </div>
      <Link
        to="/cases"
        className="inline-flex items-center gap-2 rounded border border-teal bg-deep px-3 py-1.5 text-xs font-semibold text-mist hover:bg-deep/80 focus:outline-none focus:ring-2 focus:ring-cyan"
        data-testid="report-forbidden-back"
      >
        <ArrowLeft className="h-3.5 w-3.5 text-cyan" aria-hidden="true" />
        Retour aux dossiers
      </Link>
    </div>
  )
}

/** Coupure prolongée (DP-05) : la scrutation est arrêtée. */
export function ReportNetworkCutoffState({ onRetry }: { readonly onRetry: () => void }) {
  return (
    <div
      className="space-y-3 rounded-lg border border-deep bg-deep/40 p-6"
      role="alert"
      data-testid="report-network-cutoff"
    >
      <div className="flex items-start gap-3">
        <WifiOff className="mt-0.5 h-5 w-5 flex-shrink-0 text-cyan" aria-hidden="true" />
        <p className="text-sm text-mist" data-testid="report-network-message">
          {REPORT_NETWORK_CUTOFF_MESSAGE}
        </p>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="rounded border border-cyan bg-cyan px-3 py-1.5 text-xs font-bold text-ink hover:bg-cyan/80 focus:outline-none focus:ring-2 focus:ring-cyan"
        data-testid="report-retry-connection"
      >
        {REPORT_RETRY_CONNECTION_LABEL}
      </button>
    </div>
  )
}

/** Statut non répertorié : code brut conservé, sans blocage de l'affichage. */
export function ReportUnknownState({ statusLabel }: { readonly statusLabel: string }) {
  return (
    <div
      className="space-y-1 rounded-lg border border-deep bg-deep/40 p-4"
      role="status"
      data-testid="report-unknown-state"
    >
      <p className="text-sm font-semibold text-mist" data-testid="report-unknown-label">
        {statusLabel}
      </p>
      <p className="text-xs text-teal">{REPORT_UNKNOWN_DISABLED_NOTE}</p>
    </div>
  )
}
