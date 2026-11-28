import { z } from 'zod'

/**
 * Schéma Zod du motif obligatoire de refus de la porte H1 (Story F4.2).
 * La longueur maximale est alignée sur le champ `feedback` du schéma contractuel
 * H1DecisionRequest (openapi.json, 2000 caractères). Tous les messages sont en français.
 */
export const rejectionReasonSchema = z
  .string()
  .trim()
  .min(1, 'Le motif du refus est obligatoire.')
  .max(2000, 'Le motif du refus ne doit pas dépasser 2000 caractères.')

export type RejectionReasonValues = z.infer<typeof rejectionReasonSchema>
