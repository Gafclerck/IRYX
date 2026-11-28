import { useEffect, useRef } from 'react'
import { Ban } from 'lucide-react'
import { CANCEL_REALIGNMENT_NOTE } from '../constants'

export interface RunCancelDialogProps {
  readonly isSubmitting: boolean
  readonly onCancel: () => void
  readonly onConfirm: () => void
}

/**
 * Dialogue de confirmation explicite avant toute demande d'annulation (Story F4.3).
 * Le bouton principal de la console n'émet jamais de requête : il ouvre ce dialogue.
 */
export function RunCancelDialog({ isSubmitting, onCancel, onConfirm }: RunCancelDialogProps) {
  const confirmRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    confirmRef.current?.focus()
  }, [])

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !isSubmitting) onCancel()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isSubmitting, onCancel])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/80 p-4"
      data-testid="run-cancel-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !isSubmitting) onCancel()
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="run-cancel-dialog-title"
        className="w-full max-w-lg space-y-5 rounded-lg border border-deep bg-ink p-6 text-mist"
        data-testid="run-cancel-dialog"
      >
        <div className="flex items-start gap-3">
          <Ban className="mt-0.5 h-6 w-6 flex-shrink-0 text-cyan" aria-hidden="true" />
          <div className="space-y-2">
            <h2
              id="run-cancel-dialog-title"
              className="text-lg font-bold uppercase tracking-wide text-mist"
            >
              Confirmer l’annulation de la session
            </h2>
            <p className="text-sm text-mist/90" data-testid="run-cancel-summary">
              L'interruption est définitive. Aucune annulation n'est transmise sans confirmation
              explicite.
            </p>
            <p className="text-xs uppercase tracking-wider text-teal">
              Confirmation explicite requise
            </p>
            <p className="text-xs text-cyan">{CANCEL_REALIGNMENT_NOTE}</p>
          </div>
        </div>

        <div className="flex flex-wrap justify-end gap-3 border-t border-deep pt-4">
          <button
            type="button"
            onClick={onCancel}
            disabled={isSubmitting}
            className="rounded border border-teal bg-deep px-4 py-2 text-sm font-semibold text-mist hover:bg-deep/80 focus:outline-none focus:ring-2 focus:ring-cyan disabled:cursor-not-allowed disabled:opacity-50"
            data-testid="run-cancel-decline"
          >
            Annuler la demande
          </button>
          <button
            type="button"
            ref={confirmRef}
            onClick={onConfirm}
            disabled={isSubmitting}
            className="rounded border border-cyan bg-cyan px-4 py-2 text-sm font-bold text-ink hover:bg-cyan/80 focus:outline-none focus:ring-2 focus:ring-cyan disabled:cursor-not-allowed disabled:opacity-50"
            data-testid="run-cancel-confirm"
          >
            {isSubmitting ? 'Envoi en cours...' : 'Confirmer l’annulation'}
          </button>
        </div>
      </div>
    </div>
  )
}
