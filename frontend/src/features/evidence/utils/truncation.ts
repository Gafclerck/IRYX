import { DP04_MAX_PREVIEW_LINES, DP04_MAX_PREVIEW_BYTES } from '../constants'
import type { TruncatedContent } from '../types'

/**
 * Calcule la troncature volumétrique d'un artefact ou d'une observation brute (Décision DP-04).
 *
 * RÈGLE :
 * Si le contenu textuel brut dépasse 500 lignes OU 64 Ko (65 536 octets),
 * l'aperçu est tronqué à 500 lignes / 64 Ko avec le bouton « Télécharger l'observation intégrale ».
 */
export function truncateObservationContent(content: string): TruncatedContent {
  if (!content) {
    return {
      isTruncated: false,
      previewText: '',
      fullText: '',
      totalLines: 0,
      totalBytes: 0,
    }
  }

  const encoder = new TextEncoder()
  const totalBytes = encoder.encode(content).length
  const lines = content.split('\n')
  const totalLines = lines.length

  const exceedsLines = totalLines > DP04_MAX_PREVIEW_LINES
  const exceedsBytes = totalBytes > DP04_MAX_PREVIEW_BYTES

  if (!exceedsLines && !exceedsBytes) {
    return {
      isTruncated: false,
      previewText: content,
      fullText: content,
      totalLines,
      totalBytes,
    }
  }

  let truncationReason: 'lines' | 'bytes' | 'both' = 'lines'
  if (exceedsLines && exceedsBytes) {
    truncationReason = 'both'
  } else if (exceedsBytes) {
    truncationReason = 'bytes'
  }

  // Tronque d'abord à 500 lignes au maximum
  const truncatedLines = exceedsLines ? lines.slice(0, DP04_MAX_PREVIEW_LINES) : lines
  let previewText = truncatedLines.join('\n')

  // Si le résultat dépasse encore 64 Ko, tronque les octets
  const previewBytes = encoder.encode(previewText)
  if (previewBytes.length > DP04_MAX_PREVIEW_BYTES) {
    const sliced = previewBytes.slice(0, DP04_MAX_PREVIEW_BYTES)
    previewText = new TextDecoder().decode(sliced)
  }

  return {
    isTruncated: true,
    previewText,
    fullText: content,
    totalLines,
    totalBytes,
    truncationReason,
  }
}

/**
 * Déclenche le téléchargement direct côté navigateur d'un fichier textuel (Décision DP-04).
 */
export function downloadTextFile(
  filename: string,
  content: string,
  mimeType = 'text/plain;charset=utf-8',
) {
  if (typeof window === 'undefined') return

  const blob = new Blob([content], { type: mimeType })
  if (typeof URL !== 'undefined' && typeof URL.createObjectURL === 'function') {
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }
}
