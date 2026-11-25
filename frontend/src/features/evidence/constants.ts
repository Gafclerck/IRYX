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
