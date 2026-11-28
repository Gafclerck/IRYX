import { AlertTriangle } from 'lucide-react'
import { AGENT_RETRY_REALIGNMENT_NOTE } from '../constants'
import type { AgentCardData } from '../types'

export interface AgentCardProps {
  readonly agent: AgentCardData
}

/** Carte d'un agent : seules les données dérivées du contrat sont valorisées. */
export function AgentCard({ agent }: AgentCardProps) {
  return (
    <article
      className="space-y-3 rounded-lg border border-deep bg-deep/10 p-4"
      aria-label={`Agent ${agent.name}`}
      data-testid={`run-agent-card-${agent.key}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2">
          {agent.isFailed && (
            <AlertTriangle
              className="mt-0.5 h-5 w-5 flex-shrink-0 text-cyan"
              aria-label="Agent en échec"
              data-testid={`run-agent-failed-icon-${agent.key}`}
            />
          )}
          <h3 className="text-sm font-bold uppercase tracking-wide text-mist">{agent.name}</h3>
        </div>
        <span
          className={`rounded border px-2 py-1 text-xs font-semibold ${
            agent.isFailed ? 'border-cyan bg-deep text-cyan' : 'border-deep bg-deep/40 text-teal'
          }`}
          data-testid={`run-agent-status-${agent.key}`}
        >
          {agent.statusLabel}
        </span>
      </div>

      <dl className="space-y-1.5 text-xs text-mist/90">
        <div className="flex justify-between gap-3">
          <dt className="text-teal">Temps écoulé</dt>
          <dd data-testid={`run-agent-elapsed-${agent.key}`}>{agent.elapsedLabel}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-teal">Progression</dt>
          <dd data-testid={`run-agent-progress-${agent.key}`}>{agent.progressLabel}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-teal">Dernier message</dt>
          <dd data-testid={`run-agent-message-${agent.key}`}>{agent.lastMessageLabel}</dd>
        </div>
      </dl>

      <div
        className="h-2 rounded border border-deep bg-ink"
        aria-label={`Jauge d'avancement : ${agent.progressLabel}`}
        data-testid={`run-agent-progress-gauge-${agent.key}`}
      />

      {agent.isFailed && (
        <div className="space-y-2 border-t border-deep pt-3">
          <p className="text-xs text-mist" data-testid={`run-agent-diagnostic-${agent.key}`}>
            Diagnostic : {agent.diagnosticLabel}
          </p>
          <button
            type="button"
            disabled
            title={AGENT_RETRY_REALIGNMENT_NOTE}
            className="inline-flex items-center gap-1.5 rounded border border-deep bg-deep px-3 py-1.5 text-xs font-semibold text-cyan disabled:cursor-not-allowed disabled:opacity-60"
            data-testid={`run-agent-retry-${agent.key}`}
          >
            Réessayer cet agent — {AGENT_RETRY_REALIGNMENT_NOTE}
          </button>
        </div>
      )}
    </article>
  )
}
