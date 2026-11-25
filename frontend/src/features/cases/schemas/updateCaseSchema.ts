import { z } from 'zod'

/**
 * Schéma de validation Zod pour la modification en ligne du contexte d'un dossier (Story F2.1).
 *
 * RÈGLES DE VALIDATION (en français) :
 * 1. Le titre du dossier est obligatoire et ne doit pas être constitué uniquement d'espaces (1 à 255 caractères).
 * 2. La description est optionnelle mais ne doit pas excéder 5000 caractères si fournie.
 * 3. Les champs non prévus au contrat cible OpenAPI (ex. systèmes concernés) ne sont pas modifiables.
 */
export const updateCaseSchema = z.object({
  title: z
    .string()
    .trim()
    .min(1, 'Le titre du dossier est obligatoire.')
    .max(255, 'Le titre du dossier ne doit pas dépasser 255 caractères.'),
  description: z
    .string()
    .max(5000, 'La description ne doit pas dépasser 5000 caractères.')
    .optional()
    .or(z.literal('')),
})

export type UpdateCaseFormData = z.infer<typeof updateCaseSchema>
