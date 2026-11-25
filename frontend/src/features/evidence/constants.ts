/**
 * Constantes et référentiel des formats de preuves autorisés (Story F3.1).
 *
 * RÈGLES DE CONCEPTION :
 * 1. Formats autorisés : EVTX, logs texte, ruches de registre, Prefetch, images RAM.
 * 2. Aucune valeur inventée : formats alignés sur la story F3.1 et FR-EVI-01.
 * 3. Plafond volumétrique unitaire : « à caler (C3) » — n'impose aucune valeur côté client,
 *    le serveur valide et refuse au-delà.
 */

export interface EvidenceFormatCategory {
  readonly category: string
  readonly label: string
  readonly extensions: readonly string[]
  readonly specialNames?: readonly string[]
}

export const ACCEPTED_EVIDENCE_CATEGORIES: readonly EvidenceFormatCategory[] = [
  {
    category: 'EVTX',
    label: 'Journaux d’événements Windows (EVTX)',
    extensions: ['.evtx'],
  },
  {
    category: 'LOGS',
    label: 'Journaux texte et CSV (logs)',
    extensions: ['.log', '.txt', '.csv'],
  },
  {
    category: 'REGISTRY',
    label: 'Ruches de registre Windows',
    extensions: ['.dat', '.hiv', '.hive', '.reg'],
    specialNames: ['sam', 'system', 'software', 'security', 'default', 'ntuser.dat'],
  },
  {
    category: 'PREFETCH',
    label: 'Artefacts d’exécution Windows Prefetch',
    extensions: ['.pf'],
  },
  {
    category: 'RAM',
    label: 'Images de mémoire vive (RAM)',
    extensions: ['.raw', '.dmp', '.mem', '.vmem', '.bin', '.img'],
  },
]

export const ACCEPTED_EXTENSIONS: readonly string[] = [
  '.evtx',
  '.log',
  '.txt',
  '.csv',
  '.pf',
  '.dat',
  '.hiv',
  '.hive',
  '.reg',
  '.raw',
  '.dmp',
  '.mem',
  '.vmem',
  '.bin',
  '.img',
]

export const ACCEPTED_SPECIAL_FILENAMES: readonly string[] = [
  'sam',
  'system',
  'software',
  'security',
  'default',
  'ntuser.dat',
]

export const EVIDENCE_CAPACITY_NOTE =
  'Plafond volumétrique unitaire : à caler (C3) — validation assurée par le serveur.'

export const EVIDENCE_ACCEPTED_FORMATS_SUMMARY =
  'EVTX, logs texte, ruches de registre, Prefetch, images RAM'

/**
 * Constantes de scrutation selon ADR-0008 (Option A : Retry-After: 3, cadence 3 à 5 secondes).
 */
export const ADR0008_POLLING_DEFAULT_INTERVAL_SECONDS = 3
export const ADR0008_POLLING_DEFAULT_INTERVAL_MS = 3000
export const ADR0008_POLLING_MAX_BACKOFF_MS = 15000

/**
 * Décision DP-05 : arrêt de l'interrogation en cas de coupure prolongée avec bouton « Réessayer la connexion ».
 * Le délai ou nombre de tentatives avant déclaration de coupure n'étant pas chiffré dans l'ADR-0008,
 * il est consigné « à décider » et adossé à un seuil de sécurité de 3 échecs consécutifs.
 */
export const DP05_NETWORK_CUTOFF_NOTE = 'Délai de coupure réseau prolongée : à décider (DP-05)'
export const DP05_MAX_CONSECUTIVE_NETWORK_ERRORS = 3

/**
 * Statuts d'ingestion autorisés selon docs/frontend/12-parcours-et-etats.md et docs/03-modele-de-donnees.md.
 */
export const KNOWN_INGESTION_STATUSES = ['pending', 'processing', 'completed', 'failed'] as const

export const TERMINAL_INGESTION_STATUSES = ['completed', 'failed'] as const

export interface IngestionStatusDisplayInfo {
  readonly label: string
  readonly isKnown: boolean
  readonly isTerminal: boolean
  readonly isIntegrity: boolean
  readonly isFailed: boolean
}

/**
 * Formate et valide un statut d'ingestion.
 * Conformément à la section 4 de docs/frontend/12 :
 * « Si l'API transmet une valeur de statut non répertoriée (...), le front-end applique la règle :
 * Le statut est affiché sous la forme « État inconnu » suivi du code textuel brut retourné entre parenthèses. »
 */
export function formatIngestionStatus(status: string | undefined | null): IngestionStatusDisplayInfo {
  if (!status) {
    return {
      label: 'EN ATTENTE',
      isKnown: true,
      isTerminal: false,
      isIntegrity: false,
      isFailed: false,
    }
  }

  switch (status) {
    case 'completed':
      return {
        label: 'INTÈGRE',
        isKnown: true,
        isTerminal: true,
        isIntegrity: true,
        isFailed: false,
      }
    case 'failed':
      return {
        label: 'ÉCHEC',
        isKnown: true,
        isTerminal: true,
        isIntegrity: false,
        isFailed: true,
      }
    case 'processing':
      return {
        label: 'EN COURS',
        isKnown: true,
        isTerminal: false,
        isIntegrity: false,
        isFailed: false,
      }
    case 'pending':
      return {
        label: 'EN ATTENTE',
        isKnown: true,
        isTerminal: false,
        isIntegrity: false,
        isFailed: false,
      }
    default:
      return {
        label: `État inconnu (${status})`,
        isKnown: false,
        isTerminal: true, // Statut inconnu traité comme terminal pour ne pas scruter indéfiniment
        isIntegrity: false,
        isFailed: true, // Non intègre par principe de sécurité
      }
  }
}

