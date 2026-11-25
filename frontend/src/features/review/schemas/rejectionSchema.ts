import { z } from 'zod'
import { REVIEW_REJECTION_REASON_REQUIRED } from '../constants'

export const rejectionReasonSchema = z
  .string()
  .trim()
  .min(1, REVIEW_REJECTION_REASON_REQUIRED)
  .max(2000, 'Le motif du refus ne doit pas dépasser 2000 caractères.')
