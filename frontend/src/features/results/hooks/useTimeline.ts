import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { TIMELINE_PAGE_SIZE } from '../constants'
import { getTimelineBlock, TimelineApiError } from '../services/timelineService'
import {
  EMPTY_TIMELINE_FILTERS,
  type ObservationListResponse,
  type TimelineEntry,
  type TimelineFilters,
  type TimelineViewState,
} from '../types'
import { buildTimelineEntries } from '../utils/timelineEntry'

export interface UseTimelineOptions {
  readonly caseId: string
  readonly enabled?: boolean
}

interface TimelineQuery {
  readonly caseId: string
  readonly filters: TimelineFilters
  readonly page: number
}

export interface UseTimelineReturn {
  readonly state: TimelineViewState
  readonly block: ObservationListResponse | null
  readonly entries: readonly TimelineEntry[]
  readonly errorMessage: string | null
  readonly isFetching: boolean
  readonly filters: TimelineFilters
  readonly page: number
  readonly hasMore: boolean
  readonly applyFilters: (filters: TimelineFilters) => void
  readonly resetFilters: () => void
  readonly goToNextBlock: () => void
  readonly goToPreviousBlock: () => void
  readonly refetch: () => void
}

/**
 * Chronologie unifiée par pagination serveur stricte (Story F4.6, DP-01).
 *
 * RÈGLES DE CONCEPTION :
 * 1. Une seule requête par bloc de 100 événements ; le bloc précédent est
 *    remplacé, jamais accumulé.
 * 2. Les filtres sont transmis au serveur et maintenus lors des changements de bloc.
 * 3. Aucune écriture dans localStorage ni sessionStorage ; aucune mutation.
 * 4. Aucune scrutation : la chronologie est une consultation ponctuelle, sans
 *    rapport avec le polling asynchrone de l'ADR-0008.
 */
export function useTimeline({ caseId, enabled = true }: UseTimelineOptions): UseTimelineReturn {
  const [query, setQuery] = useState<TimelineQuery>({
    caseId,
    filters: EMPTY_TIMELINE_FILTERS,
    page: 1,
  })
  const [block, setBlock] = useState<ObservationListResponse | null>(null)
  const [state, setState] = useState<TimelineViewState>('loading')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [isFetching, setIsFetching] = useState(false)
  const [reloadToken, setReloadToken] = useState(0)
  const requestIdRef = useRef(0)

  useEffect(() => {
    setQuery((current) =>
      current.caseId === caseId ? current : { caseId, filters: EMPTY_TIMELINE_FILTERS, page: 1 },
    )
  }, [caseId])

  useEffect(() => {
    if (!enabled || !caseId || query.caseId !== caseId) return

    const requestId = ++requestIdRef.current
    let active = true

    setState('loading')
    setIsFetching(true)
    setErrorMessage(null)

    getTimelineBlock({
      caseId,
      offset: (query.page - 1) * TIMELINE_PAGE_SIZE,
      filters: query.filters,
    })
      .then((response) => {
        if (!active || requestId !== requestIdRef.current) return
        setBlock(response)
        setState(response.items.length === 0 ? 'empty' : 'success')
      })
      .catch((err: unknown) => {
        if (!active || requestId !== requestIdRef.current) return
        const failure = err as TimelineApiError
        setBlock(null)
        setState(failure.status === 403 ? 'forbidden' : 'error')
        setErrorMessage(failure.message ?? 'Échec de la récupération de la chronologie.')
      })
      .finally(() => {
        if (active && requestId === requestIdRef.current) setIsFetching(false)
      })

    return () => {
      active = false
    }
  }, [caseId, enabled, query, reloadToken])

  const entries = useMemo(() => (block ? buildTimelineEntries(block.items) : []), [block])

  const applyFilters = useCallback((filters: TimelineFilters) => {
    setQuery((current) => ({ ...current, filters, page: 1 }))
  }, [])

  const resetFilters = useCallback(() => {
    setQuery((current) => ({ ...current, filters: EMPTY_TIMELINE_FILTERS, page: 1 }))
  }, [])

  const goToNextBlock = useCallback(() => {
    setQuery((current) => ({ ...current, page: current.page + 1 }))
  }, [])

  const goToPreviousBlock = useCallback(() => {
    setQuery((current) => ({ ...current, page: Math.max(1, current.page - 1) }))
  }, [])

  const refetch = useCallback(() => {
    setReloadToken((value) => value + 1)
  }, [])

  return {
    state,
    block,
    entries,
    errorMessage,
    isFetching,
    filters: query.filters,
    page: query.page,
    hasMore: block?.has_more ?? false,
    applyFilters,
    resetFilters,
    goToNextBlock,
    goToPreviousBlock,
    refetch,
  }
}
