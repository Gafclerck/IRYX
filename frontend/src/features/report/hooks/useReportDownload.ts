import { useCallback, useEffect, useRef, useState } from 'react'
import { REPORT_DOWNLOAD_ERROR_MESSAGE } from '../constants'
import type { ReportDocument, ReportFormat } from '../types'

/** Extensions et types MIME dérivés du seul format renvoyé par le back-end (ADR-0004). */
const FILE_EXTENSIONS: Record<ReportFormat, string> = {
  markdown: 'md',
  json: 'json',
}

const MIME_TYPES: Record<ReportFormat, string> = {
  markdown: 'text/markdown;charset=utf-8',
  json: 'application/json;charset=utf-8',
}

/**
 * Déclenche le téléchargement via un lien temporaire construit à partir du
 * contenu reçu. Aucun octet n'est ajouté, retiré ou réencodé : le Blob est
 * alimenté directement par `reportDocument.content` (DP-03).
 */
function startBrowserDownload(reportDocument: ReportDocument, caseId: string): void {
  const blob = new Blob([reportDocument.content], {
    type: MIME_TYPES[reportDocument.format],
  })
  const url = URL.createObjectURL(blob)
  let link: HTMLAnchorElement | null = null

  try {
    link = globalThis.document.createElement('a')
    link.href = url
    link.download = `rapport-${caseId}.${FILE_EXTENSIONS[reportDocument.format]}`
    link.rel = 'noopener'
    globalThis.document.body.appendChild(link)
    link.click()
  } finally {
    link?.remove()
    URL.revokeObjectURL(url)
  }
}

export interface UseReportDownloadReturn {
  readonly isDownloading: boolean
  readonly errorMessage: string | null
  readonly download: (reportDocument: ReportDocument) => void
  readonly retry: (reportDocument: ReportDocument) => void
}

/**
 * Téléchargement du rapport scellé (Story F5.2, FR-REP-02, DP-03).
 *
 * RÈGLES DE CONCEPTION :
 * 1. Le fichier est construit à partir de la réponse déjà reçue : aucune
 *    requête supplémentaire, aucune transformation et aucun recalcul.
 * 2. Le contenu transite uniquement par un Blob et une URL objet révoquée
 *    immédiatement après le clic ; ni localStorage ni sessionStorage.
 * 3. L'état de téléchargement désactive le bouton pendant une trame afin que
 *    l'utilisateur voie l'état « en cours ».
 */
export function useReportDownload(caseId: string): UseReportDownloadReturn {
  const [isDownloading, setIsDownloading] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const mountedRef = useRef(true)
  const busyRef = useRef(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      mountedRef.current = false
      busyRef.current = false
      if (timerRef.current !== null) clearTimeout(timerRef.current)
    }
  }, [])

  const download = useCallback(
    (reportDocument: ReportDocument) => {
      if (busyRef.current) return

      busyRef.current = true
      setIsDownloading(true)
      setErrorMessage(null)

      timerRef.current = setTimeout(() => {
        timerRef.current = null
        if (!mountedRef.current) return

        try {
          startBrowserDownload(reportDocument, caseId)
        } catch {
          setErrorMessage(REPORT_DOWNLOAD_ERROR_MESSAGE)
        } finally {
          busyRef.current = false
          setIsDownloading(false)
        }
      }, 0)
    },
    [caseId],
  )

  const retry = useCallback(
    (reportDocument: ReportDocument) => {
      setErrorMessage(null)
      download(reportDocument)
    },
    [download],
  )

  return { isDownloading, errorMessage, download, retry }
}
