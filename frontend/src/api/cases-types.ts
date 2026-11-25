/**
 * Types et interfaces de l'espace Dossiers d'investigation (Story F1.6).
 * Aligné sur le contrat cible Épic E2 (openapi.json).
 */

/**
 * Statuts opérationnels du cycle de vie d'un dossier d'investigation (E2).
 */
export type CaseStatus = 'open' | 'in_progress' | 'review' | 'closed'

/**
 * Entité représentant un dossier d'investigation dans le tableau de consultation (Story F1.6).
 * Aligné sur le schéma OpenAPI CaseOut, enrichi du décompte des preuves scellées.
 */
export interface CaseItem {
  id: string
  organization_id: string
  title: string
  description?: string | null
  status: CaseStatus
  created_by?: string | null
  created_at: string
  updated_at: string
  evidence_count: number
}

/**
 * Réponse paginée de consultation des dossiers (Story F1.6).
 * Aligné sur le schéma OpenAPI CaseListResponse.
 */
export interface CaseListResponse {
  items: CaseItem[]
  total: number
  total_items: number
  limit: number
  offset: number
  has_more: boolean
}

/**
 * Paramètres de requête transmis pour la pagination et la recherche côté serveur.
 */
export interface GetCasesParams {
  page?: number
  limit?: number
  offset?: number
  search?: string
}

/**
 * Paramètres d'architecture et points de dimensionnement (Story F1.6) :
 * Durée de pause de frappe (debounce) et taille de page par défaut : à décider.
 */
export const SEARCH_DEBOUNCE_DELAY_MS = 300
export const SEARCH_DEBOUNCE_POLICY = 'à décider'

export const DEFAULT_PAGE_SIZE = 10
export const PAGE_SIZE_POLICY = 'à décider'
