import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createCase, CaseCreationError } from '../../../api/cases'
import type { CreateCasePayload, CreateCaseResponse } from '../../../api/cases-types'

export interface UseCreateCaseOptions {
  onSuccess?: (createdCase: CreateCaseResponse) => void
  onError?: (error: CaseCreationError) => void
}

/**
 * Hook TanStack Query pour la création d'un dossier d'investigation en modale (Story F1.7).
 * Invalide automatiquement le cache des requêtes ['cases'] en cas de succès.
 */
export function useCreateCase(options: UseCreateCaseOptions = {}) {
  const queryClient = useQueryClient()

  return useMutation<CreateCaseResponse, CaseCreationError, CreateCasePayload>({
    mutationFn: (payload) => createCase(payload),
    onSuccess: (createdCase) => {
      // Invalidation immédiate du cache de consultation des dossiers
      queryClient.invalidateQueries({ queryKey: ['cases'] })
      options.onSuccess?.(createdCase)
    },
    onError: (error) => {
      options.onError?.(error)
    },
  })
}
