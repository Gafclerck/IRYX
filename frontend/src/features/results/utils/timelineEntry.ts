import { formatUtcDateTime } from '../../../lib/date'
import { TO_REALIGN } from '../constants'
import type { ObservationRead, TimelineEntry } from '../types'

function readText(value: unknown): string | null {
  if (typeof value === 'string' && value.trim()) return value.trim()
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return null
}

/**
 * Le contrat ne définit pas de champs dédiés au fichier, à l'identifiant
 * d'événement et à la ligne : ces valeurs sont lues dans `normalized_content`
 * (propriétés libres autorisées par openapi.json) et dans `source_location`.
 * Toute absence est signalée « à réaligner » plutôt qu'inventée.
 */
function readSourceLine(sourceLocation: string | null | undefined): string | null {
  if (!sourceLocation) return null
  const segments = sourceLocation.split(':')
  const candidate = segments[segments.length - 1]
  return candidate && /^\d+$/.test(candidate) ? candidate : null
}

export function toTimelineEntry(observation: ObservationRead): TimelineEntry {
  const content = observation.normalized_content ?? {}
  const sourceLocation = observation.source_location

  const fileNameLabel =
    readText(content.file_name) ?? readText(content.file) ?? sourceLocation ?? TO_REALIGN
  const eventIdLabel = readText(content.event_id) ?? observation.id
  const lineLabel = readText(content.line) ?? readSourceLine(sourceLocation) ?? TO_REALIGN
  const summaryLabel =
    readText(content.summary) ??
    readText(content.description) ??
    readText(content.message) ??
    `${observation.tool_name} — ${TO_REALIGN}`

  const sortKey = observation.timestamp_utc ?? observation.created_at
  const timestampLabel = observation.timestamp_utc
    ? formatUtcDateTime(observation.timestamp_utc)
    : `${TO_REALIGN} (horodatage absent)`

  return {
    id: observation.id,
    sortKey,
    timestampLabel,
    summaryLabel,
    sourceLabel: `${fileNameLabel} · ${eventIdLabel} · ligne ${lineLabel}`,
    fileNameLabel,
    eventIdLabel,
    lineLabel,
  }
}

/** Tri UTC du bloc reçu : aucun filtrage ni chargement complémentaire côté client. */
export function buildTimelineEntries(items: readonly ObservationRead[]): readonly TimelineEntry[] {
  return items.map(toTimelineEntry).sort((a, b) => a.sortKey.localeCompare(b.sortKey))
}
