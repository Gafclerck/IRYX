import { useCallback, useEffect, useRef, useState } from 'react'
import { DP05_MAX_CONSECUTIVE_NETWORK_ERRORS } from '../../plan/constants'
import { REVIEW_ERROR_FALLBACK_MESSAGE, REVIEW_NETWORK_CUTOFF_MESSAGE } from '../constants'
import { ReviewApiError, getFindings } from '../services/reviewService'
import type { FindingOut, ReviewViewState } from '../types'

export interface UseReviewOptions {
  readonly caseId: string
  readonly enabled?: boolean
}

export interface UseReviewReturn {
  readonly state: ReviewViewState
  readonly findings: readonly FindingOut[]
  readonly errorMessage: string | null
  readonly isFetching: boolean
  readonly isNetworkCutoff: boolean
  readonly refetch: () => void
  readonly retryConnection: () => void
}

/**
 * Chargement des findings pour la revue H2 (Story F4.8, FR-REV-01).
 *
 * RÈGLES :
 * 1. Source unique : GET /api/v1/cases/{case_id}/findings (contrat openapi.json).
 * 2. Aucune décision calculée côté front. Les décisions ne sont pas acquises ici.
 * 3. DP-05 : après coupure prolongée, arrêt et bouton "Réessayer la connexion".
 * 4. 403 => état accès refusé. Statut/code serveur conservés sans invention.
 */
export function useReview({ caseId, enabled = true }: UseReviewOptions): UseReviewReturn {
  const [state, setState] = useState<ReviewViewState>('loading')
  const [findings, setFindings] = useState<readonly FindingOut[]>([])
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [isFetching, setIsFetching] = useState(false)
  const [isNetworkCutoff, setIsNetworkCutoff] = useState(false)

  const mountedRef = useRef(true)
  const consecutiveErrorsRef = useRef(0)
  const cutoffRef = useRef(false)

  const load = useCallback(async () => {
    if (!mountedRef.current || !caseId || !enabled || cutoffRef.current) return
    setIsFetching(true)
    try {
      const { data } = await getFindings(caseId)
      if (!mountedRef.current) return
      consecutiveErrorsRef.current = 0
      setIsNetworkCutoff(false)
      setErrorMessage(null)
      setFindings(data.items)
      setState(data.items.length === 0 ? 'empty' : 'ready')
    } catch (err) {
      if (!mountedRef.current) return
      const failure = err as ReviewApiError
      if (failure.status === 0) {
        consecutiveErrorsRef.current += 1
        if (consecutiveErrorsRef.current >= DP05_MAX_CONSECUTIVE_NETWORK_ERRORS) {
          cutoffRef.current = true
          setIsNetworkCutoff(true)
          setState('error')
          setErrorMessage(REVIEW_NETWORK_CUTOFF_MESSAGE)
        } else {
          setState('error')
          setErrorMessage(failure.message || REVIEW_ERROR_FALLBACK_MESSAGE)
        }
        return
      }
      setState(failure.status === 403 ? 'forbidden' : 'error')
      setErrorMessage(failure.detail ?? failure.message ?? REVIEW_ERROR_FALLBACK_MESSAGE)
    } finally {
      if (mountedRef.current) setIsFetching(false)
    }
  }, [caseId, enabled])

  useEffect(() => {
    mountedRef.current = true
    consecutiveErrorsRef.current = 0
    cutoffRef.current = false
    setState('loading')
    setFindings([])
    setErrorMessage(null)
    setIsNetworkCutoff(false)
    if (caseId && enabled) void load()
    return () => {
      mountedRef.current = false
    }
  }, [caseId, enabled, load])

  const resetAndLoad = useCallback(() => {
    consecutiveErrorsRef.current = 0
    cutoffRef.current = false
    setIsNetworkCutoff(false)
    setErrorMessage(null)
    setState('loading')
    void load()
  }, [load])

  return {
    state,
    findings,
    errorMessage,
    isFetching,
    isNetworkCutoff,
    refetch: resetAndLoad,
    retryConnection: resetAndLoad,
  }
}
