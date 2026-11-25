import { useCallback, useRef, useState } from 'react'
import { CANCEL_REALIGNMENT_NOTE } from '../constants'
import { RunApiError, cancelInvestigation, resumeInvestigation } from '../services/runService'

export type RunControlOutcome =
  | { readonly kind: 'idle' }
  | { readonly kind: 'resumed'; readonly message: string }
  | { readonly kind: 'realigned'; readonly message: string }
  | { readonly kind: 'error'; readonly message: string }

export interface UseRunControlsOptions {
  readonly caseId: string
  readonly runId: string
  readonly onResumed: () => void
}

export interface UseRunControlsReturn {
  readonly outcome: RunControlOutcome
  readonly isSubmitting: boolean
  readonly resume: () => Promise<void>
  readonly confirmCancel: () => Promise<void>
  readonly reset: () => void
}

/**
 * Commandes de la console F4.3. Seule la reprise possède une route dans le contrat.
 * L'annulation reste bloquée par le contrat : la confirmation explicite déclenche
 * une demande locale qui n'émet aucun appel réseau et l'indique à l'utilisateur.
 */
export function useRunControls({
  caseId,
  runId,
  onResumed,
}: UseRunControlsOptions): UseRunControlsReturn {
  const [outcome, setOutcome] = useState<RunControlOutcome>({ kind: 'idle' })
  const [isSubmitting, setIsSubmitting] = useState(false)
  const inFlightRef = useRef(false)

  const resume = useCallback(async () => {
    if (inFlightRef.current || !caseId || !runId) return
    inFlightRef.current = true
    setIsSubmitting(true)
    try {
      await resumeInvestigation(caseId, runId)
      setOutcome({ kind: 'resumed', message: 'Session reprise.' })
      onResumed()
    } catch (err) {
      const failure = err as RunApiError
      setOutcome({ kind: 'error', message: failure.message ?? 'La reprise a été refusée.' })
    } finally {
      inFlightRef.current = false
      setIsSubmitting(false)
    }
  }, [caseId, onResumed, runId])

  const confirmCancel = useCallback(async () => {
    if (inFlightRef.current) return
    inFlightRef.current = true
    setIsSubmitting(true)
    try {
      await cancelInvestigation()
    } catch (err) {
      setOutcome({
        kind: 'realigned',
        message: (err as RunApiError).message || CANCEL_REALIGNMENT_NOTE,
      })
    } finally {
      inFlightRef.current = false
      setIsSubmitting(false)
    }
  }, [])

  const reset = useCallback(() => setOutcome({ kind: 'idle' }), [])

  return { outcome, isSubmitting, resume, confirmCancel, reset }
}
