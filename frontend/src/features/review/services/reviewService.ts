import { apiClient } from '../../../api/client'
import { ADR0008_POLLING_DEFAULT_INTERVAL_SECONDS } from '../../plan/constants'
import type { FindingListResponse, FindingOut } from '../types'

/** Erreur API revue H2 : conserve code HTTP et détail serveur tels quels. */
export class ReviewApiError extends Error {
  readonly status: number
  readonly detail: string | null
  readonly retryAfterSeconds: number | null
  readonly finding: FindingOut | null

  constructor(
    message: string,
    status = 0,
    detail: string | null = null,
    retryAfterSeconds: number | null = null,
    finding: FindingOut | null = null,
  ) {
    super(message)
    this.name = 'ReviewApiError'
    this.status = status
    this.detail = detail
    this.retryAfterSeconds = retryAfterSeconds
    this.finding = finding
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

function readRetryAfter(response: Response): number | null {
  const header = response.headers?.get('Retry-After')
  if (!header) return null
  const seconds = parseInt(header, 10)
  return Number.isNaN(seconds) || seconds <= 0 ? null : seconds
}

function resolveRetryAfter(response: Response): number {
  return readRetryAfter(response) ?? ADR0008_POLLING_DEFAULT_INTERVAL_SECONDS
}

function toReviewApiError(err: unknown, fallback: string): ReviewApiError {
  if (err instanceof ReviewApiError) return err
  return new ReviewApiError(fallback, 0)
}

/**
 * Liste des findings d'un dossier (contrat openapi.json).
 * GET /api/v1/cases/{case_id}/findings
 */
export async function getFindings(
  caseId: string,
): Promise<{ data: FindingListResponse; retryAfterSeconds: number }> {
  try {
    const { data, response, error } = await apiClient.GET('/api/v1/cases/{case_id}/findings', {
      params: { path: { case_id: caseId }, query: { limit: 100, offset: 0 } },
    })

    if (response.status === 403) {
      throw new ReviewApiError("Accès refusé. Vous n'avez pas accès à cette revue.", 403)
    }
    if (response.status === 401) {
      throw new ReviewApiError('Session expirée lors de la consultation des findings.', 401)
    }
    if (!response.ok || error) {
      throw new ReviewApiError(
        readDetail(error, 'Échec de la récupération des findings.'),
        response.status,
      )
    }
    if (!data) {
      throw new ReviewApiError('Findings indisponibles.', 500)
    }

    return { data, retryAfterSeconds: resolveRetryAfter(response) }
  } catch (err) {
    throw toReviewApiError(err, 'Serveur injoignable. Veuillez vérifier votre connexion.')
  }
}

/**
 * Route de décision H2 absente du contrat openapi.json (E6).
 * Cette fonction ne doit PAS être appelée tant qu'aucune route contractuelle
 * n'existe. Elle est gardée comme point d'alignement explicite.
 */
export async function submitFindingDecision(): Promise<never> {
  throw new ReviewApiError(
    'Route de décision absente du contrat : action désactivée, à réaligner (E6).',
    501,
  )
}
