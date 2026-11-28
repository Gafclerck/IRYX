/**
 * Formate un horodatage ISO en date lisible UTC (Story F1.6).
 * RÈGLE : Aucun affichage en fuseau horaire local du navigateur ;
 * toutes les investigations sont synchronisées sur l'horloge UTC.
 *
 * Format produit : AAAA-MM-JJ HH:mm UTC
 */
export function formatUtcDateTime(dateStr: string | null | undefined): string {
  if (!dateStr) return '-'
  try {
    const d = new Date(dateStr)
    if (isNaN(d.getTime())) return dateStr

    const yyyy = d.getUTCFullYear()
    const mm = String(d.getUTCMonth() + 1).padStart(2, '0')
    const dd = String(d.getUTCDate()).padStart(2, '0')
    const hh = String(d.getUTCHours()).padStart(2, '0')
    const min = String(d.getUTCMinutes()).padStart(2, '0')

    return `${yyyy}-${mm}-${dd} ${hh}:${min} UTC`
  } catch {
    return dateStr
  }
}
