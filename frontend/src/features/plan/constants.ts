import type { PlanStatusDisplayInfo } from './types'

/**
 * Constantes de scrutation lues directement dans l'ADR-0008 (Option A) :
 * - en-tête Retry-After: 3 sur les réponses asynchrones ;
 * - cadence conseillée 3 à 5 secondes ;
 * - recul exponentiel plafonné en cas d'erreur de transport HTTP.
 */
export const ADR0008_POLLING_DEFAULT_INTERVAL_SECONDS = 3
export const ADR0008_POLLING_DEFAULT_INTERVAL_MS = 3000
export const ADR0008_POLLING_MAX_BACKOFF_MS = 15000

/**
 * Décision DP-05 : arrêt de l'interrogation en cas de coupure prolongée avec bouton
 * « Réessayer la connexion ». Le seuil de déclenchement reste « à décider »
 * (docs/frontend/15-decisions-ouvertes.md) : la valeur technique de repli n'est jamais
 * présentée à l'utilisateur comme une décision validée.
 */
export const DP05_CUTOFF_NOTE = 'Seuil de coupure réseau prolongée : à décider (DP-05)'
export const DP05_MAX_CONSECUTIVE_NETWORK_ERRORS = 3

export const PLAN_NOT_FOUND_CODE = 'PLAN_NOT_FOUND'

/**
 * Statuts du cycle de vie d'une session d'investigation (docs/frontend/12, section 3.2).
 */
export const KNOWN_INVESTIGATION_STATUSES = [
  'pending',
  'running',
  'paused',
  'completed',
  'failed',
] as const

export const TERMINAL_INVESTIGATION_STATUSES = ['completed', 'failed'] as const

/**
 * Phases du contrat (PhaseName dans openapi.json). Une phase non répertoriée ne bloque
 * jamais l'affichage : elle est restituée sous la forme « État inconnu (code) ».
 */
export const KNOWN_INVESTIGATION_PHASES = [
  'triage',
  'planner',
  'planning',
  'gate_h1',
  'waiting_h1',
  'executor',
  'execution',
  'analyst',
  'analysis',
  'verifier',
  'verification',
  'gate_h2',
  'pseudonymization',
  'gate_h3',
  'reporting',
] as const

/**
 * Formate un statut de session selon la règle de robustesse de docs/frontend/12, section 4 :
 * « État inconnu » suivi du code textuel brut retourné entre parenthèses, sans blocage.
 */
export function formatInvestigationStatus(
  status: string | undefined | null,
): PlanStatusDisplayInfo {
  switch (status) {
    case 'pending':
      return { label: 'EN ATTENTE', isKnown: true, isTerminal: false }
    case 'running':
      return { label: 'EN COURS', isKnown: true, isTerminal: false }
    case 'paused':
      return { label: 'EN PAUSE', isKnown: true, isTerminal: false }
    case 'completed':
      return { label: 'TERMINÉ', isKnown: true, isTerminal: true }
    case 'failed':
      return { label: 'ÉCHEC', isKnown: true, isTerminal: true }
    default:
      return {
        label: `État inconnu (${status ?? 'non fourni'})`,
        isKnown: false,
        isTerminal: true,
      }
  }
}

/**
 * Formate une phase du contrat sans inventer de traduction : le code brut est conservé.
 */
export function formatInvestigationPhase(phase: string | undefined | null): PlanStatusDisplayInfo {
  if (phase && (KNOWN_INVESTIGATION_PHASES as readonly string[]).includes(phase)) {
    return { label: phase, isKnown: true, isTerminal: false }
  }
  return {
    label: `État inconnu (${phase ?? 'non fourni'})`,
    isKnown: false,
    isTerminal: true,
  }
}
