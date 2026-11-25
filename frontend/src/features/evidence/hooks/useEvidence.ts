import { useState, useEffect, useRef, useCallback } from 'react'
import type { EvidenceInventoryItem, EvidenceRead } from '../types'
import {
  getEvidences,
  getEvidenceIngestionStatus,
  EvidenceApiError,
} from '../services/evidenceService'
import {
  ADR0008_POLLING_DEFAULT_INTERVAL_MS,
  ADR0008_POLLING_MAX_BACKOFF_MS,
  DP05_MAX_CONSECUTIVE_NETWORK_ERRORS,
  TERMINAL_INGESTION_STATUSES,
  formatIngestionStatus,
} from '../constants'

export interface UseEvidenceOptions {
  readonly caseId: string
  readonly enabled?: boolean
}

export interface UseEvidenceReturn {
  readonly evidences: readonly EvidenceInventoryItem[]
  readonly total: number
  readonly isLoading: boolean
  readonly isFetching: boolean
  readonly isError: boolean
  readonly error: Error | EvidenceApiError | null
  readonly isForbidden: boolean
  readonly isNetworkCutoff: boolean
  readonly hasIntegrityEvidence: boolean
  readonly refetch: () => Promise<void>
  readonly retryConnection: () => void
}

/**
 * Hook de consultation de l'inventaire des preuves et suivi par scrutation (Story F3.2).
 *
 * RÈGLES DE CONCEPTION (FR-EVI-02, ADR-0008, DP-05, 12-parcours-et-etats.md) :
 * 1. Récupère la liste des preuves du dossier via GET /api/v1/cases/:caseId/evidences.
 * 2. Déclenche une scrutation asynchrone pour chaque preuve non terminée (pending / processing).
 * 3. Cadence pilotée par l'en-tête standard Retry-After (défaut 3 s, ADR-0008).
 * 4. Recul exponentiel en cas d'erreur réseau temporaire.
 * 5. La scrutation s'arrête dès qu'un état terminal est atteint (completed ou failed) ou au départ de la page.
 * 6. Dès qu'au moins une preuve est confirmée intègre (completed), hasIntegrityEvidence = true.
 * 7. DP-05 : en cas de coupure prolongée (3 erreurs consécutives), la scrutation s'interrompt et
 *    isNetworkCutoff bascule à true avec proposition du bouton « Réessayer la connexion ».
 * 8. En cas de réponse 401 ou 403, la scrutation s'interrompt immédiatement.
 */
