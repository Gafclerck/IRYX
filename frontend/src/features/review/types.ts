/**
 * Types de la revue H2 (Story F4.8, FR-REV-01).
 *
 * Les findings proviennent du contrat openapi.json (GET /cases/{case_id}/findings).
 * La route de décision H2 n'existe pas dans le contrat : aucune décision n'est
 * simulée comme acquise sans contrat. Marqué "à réaligner (E6)".
 */
import type { components } from '../../api/schema'

export type FindingOut = components['schemas']['FindingOut']
export type FindingListResponse = components['schemas']['FindingListResponse']
export type FindingStatus = components['schemas']['FindingStatus']
export type FindingSeverity = components['schemas']['FindingSeverity']
export type FindingConfidence = components['schemas']['FindingConfidence']
export type FindingType = components['schemas']['FindingType']

export type ReviewViewState = 'loading' | 'ready' | 'empty' | 'error' | 'forbidden'

export interface ReviewCounts {
  readonly validated: number
  readonly rejected: number
  readonly pending: number
}

export interface ReviewDecisionPayload {
  readonly decision: 'validated' | 'rejected'
  readonly comment?: string
  readonly rejectionReason?: string
}
