import { FileText, LockKeyhole } from 'lucide-react'
import { REPORT_FORMATS_NOTE, REPORT_READ_ONLY_NOTE } from '../constants'
import type { ReportDocument } from '../types'

export interface ReportPreviewProps {
  readonly document: ReportDocument
}

/**
 * Aperçu du rapport scellé (Story F5.1, DP-03).
 *
 * Le contenu est affiché exactement tel que renvoyé par le back-end : aucune
 * section n'est reconstruite, réordonnée ni enrichie côté front. Le conteneur
 * utilise le fond papier `mist` et le texte `ink` de la palette stricte.
 */
export function ReportPreview({ document }: ReportPreviewProps) {
  return (
    <section className="space-y-3" aria-label="Aperçu du rapport d'incident">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-lg font-bold text-mist">
          <FileText className="h-5 w-5 text-cyan" aria-hidden="true" />
          Rapport d'incident
        </h2>
        <span
          className="rounded border border-deep bg-deep/20 px-3 py-1 text-xs font-mono text-teal"
          data-testid="report-format"
        >
          {document.format}
        </span>
      </div>

      <article
        className="rounded-lg border-2 border-deep bg-mist p-6 text-ink shadow-sm"
        data-testid="report-preview"
      >
        <pre
          className="whitespace-pre-wrap break-words font-mono text-sm leading-relaxed text-ink"
          data-testid="report-content"
        >
          {document.content}
        </pre>
      </article>

      <div className="space-y-1 text-xs text-teal">
        <p className="flex items-start gap-1.5" data-testid="report-read-only-note">
          <LockKeyhole className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-cyan" aria-hidden="true" />
          {REPORT_READ_ONLY_NOTE}
        </p>
        <p data-testid="report-formats-note">{REPORT_FORMATS_NOTE}</p>
      </div>
    </section>
  )
}