export function useEvidence({
  caseId,
  enabled = true,
}: UseEvidenceOptions): UseEvidenceReturn {
  const [evidences, setEvidences] = useState<EvidenceInventoryItem[]>([])
  const [total, setTotal] = useState(0)
  const [isLoading, setIsLoading] = useState(true)
  const [isFetching, setIsFetching] = useState(false)
  const [isError, setIsError] = useState(false)
  const [error, setError] = useState<Error | EvidenceApiError | null>(null)
  const [isForbidden, setIsForbidden] = useState(false)
  const [isNetworkCutoff, setIsNetworkCutoff] = useState(false)

  const isMountedRef = useRef(true)
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())
  const consecutiveErrorsRef = useRef(0)

  // Nettoyage de l'ensemble des timers de scrutation actifs
  const clearAllTimers = useCallback(() => {
    timersRef.current.forEach((timer) => clearTimeout(timer))
    timersRef.current.clear()
  }, [])

  // Nettoyage d'un timer spécifique
  const clearEvidenceTimer = useCallback((evidenceId: string) => {
    const existing = timersRef.current.get(evidenceId)
    if (existing) {
      clearTimeout(existing)
      timersRef.current.delete(evidenceId)
    }
  }, [])

  // Fonction de scrutation d'une preuve unitaire non terminée
  const pollEvidenceStatus = useCallback(
    async (evidenceId: string) => {
      if (!isMountedRef.current || !caseId) return

      setIsFetching(true)

      try {
        const { data, retryAfterSeconds } = await getEvidenceIngestionStatus(
          caseId,
          evidenceId,
        )

        if (!isMountedRef.current) return

        // Réinitialisation du compteur d'erreurs en cas de succès
        consecutiveErrorsRef.current = 0
        if (isNetworkCutoff) {
          setIsNetworkCutoff(false)
        }

        const statusInfo = formatIngestionStatus(data.status)

        // Mise à jour de l'élément dans la liste
        setEvidences((prev) =>
          prev.map((item) => {
            if (item.id !== evidenceId) return item
            return {
              ...item,
              ingestionStatus: data.status,
              ingestionProgress: data.progress,
              ingestionErrorMessage: data.error_message,
              sha256: data.sha256 ?? item.sha256,
              detected_type: data.detected_type ?? item.detected_type,
              isPollingActive: !statusInfo.isTerminal,
            }
          }),
        )

        // Si l'état est terminal (completed, failed, ou inconnu robuste) : fin de la scrutation pour cette preuve
        if (statusInfo.isTerminal) {
          clearEvidenceTimer(evidenceId)
        } else {
          // Programmation de la prochaine scrutation selon Retry-After (ADR-0008)
          const delayMs = (retryAfterSeconds || ADR0008_POLLING_DEFAULT_INTERVAL_MS / 1000) * 1000
          clearEvidenceTimer(evidenceId)
          const timerId = setTimeout(() => {
            pollEvidenceStatus(evidenceId)
          }, delayMs)
          timersRef.current.set(evidenceId, timerId)
        }
      } catch (err: unknown) {
        if (!isMountedRef.current) return

        const apiErr = err as EvidenceApiError
        const status = apiErr?.status

        // En cas de 401 ou 403 : interruption immédiate du cycle complet de scrutation
        if (status === 401 || status === 403) {
          clearAllTimers()
          if (status === 403) {
            setIsForbidden(true)
          }
          return
        }

        // Recul exponentiel et détection de coupure prolongée DP-05
        consecutiveErrorsRef.current += 1

        if (consecutiveErrorsRef.current >= DP05_MAX_CONSECUTIVE_NETWORK_ERRORS) {
          // Arrêt de l'interrogation sur coupure prolongée
          clearAllTimers()
          setIsNetworkCutoff(true)
          setEvidences((prev) =>
            prev.map((item) => ({ ...item, isPollingActive: false })),
          )
        } else {
          // Recul exponentiel plafonné (ADR-0008)
          const backoff = Math.min(
            ADR0008_POLLING_DEFAULT_INTERVAL_MS * Math.pow(2, consecutiveErrorsRef.current),
            ADR0008_POLLING_MAX_BACKOFF_MS,
          )
          clearEvidenceTimer(evidenceId)
          const timerId = setTimeout(() => {
            pollEvidenceStatus(evidenceId)
          }, backoff)
          timersRef.current.set(evidenceId, timerId)
        }
      } finally {
        if (isMountedRef.current) {
          setIsFetching(false)
        }
      }
    },
    [caseId, clearAllTimers, clearEvidenceTimer, isNetworkCutoff],
  )

  // Chargement de l'inventaire des preuves
  const fetchEvidences = useCallback(
    async (isInitial = false) => {
      if (!caseId || !enabled) return

      if (isInitial) {
        setIsLoading(true)
      } else {
        setIsFetching(true)
      }

      setIsError(false)
      setError(null)
      setIsForbidden(false)

      try {
        const response = await getEvidences(caseId)

        if (!isMountedRef.current) return

        setTotal(response.total_items || response.total || response.items.length)

        // Conversion des preuves en items d'inventaire
        const inventoryItems: EvidenceInventoryItem[] = response.items.map((raw: EvidenceRead) => {
          // Préservation du statut d'ingestion déjà présent s'il existe
          const existing = evidences.find((e) => e.id === raw.id)
          const initialStatus = existing?.ingestionStatus || (raw.sha256 ? 'completed' : 'pending')
          const isTerminal = (TERMINAL_INGESTION_STATUSES as readonly string[]).includes(initialStatus)

          return {
            ...raw,
            ingestionStatus: initialStatus,
            ingestionProgress: existing?.ingestionProgress ?? (initialStatus === 'completed' ? 100 : 0),
            ingestionErrorMessage: existing?.ingestionErrorMessage ?? null,
            isPollingActive: !isTerminal,
          }
        })

        setEvidences(inventoryItems)

        // Lancement de la scrutation pour les éléments non terminés
        inventoryItems.forEach((item) => {
          const statusInfo = formatIngestionStatus(item.ingestionStatus)
          if (!statusInfo.isTerminal && !timersRef.current.has(item.id)) {
            // Lancement initial ou programmé
            pollEvidenceStatus(item.id)
          }
        })
      } catch (err: unknown) {
        if (!isMountedRef.current) return

        const apiErr = err as EvidenceApiError
        setIsError(true)
        setError(apiErr)

        if (apiErr?.status === 403) {
          setIsForbidden(true)
          clearAllTimers()
        }
      } finally {
        if (isMountedRef.current) {
          setIsLoading(false)
          setIsFetching(false)
        }
      }
    },
    [caseId, enabled, evidences, clearAllTimers, pollEvidenceStatus],
  )

  // Chargement au montage ou changement de dossier
  useEffect(() => {
    isMountedRef.current = true
    clearAllTimers()
    consecutiveErrorsRef.current = 0
    setIsNetworkCutoff(false)

    if (caseId && enabled) {
      fetchEvidences(true)
    }

    return () => {
      isMountedRef.current = false
      clearAllTimers()
    }
  }, [caseId, enabled]) // fetchEvidences n'est pas dans les dépendances pour éviter les recharges en boucle

  // Fonction de relance de la connexion après coupure prolongée (DP-05)
  const retryConnection = useCallback(() => {
    consecutiveErrorsRef.current = 0
    setIsNetworkCutoff(false)
    fetchEvidences(false)
  }, [fetchEvidences])

  // Détection de la condition d'analyse : au moins une preuve est intègre (completed)
  const hasIntegrityEvidence = evidences.some(
    (item) => item.ingestionStatus === 'completed',
  )

  return {
    evidences,
    total,
    isLoading,
    isFetching,
    isError,
    error,
    isForbidden,
    isNetworkCutoff,
    hasIntegrityEvidence,
    refetch: () => fetchEvidences(false),
    retryConnection,
  }
}
