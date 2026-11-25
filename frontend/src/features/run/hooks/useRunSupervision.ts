import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ADR0008_POLLING_DEFAULT_INTERVAL_MS,
  ADR0008_POLLING_DEFAULT_INTERVAL_SECONDS,
  ADR0008_POLLING_MAX_BACKOFF_MS,
  DP05_MAX_CONSECUTIVE_NETWORK_ERRORS,
} from '../../plan/constants'
import { getInvestigationRuns } from '../../plan/services/planService'
import {
  deriveActivityEntries,
  deriveAgentCards,
  formatRunStatus,
  resolveRunViewState,
} from '../constants'
import { getInvestigationRun } from '../services/runService'
import type { ActivityEntry, AgentCardData, InvestigationRunOut, RunViewState } from '../types'

export interface UseRunSupervisionOptions {
  readonly caseId: string
  readonly enabled?: boolean
  /** Réservé aux tests : raccourcit la cadence sans modifier la règle ADR-0008. */
  readonly pollIntervalMs?: number
}

export interface UseRunSupervisionReturn {
  readonly state: RunViewState
  readonly run: InvestigationRunOut | null
  readonly statusLabel: string | null
  readonly errorMessage: string | null
  readonly isFetching: boolean
  readonly isNetworkCutoff: boolean
  readonly agentCards: readonly AgentCardData[]
  readonly activityEntries: readonly ActivityEntry[]
  readonly refetch: () => void
  readonly retryConnection: () => void
}

interface ApiFailure {
  readonly status?: number
  readonly message?: string
  readonly retryAfterSeconds?: number | null
}

function isTerminal(state: RunViewState): boolean {
  return state === 'completed' || state === 'failed' || state === 'canceled' || state === 'unknown'
}

function selectLatestRun(runs: readonly InvestigationRunOut[]): InvestigationRunOut | null {
  return (
    [...runs].sort((a, b) => String(b.started_at).localeCompare(String(a.started_at)))[0] ?? null
  )
}

/**
 * Supervision par scrutation de la session d'exécution (Story F4.3, ADR-0008, DP-05).
 *
 * RÈGLES DE CONCEPTION :
 * 1. GET /cases/:caseId/investigations puis GET /investigations/:runId (contrat cible).
 * 2. Cadence issue de `Retry-After` (3 secondes par défaut) et recul exponentiel
 *    plafonné sur les erreurs de transport.
 * 3. Arrêt immédiat à un état terminal et au départ de la page.
 * 4. DP-05 : après une coupure prolongée, arrêt et bouton « Réessayer la connexion ».
 * 5. Aucune écriture dans localStorage/sessionStorage ; aucune mutation ici.
 */
export function useRunSupervision({
  caseId,
  enabled = true,
  pollIntervalMs,
}: UseRunSupervisionOptions): UseRunSupervisionReturn {
  const [state, setState] = useState<RunViewState>('loading')
  const [run, setRun] = useState<InvestigationRunOut | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [isFetching, setIsFetching] = useState(false)
  const [isNetworkCutoff, setIsNetworkCutoff] = useState(false)

  const mountedRef = useRef(true)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const consecutiveErrorsRef = useRef(0)
  const cutoffRef = useRef(false)
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
      cutoffRef.current = true
      setIsNetworkCutoff(true)
      setState('networkCutoff')
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
    if (!mountedRef.current || !caseId || !enabled || cutoffRef.current) return

    clearTimer()
    setIsFetching(true)

    try {
      const runsResponse = await getInvestigationRuns(caseId)
      if (!mountedRef.current) return

      const latestRun = selectLatestRun(runsResponse.data)
      if (!latestRun) {
        consecutiveErrorsRef.current = 0
        setIsNetworkCutoff(false)
        setRun(null)
        setErrorMessage(null)
        setState('waiting')
        scheduleNext(resolveDelay(runsResponse.retryAfterSeconds))
        return
      }

      let detailResponse: Awaited<ReturnType<typeof getInvestigationRun>>
      try {
        detailResponse = await getInvestigationRun(caseId, latestRun.id)
      } catch (err) {
        if (!mountedRef.current) return
        const failure = err as ApiFailure
        if (failure.status === 0) {
          handleTransportFailure()
          return
        }
        setState(failure.status === 403 ? 'forbidden' : 'error')
        setErrorMessage(failure.message ?? 'Échec de la consultation de la session.')
        return
      }

      if (!mountedRef.current) return

      consecutiveErrorsRef.current = 0
      setIsNetworkCutoff(false)
      setRun(detailResponse.data)
      setErrorMessage(null)

      const nextState = resolveRunViewState(detailResponse.data)
      setState(nextState)
      if (!isTerminal(nextState)) {
        scheduleNext(resolveDelay(detailResponse.retryAfterSeconds))
      }
    } catch (err) {
      if (!mountedRef.current) return
      const failure = err as ApiFailure
      if (failure.status === 0) {
        handleTransportFailure()
        return
      }
      setState(failure.status === 403 ? 'forbidden' : 'error')
      setErrorMessage(failure.message ?? 'Échec de la récupération des investigations.')
      setRun(null)
    } finally {
      if (mountedRef.current) setIsFetching(false)
    }
  }, [caseId, clearTimer, enabled, handleTransportFailure, resolveDelay, scheduleNext])

  useEffect(() => {
    cycleRef.current = runCycle
  }, [runCycle])

  useEffect(() => {
    mountedRef.current = true
    consecutiveErrorsRef.current = 0
    cutoffRef.current = false
    clearTimer()
    setIsNetworkCutoff(false)
    setRun(null)
    setErrorMessage(null)
    setState('loading')

    if (caseId && enabled) void runCycle()

    return () => {
      mountedRef.current = false
      clearTimer()
    }
  }, [caseId, clearTimer, enabled, runCycle])

  const restart = useCallback(() => {
    consecutiveErrorsRef.current = 0
    cutoffRef.current = false
    clearTimer()
    setIsNetworkCutoff(false)
    setState('loading')
    setErrorMessage(null)
    void cycleRef.current()
  }, [clearTimer])

  const agentCards = useMemo(() => deriveAgentCards(run), [run])
  const activityEntries = useMemo(() => deriveActivityEntries(run), [run])

  return {
    state,
    run,
    statusLabel: run ? formatRunStatus(run.status).label : null,
    errorMessage,
    isFetching,
    isNetworkCutoff,
    agentCards,
    activityEntries,
    refetch: restart,
    retryConnection: restart,
  }
}
