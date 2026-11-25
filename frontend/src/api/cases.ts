import { apiClient } from './client'
import type {
  CaseListResponse,
  GetCasesParams,
  CaseItem,
  CreateCasePayload,
  CreateCaseResponse,
  CaseDetail,
  UpdateCasePayload,
} from './cases-types'
import { DEFAULT_PAGE_SIZE } from './cases-types'

/**
 * Erreur spécifique liée à la consultation des dossiers.
 */
export class CasesError extends Error {
  readonly status: number

  constructor(message: string, status: number = 0) {
    super(message)
    this.name = 'CasesError'
    this.status = status
  }
}

/**
 * Erreur spécifique survenue lors de la création d'un dossier d'investigation (Story F1.7).
 * Conserve les erreurs par champ transmises par le serveur (400 / 422).
 */
export class CaseCreationError extends CasesError {
  readonly fieldErrors?: Record<string, string>

  constructor(message: string, status: number = 0, fieldErrors?: Record<string, string>) {
    super(message, status)
    this.name = 'CaseCreationError'
    this.fieldErrors = fieldErrors
  }
}

/**
 * Récupération paginée des dossiers d'investigation avec filtrage serveur par titre (Story F1.6).
 * Route cible : GET /api/v1/cases
 * Contrat cible : openapi.json (simulée E2)
 *
 * RÈGLES DE CONCEPTION :
 * 1. Pagination côté serveur stricte : le front transmet la page et la taille demandées.
 *    Il ne charge jamais la liste complète côté client.
 * 2. Filtrage par titre transmis au serveur via le paramètre de recherche.
 * 3. En cas d'erreur HTTP 403 Forbidden : lève une CasesError avec statut 403.
 * 4. En cas d'erreur HTTP 5xx : lève une CasesError avec le statut correspondant.
 */
export async function getCases(params: GetCasesParams = {}): Promise<CaseListResponse> {
  const limit = params.limit ?? DEFAULT_PAGE_SIZE
  const page = params.page && params.page > 0 ? params.page : 1
  const offset = params.offset !== undefined ? params.offset : (page - 1) * limit
  const search = params.search?.trim() || undefined

  const { data, response, error } = await apiClient.GET('/api/v1/cases', {
    params: {
      query: {
        limit,
        offset,
        ...(search ? { search } : {}),
      } as never,
    },
  })

  if (response.status === 403) {
    throw new CasesError(
      "Accès refusé. Vous n'avez pas accès aux dossiers de cette organisation. Veuillez contacter votre administrateur.",
      403,
    )
  }

  if (!response.ok || error) {
    const detail =
      (error as { detail?: string })?.detail ||
      'Échec du chargement des dossiers. Veuillez réessayer ultérieurement.'
    throw new CasesError(detail, response.status)
  }

  if (!data) {
    const status = (response as unknown as { status?: number })?.status || 500
    throw new CasesError('Données de dossiers indisponibles.', status)
  }

  const rawItems = (data.items || []) as unknown as Array<Partial<CaseItem>>
  const items: CaseItem[] = rawItems.map((item) => ({
    id: item.id || '',
    organization_id: item.organization_id || '',
    title: item.title || '',
    description: item.description ?? null,
    status: (item.status || 'open') as CaseItem['status'],
    created_by: item.created_by ?? null,
    created_at: item.created_at || new Date().toISOString(),
    updated_at: item.updated_at || new Date().toISOString(),
    evidence_count: typeof item.evidence_count === 'number' ? item.evidence_count : 0,
  }))

  const total = data.total ?? data.total_items ?? items.length
  const totalItems = data.total_items ?? data.total ?? items.length
  const responseLimit = data.limit ?? limit
  const responseOffset = data.offset ?? offset
  const hasMore =
    typeof data.has_more === 'boolean' ? data.has_more : responseOffset + items.length < total

  return {
    items,
    total,
    total_items: totalItems,
    limit: responseLimit,
    offset: responseOffset,
    has_more: hasMore,
  }
}

/**
 * Création d'un nouveau dossier d'investigation via l'API (Story F1.7).
 * Route cible : POST /api/v1/cases
 * Contrat cible : openapi.json (simulée E2)
 *
 * RÈGLES DE CONCEPTION :
 * 1. Transmission de l'en-tête Authorization: Bearer par le client réseau (client.ts).
 * 2. En cas de 403 Forbidden : notification explicite d'interdiction sans navigation forcée.
 * 3. En cas de rejet 400/422 de validation serveur : renvoi des erreurs ciblées par champ.
 * 4. En cas d'erreur 5xx ou réseau : levée d'une erreur typée permettant le réessai.
 */
