import { z } from 'zod'

/**
 * Schéma Zod de validation du formulaire de connexion.
 * Tous les messages de validation sont rédigés en langue française.
 */
export const loginSchema = z.object({
  email: z
    .string()
    .min(1, "L'adresse électronique est requise.")
    .email("Format d'adresse électronique invalide."),
  password: z.string().min(1, 'Le mot de passe est requis.'),
})

export type LoginFormValues = z.infer<typeof loginSchema>
