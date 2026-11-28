import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ADR0008_POLLING_DEFAULT_INTERVAL_MS,
  ADR0008_POLLING_DEFAULT_INTERVAL_SECONDS,
  ADR0008_POLLING_MAX_BACKOFF_MS,
  DP05_MAX_CONSECUTIVE_NETWORK_ERRORS,
  PLAN_NOT_FOUND_CODE,
  formatInvestigationStatus,
} from '../constants'
import { PlanApiError, getInvestigationPlan, getInvestigationRuns } from '../services/planService'
import type { InvestigationPlan, InvestigationRunOut, PlanViewState } from '../types'

export interface UsePlanOptions {
  readonly caseId: string
  readonly enabled?: boolean
  /**
   * Réservé aux tests automatisés : raccourcit la cadence sans modifier la règle de
   * production, qui reste exclusivement pilotée par Retry-After / ADR-0008.
   */
  readonly pollIntervalMs?: number
}

export interface UsePlanReturn {
  readonly state: PlanViewState
  readonly plan: InvestigationPlan | null
  readonly run: InvestigationRunOut | null
  readonly statusLabel: string | null
  readonly errorMessage: string | null
  readonly isFetching: boolean
  readonly isNetworkCutoff: boolean
  readonly refetch: () => void
  readonly retryConnection: () => void
}

function selectLatestRun(runs: readonly InvestigationRunOut[]): InvestigationRunOut | null {
  if (runs.length === 0) return null
  return (
    [...runs].sort((a, b) => String(b.started_at).localeCompare(String(a.started_at)))[0] ?? null
  )
}

/**
 * Consultation du plan proposé par le Planner avec scrutation de l'état d'élaboration
 * (Story F4.1, FR-PLAN-01, ADR-0008, DP-05).
 *
 * RÈGLES DE CONCEPTION :
 * 1. Interroge GET /api/v1/cases/:caseId/investigations pour obtenir la session courante,
 *    puis GET /api/v1/cases/:caseId/investigations/:runId/plan.
 * 2. Tant que le plan renvoie 404 PLAN_NOT_FOUND (ou qu'aucune session n'existe), la
 *    scrutation continue selon l'en-tête Retry-After (3 secondes par défaut ADR-0008).
 * 3. Arrêt de la scrutation dès qu'un état terminal est atteint : plan disponible (prêt,
 *    vide ou validé), erreur de l'agent, 401, 403 ou statut inconnu.
 * 4. Recul exponentiel plafonné en cas d'erreur de transport HTTP (ADR-0008).
 * 5. DP-05 : après une coupure prolongée, la scrutation s'arrête et le bouton
 *    « Réessayer la connexion » est proposé. Le seuil reste « à décider ».
 * 6. Arrêt immédiat de toute scrutation au départ de la page (nettoyage des timers).
 * 7. Lecture seule : ce hook ne déclenche aucune mutation (validation, retrait, refus).
 */
