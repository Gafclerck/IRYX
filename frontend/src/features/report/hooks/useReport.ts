import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ADR0008_POLLING_DEFAULT_INTERVAL_MS,
  ADR0008_POLLING_MAX_BACKOFF_MS,
  DP05_MAX_CONSECUTIVE_NETWORK_ERRORS,
} from '../../plan/constants'
import {
  REPORT_FAILED_FALLBACK_MESSAGE,
  REPORT_NETWORK_CUTOFF_MESSAGE,
  REPORT_UNKNOWN_DISABLED_NOTE,
  REPORT_UNKNOWN_LABEL_PREFIX,
} from '../constants'
import {
  ReportApiError,
  generateReport,
  getReport,
  getReportTask,
  readGenerationFailureMessage,
} from '../services/reportService'
import type { ReportDocument, ReportErrorPayload, ReportTask, ReportViewState } from '../types'

export interface UseReportOptions {
  readonly caseId: string
  readonly enabled?: boolean
  /** Réservé aux tests : raccourcit la cadence sans modifier la règle ADR-0008. */
  readonly pollIntervalMs?: number
}

export interface UseReportReturn {
  readonly state: ReportViewState
  readonly document: ReportDocument | null
  readonly statusLabel: string | null
  readonly errorMessage: string | null
  readonly isFetching: boolean
  readonly isNetworkCutoff: boolean
  readonly generate: () => void
  readonly retryGeneration: () => void
  readonly retryConnection: () => void
  readonly refetch: () => void
}

function isTerminalTaskStatus(status: string): boolean {
  return status === 'completed' || status === 'failed'
}

function isKnownTaskStatus(status: string): boolean {
  return status === 'pending' || status === 'processing' || isTerminalTaskStatus(status)
}

function formatUnknown(status: string | undefined | null): string {
  return `${REPORT_UNKNOWN_LABEL_PREFIX} (${status ?? 'non fourni'})`
}

/**
 * Génération et prévisualisation du rapport (Story F5.1, FR-REP-01, DP-03, DP-05).
 *
 * RÈGLES DE CONCEPTION :
 * 1. Le bouton demande uniquement la compilation au back ; aucun chapitre n'est
 *    assemblé ni calculé côté front.
 * 2. Le suivi utilise la tâche uniforme ADR-0008 (Retry-After: 3) et s'arrête
 *    dès l'état terminal `completed` / `failed` ou au départ de la page.
 * 3. Un code de statut non répertorié est restitué tel quel avec le préfixe
 *    « État inconnu » ; les actions dépendantes sont désactivées.
 * 4. DP-05 : après une coupure prolongée, arrêt de la scrutation et bouton
 *    « Réessayer la connexion ». Le seuil reste « à décider ».
 * 5. Aucune écriture dans localStorage ni sessionStorage.
 */
