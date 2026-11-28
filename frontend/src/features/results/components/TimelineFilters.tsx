import { useEffect, useState, type FormEvent } from 'react'
import { Filter, RotateCcw } from 'lucide-react'
import { FILTER_REALIGNMENT_NOTE } from '../constants'
import type { TimelineFilters } from '../types'

export interface TimelineFiltersBarProps {
  readonly value: TimelineFilters
  readonly disabled?: boolean
  readonly isFetching?: boolean
  readonly onApply: (filters: TimelineFilters) => void
  readonly onReset: () => void
}

/** Filtres transmis au serveur : source (source_id) et plage UTC (start_date/end_date). */
export function TimelineFiltersBar({
  value,
  disabled = false,
  isFetching = false,
  onApply,
  onReset,
}: TimelineFiltersBarProps) {
  const [draft, setDraft] = useState<TimelineFilters>(value)

  useEffect(() => {
    setDraft(value)
  }, [value])

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    onApply(draft)
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-3 rounded-lg border border-deep bg-deep/10 p-4"
      aria-labelledby="timeline-filters-heading"
      data-testid="timeline-filters"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2
          id="timeline-filters-heading"
          className="flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-mist"
        >
          <Filter className="h-4 w-4 text-cyan" aria-hidden="true" />
          Filtres de la chronologie
        </h2>
        <p className="text-xs text-teal">{FILTER_REALIGNMENT_NOTE}</p>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <label className="space-y-1 text-xs text-teal">
          <span>Source (identifiant)</span>
          <input
            type="text"
            value={draft.sourceId}
            onChange={(event) => setDraft({ ...draft, sourceId: event.target.value })}
            disabled={disabled}
            className="w-full rounded border border-deep bg-ink px-3 py-2 text-sm text-mist focus:outline-none focus:ring-2 focus:ring-cyan disabled:opacity-60"
            data-testid="timeline-source-filter"
          />
        </label>
        <label className="space-y-1 text-xs text-teal">
          <span>Début UTC</span>
          <input
            type="datetime-local"
            value={draft.startDate}
            onChange={(event) => setDraft({ ...draft, startDate: event.target.value })}
            disabled={disabled}
            className="w-full rounded border border-deep bg-ink px-3 py-2 font-mono text-sm text-mist focus:outline-none focus:ring-2 focus:ring-cyan disabled:opacity-60"
            data-testid="timeline-start-filter"
          />
        </label>
        <label className="space-y-1 text-xs text-teal">
          <span>Fin UTC</span>
          <input
            type="datetime-local"
            value={draft.endDate}
            onChange={(event) => setDraft({ ...draft, endDate: event.target.value })}
            disabled={disabled}
            className="w-full rounded border border-deep bg-ink px-3 py-2 font-mono text-sm text-mist focus:outline-none focus:ring-2 focus:ring-cyan disabled:opacity-60"
            data-testid="timeline-end-filter"
          />
        </label>
      </div>

      <div className="flex flex-wrap gap-3">
        <button
          type="submit"
          disabled={disabled || isFetching}
          className="rounded border border-cyan bg-cyan px-4 py-2 text-sm font-bold text-ink hover:bg-cyan/80 focus:outline-none focus:ring-2 focus:ring-cyan disabled:cursor-not-allowed disabled:opacity-60"
          data-testid="timeline-apply-filters"
        >
          Appliquer les filtres
        </button>
        <button
          type="button"
          onClick={onReset}
          disabled={disabled || isFetching}
          className="inline-flex items-center gap-1.5 rounded border border-teal bg-deep px-4 py-2 text-sm font-semibold text-mist hover:bg-deep/80 focus:outline-none focus:ring-2 focus:ring-cyan disabled:cursor-not-allowed disabled:opacity-60"
          data-testid="timeline-reset-filters"
        >
          <RotateCcw className="h-4 w-4 text-cyan" aria-hidden="true" />
          Réinitialiser les filtres
        </button>
      </div>
    </form>
  )
}
