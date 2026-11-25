/**
 * Constantes de la revue H2 (Story F4.8, FR-REV-01).
 *
 * RÈGLES :
 * 1. Aucune décision n'est calculée côté front ; toute décision est une requête
 *    distincte envoyée au back. Si la route n'existe pas dans le contrat, les
 *    actions restent désactivées avec "à réaligner (E6)".
 * 2. DP-05 : coupure prolongée signalée, seuil "à décider".
 * 3. Palette stricte via jetons Tailwind ; sévérité par libellé/icône, jamais
 *    par la couleur seule.
 */
export const REVIEW_EMPTY_MESSAGE = 'Aucun finding à examiner.'
export const REVIEW_ERROR_FALLBACK_MESSAGE =
  'Impossible de charger les findings. Veuillez réessayer.'
export const REVIEW_FORBIDDEN_MESSAGE = "Vous n'avez pas accès à la revue de ce dossier."
export const REVIEW_RETRY_LABEL = 'Réessayer'
export const REVIEW_RETRY_CONNECTION_LABEL = 'Réessayer la connexion'
export const REVIEW_NETWORK_CUTOFF_MESSAGE =
  'Connexion interrompue. La scrutation a été arrêtée (DP-05).'

export const REVIEW_DECISION_TO_REALIGN = 'à réaligner (E6)'
export const REVIEW_DECISION_DISABLED_NOTE =
  'Route de décision absente du contrat : action désactivée, à réaligner (E6).'
export const REVIEW_COMMENT_DISABLED_NOTE =
  'Route de commentaire absente du contrat : action désactivée, à réaligner (E6).'

export const REVIEW_VALIDATE_LABEL = 'Valider'
export const REVIEW_REJECT_LABEL = 'Rejeter'
export const REVIEW_COMMENT_LABEL = 'Ajouter un commentaire'
export const REVIEW_DECISION_PENDING_LABEL = 'Envoi en cours...'
export const REVIEW_DECISION_ERROR_MESSAGE =
  'La décision n’a pas été enregistrée. Veuillez réessayer.'
export const REVIEW_REJECTION_REASON_REQUIRED = 'Le motif du refus est obligatoire.'
export const REVIEW_REJECTION_REASON_LABEL = 'Motif du refus (obligatoire)'
export const REVIEW_REJECTION_REASON_PLACEHOLDER = 'Indiquez le motif du refus'

export const REVIEW_REPORT_LINK_LABEL = 'Accéder au rapport'
export const REVIEW_REPORT_LINK_BLOCKED_NOTE =
  'Le rapport reste indisponible tant qu’aucun finding n’est validé.'
export const REVIEW_UNKNOWN_LABEL_PREFIX = 'État inconnu'
export const REVIEW_UNKNOWN_DISABLED_NOTE =
  'État non répertorié : les actions dépendantes sont désactivées par mesure de sécurité.'

export const FINDING_STATUS_LABELS: Record<string, string> = {
  proposed: 'À EXAMINER',
  validated: 'VALIDÉ',
  rejected: 'REJETÉ',
}

export const FINDING_TYPE_LABELS: Record<string, string> = {
  fact: 'Fait',
  inference: 'Inférence',
  hypothesis: 'Hypothèse',
}

export const FINDING_SEVERITY_LABELS: Record<string, string> = {
  low: 'Faible',
  medium: 'Moyenne',
  high: 'Élevée',
  critical: 'Critique',
}

export const FINDING_CONFIDENCE_LABELS: Record<string, string> = {
  low: 'Faible',
  medium: 'Moyenne',
  high: 'Élevée',
}

export function formatFindingStatus(status: string | null | undefined): string {
  if (!status) return `${REVIEW_UNKNOWN_LABEL_PREFIX} (non fourni)`
  return FINDING_STATUS_LABELS[status] ?? `${REVIEW_UNKNOWN_LABEL_PREFIX} (${status})`
}

export function isKnownFindingStatus(status: string | null | undefined): boolean {
  return status === 'proposed' || status === 'validated' || status === 'rejected'
}
