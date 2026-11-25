import { formatInvestigationStatus } from '../plan/constants'
import type {
  ActivityEntry,
  AgentCardData,
  AgentKey,
  InvestigationRunOut,
  PhaseOut,
  PhaseStatusDisplayInfo,
  RunStatusDisplayInfo,
  RunViewState,
} from './types'

/**
 * Les agents nommés dans la story F4.3 proviennent de `docs/frontend/11` et `12`.
 * Seules les phases `PhaseName` du contrat peuvent renseigner leur état : aucun
 * code d'agent supplémentaire n'est inventé. Le Corrélateur n'a aucune phase
 * correspondante dans `openapi.json`, il reste donc « à réaligner ».
 */
export const AGENT_PHASES: ReadonlyArray<{
  readonly key: AgentKey
  readonly name: string
  readonly phases: readonly string[]
}> = [
  { key: 'planner', name: 'Planner', phases: ['planner', 'planning'] },
  { key: 'executor', name: 'Executor', phases: ['executor', 'execution'] },
  { key: 'analyst', name: 'Analyst', phases: ['analyst', 'analysis'] },
  { key: 'verifier', name: 'Verifier', phases: ['verifier', 'verification'] },
  { key: 'correlator', name: 'Corrélateur', phases: [] },
  { key: 'reporter', name: 'Rapporteur', phases: ['reporting'] },
]

export const TO_REALIGN = 'à réaligner'
export const PAUSE_REALIGNMENT_NOTE = `Route de pause absente du contrat : ${TO_REALIGN}`
export const CANCEL_REALIGNMENT_NOTE = `Route d'annulation absente du contrat : ${TO_REALIGN}`
export const AGENT_RETRY_REALIGNMENT_NOTE = `Route de relance d'agent absente du contrat : ${TO_REALIGN}`
export const ACTIVITY_LOG_REALIGNMENT_NOTE = `Journal d'événements déduit des phases contractuelles : ${TO_REALIGN}`

/** Statuts de session affichés par la console, sans altérer le code brut du contrat. */
export function formatRunStatus(status: string | undefined | null): RunStatusDisplayInfo {
  switch (status) {
    case 'pending':
      return { label: 'EN ATTENTE', isKnown: true, isTerminal: false, isRealigned: false }
    case 'running':
      return { label: 'EN COURS', isKnown: true, isTerminal: false, isRealigned: false }
    case 'paused':
      return { label: 'EN PAUSE', isKnown: true, isTerminal: false, isRealigned: false }
    case 'completed':
      return { label: 'TERMINÉ', isKnown: true, isTerminal: true, isRealigned: false }
    case 'failed':
      return { label: 'ÉCHEC', isKnown: true, isTerminal: true, isRealigned: false }
    case 'canceled':
      return { label: 'ANNULÉ', isKnown: false, isTerminal: true, isRealigned: true }
    default: {
      const fallback = formatInvestigationStatus(status)
      return { ...fallback, isRealigned: true }
    }
  }
}

/** Statuts de phase du contrat (`PhaseStatus`), avec la règle de robustesse F4.3. */
export function formatPhaseStatus(status: string | undefined | null): PhaseStatusDisplayInfo {
  switch (status) {
    case 'pending':
      return { label: 'EN ATTENTE', isKnown: true, isFailed: false }
    case 'active':
      return { label: 'EN COURS', isKnown: true, isFailed: false }
    case 'completed':
      return { label: 'TERMINÉ', isKnown: true, isFailed: false }
    case 'failed':
      return { label: 'ÉCHEC', isKnown: true, isFailed: true }
    default:
      return {
        label: `État inconnu (${status ?? 'non fourni'})`,
        isKnown: false,
        isFailed: false,
      }
  }
}

export function hasFailedPhase(run: InvestigationRunOut | null): boolean {
  return Boolean(run?.phases?.some((phase) => phase.status === 'failed'))
}

