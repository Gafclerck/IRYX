import type { components } from '../../api/schema'

/**
 * Types d'API strictement dérivés du contrat OpenAPI (docs/contrat/openapi.json).
 * Aucune redéclaration manuelle de schéma n'est autorisée (docs/frontend/14, règle 1).
 */
export type InvestigationPlan = components['schemas']['InvestigationPlan']
export type InvestigationPlanStep = components['schemas']['InvestigationPlanStep']
export type InvestigationRunOut = components['schemas']['InvestigationRunOut']

/**
 * États d'affichage de l'écran de consultation du plan (Story F4.1).
 */
export type PlanViewState =
  'loading' | 'planning' | 'ready' | 'empty' | 'validated' | 'error' | 'forbidden'

export interface PlanStatusDisplayInfo {
  readonly label: string
  readonly isKnown: boolean
  readonly isTerminal: boolean
}
