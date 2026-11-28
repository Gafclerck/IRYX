import { useMutation, useQueryClient } from '@tanstack/react-query'
import { updateCase, CasesError } from '../../../api/cases'
import type { CaseDetail, UpdateCasePayload } from '../../../api/cases-types'

export interface UpdateCaseVariables {
  caseId: string
  payload: UpdateCasePayload
}

/**
 * Hook TanStack Query pour la mise à jour en ligne d'un dossier (Story F2.1).
 * Route : PATCH /api/v1/cases/:caseId
 */
export function useUpdateCase() {
  const queryClient = useQueryClient()

  return useMutation<CaseDetail, CasesError, UpdateCaseVariables>({
    mutationFn: ({ caseId, payload }) => updateCase(caseId, payload),
    onSuccess: (updatedCase) => {
      // Met à jour immédiatement le cache du dossier unitaire
      queryClient.setQueryData(['cases', updatedCase.id], updatedCase)
      // Invalide la liste des dossiers pour refléter les modifications de titre
      queryClient.invalidateQueries({ queryKey: ['cases'] })
    },
  })
}
