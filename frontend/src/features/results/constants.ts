/**
 * Constantes de la chronologie unifiée (Story F4.6, FR-RES-02, DP-01).
 *
 * RÈGLES :
 * 1. DP-01 : la taille de bloc est fixée à 100 événements, pagination serveur stricte.
 * 2. Aucune autre valeur chiffrée n'est inventée : les paramètres non contractuels
 *    restent « à décider ».
 * 3. Le panneau de source relève de F4.7 : l'action est désactivée et signalée.
 */
export const TIMELINE_PAGE_SIZE = 100

export const TO_REALIGN = 'à réaligner'
export const TO_DECIDE = 'à décider'

export const EMPTY_TIMELINE_MESSAGE = 'Aucun événement chronologique.'
export const EMPTY_TIMELINE_DETAIL =
  'Aucun événement chronologique ne correspond aux critères sélectionnés.'
export const SOURCE_PANEL_REALIGNMENT_NOTE = `Panneau « Source » — ${TO_REALIGN} (F4.7)`
export const SKIPPED_TABS_NOTE = 'Artefacts et hypothèses : F4.5 sautée (hors périmètre).'
export const FILTER_REALIGNMENT_NOTE = `Paramètres de filtrage non contractuels : ${TO_DECIDE}.`
