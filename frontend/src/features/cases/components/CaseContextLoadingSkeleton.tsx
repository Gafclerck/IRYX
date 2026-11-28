/**
 * Squelettes animés pour l'état de chargement de la fiche de contexte (Story F2.1).
 */
export function CaseContextLoadingSkeleton() {
  return (
    <div className="w-full space-y-6 animate-pulse" data-testid="case-context-skeleton">
      {/* En-tête squelette */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-deep pb-4">
        <div className="space-y-2">
          <div className="h-6 w-64 bg-deep/40 rounded" />
          <div className="h-4 w-40 bg-deep/20 rounded" />
        </div>
        <div className="h-9 w-28 bg-deep/40 rounded" />
      </div>

      {/* Cartes de détails */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="p-5 rounded border border-deep bg-ink space-y-4">
          <div className="h-5 w-48 bg-deep/30 rounded" />
          <div className="space-y-2">
            <div className="h-4 w-full bg-deep/20 rounded" />
            <div className="h-4 w-5/6 bg-deep/20 rounded" />
            <div className="h-4 w-4/6 bg-deep/20 rounded" />
          </div>
        </div>

        <div className="p-5 rounded border border-deep bg-ink space-y-4">
          <div className="h-5 w-48 bg-deep/30 rounded" />
          <div className="space-y-3">
            <div className="h-4 w-3/4 bg-deep/20 rounded" />
            <div className="h-4 w-2/3 bg-deep/20 rounded" />
            <div className="h-4 w-1/2 bg-deep/20 rounded" />
          </div>
        </div>
      </div>

      {/* Squelette membres */}
      <div className="p-5 rounded border border-deep bg-ink space-y-4">
        <div className="h-5 w-44 bg-deep/30 rounded" />
        <div className="space-y-2">
          <div className="h-8 w-full bg-deep/20 rounded" />
          <div className="h-8 w-full bg-deep/20 rounded" />
        </div>
      </div>
    </div>
  )
}
