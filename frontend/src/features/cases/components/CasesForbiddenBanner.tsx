import { ShieldAlert } from 'lucide-react'

/**
 * Bannière d'accès refusé en cas de réponse HTTP 403 Forbidden (Story F1.6).
 * Empêche l'affichage de toute donnée confidentielle et invite à contacter l'administrateur.
 */
export function CasesForbiddenBanner() {
  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded border border-deep bg-ink p-4 text-mist"
      data-testid="cases-forbidden-banner"
    >
      <ShieldAlert className="h-5 w-5 flex-shrink-0 text-cyan" aria-hidden="true" />
      <div>
        <p className="text-sm font-semibold text-mist">Accès refusé</p>
        <p className="mt-0.5 text-xs text-teal">
          Vous n'avez pas accès aux dossiers de cette organisation. Veuillez contacter votre
          administrateur.
        </p>
      </div>
    </div>
  )
}
