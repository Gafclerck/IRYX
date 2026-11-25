/**
 * Types de la simulation de rapport (Story F5.1).
 *
 * Le contrat `docs/contrat/openapi.json` ne contient aucune route de rapport :
 * les formulaires ci-dessous sont strictement limités aux champs décrits par
 * ADR-0004 (formats markdown/json) et ADR-0008 (tâche asynchrone uniforme).
 * Aucun champ de rapport n'est assemblé ni enrichi côté front (DP-03).
 */

/** Formats natifs retenus pour le MVP (ADR-0004). Le PDF est différé. */
export type ReportFormat = 'markdown' | 'json'

/**
 * Statuts du cycle de vie du rapport (docs/frontend/12, section 3.5).
 * Le type reste `string` pour restituer un code non répertorié sans crash.
 */
export type ReportDocumentStatus = string

/** Statuts d'une tâche asynchrone (ADR-0008, option A). */
export type ReportTaskStatus = string

/** Format de réponse uniforme d'une tâche asynchrone (ADR-0008). */
export interface ReportTask {
  readonly task_id: string
  readonly status: ReportTaskStatus
  readonly progress: number
  readonly poll_url: string
}

/** Document renvoyé par le back-end, affiché tel quel (DP-03). */
export interface ReportDocument {
  readonly status: ReportDocumentStatus
  readonly format: ReportFormat
  readonly content: string
}

/** Enveloppe d'erreur générique déjà utilisée par les routes contractuelles. */
export interface ReportErrorPayload {
  readonly detail?: string
  readonly code?: string
  /** Motif de compilation en échec : à réaligner avec E8. */
  readonly error_message?: string
}

export type ReportViewState =
  | 'loading'
  | 'empty'
  | 'generating'
  | 'ready'
  | 'generationFailed'
  | 'forbidden'
  | 'error'
  | 'networkCutoff'
  | 'unknown'

/**
 * Description minimale des routes simulées, absent du `paths` généré depuis
 * openapi.json (RÈGLE CONTRAT de docs/frontend/14).
 */
export interface ReportPaths {
  '/api/v1/cases/{case_id}/report': {
    parameters: {
      path: { case_id: string }
      query?: never
      header?: never
      cookie?: never
    }
    get: {
      parameters: { path: { case_id: string } }
      responses: {
        200: { content: { 'application/json': ReportDocument } }
        404: { content: { 'application/json': ReportErrorPayload } }
        403: { content: { 'application/json': ReportErrorPayload } }
        default: { content: { 'application/json': ReportErrorPayload } }
      }
    }
  }
  '/api/v1/cases/{case_id}/report/generate': {
    parameters: {
      path: { case_id: string }
      query?: never
      header?: never
      cookie?: never
    }
    post: {
      parameters: { path: { case_id: string } }
      responses: {
        202: { content: { 'application/json': ReportTask } }
        403: { content: { 'application/json': ReportErrorPayload } }
        default: { content: { 'application/json': ReportErrorPayload } }
      }
    }
  }
  '/api/v1/cases/{case_id}/tasks/{task_id}': {
    parameters: {
      path: { case_id: string; task_id: string }
      query?: never
      header?: never
      cookie?: never
    }
    get: {
      parameters: { path: { case_id: string; task_id: string } }
      responses: {
        200: { content: { 'application/json': ReportTask & ReportErrorPayload } }
        403: { content: { 'application/json': ReportErrorPayload } }
        default: { content: { 'application/json': ReportErrorPayload } }
      }
    }
  }
}