export function useReport({
  caseId,
  enabled = true,
  pollIntervalMs,
}: UseReportOptions): UseReportReturn {
  const [state, setState] = useState<ReportViewState>('loading')
  const [document, setDocument] = useState<ReportDocument | null>(null)
  const [statusLabel, setStatusLabel] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [isFetching, setIsFetching] = useState(false)
  const [isNetworkCutoff, setIsNetworkCutoff] = useState(false)

  const mountedRef = useRef(true)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const consecutiveErrorsRef = useRef(0)
  const cutoffRef = useRef(false)
  const taskIdRef = useRef<string | null>(null)
  const cycleRef = useRef<() => Promise<void>>(async () => {})
  const loadRef = useRef<() => Promise<void>>(async () => {})

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
          : ADR0008_POLLING_DEFAULT_INTERVAL_MS / 1000
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
      setErrorMessage(REPORT_NETWORK_CUTOFF_MESSAGE)
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

  /**
   * Applique l'état de la tâche renvoyée par le back. Retourne `true` lorsqu'une
   * nouvelle requête a déjà été lancée (le `finally` de l'appelant ne doit alors
   * pas masquer son indicateur de charge).
   */
  const applyTask = useCallback(
    (task: ReportTask & ReportErrorPayload, retryAfter: number): boolean => {
      if (task.status === 'completed') {
        clearTimer()
        taskIdRef.current = null
        void loadRef.current()
        return true
      }

      if (task.status === 'failed') {
        clearTimer()
        taskIdRef.current = null
        setState('generationFailed')
        setStatusLabel(null)
        setErrorMessage(readGenerationFailureMessage(task) || REPORT_FAILED_FALLBACK_MESSAGE)
        return false
      }

      if (!isKnownTaskStatus(task.status)) {
        clearTimer()
        taskIdRef.current = null
        setState('unknown')
        setStatusLabel(formatUnknown(task.status))
        setErrorMessage(REPORT_UNKNOWN_DISABLED_NOTE)
        return false
      }

      setState('generating')
      setStatusLabel(null)
      setErrorMessage(null)
      scheduleNext(resolveDelay(retryAfter))
      return false
    },
    [clearTimer, resolveDelay, scheduleNext],
  )

  const loadReport = useCallback(async () => {
    if (!mountedRef.current || !caseId || !enabled || cutoffRef.current) return

    clearTimer()
    setIsFetching(true)
    try {
      const { document: received } = await getReport(caseId)
      if (!mountedRef.current) return

      consecutiveErrorsRef.current = 0
      setIsNetworkCutoff(false)
      setStatusLabel(null)
      setErrorMessage(null)

      if (!received) {
        setDocument(null)
        setState('empty')
        return
      }

      setDocument(received)

      if (received.status === 'validated' || received.status === 'exported') {
        setState('ready')
        return
      }
      if (received.status === 'draft') {
        setState('generating')
        return
      }

      setState('unknown')
      setStatusLabel(formatUnknown(received.status))
      setErrorMessage(REPORT_UNKNOWN_DISABLED_NOTE)
    } catch (err) {
      if (!mountedRef.current) return
      const failure = err as ReportApiError
      if (failure.status === 0) {
        handleTransportFailure()
        return
      }
      clearTimer()
      setState(failure.status === 403 ? 'forbidden' : 'error')
      setErrorMessage(failure.detail ?? failure.message)
      setDocument(null)
    } finally {
      if (mountedRef.current) setIsFetching(false)
    }
  }, [caseId, clearTimer, enabled, handleTransportFailure])

  loadRef.current = loadReport

  const pollTask = useCallback(async () => {
    if (!mountedRef.current || !caseId || !enabled || cutoffRef.current) return

    const taskId = taskIdRef.current
    if (!taskId) {
      void loadRef.current()
      return
    }

    clearTimer()
    setIsFetching(true)
    try {
      const { task, retryAfterSeconds } = await getReportTask(caseId, taskId)
      if (!mountedRef.current) return

      consecutiveErrorsRef.current = 0
      setIsNetworkCutoff(false)
      const initiated = applyTask(task, retryAfterSeconds)
      if (!initiated && mountedRef.current) setIsFetching(false)
    } catch (err) {
      if (!mountedRef.current) return
      const failure = err as ReportApiError
      if (failure.status === 0) {
        handleTransportFailure()
        return
      }
      clearTimer()
      setState(failure.status === 403 ? 'forbidden' : 'error')
      setErrorMessage(failure.detail ?? failure.message)
    } finally {
      if (mountedRef.current) setIsFetching(false)
    }
  }, [caseId, clearTimer, enabled, handleTransportFailure, applyTask])

  const startGeneration = useCallback(async () => {
    if (!mountedRef.current || !caseId || !enabled || cutoffRef.current) return

    clearTimer()
    taskIdRef.current = null
    setDocument(null)
    setStatusLabel(null)
    setErrorMessage(null)
    setIsNetworkCutoff(false)
    setState('generating')
    setIsFetching(true)

    try {
      const { task, retryAfterSeconds } = await generateReport(caseId)
      if (!mountedRef.current) return
      taskIdRef.current = task.task_id
      const initiated = applyTask(task, retryAfterSeconds)
      if (!initiated && mountedRef.current) setIsFetching(false)
    } catch (err) {
      if (!mountedRef.current) return
      const failure = err as ReportApiError
      if (failure.status === 0) {
        handleTransportFailure()
        return
      }
      clearTimer()
      setState(failure.status === 403 ? 'forbidden' : 'error')
      setErrorMessage(failure.detail ?? failure.message)
    } finally {
      if (mountedRef.current) setIsFetching(false)
    }
  }, [caseId, clearTimer, enabled, handleTransportFailure, applyTask])

  useEffect(() => {
    cycleRef.current = pollTask
  }, [pollTask])

  useEffect(() => {
    mountedRef.current = true
    consecutiveErrorsRef.current = 0
    cutoffRef.current = false
    taskIdRef.current = null
    clearTimer()
    setIsNetworkCutoff(false)
    setDocument(null)
    setStatusLabel(null)
    setErrorMessage(null)
    setState('loading')

    if (caseId && enabled) void loadReport()

    return () => {
      mountedRef.current = false
      clearTimer()
    }
  }, [caseId, clearTimer, enabled, loadReport])

  const reset = useCallback(() => {
    consecutiveErrorsRef.current = 0
    cutoffRef.current = false
    clearTimer()
    setIsNetworkCutoff(false)
    setStatusLabel(null)
    setErrorMessage(null)
    setState('loading')
  }, [clearTimer])

  const retryGeneration = useCallback(() => {
    reset()
    void startGeneration()
  }, [reset, startGeneration])

  const retryConnection = useCallback(() => {
    reset()
    if (taskIdRef.current) {
      void cycleRef.current()
    } else {
      void loadRef.current()
    }
  }, [reset])

  const refetch = useCallback(() => {
    reset()
    void loadRef.current()
  }, [reset])

  return {
    state,
    document,
    statusLabel,
    errorMessage,
    isFetching,
    isNetworkCutoff,
    generate: startGeneration,
    retryGeneration,
    retryConnection,
    refetch,
  }
}