/** Décide de l'état d'affichage sans jamais inventer de statut côté client. */
export function resolveRunViewState(run: InvestigationRunOut): RunViewState {
  // Le contrat n'expose pas `canceled` : le code reçu est comparé tel quel.
  switch (run.status as string) {
    case 'pending':
      return 'waiting'
    case 'running':
      return hasFailedPhase(run) ? 'partialFailure' : 'running'
    case 'paused':
      return 'paused'
    case 'completed':
      return 'completed'
    case 'failed':
      return 'failed'
    case 'canceled':
      return 'canceled'
    default:
      return 'unknown'
  }
}

function agentNameForPhase(phaseName: string): string {
  return AGENT_PHASES.find((agent) => agent.phases.includes(phaseName))?.name ?? phaseName
}

function computeElapsed(phase: PhaseOut, fallbackTimestamp: string): string {
  const startedAt = Date.parse(phase.started_at)
  const endedAt = Date.parse(phase.completed_at ?? fallbackTimestamp)
  if (Number.isNaN(startedAt) || Number.isNaN(endedAt) || endedAt < startedAt) {
    return TO_REALIGN
  }

  const seconds = Math.floor((endedAt - startedAt) / 1000)
  if (seconds < 60) return `${seconds} s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} min`
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`
}

/**
 * Cartes d'agents dérivées des seules phases présentes dans le contrat.
 * Progression, dernier message et diagnostic ne figurent pas dans `PhaseOut` :
 * ils sont explicitement marqués « à réaligner » plutôt que simulés.
 */
export function deriveAgentCards(run: InvestigationRunOut | null): readonly AgentCardData[] {
  const phases = run?.phases ?? []

  return AGENT_PHASES.map((agent) => {
    const phase = phases.find((candidate) => agent.phases.includes(candidate.phase_name))
    if (!phase) {
      return {
        key: agent.key,
        name: agent.name,
        statusLabel: TO_REALIGN,
        isFailed: false,
        isRealigned: true,
        elapsedLabel: TO_REALIGN,
        progressLabel: TO_REALIGN,
        lastMessageLabel: TO_REALIGN,
        diagnosticLabel: TO_REALIGN,
      }
    }

    const status = formatPhaseStatus(phase.status)
    return {
      key: agent.key,
      name: agent.name,
      statusLabel: status.label,
      isFailed: status.isFailed,
      isRealigned: false,
      elapsedLabel: computeElapsed(phase, run?.updated_at ?? ''),
      progressLabel: TO_REALIGN,
      lastMessageLabel: TO_REALIGN,
      diagnosticLabel: TO_REALIGN,
    }
  })
}

/** Cartes affichées en attente de prise en charge, sans inventer de phase d'agent. */
export function waitingAgentCards(): readonly AgentCardData[] {
  return AGENT_PHASES.map((agent) => ({
    key: agent.key,
    name: agent.name,
    statusLabel: 'EN ATTENTE',
    isFailed: false,
    isRealigned: true,
    elapsedLabel: TO_REALIGN,
    progressLabel: TO_REALIGN,
    lastMessageLabel: TO_REALIGN,
    diagnosticLabel: TO_REALIGN,
  }))
}

/** Entrées de journal construites uniquement à partir des horodatages contractuels. */
export function deriveActivityEntries(run: InvestigationRunOut | null): readonly ActivityEntry[] {
  const entries: ActivityEntry[] = []
  for (const phase of run?.phases ?? []) {
    const agentName = agentNameForPhase(phase.phase_name)
    entries.push({
      id: `${phase.id}:started`,
      timestamp: phase.started_at,
      agentName,
      eventLabel: 'Démarrage',
    })
    if (phase.completed_at) {
      entries.push({
        id: `${phase.id}:completed`,
        timestamp: phase.completed_at,
        agentName,
        eventLabel: 'Fin',
      })
    }
  }
  return entries.sort((a, b) => a.timestamp.localeCompare(b.timestamp))
}

/** Restitution UTC explicite : le code ISO du contrat n'est jamais réinterprété en local. */
export function formatUtcTimestamp(timestamp: string): string {
  const parsed = Date.parse(timestamp)
  const utc = Number.isNaN(parsed) ? timestamp : new Date(parsed).toISOString()
  return `${utc} (UTC)`
}
