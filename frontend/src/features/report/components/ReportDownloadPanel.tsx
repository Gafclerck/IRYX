import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, Copy, Download } from 'lucide-react'
import {
  REPORT_DOWNLOAD_DISABLED_NOTE,
  REPORT_DOWNLOAD_ERROR_MESSAGE,
  REPORT_DOWNLOAD_IN_PROGRESS_LABEL,
  REPORT_DOWNLOAD_LABEL,
  REPORT_DOWNLOAD_READY_NOTE,
  REPORT_DOWNLOAD_RETRY_LABEL,
  REPORT_FINGERPRINT_ABSENT_NOTE,
  REPORT_FINGERPRINT_COPIED_LABEL,
  REPORT_FINGERPRINT_COPY_ERROR,
  REPORT_FINGERPRINT_COPY_LABEL,
  REPORT_FINGERPRINT_LABEL,
  REPORT_FINGERPRINT_READ_ONLY_NOTE,
} from '../constants'
import { useReportDownload } from '../hooks/useReportDownload'
import type { ReportDocument } from '../types'

const FINGERPRINT_VISIBLE_CHARS = 12

/** Troncature d'affichage uniquement : la valeur intégrale reste copiable. */
function truncateFingerprint(value: string): string {
  if (value.length <= FINGERPRINT_VISIBLE_CHARS * 2 + 1) return value
  return `${value.slice(0, FINGERPRINT_VISIBLE_CHARS)}…${value.slice(-FINGERPRINT_VISIBLE_CHARS)}`
}

export interface ReportDownloadPanelProps {
  readonly caseId: string
  readonly document: ReportDocument | null
  /** Vrai uniquement lorsque le back a renvoyé un rapport prêt. */
  readonly isReady: boolean
}

/**
 * Téléchargement direct et empreinte du rapport scellé (Story F5.2, DP-03).
 *
 * Le fichier est généré par un lien Blob à partir des octets reçus : le front
 * ne transforme, ne recalcule et ne re-signe rien. L'empreinte est affichée
 * uniquement si le back l'a transmise, sans calcul local.
 */
export function ReportDownloadPanel({ caseId, document, isReady }: ReportDownloadPanelProps) {
  const { isDownloading, errorMessage, download, retry } = useReportDownload(caseId)
  const [isCopied, setIsCopied] = useState(false)
  const [copyError, setCopyError] = useState<string | null>(null)
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (copyTimerRef.current !== null) clearTimeout(copyTimerRef.current)
    }
  }, [])

  const fingerprint = document?.sha256
  const canDownload = isReady && Boolean(document?.content) && !isDownloading

  const copyFingerprint = async () => {
    if (!fingerprint) return
    try {
      if (!globalThis.navigator.clipboard?.writeText) {
        setCopyError(REPORT_FINGERPRINT_COPY_ERROR)
        return
      }
      await globalThis.navigator.clipboard.writeText(fingerprint)
      setCopyError(null)
      setIsCopied(true)
      if (copyTimerRef.current !== null) clearTimeout(copyTimerRef.current)
      copyTimerRef.current = setTimeout(() => setIsCopied(false), 2000)
    } catch {
      setCopyError(REPORT_FINGERPRINT_COPY_ERROR)
    }
  }

  return (
    <section
      className="space-y-3 rounded-lg border border-deep bg-deep/10 p-4"
      aria-label="Téléchargement du rapport scellé"
      data-testid="report-download-panel"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <h2 className="flex items-center gap-2 text-base font-bold text-mist">
            <Download className="h-4 w-4 text-cyan" aria-hidden="true" />
            Téléchargement du rapport
          </h2>
          <p className="text-xs text-teal">{REPORT_DOWNLOAD_READY_NOTE}</p>
        </div>
        <button
          type="button"
          onClick={() => document && download(document)}
          disabled={!canDownload}
          aria-describedby="report-download-explanation"
          className="rounded border border-cyan bg-cyan px-4 py-2 text-sm font-bold text-ink hover:bg-cyan/80 focus:outline-none focus:ring-2 focus:ring-cyan disabled:cursor-not-allowed disabled:border-deep disabled:bg-deep/40 disabled:text-mist/60"
          data-testid="report-download-button"
        >
          {isDownloading ? REPORT_DOWNLOAD_IN_PROGRESS_LABEL : REPORT_DOWNLOAD_LABEL}
        </button>
      </div>

      <p
        id="report-download-explanation"
        className="text-xs text-teal"
        data-testid="report-download-explanation"
      >
        {isReady ? REPORT_DOWNLOAD_READY_NOTE : REPORT_DOWNLOAD_DISABLED_NOTE}
      </p>

      {errorMessage && (
        <div
          className="space-y-2 rounded border border-deep bg-deep/40 p-3"
          role="alert"
          data-testid="report-download-error"
        >
          <p
            className="flex items-start gap-2 text-sm text-mist"
            data-testid="report-download-error-message"
          >
            <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-cyan" aria-hidden="true" />
            {errorMessage || REPORT_DOWNLOAD_ERROR_MESSAGE}
          </p>
          <button
            type="button"
            onClick={() => document && retry(document)}
            className="rounded border border-cyan bg-cyan px-3 py-1.5 text-xs font-bold text-ink hover:bg-cyan/80 focus:outline-none focus:ring-2 focus:ring-cyan"
            data-testid="report-download-retry"
          >
            {REPORT_DOWNLOAD_RETRY_LABEL}
          </button>
        </div>
      )}

      <div className="border-t border-deep pt-3" data-testid="report-fingerprint-section">
        <p className="text-xs font-semibold uppercase tracking-wider text-teal">
          {REPORT_FINGERPRINT_LABEL}
        </p>
        {fingerprint ? (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <code
              className="rounded border border-deep bg-mist px-2 py-1 font-mono text-xs text-ink"
              data-testid="report-fingerprint-value"
            >
              {truncateFingerprint(fingerprint)}
            </code>
            <button
              type="button"
              onClick={() => void copyFingerprint()}
              className="inline-flex items-center gap-1 rounded border border-teal bg-deep px-2 py-1 text-xs font-semibold text-mist hover:bg-deep/80 focus:outline-none focus:ring-2 focus:ring-cyan"
              aria-label="Copier l'empreinte complète"
              data-testid="report-fingerprint-copy"
            >
              <Copy className="h-3.5 w-3.5 text-cyan" aria-hidden="true" />
              {REPORT_FINGERPRINT_COPY_LABEL}
            </button>
            {isCopied && (
              <span
                className="text-xs font-semibold text-cyan"
                role="status"
                data-testid="report-fingerprint-copied"
              >
                {REPORT_FINGERPRINT_COPIED_LABEL}
              </span>
            )}
            {copyError && (
              <span
                className="text-xs text-mist"
                role="alert"
                data-testid="report-fingerprint-copy-error"
              >
                {copyError}
              </span>
            )}
            <span className="sr-only">{REPORT_FINGERPRINT_READ_ONLY_NOTE}</span>
          </div>
        ) : (
          <p className="mt-1 text-xs text-teal" data-testid="report-fingerprint-absent">
            {REPORT_FINGERPRINT_ABSENT_NOTE}
          </p>
        )}
      </div>
    </section>
  )
}
