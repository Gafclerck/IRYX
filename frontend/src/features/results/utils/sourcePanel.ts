import { truncateObservationContent } from '../../evidence/utils/truncation'
import { SOURCE_UNKNOWN_STATUS_PREFIX, TO_REALIGN } from '../constants'
import type { ObservationRead } from '../types'

/**
 * Dérivation contrôlée des métadonnées du panneau « Source » (Story F4.7).
 *
 * RÈGLES :
 * 1. `ObservationRead` ne porte aucun champ dédié à l'extrait brut ni à
 *    l'empreinte de preuve : ces valeurs sont lues dans `normalized_content`
 *    (champs libres autorisés par openapi.json) et signalées « à réaligner »
 *    quand elles sont absentes.
 * 2. DP-04 : l'aperçu est calculé par l'utilitaire commun de troncature
 *    (500 lignes / 64 Ko). Le contenu intégral n'est jamais chargé pour
 *    l'affichage : seul le téléchargement direct le demande, sur action explicite.
 * 3. Aucune valeur chiffrée ni aucun statut supplémentaire n'est inventé.
 */

function readText(value: unknown): string | null {
  if (typeof value === 'string' && value.trim()) return value.trim()
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return null
}

export interface SourceExcerptInfo {
  readonly rawText: string
  readonly previewText: string
  readonly isTruncated: boolean
  readonly isEmpty: boolean
  readonly totalLines: number
  readonly totalBytes: number
}

export function buildSourceExcerpt(observation: ObservationRead): SourceExcerptInfo {
  const content = observation.normalized_content ?? {}
  const rawText =
    readText(content.raw_text) ??
    readText(content.raw_excerpt) ??
    readText(content.excerpt) ??
    readText(content.raw) ??
    ''

  const truncation = truncateObservationContent(rawText)
  return {
    rawText,
    previewText: truncation.previewText,
    isTruncated: truncation.isTruncated,
    isEmpty: rawText.length === 0,
    totalLines: truncation.totalLines,
    totalBytes: truncation.totalBytes,
  }
}

export interface SourceProofInfo {
  /** Empreinte affichée, tronquée pour l'aperçu. */
  readonly label: string
  /** Valeur intégrale copiée dans le presse-papier. */
  readonly copyValue: string
  readonly isAvailable: boolean
}

const FINGERPRINT_PREVIEW_LENGTH = 16

export function readSourceProof(observation: ObservationRead): SourceProofInfo {
  const content = observation.normalized_content ?? {}
  const fingerprint =
    readText(content.sha256) ??
    readText(content.sha_256) ??
    readText(content.fingerprint) ??
    readText(content.evidence_sha256)

  if (!fingerprint) {
    return { label: TO_REALIGN, copyValue: '', isAvailable: false }
  }

  return {
    label:
      fingerprint.length > FINGERPRINT_PREVIEW_LENGTH
        ? `${fingerprint.slice(0, FINGERPRINT_PREVIEW_LENGTH)}…`
        : fingerprint,
    copyValue: fingerprint,
    isAvailable: true,
  }
}

export interface SourceStatusInfo {
  readonly label: string | null
  readonly isUnknown: boolean
}

const KNOWN_SOURCE_STATUSES = ['available', 'disponible']

export function readSourceStatus(observation: ObservationRead): SourceStatusInfo {
  const content = observation.normalized_content ?? {}
  const status = readText(content.status)
  if (!status || KNOWN_SOURCE_STATUSES.includes(status.toLowerCase())) {
    return { label: null, isUnknown: false }
  }
  return { label: `${SOURCE_UNKNOWN_STATUS_PREFIX} (${status})`, isUnknown: true }
}
