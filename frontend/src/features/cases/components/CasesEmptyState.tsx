import { FolderX } from 'lucide-react'

/**
 * État vide affiché lorsqu'aucun dossier n'est enregistré ou lors d'une recherche infructueuse (Story F1.6).
 * RÈGLE F1.6 : Aucun bouton de création affiché pour l'instant (la création relève de la story F1.7).
 */
export function CasesEmptyState() {
  return (
    <div
      className="flex flex-col items-center justify-center rounded border border-deep bg-ink py-16 px-4 text-center"
      data-testid="cases-empty-state"
    >
      <FolderX className="h-10 w-10 text-teal mb-3" aria-hidden="true" />
      <p className="text-base font-medium text-mist" data-testid="cases-empty-message">
        Aucun dossier. Créez le premier.
      </p>
      <p className="mt-1 text-xs text-teal max-w-sm">
        Aucun dossier d'investigation ne correspond à votre recherche ou votre organisation.
      </p>
    </div>
  )
}
