import type { components } from '../../api/schema'

/** Types strictement dérivés du contrat OpenAPI (docs/contrat/openapi.json). */
export type ObservationRead = components['schemas']['ObservationRead']
export type ObservationListResponse = components['schemas']['ObservationListResponse']
export type InvestigationRunOut = components['schemas']['InvestigationRunOut']

export interface TimelineFilters {
  readonly sourceId: string
  readonly startDate: string
  readonly endDate: string
}

export const EMPTY_TIMELINE_FILTERS: TimelineFilters = {
  sourceId: '',
  startDate: '',
  endDate: '',
}

export type TimelineViewState = 'loading' | 'success' | 'empty' | 'error' | 'forbidden'

export interface TimelineEntry {
  readonly id: string
  /** Horodatage contractuel utilisé pour le tri UTC (jamais le fuseau local). */
  readonly sortKey: string
  readonly timestampLabel: string
  readonly summaryLabel: string
  readonly sourceLabel: string
  readonly fileNameLabel: string
  readonly eventIdLabel: string
  readonly lineLabel: string
}

export interface ResultsStatusInfo {
  readonly statusLabel: string | null
  readonly isUnknown: boolean
  readonly failedPhases: readonly string[]
}
