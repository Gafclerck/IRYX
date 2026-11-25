import { apiClient } from '../../../api/client'
import type {
  EvidenceListResponse,
  EvidenceIngestionStatusResponse,
} from '../types'
import {
  ADR0008_POLLING_DEFAULT_INTERVAL_SECONDS,
} from '../constants'

/**
 * Erreur spécifique liée à l'inventaire et au suivi des preuves.
 */
export class EvidenceApiError extends Error {
  readonly status: number

  constructor(message: string, status: number = 0) {
    super(message)
    this.name = 'EvidenceApiError'
    this.status = status
  }
}

/**
 * Récupère l'inventaire des preuves d'un dossier.
 * Route cible : GET /api/v1/cases/{case_id}/evidences
 * Contrat : openapi.json
 */
export async function getEvidences(
  caseId: string,
  params: { limit?: number; offset?: number } = {},
): Promise<EvidenceListResponse> {
  const limit = params.limit ?? 50
  const offset = params.offset ?? 0

  const { data, response, error } = await apiClient.GET(
    '/api/v1/cases/{case_id}/evidences',
    {
      params: {
        path: { case_id: caseId },
        query: { limit, offset } as never,
      },
    },
  )

  if (response.status === 403) {
    throw new EvidenceApiError(
      "Accès refusé. Vous n'avez pas accès aux preuves de ce dossier.",
      403,
    )
  }

  if (!response.ok || error) {
    const detail =
      (error as { detail?: string })?.detail ||
      'Échec de la récupération des preuves du dossier.'
    throw new EvidenceApiError(detail, response.status)
  }

  if (!data) {
    const status = (response as unknown as { status?: number })?.status || 500
    throw new EvidenceApiError('Données de preuves indisponibles.', status)
  }

  return data as EvidenceListResponse
}

/**
 * Interroge l'état d'ingestion d'une preuve spécifique avec extraction du Retry-After (ADR-0008).
 * Route cible : GET /api/v1/cases/{case_id}/evidences/{evidence_id}/ingestion-status
 * Contrat : openapi.json
 */
export async function getEvidenceIngestionStatus(
  caseId: string,
  evidenceId: string,
): Promise<{ data: EvidenceIngestionStatusResponse; retryAfterSeconds: number }> {
  const { data, response, error } = await apiClient.GET(
    '/api/v1/cases/{case_id}/evidences/{evidence_id}/ingestion-status',
    {
      params: {
        path: { case_id: caseId, evidence_id: evidenceId },
      },
    },
  )

  if (response.status === 403) {
    throw new EvidenceApiError(
      "Accès refusé lors de la vérification d'ingestion.",
      403,
    )
  }

  if (response.status === 401) {
    throw new EvidenceApiError(
      'Session expirée lors de la vérification.',
      401,
    )
  }

  if (!response.ok || error) {
    const detail =
      (error as { detail?: string })?.detail ||
      "Échec de l'interrogation du statut d'ingestion."
    throw new EvidenceApiError(detail, response.status)
  }

  if (!data) {
    const status = (response as unknown as { status?: number })?.status || 500
    throw new EvidenceApiError("Statut d'ingestion introuvable.", status)
  }

  // Lecture de l'en-tête standard Retry-After conformément à ADR-0008
  const retryAfterHeader = (response as unknown as Response).headers?.get('Retry-After')
  let retryAfterSeconds = ADR0008_POLLING_DEFAULT_INTERVAL_SECONDS
  if (retryAfterHeader) {
    const parsed = parseInt(retryAfterHeader, 10)
    if (!isNaN(parsed) && parsed > 0) {
      retryAfterSeconds = parsed
    }
  }

  return {
    data: data as EvidenceIngestionStatusResponse,
    retryAfterSeconds,
  }
}
