import { useQuery } from '@tanstack/react-query'
import { getObservationSource, SourcePanelApiError } from '../services/sourcePanelService'
import type { ObservationRead } from '../types'

export interface UseSourceDetailOptions {
  readonly caseId: string
  readonly observationId?: string
  readonly enabled?: boolean
}

export interface UseSourceDetailResult {
  readonly observation: ObservationRead | undefined
  readonly isLoading: boolean
  readonly isError: boolean
  readonly error: SourcePanelApiError | Error | null
  readonly isForbidden: boolean
  readonly isNotFound: boolean
  readonly refetch: () => void
}

/**
 * Consultation ponctuelle de la source d'un événement (F4.7, C2).
 * Aucune scrutation : contrairement au suivi d'ingestion (ADR-0008), le
 * panneau est ouvert à la demande et ne renouvelle pas la requête seul.
 */
export function useSourceDetail({
  caseId,
  observationId,
  enabled = true,
}: UseSourceDetailOptions): UseSourceDetailResult {
  const query = useQuery({
    queryKey: ['source-detail', caseId, observationId],
    queryFn: () => getObservationSource(caseId, observationId!),
    enabled: Boolean(enabled && caseId && observationId),
    retry: false,
    staleTime: 0,
  })

  const apiError = query.error as SourcePanelApiError | null
  return {
    observation: query.data,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    isForbidden: apiError?.status === 403,
    isNotFound: apiError?.status === 404,
    refetch: query.refetch,
  }
}
