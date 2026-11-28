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

/**
 * Paramètres d'architecture et points de dimensionnement (Story F1.7) :
 * Les typologies d'incident ne sont pas définies dans le contrat cible OpenAPI (openapi.json).
 * Conformément à la règle de non-invention, la valeur proposée est marquée « à décider ».
 */
export const INCIDENT_TYPE_POLICY = 'à décider'

export interface IncidentTypeOption {
  readonly value: string
  readonly label: string
}

export const INCIDENT_TYPE_OPTIONS: readonly IncidentTypeOption[] = [
  { value: 'a_decider', label: 'À décider (typologie non arrêtée au contrat)' },
] as const

/**
 * Données requises pour la création d'un dossier d'investigation (Story F1.7).
 */
export interface CreateCasePayload {
  title: string
  description: string
  incident_date: string
  incident_type: string
  affected_systems: string
}

/**
 * Réponse du serveur lors de la création d'un nouveau dossier d'investigation (Story F1.7).
 */
export interface CreateCaseResponse extends CaseItem {
  incident_date?: string
  incident_type?: string
  affected_systems?: string
}

/**
 * Membre autorisé d'un dossier d'investigation (Story F2.1).
 * Aligné sur les rôles RBAC du contrat (MembershipRole).
 */
export interface CaseMember {
  readonly id: string
  readonly email: string
  readonly name?: string
  readonly role: 'admin' | 'analyst' | 'investigator' | 'viewer'
}

/**
 * Détail d'un dossier d'investigation pour l'écran Contexte (Story F2.1).
 * Comporte les champs du contrat OpenAPI CaseOut ainsi que les données complémentaires
 * requises pour la qualification forensique (incident_date, affected_systems, members)
 * marquées « à réaligner » tant que le contrat OpenAPI ne les formalise pas.
 */
export interface CaseDetail extends CaseItem {
  readonly incident_date?: string | null
  readonly incident_type?: string | null
  readonly affected_systems?: string | null
  readonly members?: readonly CaseMember[]
}

/**
 * Données éditables du contexte d'un dossier (Story F2.1).
 * Seuls le titre et la description sont modifiables en ligne au MVP.
 */
export interface UpdateCasePayload {
  readonly title: string
  readonly description?: string | null
}

/**
 * Matrice stricte des transitions de cycle de vie d'un dossier d'investigation (Story F2.2).
 * Conforme à openapi.json et docs/frontend/12-parcours-et-etats.md.
 * Toute transition absente est « à décider » et ne doit pas être proposée dans l'interface.
 */
export const VALID_CASE_STATUS_TRANSITIONS: Record<CaseStatus, readonly CaseStatus[]> = {
  open: ['in_progress', 'closed'],
  in_progress: ['review', 'open', 'closed'],
  review: ['closed', 'in_progress'],
  closed: [],
}

/**
 * Libellés en majuscules pour le badge d'en-tête (Story F2.2).
 */
export const CASE_STATUS_UPPERCASE_LABELS: Record<CaseStatus, string> = {
  open: 'OUVERT',
  in_progress: 'EN COURS',
  review: 'EN REVUE',
  closed: 'CLÔTURÉ',
}

/**
 * Libellés en français pour l'affichage standard et les options du sélecteur (Story F2.2).
 */
export const CASE_STATUS_LABELS: Record<CaseStatus, string> = {
  open: 'Ouvert',
  in_progress: 'En cours',
  review: 'En revue',
  closed: 'Clôturé',
}

/**
 * Libellé pour l'état vide ou indéfini (Story F2.2).
 */
export const CASE_STATUS_UNDEFINED_LABEL = 'NON DÉFINI'

/**
 * Corps de requête pour la mise à jour de statut opérationnel d'un dossier (Story F2.2).
 */
export interface UpdateCaseStatusPayload {
  readonly status: CaseStatus
}

/**
 * Mention affichée pour les champs requis par le métier mais absents du contrat OpenAPI cible.
 */
export const CONTRACT_ALIGNMENT_REQUIRED_LABEL = 'à réaligner'
