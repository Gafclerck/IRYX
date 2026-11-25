import { z } from 'zod'

/**
 * Valeurs autorisées pour le statut opérationnel d'un dossier (openapi.json / E2).
 */
export const CASE_STATUSES = ['open', 'in_progress', 'review', 'closed'] as const

/**
 * Schéma Zod validant le statut du dossier d'investigation.
 */
export const caseStatusSchema = z.enum(CASE_STATUSES, {
  message: 'Statut de dossier invalide.',
})

/**
 * Schéma Zod pour la mutation de statut PATCH /api/v1/cases/:caseId/status (Story F2.2).
 */
export const updateCaseStatusSchema = z.object({
  status: caseStatusSchema,
})

export type UpdateCaseStatusInput = z.infer<typeof updateCaseStatusSchema>
