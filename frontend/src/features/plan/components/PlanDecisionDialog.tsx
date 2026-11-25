import { useEffect, useRef, useState } from 'react'
import { Ban, ListChecks, ShieldCheck } from 'lucide-react'
import { rejectionReasonSchema } from '../schemas/planDecisionSchema'

export type PlanDecisionDialogKind = 'approve' | 'modify' | 'reject'

export interface PlanDecisionDialogProps {
  readonly kind: PlanDecisionDialogKind
  readonly stepCount: number
  readonly initialReason?: string | null
  readonly isSubmitting: boolean
  readonly onCancel: () => void
  readonly onConfirm: (reason?: string) => void
}

const TITLES: Record<PlanDecisionDialogKind, string> = {
  approve: 'Confirmer la validation du plan',
  modify: 'Confirmer le plan modifié',
  reject: 'Confirmer le refus du plan',
}

const CONFIRM_LABELS: Record<PlanDecisionDialogKind, string> = {
  approve: 'Confirmer la validation',
  modify: 'Confirmer le plan modifié',
  reject: 'Confirmer le refus',
}

/**
 * Dialogue de confirmation explicite obligatoire avant toute soumission H1 (Story F4.2).
 * La soumission réseau n'est jamais déclenchée par un bouton de l'écran principal :
 * seul le bouton de confirmation de ce dialogue appelle `onConfirm`.
 */
export function PlanDecisionDialog({
  kind,
  stepCount,
  initialReason = '',
  isSubmitting,
  onCancel,
  onConfirm,
}: PlanDecisionDialogProps) {
  const [reason, setReason] = useState(initialReason ?? '')
  const [reasonError, setReasonError] = useState<string | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const confirmRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (kind === 'reject') {
      textareaRef.current?.focus()
    } else {
      confirmRef.current?.focus()
    }
  }, [kind])

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !isSubmitting) {
        onCancel()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isSubmitting, onCancel])

  const summary =
    kind === 'reject'
      ? stepCount > 1
        ? `${stepCount} étapes proposées ne seront pas validées.`
        : `${stepCount} étape proposée ne sera pas validée.`
      : stepCount > 1
        ? `${stepCount} étapes retenues seront soumises à la porte H1.`
        : `${stepCount} étape retenue sera soumise à la porte H1.`

  const handleConfirm = () => {
    if (isSubmitting) return

    if (kind === 'reject') {
      const parsed = rejectionReasonSchema.safeParse(reason)
      if (!parsed.success) {
        setReasonError(parsed.error.issues[0]?.message ?? 'Le motif du refus est obligatoire.')
        return
      }
      setReasonError(null)
      onConfirm(parsed.data)
      return
    }

    onConfirm()
  }

  const Icon = kind === 'reject' ? Ban : kind === 'modify' ? ListChecks : ShieldCheck

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/80 p-4"
      data-testid="plan-decision-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !isSubmitting) onCancel()
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="plan-decision-dialog-title"
        className="w-full max-w-lg space-y-5 rounded-lg border border-deep bg-ink p-6 text-mist shadow-lg"
        data-testid="plan-decision-dialog"
      >
        <div className="flex items-start gap-3">
          <Icon className="mt-0.5 h-6 w-6 flex-shrink-0 text-cyan" aria-hidden="true" />
          <div className="space-y-2">
            <h2
              id="plan-decision-dialog-title"
              className="text-lg font-bold uppercase tracking-wide text-mist"
            >
              {TITLES[kind]}
            </h2>
            <p className="text-sm text-mist/90" data-testid="plan-confirmation-summary">
              {summary}
            </p>
            <p className="text-xs uppercase tracking-wider text-teal">
              Confirmation explicite requise
            </p>
          </div>
        </div>

        {kind === 'reject' && (
          <div className="space-y-2">
            <label htmlFor="plan-reject-reason" className="block text-sm font-semibold text-mist">
              Motif du refus (obligatoire)
            </label>
            <textarea
              id="plan-reject-reason"
              ref={textareaRef}
              value={reason}
              onChange={(event) => {
                setReason(event.target.value)
                if (reasonError) setReasonError(null)
              }}
              disabled={isSubmitting}
              rows={4}
              maxLength={2000}
              aria-invalid={reasonError !== null}
              aria-describedby={reasonError ? 'plan-reject-reason-error' : undefined}
              className="w-full rounded border border-deep bg-deep/20 p-3 text-sm text-mist placeholder:text-teal focus:outline-none focus:ring-2 focus:ring-cyan disabled:opacity-50"
              data-testid="plan-reject-reason"
              placeholder="Indiquez le motif du refus"
            />
            {reasonError && (
              <p
                id="plan-reject-reason-error"
                role="alert"
                className="text-sm font-semibold text-cyan"
                data-testid="plan-reject-reason-error"
              >
                {reasonError}
              </p>
            )}
          </div>
        )}

        <div className="flex flex-wrap justify-end gap-3 border-t border-deep pt-4">
          <button
            type="button"
            onClick={onCancel}
            disabled={isSubmitting}
            className="rounded border border-teal bg-deep px-4 py-2 text-sm font-semibold text-mist hover:bg-deep/80 focus:outline-none focus:ring-2 focus:ring-cyan disabled:cursor-not-allowed disabled:opacity-50"
            data-testid="plan-decision-cancel"
          >
            Annuler
          </button>
          <button
            type="button"
            ref={confirmRef}
            onClick={handleConfirm}
            disabled={isSubmitting}
            className="rounded border border-cyan bg-cyan px-4 py-2 text-sm font-bold text-ink hover:bg-cyan/80 focus:outline-none focus:ring-2 focus:ring-cyan disabled:cursor-not-allowed disabled:opacity-50"
            data-testid="plan-decision-confirm"
          >
            {isSubmitting ? 'Envoi en cours...' : CONFIRM_LABELS[kind]}
          </button>
        </div>
      </div>
    </div>
  )
}
