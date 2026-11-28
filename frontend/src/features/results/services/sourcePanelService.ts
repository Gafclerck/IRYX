import { apiClient } from '../../../api/client'
import type { ObservationRead } from '../types'

/** Erreur de consultation de la source : le code HTTP pilote l'état du tiroir. */
export class SourcePanelApiError extends Error {
  readonly status: number

  constructor(message: string, status: number = 0) {
    super(message)
    this.name = 'SourcePanelApiError'
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
 * Récupère le détail d'une observation pour le panneau « Source » (F4.7).
 * Route cible : GET /api/v1/cases/{case_id}/observations/{observation_id} (openapi.json).
 * Aucun contenu intégral n'est demandé ici (DP-04) : la réponse ne contient
 * que les métadonnées et l'extrait normalisé déjà tronqué côté serveur cible.
 */
export async function getObservationSource(
  caseId: string,
  observationId: string,
): Promise<ObservationRead> {
  try {
    const { data, response, error } = await apiClient.GET(
      '/api/v1/cases/{case_id}/observations/{observation_id}',
      { params: { path: { case_id: caseId, observation_id: observationId } } },
    )

    if (response.status === 403) {
      throw new SourcePanelApiError('Consultation de la source interdite.', 403)
    }
    if (response.status === 404) {
      throw new SourcePanelApiError('Source introuvable.', 404)
    }
    if (response.status === 401) {
      throw new SourcePanelApiError('Session expirée lors de la consultation de la source.', 401)
    }
    if (!response.ok || error) {
      throw new SourcePanelApiError(
        readDetail(error, 'Impossible de récupérer les données de source.'),
        response.status,
      )
    }
    if (!data) {
      throw new SourcePanelApiError('Données de source indisponibles.', 500)
    }
    return data
  } catch (err) {
    if (err instanceof SourcePanelApiError) throw err
    throw new SourcePanelApiError('Serveur injoignable. Veuillez vérifier votre connexion.', 0)
  }
}

/**
 * Lien de téléchargement direct de l'extrait complet (DP-04).
 * Le contrat cible ne définit pas encore cette route : le paramètre `download`
 * est simulé et sera à réaligner avec le back-end (E4).
 * Le contenu intégral n'est demandé que sur action explicite de l'utilisateur.
 */
export function buildSourceDownloadUrl(caseId: string, observationId: string): string {
  return `/api/v1/cases/${encodeURIComponent(caseId)}/observations/${encodeURIComponent(observationId)}?download=full`
}
