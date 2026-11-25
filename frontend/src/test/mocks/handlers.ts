import { http, HttpResponse } from 'msw'
import type {
  LoginRequest,
  TokenResponse,
  LogoutResponse,
  ErrorResponse,
} from '../../api/auth-types'
import type { EvidenceRead } from '../../features/evidence/types'
import type { components } from '../../api/schema'
import { TIMELINE_PAGE_SIZE } from '../../features/results/constants'

/**
 * Données simulées d'investigation pour le contrat cible E2 (Story F1.6 et F2.1).
 */
export const MOCK_CASE_MEMBERS = [
  {
    id: 'user-001',
    email: 'analyste@iryx.local',
    name: 'Analyste Forensique',
    role: 'analyst' as const,
  },
  {
    id: 'user-002',
    email: 'admin@iryx.local',
    name: 'Administrateur Sécurité',
    role: 'admin' as const,
  },
]

export const MOCK_CASES = [
  {
    id: 'case-001',
    organization_id: 'org-001',
    title: 'Incident Ransomware LockBit v3',
    description: 'Compromission initiale par pièce jointe malveillante',
    status: 'open',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-20T08:15:00Z',
    updated_at: '2026-11-20T09:00:00Z',
    evidence_count: 4,
  },
  {
    id: 'case-002',
    organization_id: 'org-001',
    title: 'Fuite de données confidentielles RH',
    description: 'Exfiltration massive détectée sur canal cloud non approuvé',
    status: 'in_progress',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-19T14:30:00Z',
    updated_at: '2026-11-19T16:00:00Z',
    evidence_count: 12,
  },
  {
    id: 'case-003',
    organization_id: 'org-001',
    title: 'Attaque DDoS infrastructure Cloud',
    description: 'Saturation volumétrique des passerelles de terminaison TLS',
    status: 'review',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-18T10:00:00Z',
    updated_at: '2026-11-18T12:00:00Z',
    evidence_count: 2,
  },
  {
    id: 'case-004',
    organization_id: 'org-001',
    title: 'Compromission Active Directory Kerberoasting',
    description: 'Détection de tickets SPN chiffrés avec algorithme faible',
    status: 'open',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-17T09:20:00Z',
    updated_at: '2026-11-17T11:00:00Z',
    evidence_count: 7,
  },
  {
    id: 'case-005',
    organization_id: 'org-001',
    title: 'Exfiltration données financières via DNS',
    description: 'Canal de communication discret sur sous-domaines dynamiques',
    status: 'closed',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-16T16:45:00Z',
    updated_at: '2026-11-16T18:00:00Z',
    evidence_count: 15,
  },
  {
    id: 'case-006',
    organization_id: 'org-001',
    title: 'Campagne Phishing bancaire ciblée',
    description: 'Messages usurpant la direction financière pour virement frauduleux',
    status: 'open',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-15T11:10:00Z',
    updated_at: '2026-11-15T13:30:00Z',
    evidence_count: 3,
  },
  {
    id: 'case-007',
    organization_id: 'org-001',
    title: 'Intrusion SCADA automate industriel',
    description: 'Anomalie de télécommande et modification de consignes critiques',
    status: 'in_progress',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-14T07:30:00Z',
    updated_at: '2026-11-14T10:00:00Z',
    evidence_count: 8,
  },
  {
    id: 'case-008',
    organization_id: 'org-001',
    title: 'Usurpation identité dirigeant BEC',
    description: 'Fraude au président par ingénierie sociale avancée',
    status: 'review',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-13T13:00:00Z',
    updated_at: '2026-11-13T15:20:00Z',
    evidence_count: 1,
  },
  {
    id: 'case-009',
    organization_id: 'org-001',
    title: 'Injection SQL portail extranet',
    description: 'Extraction partielle de tables applicatives non sensibles',
    status: 'closed',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-12T15:25:00Z',
    updated_at: '2026-11-12T17:00:00Z',
    evidence_count: 6,
  },
  {
    id: 'case-010',
    organization_id: 'org-001',
    title: 'Détection malware Cobalt Strike balise',
    description: 'Trafic C2 périodique vers adresse IP suspecte',
    status: 'in_progress',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-11T18:40:00Z',
    updated_at: '2026-11-11T20:10:00Z',
    evidence_count: 9,
  },
  {
    id: 'case-011',
    organization_id: 'org-001',
    title: 'Élévation de privilèges CVE-2026-1337',
    description: 'Exploitation locale du démon d impression sur serveur linux',
    status: 'open',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-10T12:00:00Z',
    updated_at: '2026-11-10T14:00:00Z',
    evidence_count: 5,
  },
  {
    id: 'case-012',
    organization_id: 'org-001',
    title: 'Mouvement latéral SMB pass-the-hash',
    description: 'Propagation d un compte administrateur local compromis',
    status: 'in_progress',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-09T08:50:00Z',
    updated_at: '2026-11-09T10:15:00Z',
    evidence_count: 11,
  },
  {
    id: 'case-013',
    organization_id: 'org-001',
    title: 'Compromission compte VPN sans MFA',
    description: 'Accès distant nocturne depuis géolocalisation inhabituelle',
    status: 'closed',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-08T17:15:00Z',
    updated_at: '2026-11-08T19:00:00Z',
    evidence_count: 4,
  },
  {
    id: 'case-014',
    organization_id: 'org-001',
    title: 'Détournement session OAuth collaborateur',
    description: 'Jeton de rafraîchissement réutilisé hors de l entreprise',
    status: 'review',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-07T10:45:00Z',
    updated_at: '2026-11-07T12:00:00Z',
    evidence_count: 2,
  },
  {
    id: 'case-015',
    organization_id: 'org-001',
    title: 'Attaque par force brute SSH serveur bastion',
    description: 'Tentatives répétées bloquées par fail2ban et filtrage',
    status: 'closed',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-06T22:30:00Z',
    updated_at: '2026-11-06T23:45:00Z',
    evidence_count: 0,
  },
  {
    id: 'case-016',
    organization_id: 'org-001',
    title: 'Analyse mémoire vivante machine compromise',
    description: 'Dump RAM station travail avec processus injecté',
    status: 'open',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-05T09:15:00Z',
    updated_at: '2026-11-05T11:30:00Z',
    evidence_count: 18,
  },
  {
    id: 'case-017',
    organization_id: 'org-001',
    title: 'Découverte porte dérobée script PowerShell',
    description: 'Persistance via tâche planifiée dissimulée',
    status: 'in_progress',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-04T14:10:00Z',
    updated_at: '2026-11-04T16:00:00Z',
    evidence_count: 7,
  },
  {
    id: 'case-018',
    organization_id: 'org-001',
    title: 'Attaque Supply Chain paquet npm corrompu',
    description: 'Injection de code obfusqué dans dépendance tierce',
    status: 'review',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-03T16:00:00Z',
    updated_at: '2026-11-03T18:00:00Z',
    evidence_count: 13,
  },
  {
    id: 'case-019',
    organization_id: 'org-001',
    title: 'Scan de vulnérabilités agressif externe',
    description: 'Balayage de ports et énumération de services exposés',
    status: 'closed',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-02T11:20:00Z',
    updated_at: '2026-11-02T12:30:00Z',
    evidence_count: 1,
  },
  {
    id: 'case-020',
    organization_id: 'org-001',
    title: 'Évasion bac à sable endpoint EDR',
    description: 'Contournement par appel direct d API système non surveillée',
    status: 'open',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-01T15:40:00Z',
    updated_at: '2026-11-01T17:10:00Z',
    evidence_count: 6,
  },
  {
    id: 'case-021',
    organization_id: 'org-001',
    title: 'Compromission conteneur Kubernetes',
    description: 'Échappement vers le nœud hôte via socket système',
    status: 'in_progress',
    created_by: 'analyste@iryx.local',
    created_at: '2026-10-31T13:20:00Z',
    updated_at: '2026-10-31T15:00:00Z',
    evidence_count: 5,
  },
  {
    id: 'case-022',
    organization_id: 'org-001',
    title: 'Tentative de pivot réseau zone DMZ',
    description: 'Communication inter-VLAN bloquée par filtrage',
    status: 'review',
    created_by: 'analyste@iryx.local',
    created_at: '2026-10-30T09:10:00Z',
    updated_at: '2026-10-30T10:40:00Z',
    evidence_count: 3,
  },
  {
    id: 'case-023',
    organization_id: 'org-001',
    title: 'Vol de jetons d accès API production',
    description: 'Clés statiques trouvées dans archive publique',
    status: 'open',
    created_by: 'analyste@iryx.local',
    created_at: '2026-10-29T17:00:00Z',
    updated_at: '2026-10-29T18:30:00Z',
    evidence_count: 10,
  },
  {
    id: 'case-024',
    organization_id: 'org-001',
    title: 'Sabotage logique base de données archivage',
    description: 'Tentative de suppression d enregistrements d audit',
    status: 'closed',
    created_by: 'analyste@iryx.local',
    created_at: '2026-10-28T08:00:00Z',
    updated_at: '2026-10-28T09:15:00Z',
    evidence_count: 8,
  },
  {
    id: 'case-025',
    organization_id: 'org-001',
    title: 'Altération certificat TLS passerelle web',
    description: 'Tentative d interposition sur flux chiffré',
    status: 'in_progress',
    created_by: 'analyste@iryx.local',
    created_at: '2026-10-27T14:50:00Z',
    updated_at: '2026-10-27T16:20:00Z',
    evidence_count: 2,
  },
]

const INITIAL_MOCK_CASES = [...MOCK_CASES]

/**
 * Réinitialise la liste des dossiers simulés à son état initial (Story F1.7).
 */
export function resetMockCases() {
  MOCK_CASES.length = 0
  MOCK_CASES.push(...INITIAL_MOCK_CASES)
}

/**
 * Données simulées d'inventaire des preuves pour le contrat cible E3 (Story F3.2).
 */
