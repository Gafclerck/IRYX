import { Inbox } from 'lucide-react'
import type { EvidenceUploadItem } from '../types'
import { EvidenceUploadItemRow } from './EvidenceUploadItemRow'

export interface EvidenceUploadListProps {
  readonly items: readonly EvidenceUploadItem[]
  readonly onCancel: (id: string) => void
  readonly onRetry: (id: string) => void
}

/**
 * Liste de suivi des fichiers de preuves téléversés dans la session courante (Story F3.1).
 *
 * RÈGLES DE CONCEPTION (FR-EVI-01, Section 3.4 de 11-ecrans-et-routes.md) :
 * 1. Présente chaque fichier dans une ligne avec nom, taille, progression, statut.
 * 2. État vide informatif : « Aucune preuve déposée pour ce dossier ».
 * 3. Ne réalise aucune interrogation du registre persistant (réservé à F3.2).
 */
export function EvidenceUploadList({ items, onCancel, onRetry }: EvidenceUploadListProps) {
  if (items.length === 0) {
    return (
      <div
        className="rounded-lg border border-deep bg-ink p-8 text-center"
        data-testid="evidence-empty-state"
      >
        <div className="flex flex-col items-center justify-center space-y-2">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-deep/50 text-teal">
            <Inbox className="h-6 w-6" aria-hidden="true" />
          </div>
          <h3 className="text-sm font-semibold uppercase tracking-wider text-mist">
            Aucune preuve déposée pour ce dossier
          </h3>
          <p className="text-xs text-mist/70 max-w-sm">
            Déposez ou sélectionnez un ou plusieurs fichiers compatibles dans la zone ci-dessus pour
            initier les transferts individuels.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-3" data-testid="evidence-upload-list">
      <div className="flex items-center justify-between border-b border-deep pb-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-teal">
          Transferts de la session ({items.length})
        </h3>
      </div>
      <ul className="space-y-3" role="list">
        {items.map((item) => (
          <EvidenceUploadItemRow key={item.id} item={item} onCancel={onCancel} onRetry={onRetry} />
        ))}
      </ul>
    </div>
  )
}
