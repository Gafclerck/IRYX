import { apiClient } from './client'
import type { CaseListResponse, GetCasesParams, CaseItem } from './cases-types'
import { DEFAULT_PAGE_SIZE } from './cases-types'

/**
 * Erreur spécifique liée à la consultation des dossiers.
 */
export class CasesError extends Error {
  readonly status: number

  constructor(message: string, status: number = 0) {
    super(message)
    this.name = 'CasesError'
    this.status = status
  }
}

/**
 * Récupération paginée des dossiers d'investigation avec filtrage serveur par titre (Story F1.6).
 * Route cible : GET /api/v1/cases
 * Contrat cible : openapi.json (simulée E2)
 *
 * RÈGLES DE CONCEPTION :
 * 1. Pagination côté serveur stricte : le front transmet la page et la taille demandées.
 *    Il ne charge jamais la liste complète côté client.
 * 2. Filtrage par titre transmis au serveur via le paramètre de recherche.
 * 3. En cas d'erreur HTTP 403 Forbidden : lève une CasesError avec statut 403.
 * 4. En cas d'erreur HTTP 5xx : lève une CasesError avec le statut correspondant.
 */
export async function getCases(params: GetCasesParams = {}): Promise<CaseListResponse> {
  const limit = params.limit ?? DEFAULT_PAGE_SIZE
  const page = params.page && params.page > 0 ? params.page : 1
  const offset = params.offset !== undefined ? params.offset : (page - 1) * limit
  const search = params.search?.trim() || undefined

  const { data, response, error } = await apiClient.GET('/api/v1/cases', {
    params: {
      query: {
        limit,
        offset,
        ...(search ? { search } : {}),
      } as never,
    },
  })

  if (response.status === 403) {
    throw new CasesError(
      "Accès refusé. Vous n'avez pas accès aux dossiers de cette organisation. Veuillez contacter votre administrateur.",
      403,
    )
  }

  if (!response.ok || error) {
    const detail =
      (error as { detail?: string })?.detail ||
      'Échec du chargement des dossiers. Veuillez réessayer ultérieurement.'
    throw new CasesError(detail, response.status)
  }

  if (!data) {
    const status = (response as unknown as { status?: number })?.status || 500
    throw new CasesError('Données de dossiers indisponibles.', status)
  }

  const rawItems = (data.items || []) as unknown as Array<Partial<CaseItem>>
  const items: CaseItem[] = rawItems.map((item) => ({
    id: item.id || '',
    organization_id: item.organization_id || '',
    title: item.title || '',
    description: item.description ?? null,
    status: (item.status || 'open') as CaseItem['status'],
    created_by: item.created_by ?? null,
    created_at: item.created_at || new Date().toISOString(),
    updated_at: item.updated_at || new Date().toISOString(),
    evidence_count: typeof item.evidence_count === 'number' ? item.evidence_count : 0,
  }))

  const total = data.total ?? data.total_items ?? items.length
  const totalItems = data.total_items ?? data.total ?? items.length
  const responseLimit = data.limit ?? limit
  const responseOffset = data.offset ?? offset
  const hasMore =
    typeof data.has_more === 'boolean' ? data.has_more : responseOffset + items.length < total

  return {
    items,
    total,
    total_items: totalItems,
    limit: responseLimit,
    offset: responseOffset,
    has_more: hasMore,
  }
}