export const INITIAL_MOCK_CASE_EVIDENCES: Record<string, EvidenceRead[]> = {
  'case-001': [
    {
      id: 'evi-001',
      case_id: 'case-001',
      original_name: 'Security.evtx',
      file_size: 15482880,
      sha256: 'a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef0',
      detected_type: 'application/x-ms-evtx',
      imported_by: 'analyste@iryx.local',
      created_at: '2026-11-20T08:30:00Z',
    },
    {
      id: 'evi-002',
      case_id: 'case-001',
      original_name: 'memory_dump.raw',
      file_size: 4294967296,
      sha256: 'f0e1d2c3b4a5968778695a4b3c2d1e0f0123456789abcdef0123456789abcdef',
      detected_type: 'application/octet-stream',
      imported_by: 'analyste@iryx.local',
      created_at: '2026-11-20T08:45:00Z',
    },
    {
      id: 'evi-003',
      case_id: 'case-001',
      original_name: 'auth.log',
      file_size: 204800,
      sha256: null,
      detected_type: 'text/plain',
      imported_by: 'analyste@iryx.local',
      created_at: '2026-11-20T09:00:00Z',
    },
    {
      id: 'evi-004',
      case_id: 'case-001',
      original_name: 'corrupted_artifact.bin',
      file_size: 1048576,
      sha256: null,
      detected_type: 'application/octet-stream',
      imported_by: 'analyste@iryx.local',
      created_at: '2026-11-20T09:15:00Z',
    },
  ],
}

export const MOCK_CASE_EVIDENCES: Record<string, EvidenceRead[]> = JSON.parse(
  JSON.stringify(INITIAL_MOCK_CASE_EVIDENCES),
)

export function resetMockEvidences() {
  Object.keys(MOCK_CASE_EVIDENCES).forEach((key) => {
    delete MOCK_CASE_EVIDENCES[key]
  })
  Object.assign(MOCK_CASE_EVIDENCES, JSON.parse(JSON.stringify(INITIAL_MOCK_CASE_EVIDENCES)))
}

/**
 * Construit un contenu brut volumineux pour éprouver la troncature DP-04 (Story F3.3).
 */
function buildLargeObservationText(lineCount: number): string {
  return Array.from(
    { length: lineCount },
    (_, index) =>
      `2026-11-20T08:${String(index % 60).padStart(2, '0')}:00Z evenement=4624 session=${1000 + index} compte=NT AUTHORITY\\SYSTEM`,
  ).join('\n')
}

/**
 * Données simulées de consultation détaillée d'une preuve (Story F3.3).
 * Le schéma EvidenceRead du contrat ne porte que les métadonnées de base ; les champs
 * ingestion_runs, observation_count et observations sont des enrichissements du contrat cible
 * à réaligner avec l'épic back-end E3.
 */
export function getMockEvidenceDetail(caseId: string, evidenceId: string) {
  const evidence = (MOCK_CASE_EVIDENCES[caseId] || []).find((item) => item.id === evidenceId)
  if (!evidence) return null

  if (evidenceId === 'evi-001') {
    return {
      ...evidence,
      ingestion_runs: [
        {
          id: 'run-001',
          status: 'completed',
          progress: 100,
          started_at: '2026-11-20T08:31:00Z',
          completed_at: '2026-11-20T08:32:10Z',
          error_message: null,
        },
        {
          id: 'run-000',
          status: 'failed',
          progress: 10,
          started_at: '2026-11-20T08:30:10Z',
          completed_at: '2026-11-20T08:30:40Z',
          error_message: 'Format binaire invalide ou corruption de fichier.',
        },
      ],
      observation_count: 2,
      observations: [
        {
          id: 'obs-001',
          tool_name: 'analyseur EVTX',
          timestamp_utc: '2026-11-20T08:31:30Z',
          source_location: 'Security.evtx / EventID 4624',
          raw_text:
            'EventID=4624\nCompte=NT AUTHORITY\\SYSTEM\nType de connexion=5\nHeure UTC=2026-11-20T08:31:30Z',
        },
        {
          id: 'obs-002',
          tool_name: 'analyseur EVTX',
          timestamp_utc: '2026-11-20T08:31:45Z',
          source_location: 'Security.evtx / EventID 4688',
          raw_text: buildLargeObservationText(620),
        },
      ],
      error_message: null,
    }
  }

  if (evidenceId === 'evi-002') {
    return {
      ...evidence,
      ingestion_runs: [
        {
          id: 'run-002',
          status: 'completed',
          progress: 100,
          started_at: '2026-11-20T08:46:00Z',
          completed_at: '2026-11-20T09:02:00Z',
          error_message: null,
        },
      ],
      observation_count: 1,
      observations: [
        {
          id: 'obs-003',
          tool_name: 'Volatility 3',
          timestamp_utc: '2026-11-20T09:01:00Z',
          source_location: 'memory_dump.raw / pslist',
          normalized_content: {
            processus: 'lsass.exe',
            pid: 620,
            parent_pid: 512,
          },
        },
      ],
      error_message: null,
    }
  }

  if (evidenceId === 'evi-004') {
    return {
      ...evidence,
      ingestion_runs: [
        {
          id: 'run-004',
          status: 'failed',
          progress: 10,
          started_at: '2026-11-20T09:16:00Z',
          completed_at: '2026-11-20T09:16:20Z',
          error_message: 'Format binaire invalide ou corruption de fichier.',
        },
      ],
      observation_count: 0,
      observations: [],
      error_message: 'Le scellement cryptographique n’a pas pu être achevé.',
    }
  }

  // evi-003 : ingestion en cours, aucune observation encore extraite
  return {
    ...evidence,
    ingestion_runs: [
      {
        id: 'run-003',
        status: 'processing',
        progress: 45,
        started_at: '2026-11-20T09:01:00Z',
        completed_at: null,
        error_message: null,
      },
    ],
    observation_count: 0,
    observations: [],
    error_message: null,
  }
}

/**
 * Données simulées de planification pour la Story F4.1.
 * Types strictement dérivés du contrat cible (openapi.json) : aucun champ d'agent
 * assigné n'existe dans InvestigationPlanStep, il reste « à réaligner » côté UI.
 * Statut : simulée, contrat cible : openapi.json (à réaligner pour l'agent assigné).
 */
export const MOCK_PLAN_RUN_ID = 'run-plan-001'

let mockPlanAttempts = 0

/** Réinitialise le compteur de scrutation du plan entre deux scénarios de test. */
export function resetMockPlanPolling() {
  mockPlanAttempts = 0
}

type MockH1Decision = components['schemas']['H1Decision']
type MockH1DecisionRequest = components['schemas']['H1DecisionRequest']
type MockH1DecisionResponse = components['schemas']['H1DecisionResponse']
type MockInvestigationPlanStep = components['schemas']['InvestigationPlanStep']
type MockInvestigationStatus = components['schemas']['InvestigationStatus']

interface MockH1State {
  readonly decision: MockH1Decision
  readonly steps: readonly MockInvestigationPlanStep[]
  readonly status: MockInvestigationStatus
  readonly current_phase: string
  readonly validated_plan: Record<string, unknown> | null
  readonly message: string
}

const mockH1States = new Map<string, MockH1State>()

function mockH1Key(caseId: string, runId: string): string {
  return `${caseId}::${runId}`
}

function readMockH1State(caseId: string, runId: string): MockH1State | null {
  return mockH1States.get(mockH1Key(caseId, runId)) ?? null
}

/** Réinitialise les décisions H1 simulées entre deux scénarios de test. */
export function resetMockH1Decisions() {
  mockH1States.clear()
}

/**
 * État de session conservé en mémoire pour la supervision F4.3 (reprise effective).
 * Les statuts hors contrat (`canceled`, codes inconnus) sont explicitement simulés
 * pour éprouver la robustesse et marqués « à réaligner » dans la documentation.
 */
interface MockRunState {
  readonly status: string
  readonly current_phase: string
  readonly phases: readonly components['schemas']['PhaseOut'][]
}

const mockRunStates = new Map<string, MockRunState>()

function mockRunKey(caseId: string, runId: string): string {
  return `${caseId}::${runId}`
}

/** Réinitialise les sessions simulées de supervision entre deux scénarios de test. */
export function resetMockRunSupervision() {
  mockRunStates.clear()
}

function mockRunPhase(
  runId: string,
  phaseName: string,
  status: components['schemas']['PhaseStatus'],
  startedAt: string,
  completedAt: string | null = null,
): components['schemas']['PhaseOut'] {
  return {
    id: `phase-${phaseName}`,
    investigation_run_id: runId,
    phase_name: phaseName,
    status,
    started_at: startedAt,
    completed_at: completedAt,
  }
}

function buildDefaultRunPhases(runId: string): readonly components['schemas']['PhaseOut'][] {
  return [
    mockRunPhase(runId, 'planner', 'completed', '2026-11-20T09:00:00Z', '2026-11-20T09:02:00Z'),
    mockRunPhase(runId, 'executor', 'active', '2026-11-20T09:02:00Z'),
    mockRunPhase(runId, 'analyst', 'pending', '2026-11-20T09:02:00Z'),
    mockRunPhase(runId, 'verifier', 'pending', '2026-11-20T09:02:00Z'),
    mockRunPhase(runId, 'reporting', 'pending', '2026-11-20T09:02:00Z'),
  ]
}

