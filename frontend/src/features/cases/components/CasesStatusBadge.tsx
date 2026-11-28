import { Circle, Clock, AlertCircle, CheckCircle2 } from 'lucide-react'
import type { CaseStatus } from '../../../api/cases-types'
import {
  CASE_STATUS_LABELS,
  CASE_STATUS_UPPERCASE_LABELS,
  CASE_STATUS_UNDEFINED_LABEL,
} from '../../../api/cases-types'

export interface CasesStatusBadgeProps {
  readonly status?: CaseStatus | string | null
  readonly uppercase?: boolean
}

const statusConfig: Record<
  CaseStatus,
  { label: string; uppercaseLabel: string; icon: typeof Circle; description: string }
> = {
  open: {
    label: CASE_STATUS_LABELS.open,
    uppercaseLabel: CASE_STATUS_UPPERCASE_LABELS.open,
    icon: Circle,
    description: 'Dossier ouvert',
  },
  in_progress: {
    label: CASE_STATUS_LABELS.in_progress,
    uppercaseLabel: CASE_STATUS_UPPERCASE_LABELS.in_progress,
    icon: Clock,
    description: 'Investigation en cours',
  },
  review: {
    label: CASE_STATUS_LABELS.review,
    uppercaseLabel: CASE_STATUS_UPPERCASE_LABELS.review,
    icon: AlertCircle,
    description: 'En cours de revue et arbitrage',
  },
  closed: {
    label: CASE_STATUS_LABELS.closed,
    uppercaseLabel: CASE_STATUS_UPPERCASE_LABELS.closed,
    icon: CheckCircle2,
    description: 'Dossier clôturé',
  },
}

/**
 * Badge de statut d'avancement de dossier (Story F1.6 / F2.2 / NFR-ACC-02).
 * Signalement non chromatique garantissant l'accessibilité : libellé texte explicite + icône de forme distincte.
 * Prise en charge du mode majuscule (uppercase) pour l'en-tête du contexte (Story F2.2).
 * Prise en charge de l'état vide ou non défini (Story F2.2).
 */
export function CasesStatusBadge({ status, uppercase = false }: CasesStatusBadgeProps) {
  if (!status || !(status in statusConfig)) {
    return (
      <span
        className="inline-flex items-center gap-1.5 rounded border border-deep bg-ink px-2 py-0.5 text-xs font-medium text-teal"
        data-testid="case-status-undefined"
        aria-label="Statut non défini"
      >
        <Circle className="h-3 w-3 text-teal" aria-hidden="true" />
        <span>{CASE_STATUS_UNDEFINED_LABEL}</span>
      </span>
    )
  }

  const validStatus = status as CaseStatus
  const config = statusConfig[validStatus]
  const Icon = config.icon
  const label = uppercase ? config.uppercaseLabel : config.label

  return (
    <span
      className="inline-flex items-center gap-1.5 rounded border border-deep bg-ink px-2 py-0.5 text-xs font-medium text-mist"
      data-testid={`case-status-${validStatus}`}
      aria-label={config.description}
    >
      <Icon className="h-3 w-3 text-cyan" aria-hidden="true" />
      <span>{label}</span>
    </span>
  )
}
