import { ACTIVITY_LOG_REALIGNMENT_NOTE, formatUtcTimestamp } from '../constants'
import type { ActivityEntry } from '../types'

export interface ActivityLogProps {
  readonly entries: readonly ActivityEntry[]
}

/** Journal horodaté UTC, en lecture seule, construit à partir des phases du contrat. */
export function ActivityLog({ entries }: ActivityLogProps) {
  return (
    <section
      className="space-y-3 rounded-lg border border-deep bg-deep/10 p-4 font-mono"
      aria-labelledby="run-activity-heading"
      data-testid="run-activity-log"
    >
      <div>
        <h2
          id="run-activity-heading"
          className="text-sm font-bold uppercase tracking-wide text-mist"
        >
          Journal d’activité (UTC)
        </h2>
        <p className="mt-1 text-xs text-teal">{ACTIVITY_LOG_REALIGNMENT_NOTE}</p>
      </div>

      {entries.length === 0 ? (
        <p
          className="font-mono text-xs text-mist/80"
          role="status"
          data-testid="run-activity-empty"
        >
          Initialisation du flux d'activité...
        </p>
      ) : (
        <ol
          className="max-h-96 space-y-2 overflow-y-auto font-mono text-xs text-mist"
          data-testid="run-activity-entries"
        >
          {entries.map((entry) => (
            <li
              key={entry.id}
              className="rounded border border-deep bg-deep/20 p-2"
              data-testid={`run-activity-entry-${entry.id}`}
            >
              <time className="text-cyan" dateTime={entry.timestamp}>
                {formatUtcTimestamp(entry.timestamp)}
              </time>
              <span className="ml-2 text-mist">
                {entry.agentName} — {entry.eventLabel}
              </span>
            </li>
          ))}
        </ol>
      )}
      <p className="text-xs text-teal">Lecture seule</p>
    </section>
  )
}
