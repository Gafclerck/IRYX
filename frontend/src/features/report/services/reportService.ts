import createClient from 'openapi-fetch'
import { authMiddleware } from '../../../api/client'
import { ADR0008_POLLING_DEFAULT_INTERVAL_SECONDS } from '../../plan/constants'
import type { ReportDocument, ReportErrorPayload, ReportPaths, ReportTask } from '../types'

/**
 * Client dédié aux routes simulées de rapport (Story F5.1, RÈGLE CONTRAT).
 *
 * Ces routes sont absentes de `docs/contrat/openapi.json`. Elles sont déclarées
 * localement avec les seuls champs décrits par ADR-0004 (format markdown/json)
 * et ADR-0008 (tâche asynchrone uniforme), puis marquées « simulée, contrat
 * cible » dans docs/frontend/14. Le middleware d'authentification est partagé
 * avec le client contractuel : jeton en mémoire vive, 401 et renouvellement
 * silencieux, sans localStorage ni sessionStorage.
 */
const reportClient = createClient<ReportPaths>({
  baseUrl:
    typeof window !== 'undefined' && window.location?.origin
      ? window.location.origin
      : 'http://localhost',
  fetch: (input: Request): Promise<Response> => globalThis.fetch(input),
})

reportClient.use(authMiddleware)

/** Erreur d'API de rapport : le code HTTP et le motif serveur sont conservés tels quels. */
export class ReportApiError extends Error {
  readonly status: number
  readonly detail: string | null
  readonly code: string | null
  readonly retryAfterSeconds: number | null

  constructor(
    message: string,
    status = 0,
    detail: string | null = null,
    code: string | null = null,
    retryAfterSeconds: number | null = null,
  ) {
    super(message)
    this.name = 'ReportApiError'
    this.status = status
    this.detail = detail
    this.code = code
    this.retryAfterSeconds = retryAfterSeconds
  }
}

function readErrorPayload(error: unknown): ReportErrorPayload {
  if (error && typeof error === 'object') return error as ReportErrorPayload
  return {}
}

function readDetail(error: unknown, fallback: string): string {
  const payload = readErrorPayload(error)
  return payload.error_message?.trim() || payload.detail?.trim() || fallback
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

function toReportApiError(err: unknown, fallback: string): ReportApiError {
  if (err instanceof ReportApiError) return err
  return new ReportApiError(fallback, 0)
}

/**
 * Rapport courant du dossier.
 * Route simulée : GET /api/v1/cases/{case_id}/report.
 * Un 404 signifie « aucun rapport finalisé » et n'est pas une erreur technique.
 */
export async function getReport(
  caseId: string,
): Promise<{ document: ReportDocument | null; retryAfterSeconds: number }> {
  try {
    const { data, response, error } = await reportClient.GET('/api/v1/cases/{case_id}/report', {
      params: { path: { case_id: caseId } },
    })

    if (response.status === 404) {
      return { document: null, retryAfterSeconds: resolveRetryAfter(response) }
    }
    if (response.status === 403) {
      throw new ReportApiError("Accès refusé. Vous n'avez pas accès au rapport de ce dossier.", 403)
    }
    if (response.status === 401) {
      throw new ReportApiError('Session expirée lors de la consultation du rapport.', 401)
    }
    if (!response.ok || error) {
      throw new ReportApiError(
        readDetail(error, 'Échec de la consultation du rapport.'),
        response.status,
      )
    }
    if (!data) {
      throw new ReportApiError('Rapport indisponible.', 500)
    }

    return { document: data, retryAfterSeconds: resolveRetryAfter(response) }
  } catch (err) {
    throw toReportApiError(err, 'Serveur injoignable. Veuillez vérifier votre connexion.')
  }
}

/**
 * Demande de compilation au back-end (DP-03 : aucun assemblage côté front).
 * Route simulée : POST /api/v1/cases/{case_id}/report/generate.
 * La réponse 202 et l'en-tête Retry-After suivent ADR-0008.
 */
export async function generateReport(
  caseId: string,
): Promise<{ task: ReportTask; retryAfterSeconds: number }> {
  try {
    const { data, response, error } = await reportClient.POST(
      '/api/v1/cases/{case_id}/report/generate',
      { params: { path: { case_id: caseId } } },
    )

    if (response.status === 403) {
      throw new ReportApiError(
        "Accès refusé. Vous n'avez pas les autorisations nécessaires pour compiler ce rapport.",
        403,
      )
    }
    if (response.status === 401) {
      throw new ReportApiError('Session expirée lors de la demande de compilation.', 401)
    }
    if (!response.ok || error) {
      throw new ReportApiError(
        readDetail(error, 'Échec de la demande de compilation du rapport.'),
        response.status,
      )
    }
    if (!data) {
      throw new ReportApiError('Tâche de compilation indisponible.', 500)
    }

    return { task: data, retryAfterSeconds: resolveRetryAfter(response) }
  } catch (err) {
    throw toReportApiError(err, 'Serveur injoignable. Veuillez vérifier votre connexion.')
  }
}

/**
 * Suivi de la tâche asynchrone de compilation (ADR-0008, DP-05).
 * Route simulée : GET /api/v1/cases/{case_id}/tasks/{task_id}.
 */
export async function getReportTask(
  caseId: string,
  taskId: string,
): Promise<{ task: ReportTask; retryAfterSeconds: number }> {
  try {
    const { data, response, error } = await reportClient.GET(
      '/api/v1/cases/{case_id}/tasks/{task_id}',
      { params: { path: { case_id: caseId, task_id: taskId } } },
    )

    if (response.status === 403) {
      throw new ReportApiError("Accès refusé. Vous n'avez pas accès à cette tâche.", 403)
    }
    if (response.status === 401) {
      throw new ReportApiError('Session expirée lors du suivi de la compilation.', 401)
    }
    if (!response.ok || error) {
      throw new ReportApiError(
        readDetail(error, 'Échec du suivi de la compilation.'),
        response.status,
      )
    }
    if (!data) {
      throw new ReportApiError('État de compilation indisponible.', 500)
    }

    return { task: data, retryAfterSeconds: resolveRetryAfter(response) }
  } catch (err) {
    throw toReportApiError(err, 'Serveur injoignable. Veuillez vérifier votre connexion.')
  }
}

/** Détail du motif d'échec renvoyé par le back, sans valeur inventée. */
export function readGenerationFailureMessage(task: ReportTask & ReportErrorPayload): string {
  return readDetail(task, '')
}
