import { Loader2 } from 'lucide-react'
import type { CaseStatus } from '../../../api/cases-types'
import {
  VALID_CASE_STATUS_TRANSITIONS,
  CASE_STATUS_LABELS,
  CASE_STATUS_UNDEFINED_LABEL,
} from '../../../api/cases-types'

export interface CaseStatusSelectorProps {
  readonly currentStatus?: CaseStatus | string | null
  readonly onStatusChange: (newStatus: CaseStatus) => void | Promise<void>
  readonly isUpdating?: boolean
  readonly isReadOnly?: boolean
}

/**
 * Sélecteur contrôlé d'évolution du statut global du dossier (Story F2.2).
 *
 * RÈGLES DE CONCEPTION :
 * 1. Valeurs et transitions : strictement restreintes à la matrice validée (openapi.json).
 *    Toute transition absente est « à décider » et n'est pas proposée.
 * 2. État de chargement : désactive le sélecteur avec un indicateur discret de synchronisation.
 * 3. État vide / non défini : rendu sous la mention textuelle « NON DÉFINI ».
 * 4. État d'accès refusé (lecture seule, ex. rôle viewer) : rendu en mode texte non modifiable sans contrôle interactif.
 * 5. Respect strict de la palette sans aucune couleur en dur.
 */
export function CaseStatusSelector({
  currentStatus,
  onStatusChange,
  isUpdating = false,
  isReadOnly = false,
}: CaseStatusSelectorProps) {
  // 1. Accès en lecture seule (ex. profil viewer)
  if (isReadOnly) {
    return (
      <div className="flex items-center gap-2" data-testid="case-status-selector">
        <span className="text-xs text-teal font-medium">Statut :</span>
        <span
          data-testid="case-status-readonly"
          className="text-xs text-mist font-medium px-2 py-1 rounded bg-deep/20 border border-deep"
        >
          Lecture seule
        </span>
      </div>
    )
  }

  // 2. Statut non défini ou inconnu
  if (!currentStatus || !(currentStatus in VALID_CASE_STATUS_TRANSITIONS)) {
    return (
      <div className="flex items-center gap-2" data-testid="case-status-selector">
        <span className="text-xs text-teal font-medium">Statut :</span>
        <span
          data-testid="case-status-undefined-selector"
          className="text-xs text-teal italic px-2 py-1 rounded bg-deep/20 border border-deep"
        >
          {CASE_STATUS_UNDEFINED_LABEL}
        </span>
      </div>
    )
  }

  const validCurrentStatus = currentStatus as CaseStatus
  const availableTransitions = VALID_CASE_STATUS_TRANSITIONS[validCurrentStatus] ?? []

  // 3. Statut terminal (aucune transition autorisée, ex. closed)
  if (availableTransitions.length === 0) {
    return (
      <div className="flex items-center gap-2" data-testid="case-status-selector">
        <label htmlFor="case-status-select" className="text-xs font-medium text-teal sr-only">
          Statut du dossier
        </label>
        <select
          id="case-status-select"
          data-testid="case-status-select"
          aria-label="Modifier le statut du dossier"
          disabled
          value={validCurrentStatus}
          onChange={() => {}}
          className="bg-ink border border-deep text-mist text-xs rounded px-2.5 py-1.5 opacity-60 cursor-not-allowed focus:outline-none"
        >
          <option value={validCurrentStatus}>
            {CASE_STATUS_LABELS[validCurrentStatus]} (Aucune transition autorisée)
          </option>
        </select>
      </div>
    )
  }

  // 4. État nominal interactif
  return (
    <div className="flex items-center gap-2" data-testid="case-status-selector">
      <label htmlFor="case-status-select" className="text-xs font-medium text-teal sr-only">
        Modifier le statut du dossier
      </label>
      <div className="relative inline-flex items-center">
        <select
          id="case-status-select"
          data-testid="case-status-select"
          aria-label="Modifier le statut du dossier"
          disabled={isUpdating}
          value={validCurrentStatus}
          onChange={(e) => {
            const nextStatus = e.target.value as CaseStatus
            if (nextStatus && nextStatus !== validCurrentStatus) {
              onStatusChange(nextStatus)
            }
          }}
          className="bg-ink border border-deep text-mist text-xs rounded px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-cyan disabled:opacity-50 transition-colors"
        >
          <option value={validCurrentStatus} disabled>
            {CASE_STATUS_LABELS[validCurrentStatus]} (Statut actuel)
          </option>
          {availableTransitions.map((targetStatus) => (
            <option key={targetStatus} value={targetStatus}>
              Passer à : {CASE_STATUS_LABELS[targetStatus]}
            </option>
          ))}
        </select>
      </div>

      {isUpdating && (
        <span
          data-testid="status-sync-indicator"
          className="inline-flex items-center gap-1.5 text-xs text-teal animate-pulse"
          role="status"
          aria-live="polite"
        >
          <Loader2 className="w-3.5 h-3.5 text-cyan animate-spin" aria-hidden="true" />
          <span>Synchronisation...</span>
        </span>
      )}
    </div>
  )
}
