import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { performLogout } from '../../api/auth-session'
import { useSessionUser } from '../../features/auth/hooks/useSessionUser'
import type { SessionUser } from '../../api/auth-memory'

export interface TopBarProps {
  readonly user?: SessionUser | null
}

/**
 * Barre supérieure permanente de l'application IRYX (Story F1.5 / DP-02).
 *
 * PÉRIMÈTRE & SPÉCIFICATIONS TECHNIQUES :
 * 1. Hauteur figée à 56 px (h-14).
 * 2. Fond de couleur ink et bordure inférieure deep (palette stricte).
 * 3. Affiche le logo IRYX, la dénomination de l'organisation et le nom de l'utilisateur connecté.
 * 4. Les informations proviennent exclusivement de la session en mémoire vive.
 *    Si le back ne fournit pas encore l'utilisateur courant (/api/v1/auth/me absente du contrat),
 *    affiche la valeur neutre « Utilisateur » et « Organisation » sans rien inventer (marqué à réaligner).
 * 5. Action « Se déconnecter » : appelle la déconnexion explicite de F1.4 (POST /api/v1/auth/logout,
 *    purge du jeton d'accès et des informations en mémoire, redirection vers /login).
 * 6. Exclusion formelle de tout lien vers un écran d'audit (DP-02).
 * 7. Aucune écriture dans localStorage ni sessionStorage.
 * 8. Navigation au clavier et anneau de focus cyan.
 */
export function TopBar({ user: propUser }: TopBarProps) {
  const sessionUser = useSessionUser()
  const activeUser = propUser !== undefined ? propUser : sessionUser
  const navigate = useNavigate()
  const [isLoggingOut, setIsLoggingOut] = useState(false)

  // Valeurs neutres garantissant l'absence totale de données d'identité inventées
  const organizationName = activeUser?.organizationName?.trim() || 'Organisation'
  const userName = activeUser?.userName?.trim() || 'Utilisateur'
  const role = activeUser?.role?.trim()

  const handleLogout = async () => {
    if (isLoggingOut) return
    setIsLoggingOut(true)
    try {
      await performLogout()
    } finally {
      navigate('/login', { replace: true })
    }
  }

  return (
    <header
      className="flex h-14 min-h-[56px] max-h-[56px] w-full items-center justify-between border-b border-deep bg-ink px-4 sm:px-6 select-none"
      role="banner"
    >
      {/* Côté gauche : Logo officiel IRYX et Organisation */}
      <div className="flex items-center space-x-3">
        <span className="font-display text-lg font-bold tracking-tight text-mist">IRYX</span>
        <span className="text-deep" aria-hidden="true">
          |
        </span>
        <span className="text-sm font-medium text-mist" data-testid="topbar-org">
          {organizationName}
        </span>
      </div>

      {/* Côté droit : Utilisateur connecté et Bouton Déconnexion */}
      <div className="flex items-center space-x-4">
        <div className="flex items-center space-x-2 text-sm text-mist" data-testid="topbar-user">
          <span className="font-medium text-mist">{userName}</span>
          {role && (
            <span
              className="rounded border border-deep px-1.5 py-0.5 text-xs text-teal font-mono"
              data-testid="topbar-role"
            >
              {role}
            </span>
          )}
        </div>

        <button
          type="button"
          onClick={handleLogout}
          disabled={isLoggingOut}
          className="inline-flex items-center justify-center rounded border border-deep px-3 py-1.5 text-xs font-medium text-mist transition-colors hover:border-cyan hover:text-cyan focus:outline-none focus:ring-2 focus:ring-cyan disabled:cursor-not-allowed disabled:border-deep disabled:text-teal"
          data-testid="logout-button"
        >
          {isLoggingOut ? 'Déconnexion...' : 'Se déconnecter'}
        </button>
      </div>
    </header>
  )
}
