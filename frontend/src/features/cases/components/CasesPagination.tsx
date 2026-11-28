import { ChevronLeft, ChevronRight } from 'lucide-react'

export interface CasesPaginationProps {
  readonly page: number
  readonly limit: number
  readonly total: number
  readonly hasMore: boolean
  readonly onPageChange: (newPage: number) => void
  readonly disabled?: boolean
}

/**
 * Contrôles de pagination côté serveur pour la liste des dossiers (Story F1.6).
 *
 * RÈGLES DE CONCEPTION :
 * 1. Le front transmet la page et la taille demandées ; il ne charge jamais la liste complète.
 * 2. Boutons Précédent et Suivant avec états désactivés aux limites.
 * 3. Indication précise des éléments affichés et du total.
 */
export function CasesPagination({
  page,
  limit,
  total,
  hasMore,
  onPageChange,
  disabled = false,
}: CasesPaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / limit))
  const startItem = total === 0 ? 0 : (page - 1) * limit + 1
  const endItem = Math.min(page * limit, total)

  const canGoPrevious = page > 1 && !disabled
  const canGoNext = hasMore && page < totalPages && !disabled

  return (
    <nav
      className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-3 text-xs text-teal select-none"
      aria-label="Navigation de pagination des dossiers"
      data-testid="cases-pagination"
    >
      <div>
        <span data-testid="pagination-summary">
          Affichage de <strong className="font-semibold text-mist">{startItem}</strong> à{' '}
          <strong className="font-semibold text-mist">{endItem}</strong> sur{' '}
          <strong className="font-semibold text-mist">{total}</strong> dossier{total > 1 ? 's' : ''}
        </span>
      </div>

      <div className="flex items-center gap-2">
        <span className="mr-2 text-mist" data-testid="pagination-page-indicator">
          Page {page} / {totalPages}
        </span>
        <button
          type="button"
          onClick={() => onPageChange(page - 1)}
          disabled={!canGoPrevious}
          className="inline-flex items-center gap-1 rounded border border-deep bg-ink px-2.5 py-1.5 font-medium text-mist transition-colors hover:border-cyan hover:text-cyan focus:outline-none focus:ring-2 focus:ring-cyan disabled:cursor-not-allowed disabled:border-deep disabled:text-teal"
          aria-label="Page précédente"
          data-testid="pagination-prev"
        >
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
          <span>Précédent</span>
        </button>

        <button
          type="button"
          onClick={() => onPageChange(page + 1)}
          disabled={!canGoNext}
          className="inline-flex items-center gap-1 rounded border border-deep bg-ink px-2.5 py-1.5 font-medium text-mist transition-colors hover:border-cyan hover:text-cyan focus:outline-none focus:ring-2 focus:ring-cyan disabled:cursor-not-allowed disabled:border-deep disabled:text-teal"
          aria-label="Page suivante"
          data-testid="pagination-next"
        >
          <span>Suivant</span>
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
    </nav>
  )
}
