import { apiClient } from '../../../api/client'
import { ADR0008_POLLING_DEFAULT_INTERVAL_SECONDS } from '../../plan/constants'
import { CANCEL_REALIGNMENT_NOTE } from '../constants'
import type { InvestigationRunOut } from '../types'

/**
 * Erreur de la console de supervision (Story F4.3). Le code HTTP et l'en-tête
 * Retry-After sont conservés pour respecter l'ADR-0008 sans inventer de statut.
 */
export class RunApiError extends Error {
  readonly status: number
  readonly retryAfterSeconds: number | null

  constructor(message: string, status: number = 0, retryAfterSeconds: number | null = null) {
    super(message)
    this.name = 'RunApiError'
    this.status = status
    this.retryAfterSeconds = retryAfterSeconds
  }
}

interface ApiErrorPayload {
  readonly detail?: unknown
  readonly [key: string]: unknown
}

function readErrorPayload(error: unknown): ApiErrorPayload {
  return error && typeof error === 'object' ? (error as ApiErrorPayload) : {}
}

function readDetail(error: unknown, fallback: string): string {
  const detail = readErrorPayload(error).detail
  return typeof detail === 'string' && detail.trim() ? detail : fallback
}

function readRetryAfter(response: Response): number | null {
  const header = response.headers?.get('Retry-After')
  if (!header) return null
  const parsed = parseInt(header, 10)
  return !Number.isNaN(parsed) && parsed > 0 ? parsed : null
}

function resolveRetryAfter(response: Response): number {
  return readRetryAfter(response) ?? ADR0008_POLLING_DEFAULT_INTERVAL_SECONDS
}

/**
 * Consultation d'une session d'investigation.
 * Route cible : GET /api/v1/cases/{case_id}/investigations/{run_id} (openapi.json).
 */
export async function getInvestigationRun(
  caseId: string,
  runId: string,
): Promise<{ data: InvestigationRunOut; retryAfterSeconds: number }> {
  try {
    const { data, response, error } = await apiClient.GET(
      '/api/v1/cases/{case_id}/investigations/{run_id}',
      { params: { path: { case_id: caseId, run_id: runId } } },
    )

    if (response.status === 403) {
      throw new RunApiError("Accès refusé. Vous n'avez pas accès à cette session.", 403)
    }
    if (response.status === 401) {
      throw new RunApiError('Session expirée lors de la consultation de la session.', 401)
    }
    if (!response.ok || error) {
      throw new RunApiError(
        readDetail(error, 'Échec de la récupération de la session d’investigation.'),
        response.status,
      )
    }
    if (!data) {
      throw new RunApiError('Session d’investigation indisponible.', 500)
    }

    return { data: data as InvestigationRunOut, retryAfterSeconds: resolveRetryAfter(response) }
  } catch (err) {
    if (err instanceof RunApiError) throw err
    throw new RunApiError('Serveur injoignable. Veuillez vérifier votre connexion.', 0)
  }
}

/**
 * Reprise d'une session en pause.
 * Route cible : POST /api/v1/cases/{case_id}/investigations/{run_id}/resume (openapi.json).
 * Aucun corps de requête : `requestBody` vaut `never` dans le contrat.
 */
export async function resumeInvestigation(
  caseId: string,
  runId: string,
): Promise<InvestigationRunOut> {
  try {
    const { data, response, error } = await apiClient.POST(
      '/api/v1/cases/{case_id}/investigations/{run_id}/resume',
      { params: { path: { case_id: caseId, run_id: runId } } },
    )

    if (response.status === 403) {
      throw new RunApiError(
        "Accès refusé. Vous n'avez pas les autorisations nécessaires pour reprendre la session.",
        403,
      )
    }
    if (response.status === 401) {
      throw new RunApiError('Session expirée lors de la reprise de la session.', 401)
    }
    if (!response.ok || error) {
      throw new RunApiError(
        readDetail(error, 'La reprise de la session a été refusée.'),
        response.status,
      )
    }
    if (!data) {
      throw new RunApiError('Réponse de reprise indisponible.', 500)
    }

    return data as InvestigationRunOut
  } catch (err) {
    if (err instanceof RunApiError) throw err
    throw new RunApiError('Serveur injoignable. Veuillez vérifier votre connexion.', 0)
  }
}

/**
 * Aucune route d'annulation n'est déclarée dans `openapi.json` (seule la reprise
 * existe). Aucune requête n'est donc émise : la demande reste « à réaligner ».
 */
export async function cancelInvestigation(): Promise<never> {
  throw new RunApiError(CANCEL_REALIGNMENT_NOTE, 0)
}
