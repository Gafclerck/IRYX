import { AlertTriangle, RefreshCw } from 'lucide-react'

export interface CasesErrorBannerProps {
  readonly message?: string
  readonly onRetry: () => void
}

/**
 * Bannière d'alerte en cas d'erreur de communication ou d'échec de chargement (Story F1.6).
 * Fournit un bouton d'action explicite « Réessayer ».
 */
export function CasesErrorBanner({
  message = 'Échec du chargement des dossiers.',
  onRetry,
}: CasesErrorBannerProps) {
  return (
    <div
      role="alert"
      className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 rounded border border-deep bg-ink p-4"
      data-testid="cases-error-banner"
    >
      <div className="flex items-center gap-2 text-mist">
        <AlertTriangle className="h-5 w-5 flex-shrink-0 text-cyan" aria-hidden="true" />
        <span className="text-sm font-medium text-mist">{message}</span>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="inline-flex items-center gap-1.5 rounded border border-deep bg-ink px-3 py-1.5 text-xs font-semibold text-mist hover:border-cyan hover:text-cyan focus:outline-none focus:ring-2 focus:ring-cyan"
        data-testid="cases-retry-button"
      >
        <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
        <span>Réessayer</span>
      </button>
    </div>
  )
}
