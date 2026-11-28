import { useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle2, CircleHelp, XCircle } from 'lucide-react'
import {
  FINDING_CONFIDENCE_LABELS,
  FINDING_SEVERITY_LABELS,
  FINDING_TYPE_LABELS,
  REVIEW_COMMENT_DISABLED_NOTE,
  REVIEW_COMMENT_LABEL,
  REVIEW_DECISION_DISABLED_NOTE,
  REVIEW_DECISION_TO_REALIGN,
  REVIEW_REJECT_LABEL,
  REVIEW_REJECTION_REASON_LABEL,
  REVIEW_REJECTION_REASON_PLACEHOLDER,
  REVIEW_REJECTION_REASON_REQUIRED,
  REVIEW_VALIDATE_LABEL,
  formatFindingStatus,
  isKnownFindingStatus,
} from '../constants'
import { rejectionReasonSchema } from '../schemas/rejectionSchema'
import type { FindingOut } from '../types'

interface FindingCardProps {
  readonly finding: FindingOut
}

function statusIcon(status: string) {
  if (status === 'validated') return CheckCircle2
  if (status === 'rejected') return XCircle
  return CircleHelp
}

export function FindingCard({ finding }: FindingCardProps) {
  const [rejectOpen, setRejectOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [reasonError, setReasonError] = useState<string | null>(null)
  const StatusIcon = statusIcon(finding.status)
  const statusLabel = formatFindingStatus(finding.status)
  const known = isKnownFindingStatus(finding.status)
  const severityLabel = FINDING_SEVERITY_LABELS[finding.severity] ?? finding.severity
  const confidenceLabel = FINDING_CONFIDENCE_LABELS[finding.confidence] ?? finding.confidence
  const typeLabel = FINDING_TYPE_LABELS[finding.finding_type] ?? finding.finding_type

  const observationRefs = useMemo(() => finding.observation_refs ?? [], [finding.observation_refs])

  const onRejectClick = () => {
    setRejectOpen(true)
    setReasonError(null)
  }

  const onRejectConfirm = () => {
    const parsed = rejectionReasonSchema.safeParse(reason)
    if (!parsed.success) {
      setReasonError(parsed.error.issues[0]?.message ?? REVIEW_REJECTION_REASON_REQUIRED)
      return
    }
    // Route de décision absente du contrat (E6) : aucune décision envoyée/simulée.
    setReasonError(REVIEW_DECISION_DISABLED_NOTE)
  }

  return (
    <article
      className="space-y-4 rounded-lg border border-deep bg-deep/10 p-4"
      data-testid={`finding-card-${finding.id}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h3 className="text-base font-bold text-mist">{finding.title}</h3>
          <p className="text-xs text-teal font-mono">ID {finding.id}</p>
        </div>
        <span
          className="inline-flex items-center gap-1.5 rounded border border-deep bg-deep/30 px-2.5 py-1 text-xs font-semibold text-mist"
          data-testid={`finding-status-${finding.id}`}
        >
          <StatusIcon className="h-3.5 w-3.5 text-cyan" aria-hidden="true" />
          {statusLabel}
        </span>
      </div>

      <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-xs uppercase tracking-wider text-teal">Sévérité</dt>
          <dd className="text-mist" data-testid={`finding-severity-${finding.id}`}>
            {severityLabel} <span className="text-xs text-teal">({finding.severity})</span>
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wider text-teal">Typologie</dt>
          <dd className="text-mist">{typeLabel}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wider text-teal">Confiance</dt>
          <dd className="text-mist">{confidenceLabel}</dd>
        </div>
      </dl>

      <div>
        <p className="text-xs uppercase tracking-wider text-teal">Références observations</p>
        {observationRefs.length > 0 ? (
          <ul className="mt-1 space-y-1">
            {observationRefs.map((ref: string) => (
              <li key={ref} className="font-mono text-xs text-mist/90">
                {ref}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-xs text-mist/80">Aucune référence d’observation transmise.</p>
        )}
      </div>

      {!known && (
        <p className="text-xs text-teal" role="status">
          {statusLabel}. Actions désactivées par mesure de sécurité.
        </p>
      )}

      <div className="space-y-2 border-t border-deep pt-3">
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled
            title={REVIEW_DECISION_DISABLED_NOTE}
            className="rounded border border-teal bg-deep px-3 py-1.5 text-xs font-semibold text-mist/60 disabled:cursor-not-allowed"
            data-testid={`finding-validate-${finding.id}`}
          >
            {REVIEW_VALIDATE_LABEL}
          </button>
          <button
            type="button"
            disabled
            title={REVIEW_DECISION_DISABLED_NOTE}
            onClick={onRejectClick}
            className="rounded border border-teal bg-deep px-3 py-1.5 text-xs font-semibold text-mist/60 disabled:cursor-not-allowed"
            data-testid={`finding-reject-${finding.id}`}
          >
            {REVIEW_REJECT_LABEL}
          </button>
          <button
            type="button"
            disabled
            title={REVIEW_COMMENT_DISABLED_NOTE}
            className="rounded border border-teal bg-deep px-3 py-1.5 text-xs font-semibold text-mist/60 disabled:cursor-not-allowed"
            data-testid={`finding-comment-${finding.id}`}
          >
            {REVIEW_COMMENT_LABEL}
          </button>
        </div>
        <p className="text-xs text-teal" data-testid={`finding-decision-gap-${finding.id}`}>
          <AlertTriangle className="mr-1 inline h-3.5 w-3.5 text-cyan" aria-hidden="true" />
          {REVIEW_DECISION_TO_REALIGN} — {REVIEW_DECISION_DISABLED_NOTE}
        </p>

        {rejectOpen && (
          <div
            className="space-y-2 rounded border border-deep bg-deep/20 p-3"
            data-testid={`finding-reject-form-${finding.id}`}
          >
            <label
              htmlFor={`reject-reason-${finding.id}`}
              className="block text-xs font-semibold text-mist"
            >
              {REVIEW_REJECTION_REASON_LABEL}
            </label>
            <textarea
              id={`reject-reason-${finding.id}`}
              value={reason}
              onChange={(e) => {
                setReason(e.target.value)
                if (reasonError) setReasonError(null)
              }}
              rows={3}
              maxLength={2000}
              className="w-full rounded border border-deep bg-ink p-2 text-sm text-mist placeholder:text-teal focus:outline-none focus:ring-2 focus:ring-cyan"
              placeholder={REVIEW_REJECTION_REASON_PLACEHOLDER}
              data-testid={`finding-reject-reason-${finding.id}`}
            />
            {reasonError && (
              <p
                role="alert"
                className="text-xs font-semibold text-cyan"
                data-testid={`finding-reject-error-${finding.id}`}
              >
                {reasonError}
              </p>
            )}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={onRejectConfirm}
                className="rounded border border-cyan bg-cyan px-3 py-1.5 text-xs font-bold text-ink hover:bg-cyan/80 focus:outline-none focus:ring-2 focus:ring-cyan"
                data-testid={`finding-reject-confirm-${finding.id}`}
              >
                Confirmer le rejet
              </button>
              <button
                type="button"
                onClick={() => setRejectOpen(false)}
                className="rounded border border-teal bg-deep px-3 py-1.5 text-xs font-semibold text-mist hover:bg-deep/80 focus:outline-none focus:ring-2 focus:ring-cyan"
              >
                Annuler
              </button>
            </div>
            <p className="text-xs text-teal">{REVIEW_DECISION_DISABLED_NOTE}</p>
          </div>
        )}
      </div>
    </article>
  )
}
