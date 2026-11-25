/**
 * Constantes textuelles de la prévisualisation du rapport (Story F5.1, FR-REP-01).
 *
 * RÈGLES :
 * 1. DP-03 : le front ne compile ni n'assemble le rapport ; il affiche le
 *    document renvoyé par le back-end, sans modification.
 * 2. DP-05 : après une coupure prolongée, la scrutation s'arrête et le bouton
 *    « Réessayer la connexion » est proposé. Le seuil reste « à décider ».
 * 3. F4.8 et F4.9 ne sont pas implémentées : la génération reste active sans
 *    contrôle H2/H3. L'écart est signalé explicitement, à réaligner.
 * 4. Aucune couleur en dur : fond mist et texte ink via les jetons Tailwind.
 */

export const REPORT_EMPTY_MESSAGE =
  'Aucun rapport finalisé pour ce dossier. Déclenchez la génération ci-dessus.'
export const REPORT_GENERATING_MESSAGE = 'Compilation et scellement du rapport en cours...'
export const REPORT_GENERATE_LABEL = 'Générer le rapport'
export const REPORT_RETRY_GENERATION_LABEL = 'Réessayer la compilation'
export const REPORT_RETRY_CONNECTION_LABEL = 'Réessayer la connexion'
export const REPORT_FORBIDDEN_MESSAGE = "Vous n'avez pas accès au rapport de ce dossier."
export const REPORT_FAILED_FALLBACK_MESSAGE = 'La compilation du rapport a échoué côté back-end.'
export const REPORT_ERROR_FALLBACK_MESSAGE = 'Le rapport est indisponible. Veuillez réessayer.'
export const REPORT_NETWORK_CUTOFF_MESSAGE =
  'Connexion interrompue. La scrutation a été arrêtée (DP-05).'

export const REPORT_READ_ONLY_NOTE =
  'Aperçu fourni par le back-end, affiché tel que reçu. Aucune modification côté front (DP-03).'
export const REPORT_FORMATS_NOTE =
  'Formats cibles du MVP : markdown et json (ADR-0004). Export scellé et historique : F5.2 (hors périmètre).'
export const REPORT_H2_H3_GAP_NOTE =
  'Écart à réaligner : les contrôles H2 (F4.8) et H3 (F4.9) ne sont pas implémentés. Le bouton « Générer le rapport » reste actif sans contrôle préalable.'

export const REPORT_UNKNOWN_LABEL_PREFIX = 'État inconnu'
export const REPORT_UNKNOWN_DISABLED_NOTE =
  'État non répertorié : les actions dépendantes du rapport sont désactivées par mesure de sécurité.'
export const REPORT_TO_REALIGN = 'à réaligner'
