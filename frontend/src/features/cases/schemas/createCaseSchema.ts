import { z } from 'zod'

/**
 * Schéma Zod de validation du formulaire de création de dossier d'investigation (Story F1.7).
 * Tous les messages de validation sont formulés en langue française.
 *
 * Contraintes :
 * - title : obligatoire, 1 à 255 caractères (aligné OpenAPI CaseCreate)
 * - incident_date : obligatoire, horodatage valide
 * - incident_type : obligatoire, sélection parmi les options contractuelles ou « à décider »
 * - affected_systems : obligatoire
 * - description : obligatoire, 1 à 5000 caractères (aligné OpenAPI CaseCreate)
 */
export const createCaseSchema = z.object({
  title: z
    .string()
    .trim()
    .min(1, 'Le titre du dossier est obligatoire.')
    .max(255, 'Le titre ne doit pas dépasser 255 caractères.'),
  incident_date: z.string().trim().min(1, "La date de l'incident est obligatoire."),
  incident_type: z.string().trim().min(1, "Le type d'incident est obligatoire."),
  affected_systems: z.string().trim().min(1, 'Les systèmes concernés sont obligatoires.'),
  description: z
    .string()
    .trim()
    .min(1, 'La description est obligatoire.')
    .max(5000, 'La description ne doit pas dépasser 5000 caractères.'),
})

export type CreateCaseFormValues = z.infer<typeof createCaseSchema>
