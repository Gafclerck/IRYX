import { apiClient } from '../../../api/client'
import { ADR0008_POLLING_DEFAULT_INTERVAL_SECONDS, PLAN_NOT_FOUND_CODE } from '../constants'
import type { InvestigationPlan, InvestigationRunOut } from '../types'

/**
 * Erreur spécifique à la consultation du plan d'investigation (Story F4.1).
 * Le code HTTP et le code métier éventuel sont conservés pour piloter l'état
 * « planification en cours » sans inventer de statut côté client.
 */
export class PlanApiError extends Error {
  readonly status: number
  readonly code: string | null
  readonly retryAfterSeconds: number | null

  constructor(
    message: string,
    status: number = 0,
    code: string | null = null,
    retryAfterSeconds: number | null = null,
  ) {
    super(message)
    this.name = 'PlanApiError'
    this.status = status
    this.code = code
    this.retryAfterSeconds = retryAfterSeconds
  }
}

interface ApiErrorPayload {
  readonly detail?: unknown
  readonly code?: unknown
}

function readErrorPayload(error: unknown): ApiErrorPayload {
  if (error && typeof error === 'object') {
    return error as ApiErrorPayload
  }
  return {}
}

function readDetail(error: unknown, fallback: string): string {
  const detail = readErrorPayload(error).detail
  return typeof detail === 'string' && detail.trim() ? detail : fallback
}

function readCode(error: unknown): string | null {
  const code = readErrorPayload(error).code
  return typeof code === 'string' && code.trim() ? code : null
}

/**
 * Lecture de l'en-tête standard Retry-After (ADR-0008, Option A : 3 secondes).
 */
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
 * Liste des sessions d'investigation d'un dossier.
 * Route cible : GET /api/v1/cases/{case_id}/investigations (contrat openapi.json).
 */
export async function getInvestigationRuns(
  caseId: string,
): Promise<{ data: InvestigationRunOut[]; retryAfterSeconds: number }> {
  try {
    const { data, response, error } = await apiClient.GET(
      '/api/v1/cases/{case_id}/investigations',
      {
        params: { path: { case_id: caseId } },
      },
    )

    if (response.status === 403) {
      throw new PlanApiError("Accès refusé. Vous n'avez pas accès à ce dossier.", 403)
    }
    if (response.status === 401) {
      throw new PlanApiError('Session expirée lors de la consultation des investigations.', 401)
    }
    if (!response.ok || error) {
      throw new PlanApiError(
        readDetail(error, 'Échec de la récupération des sessions d’investigation.'),
        response.status,
      )
    }
    if (!data) {
      throw new PlanApiError('Sessions d’investigation indisponibles.', 500)
    }

    return { data: data as InvestigationRunOut[], retryAfterSeconds: resolveRetryAfter(response) }
  } catch (err) {
    if (err instanceof PlanApiError) throw err
    throw new PlanApiError('Serveur injoignable. Veuillez vérifier votre connexion.', 0)
  }
}

/**
 * Plan proposé par le Planner pour une session d'investigation.
 * Route cible : GET /api/v1/cases/{case_id}/investigations/{run_id}/plan (contrat openapi.json).
 *
 * Un code 404 PLAN_NOT_FOUND signifie que le plan est encore en cours d'élaboration :
 * l'état d'attente est pilote par l'en-tête Retry-After conformément à l'ADR-0008.
 */
export async function getInvestigationPlan(
  caseId: string,
  runId: string,
): Promise<{ data: InvestigationPlan; retryAfterSeconds: number }> {
  try {
    const { data, response, error } = await apiClient.GET(
      '/api/v1/cases/{case_id}/investigations/{run_id}/plan',
      {
        params: { path: { case_id: caseId, run_id: runId } },
      },
    )

    if (response.status === 404) {
      const code = readCode(error) ?? PLAN_NOT_FOUND_CODE
      throw new PlanApiError(
        code === PLAN_NOT_FOUND_CODE
          ? 'Le plan est en cours d’élaboration par le Planner.'
          : readDetail(error, 'Plan introuvable pour cette session.'),
        404,
        code,
        resolveRetryAfter(response),
      )
    }
    if (response.status === 403) {
      throw new PlanApiError("Accès refusé. Vous n'avez pas accès à ce plan.", 403)
    }
    if (response.status === 401) {
      throw new PlanApiError('Session expirée lors de la consultation du plan.', 401)
    }
    if (!response.ok || error) {
      throw new PlanApiError(
        readDetail(error, 'Échec de l’agent Planner lors de l’élaboration du plan.'),
        response.status,
      )
    }
    if (!data) {
      throw new PlanApiError('Plan indisponible pour cette session.', 500)
    }

    return { data: data as InvestigationPlan, retryAfterSeconds: resolveRetryAfter(response) }
  } catch (err) {
    if (err instanceof PlanApiError) throw err
    throw new PlanApiError('Serveur injoignable. Veuillez vérifier votre connexion.', 0)
  }
}
