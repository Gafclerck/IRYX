import { useMutation, useQueryClient } from '@tanstack/react-query'
import { updateCaseStatus, CasesError } from '../../../api/cases'
import type { CaseDetail, UpdateCaseStatusPayload } from '../../../api/cases-types'

export interface UpdateCaseStatusVariables {
  caseId: string
  payload: UpdateCaseStatusPayload
}

/**
 * Hook TanStack Query pour l'évolution du statut global d'un dossier (Story F2.2).
 * Route : PATCH /api/v1/cases/:caseId/status
 */
export function useUpdateCaseStatus() {
  const queryClient = useQueryClient()

  return useMutation<CaseDetail, CasesError, UpdateCaseStatusVariables>({
    mutationFn: ({ caseId, payload }) => updateCaseStatus(caseId, payload),
    onSuccess: (updatedCase) => {
      // 1. Met à jour immédiatement le cache du dossier unitaire
      queryClient.setQueryData(['cases', updatedCase.id], updatedCase)
      // 2. Invalide le cache des dossiers pour synchroniser la barre latérale et la liste
      queryClient.invalidateQueries({ queryKey: ['cases'] })
    },
  })
}
