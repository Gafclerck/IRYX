import { Loader2 } from 'lucide-react'

interface LoadingFallbackProps {
  message?: string
}

export function LoadingFallback({
  message = "Chargement de l'application...",
}: LoadingFallbackProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex min-h-screen flex-col items-center justify-center bg-ink text-mist p-6"
    >
      <Loader2 className="h-8 w-8 animate-spin text-cyan" aria-hidden="true" />
      <p className="mt-4 text-sm font-medium text-mist">{message}</p>
    </div>
  )
}
