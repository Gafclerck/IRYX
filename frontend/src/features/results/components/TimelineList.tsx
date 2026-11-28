import { ChevronLeft, ChevronRight, MousePointerClick } from 'lucide-react'
import { SKIPPED_TABS_NOTE, SOURCE_PANEL_OPEN_NOTE, TIMELINE_PAGE_SIZE } from '../constants'
import type { TimelineEntry } from '../types'

export interface TimelineListProps {
  readonly entries: readonly TimelineEntry[]
  readonly page: number
  readonly hasMore: boolean
  readonly isFetching: boolean
  readonly onNext: () => void
  readonly onPrevious: () => void
  readonly onOpenSource: (entry: TimelineEntry, origin: HTMLElement) => void
}

/**
 * Liste UTC de la chronologie (Story F4.6).
 *
 * RÈGLES :
 * 1. Un seul bloc de 100 événements est rendu à la fois (DP-01).
 * 2. Chaque ligne affiche date UTC en police mono, résumé court et source en puce.
 * 3. L'ouverture de l'événement ou de la source active le tiroir latéral F4.7
 *    sans quitter la page ; l'élément d'origine est transmis pour le focus.
 */
export function TimelineList({
  entries,
  page,
  hasMore,
  isFetching,
  onNext,
  onPrevious,
  onOpenSource,
}: TimelineListProps) {
  return (
    <section className="space-y-4" aria-labelledby="timeline-heading" data-testid="timeline-list">
      <div className="space-y-2 border-b border-deep pb-3">
        <div role="tablist" aria-label="Vues des résultats" className="flex gap-2">
          <button
            type="button"
            role="tab"
            aria-selected="true"
            className="rounded border border-cyan bg-cyan px-4 py-2 text-sm font-bold text-ink focus:outline-none focus:ring-2 focus:ring-cyan"
            data-testid="timeline-tab"
          >
            Chronologie
          </button>
        </div>
        <p className="text-xs text-teal">{SKIPPED_TABS_NOTE}</p>
      </div>

      <ol className="space-y-3" data-testid="timeline-entries">
        {entries.map((entry) => (
          <li
            key={entry.id}
            className="grid gap-3 rounded-lg border border-deep bg-deep/10 p-4 md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]"
            data-testid="timeline-event-row"
          >
            <time
              dateTime={entry.sortKey}
              className="font-mono text-sm text-teal"
              data-testid="timeline-event-date"
            >
              {entry.timestampLabel}
            </time>

            <div className="space-y-2">
              <button
                type="button"
                onClick={(event) => onOpenSource(entry, event.currentTarget)}
                title="Ouvrir le panneau d’inspection de la source"
                className="block w-full rounded text-left text-sm font-semibold text-mist hover:text-cyan focus:outline-none focus:ring-2 focus:ring-cyan"
                data-testid="timeline-event-open"
              >
                <span data-testid="timeline-event-summary">{entry.summaryLabel}</span>
              </button>

              <button
                type="button"
                onClick={(event) => onOpenSource(entry, event.currentTarget)}
                title="Ouvrir le panneau d’inspection de la source"
                className="inline-flex max-w-full items-center gap-2 rounded-full border border-teal bg-deep px-3 py-1 text-xs text-mist hover:text-cyan focus:outline-none focus:ring-2 focus:ring-cyan"
                data-testid="timeline-source-chip"
              >
                <span className="truncate" data-testid="timeline-source-label">
                  {entry.sourceLabel}
                </span>
              </button>
            </div>
          </li>
        ))}
      </ol>

      <div
        className="flex items-center gap-2 rounded-lg border border-deep bg-deep/10 p-3 text-xs text-teal"
        role="status"
        data-testid="source-panel-placeholder"
      >
        <MousePointerClick className="h-4 w-4 flex-shrink-0 text-cyan" aria-hidden="true" />
        {SOURCE_PANEL_OPEN_NOTE}
      </div>

      <nav
        className="flex flex-wrap items-center justify-between gap-3 border-t border-deep pt-4"
        aria-label="Pagination serveur de la chronologie"
        data-testid="timeline-pagination"
      >
        <p className="text-xs text-teal" data-testid="timeline-page-label">
          Bloc {page} — {TIMELINE_PAGE_SIZE} événements maximum par bloc (DP-01)
        </p>
        <div className="flex gap-3">
          <button
            type="button"
            onClick={onPrevious}
            disabled={page <= 1 || isFetching}
            className="inline-flex items-center gap-1.5 rounded border border-teal bg-deep px-3 py-1.5 text-xs font-semibold text-mist hover:bg-deep/80 focus:outline-none focus:ring-2 focus:ring-cyan disabled:cursor-not-allowed disabled:opacity-60"
            data-testid="timeline-previous-block"
          >
            <ChevronLeft className="h-4 w-4 text-cyan" aria-hidden="true" />
            Bloc précédent
          </button>
          <button
            type="button"
            onClick={onNext}
            disabled={!hasMore || isFetching}
            className="inline-flex items-center gap-1.5 rounded border border-cyan bg-cyan px-3 py-1.5 text-xs font-bold text-ink hover:bg-cyan/80 focus:outline-none focus:ring-2 focus:ring-cyan disabled:cursor-not-allowed disabled:opacity-60"
            data-testid="timeline-next-block"
          >
            Charger les 100 suivants
            <ChevronRight className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </nav>
    </section>
  )
}
