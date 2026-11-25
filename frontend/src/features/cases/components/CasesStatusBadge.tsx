import { Circle, Clock, AlertCircle, CheckCircle2 } from 'lucide-react'
import type { CaseStatus } from '../../../api/cases-types'

export interface CasesStatusBadgeProps {
  readonly status: CaseStatus
}

const statusConfig: Record<
  CaseStatus,
  { label: string; icon: typeof Circle; description: string }
> = {
  open: {
    label: 'Ouvert',
    icon: Circle,
    description: 'Dossier ouvert',
  },
  in_progress: {
    label: 'En cours',
    icon: Clock,
    description: 'Investigation en cours',
  },
  review: {
    label: 'En revue',
    icon: AlertCircle,
    description: 'En cours de revue et arbitrage',
  },
  closed: {
    label: 'Clôturé',
    icon: CheckCircle2,
    description: 'Dossier clôturé',
  },
}

/**
 * Badge de statut d'avancement de dossier (Story F1.6 / NFR-ACC-02).
 * Signalement non chromatique garantissant l'accessibilité : libellé texte explicite + icône de forme distincte.
 */
export function CasesStatusBadge({ status }: CasesStatusBadgeProps) {
  const config = statusConfig[status] || statusConfig.open
  const Icon = config.icon

  return (
    <span
      className="inline-flex items-center gap-1.5 rounded border border-deep bg-ink px-2 py-0.5 text-xs font-medium text-mist"
      data-testid={`case-status-${status}`}
      aria-label={config.description}
    >
      <Icon className="h-3 w-3 text-cyan" aria-hidden="true" />
      <span>{config.label}</span>
    </span>
  )
}
