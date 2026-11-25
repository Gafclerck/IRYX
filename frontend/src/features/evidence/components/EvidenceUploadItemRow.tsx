import { FileText, Loader2, CheckCircle2, AlertTriangle, XCircle, RotateCw, X } from 'lucide-react'
import type { EvidenceUploadItem } from '../types'
import { formatFileSize } from '../utils/fileValidation'

export interface EvidenceUploadItemRowProps {
  readonly item: EvidenceUploadItem
  readonly onCancel: (id: string) => void
  readonly onRetry: (id: string) => void
}

/**
 * Ligne individuelle de suivi de téléversement d'une preuve (Story F3.1).
 *
 * RÈGLES DE CONCEPTION (FR-EVI-01, Section 3.4 de 11-ecrans-et-routes.md) :
 * 1. Affiche le nom d'origine du fichier et sa volumétrie formatée.
 * 2. Jauge de progression calculée en temps réel avec pourcentage.
 * 3. Double signalement non chromatique (libellé majuscule + icône lucide-react).
 * 4. Bouton individuel « Annuler » permettant d'interrompre la requête XHR en cours.
 * 5. Bouton « Réessayer » en cas d'échec ou d'interruption.
 * 6. Statut nominal post-transfert : « en attente d'ingestion » affiché tel quel.
 * 7. Aucune couleur en dur, palette Tailwind stricte (ink, deep, teal, cyan, mist).
 */