export async function createCase(payload: CreateCasePayload): Promise<CreateCaseResponse> {
  try {
    const postFn = apiClient.POST as unknown as (
      url: string,
      options: { body: unknown },
    ) => Promise<{ data?: unknown; response: Response; error?: unknown }>

    const { data, response, error } = await postFn('/api/v1/cases', {
      body: payload,
    })

    if (response.status === 403) {
      throw new CaseCreationError(
        "Vous n'avez pas les autorisations nécessaires pour créer un dossier dans cette organisation.",
        403,
      )
    }

    if (response.status === 400 || response.status === 422) {
      const err = error as unknown as {
        detail?: string | Array<{ loc?: string[]; msg?: string }>
        errors?: Record<string, string>
      } | null
      let message = 'Erreur de validation des données transmises.'
      const fieldErrors: Record<string, string> = {}

      if (err?.errors && typeof err.errors === 'object') {
        Object.assign(fieldErrors, err.errors)
      }

      if (Array.isArray(err?.detail)) {
        for (const item of err.detail) {
          if (item?.loc && Array.isArray(item.loc) && item.loc.length > 0) {
            const field = item.loc[item.loc.length - 1]
            if (field && item.msg) {
              fieldErrors[field] = item.msg
            }
          }
        }
      } else if (typeof err?.detail === 'string') {
        message = err.detail
      }

      throw new CaseCreationError(message, response.status, fieldErrors)
    }

    if (!response.ok || error) {
      const detail =
        (error as unknown as { detail?: string })?.detail ||
        'Erreur serveur lors de la création du dossier. Veuillez réessayer.'
      throw new CaseCreationError(detail, response.status)
    }

    if (!data) {
      throw new CaseCreationError('Réponse de création de dossier indisponible.', response.status)
    }

    const raw = data as unknown as Partial<CreateCaseResponse>
    return {
      id: raw.id || '',
      organization_id: raw.organization_id || '',
      title: raw.title || payload.title,
      description: raw.description ?? payload.description,
      status: (raw.status || 'open') as CaseItem['status'],
      created_by: raw.created_by ?? null,
      created_at: raw.created_at || new Date().toISOString(),
      updated_at: raw.updated_at || new Date().toISOString(),
      evidence_count: typeof raw.evidence_count === 'number' ? raw.evidence_count : 0,
      incident_date: raw.incident_date || payload.incident_date,
      incident_type: raw.incident_type || payload.incident_type,
      affected_systems: raw.affected_systems || payload.affected_systems,
    }
  } catch (err) {
    if (err instanceof CaseCreationError) {
      throw err
    }
    const message =
      err instanceof Error &&
      (err.name === 'TypeError' || err.message.toLowerCase().includes('fetch'))
        ? 'Erreur réseau : impossible de joindre le serveur. Vérifiez votre connexion et réessayez.'
        : err instanceof Error
          ? err.message
          : 'Une erreur imprévue est survenue lors de la création du dossier.'
    throw new CaseCreationError(message, 0)
  }
}

/**
 * Consultation unitaire des métadonnées détaillées d'un dossier (Story F2.1).
 * Route cible : GET /api/v1/cases/{case_id}
 * Contrat cible : openapi.json (simulée E2)
 *
 * RÈGLES DE CONCEPTION :
 * 1. Transmission de l'en-tête Authorization: Bearer par le client réseau (client.ts).
 * 2. En cas de 403 Forbidden : lève CasesError avec statut 403 pour affichage de la notification d'interdiction et redirection /cases.
 * 3. En cas de 404 Not Found : lève CasesError avec statut 404 pour message neutre de dossier introuvable.
 * 4. En cas d'erreur 5xx ou réseau : lève CasesError avec statut correspondant permettant l'action « Réessayer ».
 */
