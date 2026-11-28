import { useQuery } from '@tanstack/react-query'
import { getCase, CasesError } from '../../../api/cases'
import type { CaseDetail } from '../../../api/cases-types'

export interface UseCaseDetailOptions {
  readonly enabled?: boolean
  readonly retry?: boolean | number | ((failureCount: number, error: CasesError) => boolean)
}

/**
 * Hook TanStack Query pour la consultation unitaire d'un dossier (Story F2.1).
 * Route : GET /api/v1/cases/:caseId
 */
export function useCaseDetail(caseId: string | undefined, options: UseCaseDetailOptions = {}) {
  const enabled = Boolean(caseId) && options.enabled !== false
  const retry = options.retry !== undefined ? options.retry : false

  return useQuery<CaseDetail, CasesError>({
    queryKey: ['cases', caseId],
    queryFn: () => {
      if (!caseId) {
        throw new CasesError('Identifiant de dossier manquant.', 400)
      }
      return getCase(caseId)
    },
    enabled,
    retry,
  })
}