function buildMockRunDetail(caseId: string, runId: string, simulation: string | null) {
  const override = mockRunStates.get(mockRunKey(caseId, runId))
  if (override) {
    return {
      id: runId,
      case_id: caseId,
      status: override.status,
      current_phase: override.current_phase,
      validated_plan: {},
      iteration_count: 0,
      error_count: 0,
      started_at: '2026-11-20T09:00:00Z',
      updated_at: '2026-11-20T09:05:00Z',
      phases: [...override.phases],
    }
  }

  const scenario = simulation ?? (caseId.startsWith('case-run-') ? caseId : '')
  const defaultPhases = buildDefaultRunPhases(runId)
  let status = 'running'
  let currentPhase = 'execution'
  let phases: readonly components['schemas']['PhaseOut'][] = defaultPhases

  if (scenario === 'case-run-pending' || scenario === 'pending') {
    status = 'pending'
    currentPhase = 'planning'
    phases = [
      mockRunPhase(runId, 'planner', 'pending', '2026-11-20T09:00:00Z'),
      mockRunPhase(runId, 'executor', 'pending', '2026-11-20T09:00:00Z'),
      mockRunPhase(runId, 'analyst', 'pending', '2026-11-20T09:00:00Z'),
      mockRunPhase(runId, 'verifier', 'pending', '2026-11-20T09:00:00Z'),
      mockRunPhase(runId, 'reporting', 'pending', '2026-11-20T09:00:00Z'),
    ]
  } else if (scenario === 'case-run-paused' || scenario === 'paused') {
    status = 'paused'
  } else if (scenario === 'case-run-partial' || scenario === 'partial-failure') {
    currentPhase = 'analysis'
    phases = [
      mockRunPhase(runId, 'planner', 'completed', '2026-11-20T09:00:00Z', '2026-11-20T09:02:00Z'),
      mockRunPhase(runId, 'executor', 'failed', '2026-11-20T09:02:00Z', '2026-11-20T09:04:00Z'),
      mockRunPhase(runId, 'analyst', 'active', '2026-11-20T09:04:00Z'),
      mockRunPhase(runId, 'verifier', 'pending', '2026-11-20T09:04:00Z'),
      mockRunPhase(runId, 'reporting', 'pending', '2026-11-20T09:04:00Z'),
    ]
  } else if (scenario === 'case-run-completed' || scenario === 'completed') {
    status = 'completed'
    currentPhase = 'reporting'
    phases = [
      mockRunPhase(runId, 'planner', 'completed', '2026-11-20T09:00:00Z', '2026-11-20T09:02:00Z'),
      mockRunPhase(runId, 'executor', 'completed', '2026-11-20T09:02:00Z', '2026-11-20T09:06:00Z'),
      mockRunPhase(runId, 'analyst', 'completed', '2026-11-20T09:06:00Z', '2026-11-20T09:09:00Z'),
      mockRunPhase(runId, 'verifier', 'completed', '2026-11-20T09:09:00Z', '2026-11-20T09:11:00Z'),
      mockRunPhase(runId, 'reporting', 'completed', '2026-11-20T09:11:00Z', '2026-11-20T09:12:00Z'),
    ]
  } else if (scenario === 'case-run-canceled' || scenario === 'canceled') {
    // Statut demandé par la story mais absent de InvestigationStatus : à réaligner.
    status = 'canceled'
  } else if (scenario === 'case-run-unknown' || scenario === 'unknown-status') {
    status = 'unrecognized_run_code'
    currentPhase = 'unrecognized_phase_code'
  }

  return {
    id: runId,
    case_id: caseId,
    status,
    current_phase: currentPhase,
    validated_plan: {},
    iteration_count: 0,
    error_count: 0,
    started_at: '2026-11-20T09:00:00Z',
    updated_at: '2026-11-20T09:05:00Z',
    phases: [...phases],
  }
}

function isRunForbidden(request: Request, caseId: string): boolean {
  const authHeader = request.headers.get('Authorization')
  const token = authHeader?.startsWith('Bearer ') ? authHeader.replace('Bearer ', '').trim() : ''
  return (
    token === 'mock-forbidden-token' ||
    request.headers.get('X-Simulation-Run') === 'forbidden' ||
    caseId === 'case-forbidden' ||
    caseId === 'case-run-forbidden'
  )
}

function isRunServerError(request: Request, caseId: string): boolean {
  const authHeader = request.headers.get('Authorization')
  const token = authHeader?.startsWith('Bearer ') ? authHeader.replace('Bearer ', '').trim() : ''
  return (
    token === 'mock-server-error-token' ||
    request.headers.get('X-Simulation-Run') === 'server-error' ||
    caseId === 'case-run-error'
  )
}

function isRunNetworkError(request: Request, caseId: string): boolean {
  return (
    request.headers.get('X-Simulation-Run') === 'network-error' ||
    caseId === 'case-run-network-error'
  )
}

const MOCK_PLAN_STEPS: components['schemas']['InvestigationPlanStep'][] = [
  {
    step_id: 1,
    tool_name: 'Analyseur EVTX',
    target_evidence_id: 'evi-001',
    rationale: 'Extraire les événements d’authentification et les sessions suspectes.',
    is_blocking: true,
    continue_on_error: false,
  },
  {
    step_id: 2,
    tool_name: 'regipy',
    target_evidence_id: 'evi-004',
    rationale: 'Analyser les ruches de registre à la recherche de persistance.',
    is_blocking: false,
    continue_on_error: true,
  },
  {
    step_id: 3,
    tool_name: 'Volatility 3',
    target_evidence_id: 'evi-002',
    rationale: 'Rechercher les artefacts d’exécution dans l’image mémoire.',
    is_blocking: false,
    continue_on_error: true,
  },
]

function buildMockPlan(steps = MOCK_PLAN_STEPS): components['schemas']['InvestigationPlan'] {
  return {
    steps,
    summary: 'Trois étapes forensiques permettent d’établir la chronologie de la compromission.',
  }
}

function buildMockInvestigationRun(caseId: string, simulation: string | null) {
  const decisionState = readMockH1State(caseId, MOCK_PLAN_RUN_ID)
  const isUnknown =
    caseId === 'case-plan-unknown' ||
    caseId === 'case-timeline-unknown' ||
    simulation === 'unknown-status'
  const isValidated = caseId === 'case-plan-validated' || simulation === 'validated'
  const isPartial =
    caseId === 'case-results-partial' ||
    caseId === 'case-timeline-partial' ||
    simulation === 'partial-failure'

  // Le contrat signale un résultat partiel par une phase `failed` : aucun champ
  // supplémentaire n'est inventé pour déclencher le bandeau de la chronologie.
  const phases: readonly components['schemas']['PhaseOut'][] | undefined = isPartial
    ? [
        mockRunPhase(
          MOCK_PLAN_RUN_ID,
          'executor',
          'failed',
          '2026-11-20T09:00:00Z',
          '2026-11-20T09:04:00Z',
        ),
        mockRunPhase(MOCK_PLAN_RUN_ID, 'analyst', 'active', '2026-11-20T09:04:00Z'),
      ]
    : undefined

  return {
    id: MOCK_PLAN_RUN_ID,
    case_id: caseId,
    // Un statut non répertorié est délibérément restitué brut pour éprouver la robustesse.
    status: decisionState
      ? decisionState.status
      : isUnknown
        ? 'unrecognized_state_code'
        : isValidated
          ? 'completed'
          : 'running',
    current_phase: decisionState
      ? decisionState.current_phase
      : isUnknown
        ? 'unrecognized_phase_code'
        : 'planning',
    validated_plan: decisionState ? decisionState.validated_plan : isValidated ? {} : null,
    iteration_count: 0,
    error_count: 0,
    started_at: '2026-11-20T09:00:00Z',
    updated_at: '2026-11-20T09:05:00Z',
    ...(phases ? { phases: [...phases] } : {}),
  }
}

function isPlanForbidden(request: Request, caseId: string): boolean {
  const authHeader = request.headers.get('Authorization')
  const token = authHeader?.startsWith('Bearer ') ? authHeader.replace('Bearer ', '').trim() : ''
  const simulation = request.headers.get('X-Simulation-Plan')
  return (
    token === 'mock-forbidden-token' ||
    simulation === 'forbidden' ||
    caseId === 'case-forbidden' ||
    caseId === 'case-plan-forbidden'
  )
}

function isPlanServerError(request: Request, caseId: string): boolean {
  const authHeader = request.headers.get('Authorization')
  const token = authHeader?.startsWith('Bearer ') ? authHeader.replace('Bearer ', '').trim() : ''
  const simulation = request.headers.get('X-Simulation-Plan')
  return (
    token === 'mock-server-error-token' ||
    simulation === 'server-error' ||
    caseId === 'case-error' ||
    caseId === 'case-plan-error'
  )
}

/**
 * Données simulées de la chronologie unifiée (Story F4.6).
 * Chaque objet respecte `ObservationRead` de openapi.json. Le volume simulé
 * couvre plusieurs blocs complets (DP-01), y compris après filtrage par source,
 * pour éprouver la pagination serveur sans accumulation côté client.
 */
const TIMELINE_MOCK_TOOLS = ['Analyseur EVTX', 'regipy', 'Volatility 3', 'Prefetch'] as const
const TIMELINE_MOCK_FILES = ['Security.evtx', 'auth.log', 'memory_dump.raw', 'NTUSER.DAT'] as const
const TIMELINE_MOCK_EVENT_COUNT =
  TIMELINE_PAGE_SIZE * TIMELINE_MOCK_FILES.length + TIMELINE_MOCK_FILES.length
const TIMELINE_MOCK_STEP_MS = 3000

function buildMockObservations(caseId: string): components['schemas']['ObservationRead'][] {
  return Array.from({ length: TIMELINE_MOCK_EVENT_COUNT }, (_, index) => {
    const file = TIMELINE_MOCK_FILES[index % TIMELINE_MOCK_FILES.length] ?? TIMELINE_MOCK_FILES[0]
    const toolName =
      TIMELINE_MOCK_TOOLS[index % TIMELINE_MOCK_TOOLS.length] ?? TIMELINE_MOCK_TOOLS[0]
    const line = index + 1
    const sourceId = `evi-00${(index % 4) + 1}`
    const timestamp = new Date(Date.UTC(2026, 10, 20, 9, 0, 0) + index * TIMELINE_MOCK_STEP_MS)

    return {
      id: `${caseId}-obs-${String(line).padStart(3, '0')}`,
      case_id: caseId,
      source_id: sourceId,
      tool_name: toolName,
      tool_execution_id: `exec-${sourceId}`,
      normalized_content: {
        summary: `${toolName} — fait technique ${line}`,
        file_name: file,
        event_id: `evt-${String(line).padStart(3, '0')}`,
        line,
      },
      timestamp_utc: timestamp.toISOString(),
      source_location: `${file}:${line}`,
      created_at: timestamp.toISOString(),
    }
  })
}