export async function getCase(caseId: string): Promise<CaseDetail> {
  try {
    const { data, response, error } = await apiClient.GET('/api/v1/cases/{case_id}', {
      params: {
        path: { case_id: caseId },
      },
    })

    if (response.status === 403) {
      throw new CasesError("Vous n'avez pas accès à ce dossier.", 403)
    }

    if (response.status === 404) {
      throw new CasesError('Dossier introuvable.', 404)
    }

    if (!response.ok || error) {
      const detail =
        (error as { detail?: string })?.detail ||
        'Échec du chargement du dossier. Veuillez réessayer ultérieurement.'
      throw new CasesError(detail, response.status)
    }

    if (!data) {
      throw new CasesError('Données de dossier indisponibles.', 500)
    }

    const raw = data as unknown as Partial<CaseDetail>
    return {
      id: raw.id || caseId,
      organization_id: raw.organization_id || '',
      title: raw.title || '',
      description: raw.description ?? null,
      status: (raw.status || 'open') as CaseItem['status'],
      created_by: raw.created_by ?? null,
      created_at: raw.created_at || new Date().toISOString(),
      updated_at: raw.updated_at || new Date().toISOString(),
      evidence_count: typeof raw.evidence_count === 'number' ? raw.evidence_count : 0,
      incident_date: raw.incident_date ?? null,
      incident_type: raw.incident_type ?? null,
      affected_systems: raw.affected_systems ?? null,
      members: raw.members || [],
    }
  } catch (err) {
    if (err instanceof CasesError) {
      throw err
    }
    const message =
      err instanceof Error &&
      (err.name === 'TypeError' || err.message.toLowerCase().includes('fetch'))
        ? 'Erreur réseau : impossible de joindre le serveur. Vérifiez votre connexion et réessayez.'
        : err instanceof Error
          ? err.message
          : 'Une erreur imprévue est survenue lors de la récupération du dossier.'
    throw new CasesError(message, 0)
  }
}

/**
 * Mise à jour en ligne du contexte d'un dossier d'investigation (Story F2.1).
 * Route cible : PATCH /api/v1/cases/{case_id}
 * Contrat cible : openapi.json (simulée, à réaligner E2)
 *
 * RÈGLES DE CONCEPTION :
 * 1. Modifie le titre et la description avec validation Zod préalable.
 * 2. Les champs non formalisés au contrat OpenAPI (ex. systèmes concernés) restent non éditables tant que le contrat ne les prévoit pas.
 * 3. En cas d'erreur 5xx ou réseau : lève CasesError avec statut correspondant, les saisies en cours restent conservées (NFR-ERR-02).
 */
export async function updateCase(caseId: string, payload: UpdateCasePayload): Promise<CaseDetail> {
  try {
    const patchFn = apiClient.PATCH as unknown as (
      url: string,
      options: { body: unknown },
    ) => Promise<{ data?: unknown; response: Response; error?: unknown }>

    const { data, response, error } = await patchFn(`/api/v1/cases/${caseId}`, {
      body: payload,
    })

    if (response.status === 403) {
      throw new CasesError("Vous n'avez pas accès à ce dossier.", 403)
    }

    if (response.status === 404) {
      throw new CasesError('Dossier introuvable.', 404)
    }

    if (response.status === 400 || response.status === 422) {
      const err = error as unknown as {
        detail?: string | Array<{ loc?: string[]; msg?: string }>
      } | null
      const message =
        typeof err?.detail === 'string'
          ? err.detail
          : 'Erreur de validation lors de la mise à jour du dossier.'
      throw new CasesError(message, response.status)
    }

    if (!response.ok || error) {
      const detail =
        (error as unknown as { detail?: string })?.detail ||
        'Erreur serveur lors de la mise à jour du dossier. Veuillez réessayer.'
      throw new CasesError(detail, response.status)
    }

    if (!data) {
      throw new CasesError('Réponse de mise à jour indisponible.', response.status)
    }

    const raw = data as unknown as Partial<CaseDetail>
    return {
      id: raw.id || caseId,
      organization_id: raw.organization_id || '',
      title: raw.title || payload.title,
      description: raw.description ?? payload.description ?? null,
      status: (raw.status || 'open') as CaseItem['status'],
      created_by: raw.created_by ?? null,
      created_at: raw.created_at || new Date().toISOString(),
      updated_at: raw.updated_at || new Date().toISOString(),
      evidence_count: typeof raw.evidence_count === 'number' ? raw.evidence_count : 0,
      incident_date: raw.incident_date ?? null,
      incident_type: raw.incident_type ?? null,
      affected_systems: raw.affected_systems ?? null,
      members: raw.members || [],
    }
  } catch (err) {
    if (err instanceof CasesError) {
      throw err
    }
    const message =
      err instanceof Error &&
      (err.name === 'TypeError' || err.message.toLowerCase().includes('fetch'))
        ? 'Erreur réseau : impossible de joindre le serveur. Vérifiez votre connexion et réessayez.'
        : err instanceof Error
          ? err.message
          : 'Une erreur imprévue est survenue lors de la mise à jour du dossier.'
    throw new CasesError(message, 0)
  }
}
