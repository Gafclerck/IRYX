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
