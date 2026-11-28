import {
  ACCEPTED_EXTENSIONS,
  ACCEPTED_SPECIAL_FILENAMES,
  EVIDENCE_ACCEPTED_FORMATS_SUMMARY,
} from '../constants'

export interface FileValidationResult {
  readonly valid: boolean
  readonly reason?: string
}

/**
 * Valide le format d'un fichier de preuve selon la liste stricte des formats autorisés (Story F3.1).
 *
 * Formats autorisés : EVTX, logs texte, ruches de registre, Prefetch, images RAM.
 *
 * RÈGLE D'ARCHITECTURE :
 * Le format est refusé immédiatement sans émission de requête réseau, avec motif explicite.
 * Aucune limite volumétrique n'est imposée côté client (« à caler C3 »).
 */
export function validateEvidenceFile(file: File): FileValidationResult {
  const fileName = file.name.toLowerCase().trim()

  // 1. Ruches de registre sans extension ou avec extension spéciale
  const isSpecialHive = ACCEPTED_SPECIAL_FILENAMES.some(
    (name) => fileName === name || fileName.startsWith(`${name}.`),
  )
  if (isSpecialHive) {
    return { valid: true }
  }

  // 2. Extensions autorisées
  const hasValidExt = ACCEPTED_EXTENSIONS.some((ext) => fileName.endsWith(ext))
  if (hasValidExt) {
    return { valid: true }
  }

  return {
    valid: false,
    reason: `Format de fichier non supporté pour « ${file.name} ». Formats acceptés : ${EVIDENCE_ACCEPTED_FORMATS_SUMMARY}.`,
  }
}

/**
 * Formate une taille en octets en chaîne lisible en français (o, Ko, Mo, Go, To).
 */
export function formatFileSize(bytes: number): string {
  if (bytes <= 0) return '0 o'
  const units = ['o', 'Ko', 'Mo', 'Go', 'To']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  const size = bytes / Math.pow(1024, i)
  return `${size.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}
