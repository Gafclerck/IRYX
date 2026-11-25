import type { components } from '../../api/schema'

/**
 * Types strictement dérivés du contrat OpenAPI (docs/contrat/openapi.json).
 * Aucun champ d'agent, de progression, de message ou de journal n'est redéclaré :
 * ces informations absentes du contrat restent « à réaligner » côté interface.
 */
export type InvestigationRunOut = components['schemas']['InvestigationRunOut']
export type PhaseOut = components['schemas']['PhaseOut']
export type PhaseStatus = components['schemas']['PhaseStatus']

/**
 * États d'affichage de la console de supervision (Story F4.3).
 * `canceled` est demandé par la story mais absent de `InvestigationStatus` : il est
 * restitué avec la mention « à réaligner » lorsqu'il est reçu par le client.
 */
export type RunViewState =
  | 'loading'
  | 'waiting'
  | 'running'
  | 'paused'
  | 'partialFailure'
  | 'completed'
  | 'failed'
  | 'canceled'
  | 'unknown'
  | 'error'
  | 'networkCutoff'
  | 'forbidden'

export interface RunStatusDisplayInfo {
  readonly label: string
  readonly isKnown: boolean
  readonly isTerminal: boolean
  readonly isRealigned: boolean
}

export interface PhaseStatusDisplayInfo {
  readonly label: string
  readonly isKnown: boolean
  readonly isFailed: boolean
}

export type AgentKey = 'planner' | 'executor' | 'analyst' | 'verifier' | 'correlator' | 'reporter'

export interface AgentCardData {
  readonly key: AgentKey
  readonly name: string
  readonly statusLabel: string
  readonly isFailed: boolean
  readonly isRealigned: boolean
  readonly elapsedLabel: string
  readonly progressLabel: string
  readonly lastMessageLabel: string
  readonly diagnosticLabel: string
}

export interface ActivityEntry {
  readonly id: string
  readonly timestamp: string
  readonly agentName: string
  readonly eventLabel: string
}
