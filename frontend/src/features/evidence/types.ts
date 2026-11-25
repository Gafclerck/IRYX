export type EvidenceUploadStatus =
  | 'pending'
  | 'uploading'
  | 'success' // en attente d'ingestion
  | 'error'
  | 'aborted'

export interface EvidenceUploadItem {
  readonly id: string
  readonly file: File
  readonly name: string
  readonly size: number
  readonly progress: number
  readonly status: EvidenceUploadStatus
  readonly evidenceId?: string
  readonly ingestionRunId?: string
  readonly errorMessage?: string
  readonly abortFn?: () => void
}

export interface EvidenceUploadResponse {
  readonly evidence_id: string
  readonly ingestion_run_id: string
}

export interface RejectedFileInfo {
  readonly name: string
  readonly reason: string
}

/**
 * Statuts officiels du cycle d'ingestion (Story F3.2, docs/frontend/12, docs/03).
 */
export type IngestionStatus = 'pending' | 'processing' | 'completed' | 'failed'

/**
 * Représentation d'une preuve archivée (schéma EvidenceRead de openapi.json).
 */
export interface EvidenceRead {
  readonly id: string
  readonly case_id: string
  readonly original_name: string
  readonly file_size: number
  readonly sha256?: string | null
  readonly detected_type?: string | null
  readonly imported_by?: string | null
  readonly created_at: string
}

/**
 * Réponse paginée de la liste des preuves d'un dossier.
 */
export interface EvidenceListResponse {
  readonly items: readonly EvidenceRead[]
  readonly total: number
  readonly total_items: number
  readonly limit: number
  readonly offset: number
  readonly has_more: boolean
}

/**
 * Statut d'ingestion retourné par GET /api/v1/cases/:caseId/evidences/:evidenceId/ingestion-status.
 */
export interface EvidenceIngestionStatusResponse {
  readonly status: IngestionStatus | string
  readonly progress: number
  readonly error_message?: string | null
  readonly sha256?: string | null
  readonly detected_type?: string | null
}

/**
 * Preuve enrichie de son statut d'ingestion temps réel pour l'inventaire du registre.
 */
export interface EvidenceInventoryItem extends EvidenceRead {
  readonly ingestionStatus: IngestionStatus | string
  readonly ingestionProgress: number
  readonly ingestionErrorMessage?: string | null
  readonly isPollingActive?: boolean
}

