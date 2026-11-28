export interface CasesLoadingSkeletonProps {
  readonly rowCount?: number
}

/**
 * Lignes de squelettes animées remplaçant le tableau pendant le chargement (Story F1.6).
 */
export function CasesLoadingSkeleton({ rowCount = 5 }: CasesLoadingSkeletonProps) {
  return (
    <div
      className="w-full space-y-2 py-2"
      data-testid="cases-loading-skeleton"
      role="status"
      aria-label="Chargement des dossiers d'investigation en cours"
    >
      {Array.from({ length: rowCount }).map((_, idx) => (
        <div
          key={idx}
          className="flex h-12 w-full animate-pulse items-center justify-between rounded border border-deep bg-ink px-4"
        >
          <div className="h-4 w-1/3 rounded bg-deep/50" />
          <div className="h-4 w-20 rounded bg-deep/50" />
          <div className="h-4 w-28 rounded bg-deep/50" />
          <div className="h-4 w-12 rounded bg-deep/50" />
        </div>
      ))}
      <span className="sr-only">Chargement des dossiers...</span>
    </div>
  )
}
