import { apiClient } from '../../../api/client'
import { TIMELINE_PAGE_SIZE } from '../constants'
import type { ObservationListResponse, TimelineFilters } from '../types'

/** Erreur de la chronologie : le code HTTP est conservé pour piloter l'état 403. */
export class TimelineApiError extends Error {
  readonly status: number

  constructor(message: string, status: number = 0) {
    super(message)
    this.name = 'TimelineApiError'
    this.status = status
  }
}

interface ApiErrorPayload {
  readonly detail?: unknown
  readonly [key: string]: unknown
}

function readDetail(error: unknown, fallback: string): string {
  if (!error || typeof error !== 'object') return fallback
  const detail = (error as ApiErrorPayload).detail
  return typeof detail === 'string' && detail.trim() ? detail : fallback
}

/**
 * Convertit une saisie `datetime-local` en horodatage ISO UTC sans interpréter
 * le fuseau horaire du navigateur. Aucune valeur par défaut n'est inventée.
 */
export function toUtcQuery(value: string): string | undefined {
  const trimmed = value.trim()
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(trimmed)) return `${trimmed}:00Z`
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(trimmed)) return `${trimmed}Z`
  return undefined
}

export interface TimelineBlockRequest {
  readonly caseId: string
  readonly offset: number
  readonly filters: TimelineFilters
}

/**
 * Récupère un seul bloc de 100 observations (DP-01).
 * Route cible : GET /api/v1/cases/{case_id}/observations (openapi.json).
 * Les filtres sont transmis au serveur : aucun filtrage client sur un bloc partiel.
 */
export async function getTimelineBlock({
  caseId,
  offset,
  filters,
}: TimelineBlockRequest): Promise<ObservationListResponse> {
  try {
    const { data, response, error } = await apiClient.GET('/api/v1/cases/{case_id}/observations', {
      params: {
        path: { case_id: caseId },
        query: {
          limit: TIMELINE_PAGE_SIZE,
          offset,
          source_id: filters.sourceId.trim() || undefined,
          start_date: toUtcQuery(filters.startDate),
          end_date: toUtcQuery(filters.endDate),
        },
      },
    })

    if (response.status === 403) {
      throw new TimelineApiError("Accès refusé. Vous n'avez pas accès à cette chronologie.", 403)
    }
    if (response.status === 401) {
      throw new TimelineApiError('Session expirée lors de la consultation de la chronologie.', 401)
    }
    if (!response.ok || error) {
      throw new TimelineApiError(
        readDetail(error, 'Échec de la récupération de la chronologie.'),
        response.status,
      )
    }
    if (!data) {
      throw new TimelineApiError('Chronologie indisponible.', 500)
    }

    // Garde-fou DP-01 : jamais plus d'un bloc de 100 événements ne peut être affiché.
    return {
      ...data,
      items: data.items.slice(0, TIMELINE_PAGE_SIZE),
      limit: Math.min(data.limit, TIMELINE_PAGE_SIZE),
    }
  } catch (err) {
    if (err instanceof TimelineApiError) throw err
    throw new TimelineApiError('Serveur injoignable. Veuillez vérifier votre connexion.', 0)
  }
}
