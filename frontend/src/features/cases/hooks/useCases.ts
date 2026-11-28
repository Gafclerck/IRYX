import { useQuery } from '@tanstack/react-query'
import { getCases, CasesError } from '../../../api/cases'
import type { CaseListResponse, GetCasesParams } from '../../../api/cases-types'
import { DEFAULT_PAGE_SIZE } from '../../../api/cases-types'

export interface UseCasesOptions extends GetCasesParams {
  readonly enabled?: boolean
  readonly retry?: boolean | number | ((failureCount: number, error: CasesError) => boolean)
}

/**
 * Hook TanStack Query de récupération paginée des dossiers d'investigation (Story F1.6).
 *
 * RÈGLES DE CONCEPTION :
 * 1. Découplage strict : les composants de présentation n'exécutent aucun appel réseau direct.
 * 2. Pagination côté serveur : ne charge jamais la liste complète en mémoire client.
 * 3. Filtrage dynamique par titre : rechargement de page 1 sur changement de recherche.
 * 4. Gestion des 5 états : loading, empty, error (5xx), forbidden (403), nominal.
 * 5. En cas d'erreur 5xx ou 403 : affichage direct de la bannière dédiée avec bouton Réessayer (pas de réessai silencieux masquant l'erreur).
 */
export function useCases(options: UseCasesOptions = {}) {
  const page = options.page && options.page > 0 ? options.page : 1
  const limit = options.limit ?? DEFAULT_PAGE_SIZE
  const search = options.search?.trim() || ''
  const enabled = options.enabled !== false
  const retry = options.retry !== undefined ? options.retry : false

  return useQuery<CaseListResponse, CasesError>({
    queryKey: ['cases', { page, limit, search }],
    queryFn: () => getCases({ page, limit, search }),
    enabled,
    retry,
  })
}