export function EvidenceUploadItemRow({ item, onCancel, onRetry }: EvidenceUploadItemRowProps) {
  const isUploading = item.status === 'uploading'
  const isSuccess = item.status === 'success'
  const isError = item.status === 'error'
  const isAborted = item.status === 'aborted'
  const isPending = item.status === 'pending'

  return (
    <li
      className="flex flex-col space-y-2 rounded-lg border border-deep bg-ink p-4 transition-colors hover:border-teal/50"
      data-testid={`evidence-upload-item-${item.id}`}
      aria-label={`Preuve ${item.name}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Nom du fichier et taille */}
        <div className="flex items-center space-x-3 min-w-0 flex-1">
          <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded bg-deep text-cyan">
            <FileText className="h-5 w-5" aria-hidden="true" />
          </div>
          <div className="min-w-0 flex-1">
            <p
              className="truncate text-sm font-semibold text-mist"
              title={item.name}
              data-testid={`evidence-name-${item.id}`}
            >
              {item.name}
            </p>
            <p className="text-xs text-mist/70" data-testid={`evidence-size-${item.id}`}>
              {formatFileSize(item.size)}
            </p>
          </div>
        </div>

        {/* Indicateur de statut non chromatique et actions */}
        <div className="flex items-center space-x-3">
          {isPending && (
            <span
              className="inline-flex items-center gap-1.5 rounded bg-deep px-2.5 py-1 text-xs font-semibold uppercase tracking-wider text-mist"
              data-testid={`evidence-status-${item.id}`}
            >
              <Loader2 className="h-3.5 w-3.5 animate-spin text-teal" aria-hidden="true" />
              <span>EN ATTENTE</span>
            </span>
          )}

          {isUploading && (
            <div className="flex items-center space-x-2">
              <span
                className="inline-flex items-center gap-1.5 rounded bg-deep px-2.5 py-1 text-xs font-semibold uppercase tracking-wider text-cyan"
                data-testid={`evidence-status-${item.id}`}
              >
                <Loader2 className="h-3.5 w-3.5 animate-spin text-cyan" aria-hidden="true" />
                <span>EN COURS ({item.progress}%)</span>
              </span>
              <button
                type="button"
                onClick={() => onCancel(item.id)}
                className="inline-flex items-center gap-1 rounded border border-deep bg-deep/40 px-2 py-1 text-xs font-medium text-mist hover:border-cyan hover:text-cyan focus:outline-none focus:ring-2 focus:ring-cyan"
                aria-label={`Annuler le téléversement de ${item.name}`}
                data-testid={`evidence-cancel-btn-${item.id}`}
              >
                <X className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Annuler</span>
              </button>
            </div>
          )}

          {isSuccess && (
            <div className="flex flex-col items-end">
              <span
                className="inline-flex items-center gap-1.5 rounded bg-deep px-2.5 py-1 text-xs font-semibold uppercase tracking-wider text-teal"
                data-testid={`evidence-status-${item.id}`}
              >
                <CheckCircle2 className="h-3.5 w-3.5 text-teal" aria-hidden="true" />
                <span>EN ATTENTE D'INGESTION</span>
              </span>
              <span className="text-[11px] text-mist/70 italic mt-0.5">en attente d'ingestion</span>
            </div>
          )}

          {isError && (
            <div className="flex items-center space-x-2">
              <span
                className="inline-flex items-center gap-1.5 rounded bg-deep px-2.5 py-1 text-xs font-semibold uppercase tracking-wider text-mist border border-teal"
                data-testid={`evidence-status-${item.id}`}
              >
                <AlertTriangle className="h-3.5 w-3.5 text-cyan" aria-hidden="true" />
                <span>ÉCHEC DE TRANSFERT</span>
              </span>
              <button
                type="button"
                onClick={() => onRetry(item.id)}
                className="inline-flex items-center gap-1 rounded border border-teal bg-deep px-2.5 py-1 text-xs font-medium text-cyan hover:bg-deep/80 focus:outline-none focus:ring-2 focus:ring-cyan"
                aria-label={`Réessayer le téléversement de ${item.name}`}
                data-testid={`evidence-retry-btn-${item.id}`}
              >
                <RotateCw className="h-3.5 w-3.5 text-cyan" aria-hidden="true" />
                <span>Réessayer</span>
              </button>
            </div>
          )}

          {isAborted && (
            <div className="flex items-center space-x-2">
              <span
                className="inline-flex items-center gap-1.5 rounded bg-deep px-2.5 py-1 text-xs font-semibold uppercase tracking-wider text-mist"
                data-testid={`evidence-status-${item.id}`}
              >
                <XCircle className="h-3.5 w-3.5 text-mist" aria-hidden="true" />
                <span>ANNULÉ</span>
              </span>
              <button
                type="button"
                onClick={() => onRetry(item.id)}
                className="inline-flex items-center gap-1 rounded border border-deep bg-deep/40 px-2.5 py-1 text-xs font-medium text-cyan hover:border-cyan focus:outline-none focus:ring-2 focus:ring-cyan"
                aria-label={`Réessayer le téléversement de ${item.name}`}
                data-testid={`evidence-retry-btn-${item.id}`}
              >
                <RotateCw className="h-3.5 w-3.5 text-cyan" aria-hidden="true" />
                <span>Réessayer</span>
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Barre de progression XHR (D-38) */}
      <div className="space-y-1">
        <div
          role="progressbar"
          aria-valuenow={item.progress}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Progression du téléversement de ${item.name}`}
          className="h-2 w-full overflow-hidden rounded bg-deep/40"
          data-testid={`evidence-progressbar-${item.id}`}
        >
          <div
            className={`h-full transition-all duration-200 ${
              isError ? 'bg-deep border-b border-teal' : isSuccess ? 'bg-teal' : 'bg-cyan'
            }`}
            style={{ width: `${item.progress}%` }}
          />
        </div>

        {/* Détails d'erreur ou message descriptif du serveur */}
        {isError && item.errorMessage && (
          <p
            className="text-xs text-mist/90 bg-deep/30 rounded p-1.5 border-l-2 border-teal"
            data-testid={`evidence-error-message-${item.id}`}
          >
            {item.errorMessage}
          </p>
        )}

        {isAborted && item.errorMessage && (
          <p
            className="text-xs text-mist/70 italic"
            data-testid={`evidence-aborted-message-${item.id}`}
          >
            {item.errorMessage}
          </p>
        )}
      </div>
    </li>
  )
}