function isTimelineForbidden(request: Request, caseId: string): boolean {
  const authHeader = request.headers.get('Authorization')
  const token = authHeader?.startsWith('Bearer ') ? authHeader.replace('Bearer ', '').trim() : ''
  return (
    token === 'mock-forbidden-token' ||
    request.headers.get('X-Simulation-Timeline') === 'forbidden' ||
    caseId === 'case-forbidden' ||
    caseId === 'case-timeline-forbidden'
  )
}

function isTimelineServerError(request: Request, caseId: string): boolean {
  const authHeader = request.headers.get('Authorization')
  const token = authHeader?.startsWith('Bearer ') ? authHeader.replace('Bearer ', '').trim() : ''
  return (
    token === 'mock-server-error-token' ||
    request.headers.get('X-Simulation-Timeline') === 'server-error' ||
    caseId === 'case-timeline-error'
  )
}

/**
 * Handlers MSW simulant les routes réseau de l'application IRYX.
 *
 * Routes d'authentification simulées d'après le contrat cible (Stories F1.2 et F1.4) :
 * - POST /api/v1/auth/login (simulée, contrat cible : auth-contrat-cible.yaml)
 * - POST /api/v1/auth/refresh (simulée, contrat cible : auth-contrat-cible.yaml)
 * - POST /api/v1/auth/logout (simulée, contrat cible : auth-contrat-cible.yaml)
 *
 * Routes protégées simulées d'après le contrat OpenAPI (Stories F1.3, F1.6 et F1.7) :
 * - GET /api/v1/auth/me (simulée, contrat cible : openapi.json)
 * - GET /api/v1/cases (simulée, contrat cible : openapi.json)
 * - POST /api/v1/cases (simulée, contrat cible : openapi.json)
 */
