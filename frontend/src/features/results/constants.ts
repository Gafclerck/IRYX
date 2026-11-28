/**
 * Constantes de la chronologie unifiée (Story F4.6, FR-RES-02, DP-01).
 *
 * RÈGLES :
 * 1. DP-01 : la taille de bloc est fixée à 100 événements, pagination serveur stricte.
 * 2. Aucune autre valeur chiffrée n'est inventée : les paramètres non contractuels
 *    restent « à décider ».
 * 3. Le panneau de source est activé en F4.7 : les actions ouvrent le tiroir
 *    latéral sans quitter la chronologie (aucune valeur chiffrée inventée).
 */
export const TIMELINE_PAGE_SIZE = 100

export const TO_REALIGN = 'à réaligner'
export const TO_DECIDE = 'à décider'

export const EMPTY_TIMELINE_MESSAGE = 'Aucun événement chronologique.'
export const EMPTY_TIMELINE_DETAIL =
  'Aucun événement chronologique ne correspond aux critères sélectionnés.'
export const SKIPPED_TABS_NOTE = 'Artefacts et hypothèses : F4.5 sautée (hors périmètre).'
export const FILTER_REALIGNMENT_NOTE = `Paramètres de filtrage non contractuels : ${TO_DECIDE}.`

/**
 * Constantes textuelles du panneau « Source » (Story F4.7, FR-RES-03, DP-04).
 * Les seuils de troncature sont ceux de DP-04, déjà définis dans la feature preuves.
 * Toute autre valeur chiffrée reste « à décider ».
 */
export const SOURCE_PANEL_TITLE = 'Inspection de la source forensique'
export const SOURCE_PANEL_OPEN_NOTE =
  'Panneau « Source » actif : cliquez sur un événement ou sur sa source (F4.7).'
export const SOURCE_CONFIDENTIALITY_NOTE =
  'Original conservé en local. Aucun contenu original transmis.'
export const SOURCE_EMPTY_MESSAGE = 'Aucun détail textuel supplémentaire pour cette observation'
export const SOURCE_UNAVAILABLE_MESSAGE = 'Données de source indisponibles'
export const SOURCE_FORBIDDEN_MESSAGE = 'Consultation de la source interdite.'
export const SOURCE_NOT_FOUND_MESSAGE = 'Source introuvable.'
export const SOURCE_TRUNCATION_MESSAGE = 'Extrait tronqué à 500 lignes / 64 Ko'
export const SOURCE_UNKNOWN_STATUS_PREFIX = 'État inconnu'
export const SOURCE_REACTIVITY_NOTE = `Délai maximal de réactivité à l’ouverture du tiroir : ${TO_DECIDE} (C2).`
export const SOURCE_STATUS_REALIGNMENT_NOTE = `Statut lu dans un champ libre du contrat : ${TO_REALIGN}.`
