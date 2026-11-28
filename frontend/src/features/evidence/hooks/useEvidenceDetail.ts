import { useQuery } from '@tanstack/react-query'
import { getEvidenceDetail, EvidenceApiError } from '../services/evidenceService'
import type { EvidenceDetail } from '../types'

export interface UseEvidenceDetailOptions {
  readonly caseId: string
  readonly evidenceId?: string
  readonly enabled?: boolean
}

export interface UseEvidenceDetailResult {
  readonly evidence: EvidenceDetail | undefined
  readonly isLoading: boolean
  readonly isFetching: boolean
  readonly isError: boolean
  readonly error: EvidenceApiError | Error | null
  readonly isForbidden: boolean
  readonly isNotFound: boolean
  readonly refetch: () => void
}

/**
 * Hook de consultation détaillée d'une preuve pour le panneau latéral (Story F3.3).
 *
 * RÈGLES DE CONCEPTION (FR-EVI-03, C2, DP-04, 11-ecrans-et-routes.md, 12-parcours-et-etats.md) :
 * 1. Déclenché lorsque evidenceId est défini et que le panneau est ouvert.
 * 2. Principe C2 : réactivité immédiate sans délai artificiel.
 * 3. États gérés : chargement, erreur avec réessai, accès refusé (403), introuvable (404, message neutre), nominal.
 */
export function useEvidenceDetail({
  caseId,
  evidenceId,
  enabled = true,
}: UseEvidenceDetailOptions): UseEvidenceDetailResult {
  const query = useQuery({
    queryKey: ['evidence-detail', caseId, evidenceId],
    queryFn: () => getEvidenceDetail(caseId, evidenceId!),
    enabled: Boolean(enabled && caseId && evidenceId),
    retry: false,
    staleTime: 5000,
  })

  const apiError = query.error as EvidenceApiError | null
  const isForbidden = apiError?.status === 403
  const isNotFound = apiError?.status === 404

  return {
    evidence: query.data,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isError: query.isError,
    error: query.error,
    isForbidden,
    isNotFound,
    refetch: query.refetch,
  }
}