export function usePlan({ caseId, enabled = true, pollIntervalMs }: UsePlanOptions): UsePlanReturn {
  const [state, setState] = useState<PlanViewState>('loading')
  const [plan, setPlan] = useState<InvestigationPlan | null>(null)
  const [run, setRun] = useState<InvestigationRunOut | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [isFetching, setIsFetching] = useState(false)
  const [isNetworkCutoff, setIsNetworkCutoff] = useState(false)

  const mountedRef = useRef(true)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const consecutiveErrorsRef = useRef(0)
  const cycleRef = useRef<() => Promise<void>>(async () => {})

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const scheduleNext = useCallback(
    (delayMs: number) => {
      clearTimer()
      timerRef.current = setTimeout(() => {
        void cycleRef.current()
      }, delayMs)
    },
    [clearTimer],
  )

  const resolveDelay = useCallback(
    (retryAfterSeconds?: number | null): number => {
      if (pollIntervalMs !== undefined) return pollIntervalMs
      const seconds =
        retryAfterSeconds && retryAfterSeconds > 0
          ? retryAfterSeconds
          : ADR0008_POLLING_DEFAULT_INTERVAL_SECONDS
      return seconds * 1000
    },
    [pollIntervalMs],
  )

  const handleTransportFailure = useCallback(() => {
    consecutiveErrorsRef.current += 1

    if (consecutiveErrorsRef.current >= DP05_MAX_CONSECUTIVE_NETWORK_ERRORS) {
      clearTimer()
      setIsNetworkCutoff(true)
      setState('error')
      setErrorMessage('Connexion interrompue. La scrutation a été arrêtée (DP-05).')
      return
    }

    const backoffMs =
      pollIntervalMs ??
      Math.min(
        ADR0008_POLLING_DEFAULT_INTERVAL_MS * Math.pow(2, consecutiveErrorsRef.current),
        ADR0008_POLLING_MAX_BACKOFF_MS,
      )
    scheduleNext(backoffMs)
  }, [clearTimer, pollIntervalMs, scheduleNext])

  const runCycle = useCallback(async () => {
    if (!mountedRef.current || !caseId || !enabled) return

    clearTimer()
    setIsFetching(true)

    try {
      const runsResponse = await getInvestigationRuns(caseId)
      if (!mountedRef.current) return

      const latestRun = selectLatestRun(runsResponse.data)
      setRun(latestRun)

      // Aucune session : le Planner n'a pas encore démarré, on attend selon Retry-After.
      if (!latestRun) {
        consecutiveErrorsRef.current = 0
        setState('planning')
        setErrorMessage(null)
        setPlan(null)
        scheduleNext(resolveDelay(runsResponse.retryAfterSeconds))
        return
      }

      let planResponse: Awaited<ReturnType<typeof getInvestigationPlan>>
      try {
        planResponse = await getInvestigationPlan(caseId, latestRun.id)
      } catch (planError) {
        if (!mountedRef.current) return
        const apiError = planError as PlanApiError

        // 404 PLAN_NOT_FOUND : planification asynchrone toujours en cours.
        if (apiError.status === 404 && apiError.code === PLAN_NOT_FOUND_CODE) {
          setState('planning')
          setErrorMessage(null)
          setPlan(null)
          scheduleNext(resolveDelay(apiError.retryAfterSeconds))
          return
        }

        if (apiError.status === 0) {
          handleTransportFailure()
          return
        }

        setState(apiError.status === 403 ? 'forbidden' : 'error')
        setErrorMessage(apiError.message)
        return
      }

      if (!mountedRef.current) return

      consecutiveErrorsRef.current = 0
      setIsNetworkCutoff(false)
      setIsFetching(false)
      setPlan(planResponse.data)
      setErrorMessage(null)

      setRun(latestRun)

      // Un statut non répertorié est restitué tel quel par statusLabel sans bloquer
      // la consultation : la disponibilité du plan fait foi, pas l'étiquette du statut.
      if (latestRun.validated_plan != null) {
        setState('validated')
        return
      }

      setState(planResponse.data.steps.length === 0 ? 'empty' : 'ready')
      // État terminal : aucune scrutation supplémentaire n'est programmée.
    } catch (err) {
      if (!mountedRef.current) return

      const apiError = err as PlanApiError
      if (apiError.status === 0) {
        handleTransportFailure()
        return
      }

      setState(apiError.status === 403 ? 'forbidden' : 'error')
      setErrorMessage(apiError.message)
      setPlan(null)
    } finally {
      if (mountedRef.current) {
        setIsFetching(false)
      }
    }
  }, [caseId, clearTimer, enabled, handleTransportFailure, resolveDelay, scheduleNext])

  useEffect(() => {
    cycleRef.current = runCycle
  }, [runCycle])

  useEffect(() => {
    mountedRef.current = true
    consecutiveErrorsRef.current = 0
    clearTimer()
    setIsNetworkCutoff(false)
    setPlan(null)
    setRun(null)
    setErrorMessage(null)
    setState('loading')

    if (caseId && enabled) {
      void runCycle()
    }

    return () => {
      mountedRef.current = false
      clearTimer()
    }
  }, [caseId, clearTimer, enabled, runCycle])

  const restart = useCallback(() => {
    consecutiveErrorsRef.current = 0
    clearTimer()
    setIsNetworkCutoff(false)
    setState('loading')
    setErrorMessage(null)
    void cycleRef.current()
  }, [clearTimer])

  return {
    state,
    plan,
    run,
    statusLabel: run ? formatInvestigationStatus(run.status).label : null,
    errorMessage,
    isFetching,
    isNetworkCutoff,
    refetch: restart,
    retryConnection: restart,
  }
}
