import { useCallback, useRef, useState } from 'react'
import { PlanApiError, submitH1Decision } from '../services/planService'
import type { H1DecisionRequest } from '../types'

/**
 * Résultats locaux d'un arbitrage de la porte H1 (Story F4.2).
 * Aucun de ces états ne persiste hors mémoire vive : aucun localStorage/sessionStorage.
 */
export type H1DecisionOutcome =
  | { readonly kind: 'idle' }
  | { readonly kind: 'validated'; readonly message: string | null }
  | { readonly kind: 'refused'; readonly message: string | null }
  | { readonly kind: 'error'; readonly message: string; readonly payload: H1DecisionRequest }
  | {
      readonly kind: 'conflict'
      readonly status: string | null
      readonly phase: string | null
      readonly message: string | null
    }

export interface UseH1DecisionOptions {
  readonly caseId: string
  readonly runId: string
}

export interface UseH1DecisionReturn {
  readonly outcome: H1DecisionOutcome
  readonly isSubmitting: boolean
  /** Envoie une décision déjà confirmée. Renvoie false si un envoi est déjà en vol. */
  readonly submit: (payload: H1DecisionRequest) => Promise<boolean>
  /** Efface l'état d'arbitrage local après un rafraîchissement du plan par le serveur. */
  readonly reset: () => void
}

/**
 * Gestion de la mutation POST gates/h1.
 *
 * RÈGLES STRICTES :
 * 1. Une garde référentielle interdit deux envois concurrents, même avant que l'état
 *    React « isSubmitting » ne soit appliqué.
 * 2. Le plan reste « prêt » sur erreur réseau ou 5xx : aucun succès n'est déduit ;
 *    la décision confirmée est conservée en mémoire pour un nouveau « Réessayer ».
 * 3. Sur 409, l'état réel renvoyé par le serveur est conservé sans validation locale.
 * 4. Aucune action n'est déclenchée ici : toute soumission passe par une confirmation
 *    explicite au niveau de l'interface.
 */
export function useH1Decision({ caseId, runId }: UseH1DecisionOptions): UseH1DecisionReturn {
  const [outcome, setOutcome] = useState<H1DecisionOutcome>({ kind: 'idle' })
  const [isSubmitting, setIsSubmitting] = useState(false)
  const inFlightRef = useRef(false)

  const submit = useCallback(
    async (payload: H1DecisionRequest): Promise<boolean> => {
      if (inFlightRef.current) return false

      inFlightRef.current = true
      setIsSubmitting(true)

      try {
        const response = await submitH1Decision(caseId, runId, payload)
        setOutcome(
          response.decision === 'reject'
            ? { kind: 'refused', message: response.message ?? null }
            : { kind: 'validated', message: response.message ?? null },
        )
        return true
      } catch (err) {
        const apiError = err as PlanApiError
        if (apiError.status === 409) {
          setOutcome({
            kind: 'conflict',
            status: apiError.returnedStatus,
            phase: apiError.returnedPhase,
            message: apiError.serverMessage ?? apiError.message,
          })
        } else {
          setOutcome({ kind: 'error', message: apiError.message, payload })
        }
        return false
      } finally {
        inFlightRef.current = false
        setIsSubmitting(false)
      }
    },
    [caseId, runId],
  )

  const reset = useCallback(() => {
    setOutcome({ kind: 'idle' })
  }, [])

  return { outcome, isSubmitting, submit, reset }
}