export const handlers = [
  http.get('*/api/test-simulation', () => {
    return HttpResponse.json({ status: 'ok', simulation: true })
  }),

  http.get('*/api/health', () => {
    return HttpResponse.json({ status: 'healthy' })
  }),

  // POST /api/v1/auth/login (simulée, contrat cible : auth-contrat-cible.yaml)
  http.post('*/api/v1/auth/login', async ({ request }) => {
    try {
      const body = (await request.json()) as Partial<LoginRequest>
      const { email, password } = body

      if (!email || !password) {
        return HttpResponse.json<ErrorResponse>(
          { detail: 'Champs obligatoires manquants.' },
          { status: 400 },
        )
      }

      // Simulation compte inactif / révoqué (403)
      if (email === 'bloque@iryx.local') {
        return HttpResponse.json<ErrorResponse>(
          { detail: 'Compte inactif ou accès révoqué. Contactez votre administrateur.' },
          { status: 403 },
        )
      }

      // Simulation erreur serveur 500
      if (email === 'serveur-erreur@iryx.local') {
        return HttpResponse.json<ErrorResponse>(
          { detail: 'Erreur interne du serveur.' },
          { status: 500 },
        )
      }

      // Simulation identifiants incorrects (401)
      if (
        password === 'mauvaismdp' ||
        password === 'wrong-password' ||
        email === 'inconnu@iryx.local'
      ) {
        return HttpResponse.json<ErrorResponse>(
          { detail: 'Identifiants incorrects.' },
          { status: 401 },
        )
      }

      // Cas nominal (200) : délivrance de l'access token (15 min) et positionnement du cookie refresh (7 j)
      const tokenResponse: TokenResponse = {
        access_token: 'mock-access-token-bearer-15min',
        token_type: 'bearer',
        expires_in: 900,
      }

      return HttpResponse.json(tokenResponse, {
        status: 200,
        headers: {
          'Set-Cookie':
            'refresh_token=mock-refresh-token-jwt-7d; Path=/api/v1/auth/refresh; Max-Age=604800; HttpOnly; Secure; SameSite=Strict',
        },
      })
    } catch {
      return HttpResponse.json<ErrorResponse>({ detail: 'Requête malformée.' }, { status: 400 })
    }
  }),

  // POST /api/v1/auth/refresh (simulée, contrat cible : auth-contrat-cible.yaml)
  http.post('*/api/v1/auth/refresh', async ({ request }) => {
    const origin = request.headers.get('Origin')
    // Simulation rejet anti-CSRF
    if (origin === 'http://malicious-site.local') {
      return HttpResponse.json<ErrorResponse>({ detail: 'Origine non autorisée.' }, { status: 403 })
    }

    const simHeader = request.headers.get('X-Simulation-Refresh')
    if (simHeader === 'network-error') {
      return HttpResponse.error()
    }

    const cookieHeader = request.headers.get('Cookie')
    if (
      simHeader === 'expired' ||
      cookieHeader?.includes('expired') ||
      cookieHeader?.includes('invalid')
    ) {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Session expirée. Veuillez vous reconnecter.' },
        { status: 401 },
      )
    }

    const tokenResponse: TokenResponse = {
      access_token: 'mock-refreshed-access-token-bearer-15min',
      token_type: 'bearer',
      expires_in: 900,
    }

    return HttpResponse.json(tokenResponse, { status: 200 })
  }),

  // POST /api/v1/auth/logout (simulée, contrat cible : auth-contrat-cible.yaml)
  http.post('*/api/v1/auth/logout', async () => {
    const logoutResponse: LogoutResponse = {
      message: 'Déconnexion réussie.',
    }

    return HttpResponse.json(logoutResponse, {
      status: 200,
      headers: {
        'Set-Cookie':
          'refresh_token=; Path=/api/v1/auth/refresh; Max-Age=0; HttpOnly; Secure; SameSite=Strict; Expires=Thu, 01 Jan 1970 00:00:00 GMT',
      },
    })
  }),

  // GET /api/v1/auth/me (simulée, contrat cible : openapi.json - Story F1.3)
  http.get('*/api/v1/auth/me', ({ request }) => {
    const authHeader = request.headers.get('Authorization')

    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Jeton d'accès expiré ou absent." },
        { status: 401 },
      )
    }

    const token = authHeader.replace('Bearer ', '').trim()

    if (token === 'mock-expired-token' || token.includes('expired')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Jeton d'accès expiré ou absent." },
        { status: 401 },
      )
    }

    if (token === 'mock-server-error-token' || token.includes('server-error')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Erreur interne du serveur.' },
        { status: 500 },
      )
    }

    return HttpResponse.json(
      {
        id: '00000000-0000-0000-0000-000000000001',
        email: 'analyste@iryx.local',
        is_active: true,
        created_at: '2026-11-25T00:00:00Z',
        updated_at: '2026-11-25T00:00:00Z',
      },
      { status: 200 },
    )
  }),

  // GET /api/v1/cases (simulée, contrat cible : openapi.json - Stories F1.3 et F1.6)
  http.get('*/api/v1/cases', ({ request }) => {
    const authHeader = request.headers.get('Authorization')

    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Jeton d'accès expiré ou absent." },
        { status: 401 },
      )
    }

    const token = authHeader.replace('Bearer ', '').trim()

    if (token === 'mock-expired-token' || token.includes('expired')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Jeton d'accès expiré ou absent." },
        { status: 401 },
      )
    }

    const simHeader = request.headers.get('X-Simulation-Cases')

    // Simulation accès refusé 403 Forbidden (Story F1.6)
    if (token === 'mock-forbidden-token' || simHeader === 'forbidden') {
      return HttpResponse.json<ErrorResponse>(
        {
          detail:
            "Accès refusé. Vous n'avez pas accès aux dossiers de cette organisation. Veuillez contacter votre administrateur.",
        },
        { status: 403 },
      )
    }

    // Simulation erreur interne 500 (Story F1.6)
    if (
      token === 'mock-server-error-token' ||
      token.includes('server-error') ||
      simHeader === 'server-error'
    ) {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Erreur interne du serveur lors de la récupération des dossiers.' },
        { status: 500 },
      )
    }

    // Simulation organisation sans dossier ou recherche infructueuse (Story F1.6)
    if (simHeader === 'empty') {
      return HttpResponse.json(
        {
          items: [],
          total: 0,
          total_items: 0,
          limit: 10,
          offset: 0,
          has_more: false,
        },
        { status: 200 },
      )
    }

    const url = new URL(request.url)
    const hasLimit = url.searchParams.has('limit')
    const hasOffset = url.searchParams.has('offset')
    const hasSearch = url.searchParams.has('search')

    // Règle de compatibilité ascendante stricte avec les tests F1.3 et F1.4
    // (qui appellent GET /api/v1/cases sans paramètre de pagination et attendent items: [])
    if (!hasLimit && !hasOffset && !hasSearch) {
      return HttpResponse.json(
        {
          items: [],
          total: 0,
          total_items: 0,
          limit: 20,
          offset: 0,
          has_more: false,
        },
        { status: 200 },
      )
    }

    const limitParam = parseInt(url.searchParams.get('limit') || '10', 10)
    const limit = isNaN(limitParam) || limitParam <= 0 ? 10 : Math.min(limitParam, 100)
    const offsetParam = parseInt(url.searchParams.get('offset') || '0', 10)
    const offset = isNaN(offsetParam) || offsetParam < 0 ? 0 : offsetParam
    const search = url.searchParams.get('search')?.trim().toLowerCase() || ''

    let filtered = MOCK_CASES
    if (search) {
      filtered = MOCK_CASES.filter(
        (c) =>
          c.title.toLowerCase().includes(search) ||
          (c.description && c.description.toLowerCase().includes(search)),
      )
    }

    const total = filtered.length
    const items = filtered.slice(offset, offset + limit)
    const hasMore = offset + items.length < total

    return HttpResponse.json(
      {
        items,
        total,
        total_items: total,
        limit,
        offset,
        has_more: hasMore,
      },
      { status: 200 },
    )
  }),

  /**
   * Création d'un nouveau dossier d'investigation en modale (Story F1.7).
   * Route cible : POST /api/v1/cases
   * Contrat cible : openapi.json (simulée E2)
   */
  http.post('*/api/v1/cases', async ({ request }) => {
    const authHeader = request.headers.get('Authorization')

    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Jeton d'accès expiré ou absent." },
        { status: 401 },
      )
    }

    const token = authHeader.replace('Bearer ', '').trim()

    if (token === 'mock-expired-token' || token.includes('expired')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Jeton d'accès expiré ou absent." },
        { status: 401 },
      )
    }

    const simHeader =
      request.headers.get('X-Simulation-Create-Case') || request.headers.get('X-Simulation-Cases')

    // Simulation accès refusé 403 Forbidden (Story F1.7)
    if (token === 'mock-forbidden-token' || simHeader === 'forbidden') {
      return HttpResponse.json<ErrorResponse>(
        {
          detail:
            "Vous n'avez pas les autorisations nécessaires pour créer un dossier dans cette organisation.",
        },
        { status: 403 },
      )
    }

    // Simulation erreur interne 500 (Story F1.7)
    if (
      token === 'mock-server-error-token' ||
      token.includes('server-error') ||
      simHeader === 'server-error' ||
      simHeader === '500'
    ) {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Erreur interne du serveur lors de la création du dossier.' },
        { status: 500 },
      )
    }

    // Simulation rejet de validation serveur 400 (Story F1.7)
    if (simHeader === 'validation-error' || simHeader === '400') {
      return HttpResponse.json(
        {
          detail: 'Données de dossier invalides.',
          errors: {
            title: 'Ce titre de dossier est déjà utilisé dans votre organisation.',
          },
        },
        { status: 400 },
      )
    }

    let body: Record<string, unknown> = {}
    try {
      body = (await request.json()) as Record<string, unknown>
    } catch {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Format de corps de requête invalide.' },
        { status: 400 },
      )
    }

    const title = typeof body.title === 'string' ? body.title.trim() : ''
    const description = typeof body.description === 'string' ? body.description.trim() : null
    const incidentDate = typeof body.incident_date === 'string' ? body.incident_date.trim() : ''
    const incidentType = typeof body.incident_type === 'string' ? body.incident_type.trim() : ''
    const affectedSystems =
      typeof body.affected_systems === 'string' ? body.affected_systems.trim() : ''

    // Validation minimale côté serveur (Story F1.7)
    if (!title) {
      return HttpResponse.json(
        {
          detail: 'Le titre du dossier est obligatoire.',
          errors: { title: 'Le titre du dossier est obligatoire.' },
        },
        { status: 422 },
      )
    }

    const newCase = {
      id: `case-${Date.now()}`,
      organization_id: 'org-001',
      title,
      description: description || '',
      status: 'open' as const,
      created_by: 'analyste@iryx.local',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      evidence_count: 0,
      incident_date: incidentDate || new Date().toISOString(),
      incident_type: incidentType || 'a_decider',
      affected_systems: affectedSystems,
      members: MOCK_CASE_MEMBERS,
    }

    MOCK_CASES.unshift(newCase)

    return HttpResponse.json(newCase, { status: 201 })
  }),

  /**
   * Liste des sessions d'investigation du dossier (Story F4.1).
   * Route cible : GET /api/v1/cases/{case_id}/investigations
   * Statut : simulée, contrat cible : openapi.json
   */
  http.get('*/api/v1/cases/:caseId/investigations', ({ params, request }) => {
    const authHeader = request.headers.get('Authorization')
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Jeton d'accès expiré ou absent." },
        { status: 401 },
      )
    }

    const caseId = String(params.caseId)
    const simulation = request.headers.get('X-Simulation-Plan')

    if (isPlanForbidden(request, caseId)) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Vous n'avez pas accès à ce dossier." },
        { status: 403 },
      )
    }

    if (isPlanServerError(request, caseId)) {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Erreur interne lors de la récupération des investigations.' },
        { status: 500 },
      )
    }

    // Aucune session : le Planner n'a pas encore démarré (scrutation selon Retry-After).
    if (caseId === 'case-plan-pending') {
      return HttpResponse.json([], { headers: { 'Retry-After': '3' } })
    }

    return HttpResponse.json([buildMockInvestigationRun(caseId, simulation)], {
      headers: { 'Retry-After': '3' },
    })
  }),

  /**
   * Chronologie unifiée des faits techniques (Story F4.6).
   * Route cible : GET /api/v1/cases/{case_id}/observations
   * Statut : simulée, contrat cible : openapi.json.
   * Pagination serveur stricte : limit est plafonné à 100 (DP-01) et les
   * filtres source_id / start_date / end_date sont appliqués côté serveur.
   */
  http.get('*/api/v1/cases/:caseId/observations', ({ params, request }) => {
    const authHeader = request.headers.get('Authorization')
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Jeton d'accès expiré ou absent." },
        { status: 401 },
      )
    }

    const caseId = String(params.caseId)
    if (isTimelineForbidden(request, caseId)) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Vous n'avez pas accès à cette chronologie." },
        { status: 403 },
      )
    }
    if (isTimelineServerError(request, caseId)) {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Erreur interne lors de la récupération de la chronologie.' },
        { status: 500 },
      )
    }

    const url = new URL(request.url)
    const requestedLimit = Number(url.searchParams.get('limit') ?? '50')
    const safeLimit = Number.isFinite(requestedLimit) ? requestedLimit : 50
    const limit = Math.min(Math.max(safeLimit, 1), TIMELINE_PAGE_SIZE)
    const requestedOffset = Number(url.searchParams.get('offset') ?? '0')
    const offset = Number.isFinite(requestedOffset) ? Math.max(requestedOffset, 0) : 0
    const sourceId = url.searchParams.get('source_id')
    const startDate = url.searchParams.get('start_date')
    const endDate = url.searchParams.get('end_date')
    const parsedStart = startDate ? Date.parse(startDate) : NaN
    const parsedEnd = endDate ? Date.parse(endDate) : NaN
    const simulation = request.headers.get('X-Simulation-Timeline')

    let items = buildMockObservations(caseId)
    if (simulation === 'empty' || caseId === 'case-timeline-empty') {
      items = []
    } else {
      if (sourceId) items = items.filter((item) => item.source_id === sourceId)
      if (Number.isFinite(parsedStart)) {
        items = items.filter((item) => Date.parse(item.timestamp_utc ?? '') >= parsedStart)
      }
      if (Number.isFinite(parsedEnd)) {
        items = items.filter((item) => Date.parse(item.timestamp_utc ?? '') <= parsedEnd)
      }
    }

    const pagedItems = items.slice(offset, offset + limit)
    return HttpResponse.json({
      items: pagedItems,
      total: items.length,
      total_items: items.length,
      limit,
      offset,
      has_more: offset + pagedItems.length < items.length,
    })
  }),

  /**
   * Détail d'une observation normalisée (route réservée au panneau Source, F4.7).
   * Route cible : GET /api/v1/cases/{case_id}/observations/{observation_id}
   * Statut : simulée, contrat cible : openapi.json.
   * La chronologie F4.6 ne l'appelle pas : l'emplacement du panneau est seulement
   * prévu et l'action reste désactivée avec la mention « à réaligner (F4.7) ».
   */
  http.get('*/api/v1/cases/:caseId/observations/:observationId', ({ params, request }) => {
    const authHeader = request.headers.get('Authorization')
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Jeton d'accès expiré ou absent." },
        { status: 401 },
      )
    }

    const caseId = String(params.caseId)
    const observationId = String(params.observationId)
    if (isTimelineForbidden(request, caseId)) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Vous n'avez pas accès à cette observation." },
        { status: 403 },
      )
    }
    if (isTimelineServerError(request, caseId)) {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Erreur interne lors de la récupération de l’observation.' },
        { status: 500 },
      )
    }

    const observation = buildMockObservations(caseId).find((item) => item.id === observationId)
    if (!observation) {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Observation introuvable pour ce dossier.' },
        { status: 404 },
      )
    }

    return HttpResponse.json(observation)
  }),

  /**
   * Plan proposé par le Planner pour une session d'investigation (Story F4.1).
   * Route cible : GET /api/v1/cases/{case_id}/investigations/{run_id}/plan
   * Statut : simulée, contrat cible : openapi.json
   *  - 404 PLAN_NOT_FOUND : élaboration asynchrone en cours, Retry-After: 3 (ADR-0008) ;
   *  - état vide : steps [] (écart volontaire à minItems:1 du contrat, à réaligner avec E5) ;
   *  - scénarios pilotés par l'en-tête X-Simulation-Plan ou l'identifiant du dossier.
   */
  http.get('*/api/v1/cases/:caseId/investigations/:runId/plan', ({ params, request }) => {
    const authHeader = request.headers.get('Authorization')
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Jeton d'accès expiré ou absent." },
        { status: 401 },
      )
    }

    const caseId = String(params.caseId)
    const runId = String(params.runId)
    const simulation = request.headers.get('X-Simulation-Plan')
    const decisionState = readMockH1State(caseId, runId)

    if (isPlanForbidden(request, caseId)) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Vous n'avez pas accès à ce plan." },
        { status: 403 },
      )
    }

    if (isPlanServerError(request, caseId)) {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Échec de l’agent Planner lors de l’élaboration du plan.' },
        { status: 500 },
      )
    }

    // Coupure de transport simulée : déclenche le recul exponentiel puis DP-05.
    if (simulation === 'network-error') {
      return HttpResponse.error()
    }

    const isPlanning = caseId === 'case-planning' || simulation === 'planning'
    if (isPlanning) {
      mockPlanAttempts += 1
      if (mockPlanAttempts === 1) {
        return HttpResponse.json(
          {
            detail: 'Le plan est en cours d’élaboration par le Planner.',
            code: 'PLAN_NOT_FOUND',
          },
          { status: 404, headers: { 'Retry-After': '3' } },
        )
      }
    }

    // Refus H1 : aucun plan disponible tant que le Planner n'a pas produit une nouvelle proposition.
    if (decisionState?.decision === 'reject') {
      return HttpResponse.json(
        {
          detail: 'Le plan est en cours d’élaboration par le Planner.',
          code: 'PLAN_NOT_FOUND',
        },
        { status: 404, headers: { 'Retry-After': '3' } },
      )
    }

    const isEmpty = caseId === 'case-plan-empty' || simulation === 'empty'
    const steps =
      decisionState?.decision === 'modify' ? decisionState.steps : isEmpty ? [] : MOCK_PLAN_STEPS
    const plan = buildMockPlan([...steps])
    return HttpResponse.json(plan, { headers: { 'Retry-After': '3' } })
  }),

  /**
   * Arbitrage formel de la porte H1 (Story F4.2).
   * Route cible : POST /api/v1/cases/{case_id}/investigations/{run_id}/gates/h1
   * Statut : simulée, contrat cible : openapi.json (H1DecisionRequest / H1DecisionResponse).
   * Le conflit 409 renvoie l'état réel du serveur et n'est pas documenté par le contrat
   * actuel : scénario marqué « à réaligner » avec l'épic E5.
   */
  http.post(
    '*/api/v1/cases/:caseId/investigations/:runId/gates/h1',
    async ({ params, request }) => {
      const authHeader = request.headers.get('Authorization')
      if (!authHeader || !authHeader.startsWith('Bearer ')) {
        return HttpResponse.json<ErrorResponse>(
          { detail: "Jeton d'accès expiré ou absent." },
          { status: 401 },
        )
      }

      const token = authHeader.replace('Bearer ', '').trim()
      const caseId = String(params.caseId)
      const runId = String(params.runId)
      const simulation = request.headers.get('X-Simulation-H1')

      if (
        token === 'mock-forbidden-token' ||
        simulation === 'forbidden' ||
        isPlanForbidden(request, caseId)
      ) {
        return HttpResponse.json<ErrorResponse>(
          {
            detail:
              "Accès refusé. Vous n'avez pas les autorisations nécessaires pour arbitrer la porte H1.",
          },
          { status: 403 },
        )
      }

      if (simulation === 'network-error' || caseId === 'case-h1-network-error') {
        return HttpResponse.error()
      }

      if (
        token === 'mock-server-error-token' ||
        simulation === 'server-error' ||
        caseId === 'case-h1-500' ||
        isPlanServerError(request, caseId)
      ) {
        return HttpResponse.json<ErrorResponse>(
          { detail: 'Erreur interne lors de la transmission de la décision H1.' },
          { status: 500 },
        )
      }

      let body: MockH1DecisionRequest
      try {
        body = (await request.json()) as MockH1DecisionRequest
      } catch {
        return HttpResponse.json<ErrorResponse>(
          { detail: 'Format de corps de requête invalide.' },
          { status: 400 },
        )
      }

      if (!['approve', 'modify', 'reject'].includes(body.decision)) {
        return HttpResponse.json<ErrorResponse>(
          { detail: 'Décision H1 inconnue.' },
          { status: 422 },
        )
      }
      if (body.decision === 'reject' && !body.feedback?.trim()) {
        return HttpResponse.json<ErrorResponse>(
          { detail: 'Le motif du refus est obligatoire.' },
          { status: 422 },
        )
      }
      if (
        body.decision === 'modify' &&
        (!body.modified_plan || !Array.isArray((body.modified_plan as { steps?: unknown }).steps))
      ) {
        return HttpResponse.json<ErrorResponse>(
          { detail: 'Le plan modifié est obligatoire pour une modification.' },
          { status: 422 },
        )
      }

      // Conflit : l'état réel du serveur est renvoyé et enregistré pour le prochain GET.
      if (simulation === 'conflict' || caseId === 'case-h1-conflict') {
        const conflictState: MockH1State = {
          decision: 'approve',
          steps: MOCK_PLAN_STEPS,
          status: 'completed',
          current_phase: 'executor',
          validated_plan: {},
          message: 'Le plan a déjà été validé et la session a changé de phase.',
        }
        mockH1States.set(mockH1Key(caseId, runId), conflictState)
        return HttpResponse.json<MockH1DecisionResponse>(
          {
            run_id: runId,
            case_id: caseId,
            status: conflictState.status,
            current_phase: conflictState.current_phase,
            decision: conflictState.decision,
            validated_plan: conflictState.validated_plan,
            message: conflictState.message,
            phases: [],
          },
          { status: 409 },
        )
      }

      const retainedSteps: readonly MockInvestigationPlanStep[] =
        body.decision === 'modify'
          ? ((body.modified_plan as { steps: MockInvestigationPlanStep[] }).steps ?? [])
          : MOCK_PLAN_STEPS
      const isRefused = body.decision === 'reject'
      const decisionState: MockH1State = {
        decision: body.decision,
        steps: [...retainedSteps],
        status: isRefused ? 'pending' : 'running',
        current_phase: isRefused ? 'planner' : 'executor',
        validated_plan: isRefused ? null : {},
        message: isRefused
          ? 'Plan refusé. Replanification engagée.'
          : body.decision === 'modify'
            ? 'Plan modifié validé. Session d’exécution lancée.'
            : 'Plan validé. Session d’exécution lancée.',
      }
      mockH1States.set(mockH1Key(caseId, runId), decisionState)

      return HttpResponse.json<MockH1DecisionResponse>(
        {
          run_id: runId,
          case_id: caseId,
          status: decisionState.status,
          current_phase: decisionState.current_phase,
          decision: decisionState.decision,
          validated_plan: decisionState.validated_plan,
          message: decisionState.message,
          phases: [],
        },
        { status: 200 },
      )
    },
  ),

  /**
   * Supervision temps réel de l'orchestration des agents (Story F4.3).
   * Route cible : GET /api/v1/cases/{case_id}/investigations/{run_id}
   * Statut : simulée, contrat cible : openapi.json.
   * `phases` est le seul vecteur contractuel d'état par agent : progression,
   * messages, diagnostic et journal d'événements restent « à réaligner ».
   */
  http.get('*/api/v1/cases/:caseId/investigations/:runId', ({ params, request }) => {
    const authHeader = request.headers.get('Authorization')
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Jeton d'accès expiré ou absent." },
        { status: 401 },
      )
    }

    const caseId = String(params.caseId)
    const runId = String(params.runId)
    if (isRunForbidden(request, caseId)) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Vous n'avez pas accès à cette session." },
        { status: 403 },
      )
    }
    if (isRunServerError(request, caseId)) {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Erreur interne lors de la consultation de la session.' },
        { status: 500 },
      )
    }
    if (isRunNetworkError(request, caseId)) return HttpResponse.error()

    return HttpResponse.json(
      buildMockRunDetail(caseId, runId, request.headers.get('X-Simulation-Run')),
      {
        headers: { 'Retry-After': '3' },
      },
    )
  }),

  /**
   * Reprise d'une session en pause (Story F4.3).
   * Route cible : POST /api/v1/cases/{case_id}/investigations/{run_id}/resume
   * Statut : simulée, contrat cible : openapi.json (aucun corps de requête).
   */
  http.post('*/api/v1/cases/:caseId/investigations/:runId/resume', ({ params, request }) => {
    const authHeader = request.headers.get('Authorization')
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Jeton d'accès expiré ou absent." },
        { status: 401 },
      )
    }

    const caseId = String(params.caseId)
    const runId = String(params.runId)
    if (isRunForbidden(request, caseId)) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Accès refusé. Vous n'avez pas les autorisations nécessaires." },
        { status: 403 },
      )
    }
    if (isRunServerError(request, caseId)) {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Erreur interne lors de la reprise de la session.' },
        { status: 500 },
      )
    }
    if (isRunNetworkError(request, caseId)) return HttpResponse.error()

    const key = mockRunKey(caseId, runId)
    const current = mockRunStates.get(key) ?? buildMockRunDetail(caseId, runId, null)
    if (current.status !== 'paused') {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Seules les sessions en pause peuvent être reprises.' },
        { status: 400 },
      )
    }

    const resumed: MockRunState = {
      status: 'running',
      current_phase: 'execution',
      phases: buildDefaultRunPhases(runId),
    }
    mockRunStates.set(key, resumed)
    return HttpResponse.json(
      { ...buildMockRunDetail(caseId, runId, null), ...resumed },
      { headers: { 'Retry-After': '3' } },
    )
  }),

  /**
   * Consultation unitaire d'un dossier d'investigation (Story F2.1).
   * Route cible : GET /api/v1/cases/:caseId
   * Statut : simulée, contrat cible : openapi.json
   */
  http.get('*/api/v1/cases/:caseId', ({ params, request }) => {
    const authHeader = request.headers.get('Authorization')

    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Jeton d'accès expiré ou absent." },
        { status: 401 },
      )
    }

    const token = authHeader.replace('Bearer ', '').trim()

    if (token === 'mock-expired-token' || token.includes('expired')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Jeton d'accès expiré ou absent." },
        { status: 401 },
      )
    }

    const caseId = String(params.caseId)
    const simHeader =
      request.headers.get('X-Simulation-Case') || request.headers.get('X-Simulation-Cases')

    // Simulation accès refusé 403 Forbidden
    if (
      token === 'mock-forbidden-token' ||
      simHeader === 'forbidden' ||
      caseId === 'case-forbidden'
    ) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Vous n'avez pas accès à ce dossier." },
        { status: 403 },
      )
    }

    // Simulation erreur interne 500
    if (
      token === 'mock-server-error-token' ||
      token.includes('server-error') ||
      simHeader === 'server-error' ||
      simHeader === '500' ||
      caseId === 'case-500'
    ) {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Erreur interne du serveur lors de la récupération du dossier.' },
        { status: 500 },
      )
    }

    // Simulation dossier introuvable 404 Not Found
    if (simHeader === 'not-found' || simHeader === '404' || caseId === 'case-not-found') {
      return HttpResponse.json<ErrorResponse>({ detail: 'Dossier introuvable.' }, { status: 404 })
    }

    if (caseId === 'case-empty') {
      return HttpResponse.json(
        {
          id: 'case-empty',
          organization_id: 'org-001',
          title: 'Dossier d investigation vide',
          description: null,
          status: 'open' as const,
          created_by: 'analyste@iryx.local',
          created_at: '2026-11-20T08:00:00Z',
          updated_at: '2026-11-20T08:00:00Z',
          evidence_count: 0,
          incident_date: null,
          incident_type: null,
          affected_systems: null,
          members: [],
        },
        { status: 200 },
      )
    }

    const found = MOCK_CASES.find((c) => c.id === caseId)
    if (!found) {
      return HttpResponse.json<ErrorResponse>({ detail: 'Dossier introuvable.' }, { status: 404 })
    }

    const caseDetail = {
      ...found,
      incident_date: (found as Record<string, unknown>).incident_date ?? '2026-11-20T08:00:00Z',
      incident_type: (found as Record<string, unknown>).incident_type ?? 'a_decider',
      affected_systems:
        (found as Record<string, unknown>).affected_systems ??
        (caseId === 'case-001'
          ? 'Contrôleur de domaine AD, Serveur Exchange, Postes analystes'
          : 'Contrôleur de domaine AD, Serveur Exchange'),
      members: (found as Record<string, unknown>).members ?? MOCK_CASE_MEMBERS,
    }

    return HttpResponse.json(caseDetail, { status: 200 })
  }),

  /**
   * Évolution du statut global d'un dossier d'investigation (Story F2.2).
   * Route cible : PATCH /api/v1/cases/:caseId/status
   * Statut : simulée, contrat cible : openapi.json
   */
  http.patch('*/api/v1/cases/:caseId/status', async ({ params, request }) => {
    const authHeader = request.headers.get('Authorization')

    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Jeton d'accès expiré ou absent." },
        { status: 401 },
      )
    }

    const token = authHeader.replace('Bearer ', '').trim()

    if (token === 'mock-expired-token' || token.includes('expired')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Jeton d'accès expiré ou absent." },
        { status: 401 },
      )
    }

    const caseId = String(params.caseId)
    const simHeader =
      request.headers.get('X-Simulation-Status') ||
      request.headers.get('X-Simulation-Update-Status') ||
      request.headers.get('X-Simulation-Case')

    // Simulation accès refusé 403 Forbidden
    if (
      token === 'mock-forbidden-token' ||
      token === 'mock-viewer-token' ||
      simHeader === 'forbidden' ||
      caseId === 'case-status-forbidden'
    ) {
      return HttpResponse.json<ErrorResponse>(
        {
          detail:
            "Accès refusé. Vous n'avez pas les autorisations nécessaires pour modifier le statut de ce dossier.",
        },
        { status: 403 },
      )
    }

    // Simulation erreur serveur 500
    if (
      token === 'mock-server-error-token' ||
      simHeader === 'server-error' ||
      simHeader === '500' ||
      caseId === 'case-status-500'
    ) {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Erreur interne du serveur lors de la mise à jour du statut du dossier.' },
        { status: 500 },
      )
    }

    // Simulation conflit 409 Conflict
    if (simHeader === 'conflict' || simHeader === '409' || caseId === 'case-status-conflict') {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Conflit de version ou transition concurrente détectée sur le dossier.' },
        { status: 409 },
      )
    }

    let body: Record<string, unknown> = {}
    try {
      body = (await request.json()) as Record<string, unknown>
    } catch {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Format de corps de requête invalide.' },
        { status: 400 },
      )
    }

    const newStatus = typeof body.status === 'string' ? body.status : ''

    if (!newStatus || !['open', 'in_progress', 'review', 'closed'].includes(newStatus)) {
      return HttpResponse.json<ErrorResponse>(
        { detail: `Statut cible invalide: '${newStatus}'.` },
        { status: 422 },
      )
    }

    const found = MOCK_CASES.find((c) => c.id === caseId)
    if (!found) {
      return HttpResponse.json<ErrorResponse>({ detail: 'Dossier introuvable.' }, { status: 404 })
    }

    // Matrice stricte des transitions autorisées (openapi.json / E2)
    const validTransitions: Record<string, string[]> = {
      open: ['in_progress', 'closed'],
      in_progress: ['review', 'open', 'closed'],
      review: ['closed', 'in_progress'],
      closed: [],
    }

    // Simulation rejet de transition 400
    if (simHeader === 'invalid-transition' || simHeader === '400') {
      return HttpResponse.json<ErrorResponse>(
        { detail: `Transition non autorisée du statut '${found.status}' vers '${newStatus}'.` },
        { status: 400 },
      )
    }

    const allowed = validTransitions[found.status] || []
    if (!allowed.includes(newStatus)) {
      return HttpResponse.json<ErrorResponse>(
        { detail: `Transition non autorisée du statut '${found.status}' vers '${newStatus}'.` },
        { status: 400 },
      )
    }

    found.status = newStatus
    found.updated_at = new Date().toISOString()

    const updatedDetail = {
      ...found,
      incident_date: (found as Record<string, unknown>).incident_date ?? '2026-11-20T08:00:00Z',
      incident_type: (found as Record<string, unknown>).incident_type ?? 'a_decider',
      affected_systems:
        (found as Record<string, unknown>).affected_systems ??
        'Contrôleur de domaine AD, Serveur Exchange',
      members: (found as Record<string, unknown>).members ?? MOCK_CASE_MEMBERS,
    }

    return HttpResponse.json(updatedDetail, { status: 200 })
  }),

  /**
   * Mise à jour en ligne d'un dossier d'investigation (Story F2.1).
   * Route cible : PATCH /api/v1/cases/:caseId
   * Statut : simulée, contrat cible : à réaligner
   */
  http.patch('*/api/v1/cases/:caseId', async ({ params, request }) => {
    const authHeader = request.headers.get('Authorization')

    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Jeton d'accès expiré ou absent." },
        { status: 401 },
      )
    }

    const token = authHeader.replace('Bearer ', '').trim()

    if (token === 'mock-expired-token' || token.includes('expired')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Jeton d'accès expiré ou absent." },
        { status: 401 },
      )
    }

    const caseId = String(params.caseId)
    const simHeader =
      request.headers.get('X-Simulation-Update-Case') || request.headers.get('X-Simulation-Case')

    // Simulation accès refusé 403 Forbidden
    if (
      token === 'mock-forbidden-token' ||
      simHeader === 'forbidden' ||
      caseId === 'case-forbidden'
    ) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Vous n'avez pas accès à ce dossier." },
        { status: 403 },
      )
    }

    // Simulation erreur interne 500
    if (
      token === 'mock-server-error-token' ||
      token.includes('server-error') ||
      simHeader === 'server-error' ||
      simHeader === '500' ||
      caseId === 'case-patch-500'
    ) {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Erreur interne du serveur lors de la mise à jour du dossier.' },
        { status: 500 },
      )
    }

    // Simulation erreur de validation serveur 422
    if (simHeader === 'validation-error' || simHeader === '422') {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Erreur de validation des données transmises.' },
        { status: 422 },
      )
    }

    let body: Record<string, unknown> = {}
    try {
      body = (await request.json()) as Record<string, unknown>
    } catch {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Format de corps de requête invalide.' },
        { status: 400 },
      )
    }

    const title = typeof body.title === 'string' ? body.title.trim() : ''
    const description =
      typeof body.description === 'string'
        ? body.description.trim()
        : body.description === null
          ? null
          : undefined

    if (!title) {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Le titre du dossier est obligatoire.' },
        { status: 422 },
      )
    }

    const found = MOCK_CASES.find((c) => c.id === caseId)
    if (!found) {
      return HttpResponse.json<ErrorResponse>({ detail: 'Dossier introuvable.' }, { status: 404 })
    }

    found.title = title
    if (description !== undefined) {
      found.description = description || ''
    }
    found.updated_at = new Date().toISOString()

    const updatedDetail = {
      ...found,
      incident_date: (found as Record<string, unknown>).incident_date ?? '2026-11-20T08:00:00Z',
      incident_type: (found as Record<string, unknown>).incident_type ?? 'a_decider',
      affected_systems:
        (found as Record<string, unknown>).affected_systems ??
        (caseId === 'case-001'
          ? 'Contrôleur de domaine AD, Serveur Exchange, Postes analystes'
          : 'Contrôleur de domaine AD, Serveur Exchange'),
      members: (found as Record<string, unknown>).members ?? MOCK_CASE_MEMBERS,
    }

    return HttpResponse.json(updatedDetail, { status: 200 })
  }),

  /**
   * Téléversement d'une preuve numérique (Story F3.1).
   * Route cible : POST /api/v1/cases/:caseId/evidences
   * Statut : simulée, contrat cible : openapi.json
   */
  http.post('*/api/v1/cases/:caseId/evidences', async ({ params, request }) => {
    const authHeader = request.headers.get('Authorization')

    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Jeton d'accès expiré ou absent." },
        { status: 401 },
      )
    }

    const token = authHeader.replace('Bearer ', '').trim()
    if (!token || token === 'expired-token') {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Jeton d'accès expiré ou absent." },
        { status: 401 },
      )
    }

    const caseId = String(params.caseId)
    const simHeader =
      request.headers.get('X-Simulation-Evidence') || request.headers.get('X-Simulation-Case')

    // Simulation accès refusé 403 Forbidden
    if (
      token === 'mock-forbidden-token' ||
      simHeader === 'forbidden' ||
      caseId === 'case-forbidden'
    ) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Vous n'avez pas accès à ce dossier." },
        { status: 403 },
      )
    }

    // Simulation erreur serveur 500
    if (
      token === 'mock-server-error-token' ||
      simHeader === 'server-error' ||
      simHeader === '500' ||
      caseId === 'case-upload-500' ||
      caseId === 'case-500'
    ) {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Erreur interne du serveur lors du téléversement de la preuve.' },
        { status: 500 },
      )
    }

    // Simulation rejet plafond volumétrique 413 Payload Too Large (C3)
    if (simHeader === 'payload-too-large' || simHeader === '413' || caseId === 'case-upload-413') {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Fichier volumineux : dépassement du plafond configuré par le serveur.' },
        { status: 413 },
      )
    }

    // Simulation fichier vide 400 Bad Request
    if (simHeader === 'empty-file' || simHeader === '400') {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Le fichier de preuve est vide (0 octet).' },
        { status: 400 },
      )
    }

    // Dossier introuvable 404 Not Found
    const found = MOCK_CASES.find((c) => c.id === caseId)
    if (!found && caseId === 'case-not-found') {
      return HttpResponse.json<ErrorResponse>({ detail: 'Dossier introuvable.' }, { status: 404 })
    }

    let originalName = 'artefact.raw'
    let fileSize = 1024
    let detectedType = 'application/octet-stream'

    try {
      const formData = await request.formData()
      const file = formData.get('file')
      if (file && typeof file === 'object' && 'name' in file) {
        const fileObj = file as File
        originalName = fileObj.name || originalName
        fileSize = fileObj.size
        detectedType = fileObj.type || detectedType
        if (fileSize === 0) {
          return HttpResponse.json<ErrorResponse>(
            { detail: 'Le fichier de preuve est vide (0 octet).' },
            { status: 400 },
          )
        }
      }
    } catch {
      // Ignoré si le parsing multipart échoue en environnement de test
    }

    const evidenceId = `evi-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
    const ingestionRunId = `run-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`

    if (found) {
      found.evidence_count = (found.evidence_count || 0) + 1
    }

    const newEvidence: EvidenceRead = {
      id: evidenceId,
      case_id: caseId,
      original_name: originalName,
      file_size: fileSize,
      sha256: null,
      detected_type: detectedType,
      imported_by: 'analyste@iryx.local',
      created_at: new Date().toISOString(),
    }
    if (!MOCK_CASE_EVIDENCES[caseId]) {
      MOCK_CASE_EVIDENCES[caseId] = []
    }
    MOCK_CASE_EVIDENCES[caseId].unshift(newEvidence)

    return HttpResponse.json(
      {
        evidence_id: evidenceId,
        ingestion_run_id: ingestionRunId,
      },
      {
        status: 202,
        headers: {
          Location: `/api/v1/cases/${caseId}/evidences/${evidenceId}/ingestion-status`,
        },
      },
    )
  }),

  /**
   * Consultation paginée de l'inventaire des preuves d'un dossier (Story F3.2).
   * Route cible : GET /api/v1/cases/:caseId/evidences
   * Statut : simulée, contrat cible : openapi.json
   */
  http.get('*/api/v1/cases/:caseId/evidences', ({ params, request }) => {
    const authHeader = request.headers.get('Authorization')

    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Jeton d'accès expiré ou absent." },
        { status: 401 },
      )
    }

    const token = authHeader.replace('Bearer ', '').trim()
    const caseId = String(params.caseId)
    const simHeader =
      request.headers.get('X-Simulation-Evidence') || request.headers.get('X-Simulation-Case')

    if (
      token === 'mock-forbidden-token' ||
      simHeader === 'forbidden' ||
      caseId === 'case-forbidden'
    ) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Accès refusé. Vous n'avez pas accès aux preuves de ce dossier." },
        { status: 403 },
      )
    }

    if (
      token === 'mock-server-error-token' ||
      simHeader === 'server-error' ||
      caseId === 'case-error'
    ) {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Erreur interne du serveur lors de la récupération des preuves.' },
        { status: 500 },
      )
    }

    if (caseId === 'case-not-found') {
      return HttpResponse.json<ErrorResponse>({ detail: 'Dossier introuvable.' }, { status: 404 })
    }

    if (caseId === 'case-empty' || simHeader === 'empty') {
      return HttpResponse.json({
        items: [],
        total: 0,
        total_items: 0,
        limit: 50,
        offset: 0,
        has_more: false,
      })
    }

    const url = new URL(request.url)
    const limit = parseInt(url.searchParams.get('limit') || '50', 10)
    const offset = parseInt(url.searchParams.get('offset') || '0', 10)

    const allItems = MOCK_CASE_EVIDENCES[caseId] || []
    const paginatedItems = allItems.slice(offset, offset + limit)

    return HttpResponse.json({
      items: paginatedItems,
      total: allItems.length,
      total_items: allItems.length,
      limit,
      offset,
      has_more: offset + paginatedItems.length < allItems.length,
    })
  }),

  /**
   * Consultation de l'état d'ingestion d'une preuve et scrutation avec Retry-After (Story F3.2).
   * Route cible : GET /api/v1/cases/:caseId/evidences/:evidenceId/ingestion-status
   * Statut : simulée, contrat cible : openapi.json
   */
  http.get(
    '*/api/v1/cases/:caseId/evidences/:evidenceId/ingestion-status',
    ({ params, request }) => {
      const authHeader = request.headers.get('Authorization')

      if (!authHeader || !authHeader.startsWith('Bearer ')) {
        return HttpResponse.json<ErrorResponse>(
          { detail: "Jeton d'accès expiré ou absent." },
          { status: 401 },
        )
      }

      const token = authHeader.replace('Bearer ', '').trim()
      const caseId = String(params.caseId)
      const evidenceId = String(params.evidenceId)
      const simHeader =
        request.headers.get('X-Simulation-Evidence') || request.headers.get('X-Simulation-Status')

      if (
        token === 'mock-forbidden-token' ||
        simHeader === 'forbidden' ||
        caseId === 'case-forbidden'
      ) {
        return HttpResponse.json<ErrorResponse>(
          { detail: "Accès refusé lors de la vérification d'ingestion." },
          { status: 403 },
        )
      }

      if (
        token === 'mock-server-error-token' ||
        simHeader === 'server-error' ||
        evidenceId === 'evi-error'
      ) {
        return HttpResponse.json<ErrorResponse>(
          { detail: "Erreur interne lors de la consultation d'ingestion." },
          { status: 500 },
        )
      }

      // Simulation de statut inconnu (règle docs/frontend/12 section 4)
      if (evidenceId === 'evi-unknown' || simHeader === 'unknown-status') {
        return HttpResponse.json({
          status: 'unrecognized_state_code',
          progress: 0,
          error_message: null,
          sha256: null,
          detected_type: 'application/octet-stream',
        })
      }

      // Simulation statut failed
      if (evidenceId === 'evi-004' || evidenceId === 'evi-failed' || simHeader === 'failed') {
        return HttpResponse.json({
          status: 'failed',
          progress: 10,
          error_message: 'Format binaire invalide ou corruption de fichier.',
          sha256: null,
          detected_type: 'application/octet-stream',
        })
      }

      // Simulation statut pending
      if (evidenceId === 'evi-pending' || simHeader === 'pending') {
        return HttpResponse.json(
          {
            status: 'pending',
            progress: 0,
            error_message: null,
            sha256: null,
            detected_type: 'application/x-ms-evtx',
          },
          {
            headers: {
              'Retry-After': '3',
            },
          },
        )
      }

      // Simulation statut processing
      if (
        evidenceId === 'evi-003' ||
        evidenceId === 'evi-processing' ||
        simHeader === 'processing'
      ) {
        return HttpResponse.json(
          {
            status: 'processing',
            progress: 45,
            error_message: null,
            sha256: null,
            detected_type: 'text/plain',
          },
          {
            headers: {
              'Retry-After': '3',
            },
          },
        )
      }

      // Simulation statut completed par défaut (intègre)
      const foundItem = (MOCK_CASE_EVIDENCES[caseId] || []).find((e) => e.id === evidenceId)
      return HttpResponse.json({
        status: 'completed',
        progress: 100,
        error_message: null,
        sha256:
          foundItem?.sha256 || 'a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef0',
        detected_type: foundItem?.detected_type || 'application/x-ms-evtx',
      })
    },
  ),

  /**
   * Consultation des métadonnées détaillées d'une preuve (Story F3.3).
   * Route cible : GET /api/v1/cases/:caseId/evidences/:evidenceId
   * Statut : simulée, contrat cible : openapi.json
   */
  http.get('*/api/v1/cases/:caseId/evidences/:evidenceId', ({ params, request }) => {
    const authHeader = request.headers.get('Authorization')

    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Jeton d'accès expiré ou absent." },
        { status: 401 },
      )
    }

    const token = authHeader.replace('Bearer ', '').trim()
    const caseId = String(params.caseId)
    const evidenceId = String(params.evidenceId)
    const simHeader =
      request.headers.get('X-Simulation-Evidence') ||
      request.headers.get('X-Simulation-Evidence-Detail')

    if (
      token === 'mock-forbidden-token' ||
      simHeader === 'forbidden' ||
      caseId === 'case-forbidden'
    ) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Accès refusé. Vous n'avez pas accès aux détails de cette preuve." },
        { status: 403 },
      )
    }

    if (
      token === 'mock-server-error-token' ||
      simHeader === 'server-error' ||
      caseId === 'case-error' ||
      evidenceId === 'evi-error'
    ) {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Erreur interne lors de la consultation des détails de la preuve.' },
        { status: 500 },
      )
    }

    if (caseId === 'case-not-found') {
      return HttpResponse.json<ErrorResponse>({ detail: 'Dossier introuvable.' }, { status: 404 })
    }

    const detail = getMockEvidenceDetail(caseId, evidenceId)
    if (!detail) {
      return HttpResponse.json<ErrorResponse>({ detail: 'Preuve introuvable.' }, { status: 404 })
    }

    return HttpResponse.json(detail)
  }),
]
