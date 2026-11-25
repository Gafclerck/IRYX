import { Link } from 'react-router-dom'
import { AlertTriangle, ArrowLeft, LoaderCircle, ShieldAlert, WifiOff } from 'lucide-react'
import { TO_REALIGN } from '../constants'

export interface RunLoadingSkeletonProps {
  readonly label?: string
}

/** État de chargement initial de la console. */
export function RunLoadingSkeleton({
  label = 'Initialisation de la session d’exécution',
}: RunLoadingSkeletonProps) {
  return (
    <div
      className="animate-pulse space-y-4 rounded-lg border border-deep bg-deep/10 p-6"
      role="status"
      aria-label={label}
      data-testid="run-page-loading"
    >
      <div className="h-6 w-1/3 rounded bg-deep" />
      <div className="h-24 rounded bg-deep/40" />
      <span className="sr-only">{label}</span>
    </div>
  )
}

/** Session en attente de prise en charge : la scrutation reste active. */
export function RunWaitingState({ isFetching = false }: { readonly isFetching?: boolean }) {
  return (
    <div
      className="space-y-2 rounded-lg border border-deep bg-deep/10 p-4"
      role="status"
      data-testid="run-waiting-state"
    >
      <div className="flex items-center gap-2 text-sm font-semibold text-teal">
        <LoaderCircle
          className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`}
          aria-hidden="true"
        />
        Initialisation de la session d'exécution
      </div>
      <p className="text-xs text-mist/80">Les agents sont en attente de prise en charge.</p>
    </div>
  )
}

/** Session suspendue : la reprise est la seule commande disponible par contrat. */
export function RunPausedState() {
  return (
    <div
      className="rounded-lg border border-deep bg-deep/40 p-4 text-sm text-mist"
      role="status"
      data-testid="run-paused-state"
    >
      Traitement suspendu. Utilisez « Reprendre » pour poursuivre la session.
    </div>
  )
}

/** Échec d'un agent : les autres agents poursuivent l'exécution. */
export function RunPartialFailureBanner() {
  return (
    <div
      className="flex items-start gap-3 rounded-lg border border-deep bg-deep/40 p-4"
      role="alert"
      data-testid="run-partial-failure-banner"
    >
      <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-cyan" aria-hidden="true" />
      <div className="space-y-1">
        <h2 className="text-sm font-bold uppercase tracking-wide text-mist">Échec partiel</h2>
        <p className="text-xs text-mist/90">
          Un agent est en échec. Les autres agents poursuivent l’exécution ; le suivi reste actif.
        </p>
      </div>
    </div>
  )
}

export interface RunCompletedStateProps {
  readonly caseId: string
}

/** État terminal nominal : accès mis en avant aux résultats (Story F4.5). */
export function RunCompletedState({ caseId }: RunCompletedStateProps) {
  return (
    <div
      className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-teal bg-deep p-4"
      role="status"
      data-testid="run-completed-state"
    >
      <div>
        <h2 className="text-sm font-bold uppercase tracking-wide text-mist">Session terminée</h2>
        <p className="mt-1 text-xs text-mist/80">
          L’exécution est achevée. La scrutation est arrêtée.
        </p>
      </div>
      <Link
        to={`/cases/${caseId}/results`}
        className="inline-flex items-center gap-2 rounded border border-cyan bg-cyan px-4 py-2 text-sm font-bold text-ink hover:bg-cyan/80 focus:outline-none focus:ring-2 focus:ring-cyan"
        data-testid="run-see-results-link"
      >
        Voir les résultats
      </Link>
    </div>
  )
}

/** Statut `canceled` demandé par la story mais absent du contrat. */
export function RunCanceledState() {
  return (
    <div
      className="space-y-1 rounded-lg border border-deep bg-deep/40 p-4"
      role="status"
      data-testid="run-canceled-state"
    >
      <h2 className="text-sm font-bold uppercase tracking-wide text-mist">Session annulée</h2>
      <p className="text-xs text-mist/80">Statut reçu du serveur : ANNULÉ — {TO_REALIGN}</p>
    </div>
  )
}

export function RunFailedState() {
  return (
    <div
      className="rounded-lg border border-deep bg-deep/40 p-4"
      role="alert"
      data-testid="run-failed-state"
    >
      <h2 className="text-sm font-bold uppercase tracking-wide text-mist">Session en échec</h2>
      <p className="mt-1 text-xs text-mist/80">Diagnostic : {TO_REALIGN}</p>
    </div>
  )
}

export interface RunErrorStateProps {
  readonly message: string | null
  readonly onRetry: () => void
}

/** Erreur de service (5xx) avec action de reprise de la consultation. */
export function RunErrorState({ message, onRetry }: RunErrorStateProps) {
  return (
    <div
      className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-deep bg-deep/40 p-4"
      role="alert"
      data-testid="run-error-state"
    >
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-cyan" aria-hidden="true" />
        <div className="space-y-1">
          <h2 className="text-sm font-bold uppercase tracking-wide text-mist">
            Erreur de consultation
          </h2>
          <p className="text-xs text-mist/90">{message}</p>
        </div>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="rounded border border-teal bg-deep px-3 py-1.5 text-xs font-semibold text-cyan hover:bg-deep/80 focus:outline-none focus:ring-2 focus:ring-cyan"
        data-testid="run-retry-button"
      >
        Réessayer
      </button>
    </div>
  )
}

export interface RunNetworkCutoffStateProps {
  readonly onRetryConnection: () => void
}

/** DP-05 : la scrutation est arrêtée après une coupure prolongée. */
export function RunNetworkCutoffState({ onRetryConnection }: RunNetworkCutoffStateProps) {
  return (
    <div
      className="space-y-3 rounded-lg border border-deep bg-deep/40 p-4"
      role="alert"
      data-testid="run-network-cutoff-state"
    >
      <div className="flex items-start gap-3">
        <WifiOff className="mt-0.5 h-5 w-5 flex-shrink-0 text-cyan" aria-hidden="true" />
        <div className="space-y-1">
          <h2 className="text-sm font-bold uppercase tracking-wide text-mist">
            Connexion interrompue
          </h2>
          <p className="text-xs text-mist/90">
            La scrutation a été arrêtée (DP-05). Le seuil de coupure reste à décider.
          </p>
        </div>
      </div>
      <button
        type="button"
        onClick={onRetryConnection}
        className="rounded border border-teal bg-deep px-3 py-1.5 text-xs font-semibold text-cyan hover:bg-deep/80 focus:outline-none focus:ring-2 focus:ring-cyan"
        data-testid="run-retry-connection-button"
      >
        Réessayer la connexion
      </button>
    </div>
  )
}

/** Accès refusé (403) : la console n'expose aucune donnée de la session. */
export function RunForbiddenState() {
  return (
    <div
      className="space-y-3 rounded-lg border border-deep bg-deep/40 p-4"
      role="alert"
      data-testid="run-forbidden-state"
    >
      <div className="flex items-start gap-3">
        <ShieldAlert className="mt-0.5 h-5 w-5 flex-shrink-0 text-cyan" aria-hidden="true" />
        <div className="space-y-1">
          <h2 className="text-sm font-bold uppercase tracking-wide text-mist">Accès refusé</h2>
          <p className="text-xs text-mist/90">
            Vous n'avez pas accès à cette session d'investigation.
          </p>
        </div>
      </div>
      <Link
        to="/cases"
        className="inline-flex items-center gap-2 rounded border border-teal bg-deep px-3 py-1.5 text-xs font-semibold text-cyan hover:bg-deep/80 focus:outline-none focus:ring-2 focus:ring-cyan"
        data-testid="run-forbidden-back-to-cases"
      >
        <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
        Retour aux dossiers
      </Link>
    </div>
  )
}
