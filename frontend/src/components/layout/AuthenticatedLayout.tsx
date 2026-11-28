import { type ReactNode } from 'react'
import { Outlet } from 'react-router-dom'
import { TopBar } from './TopBar'

export interface AuthenticatedLayoutProps {
  readonly children?: ReactNode
}

/**
 * Layout permanent enveloppant l'ensemble des routes authentifiées (Story F1.5).
 *
 * RÈGLES D'ARCHITECTURE :
 * 1. Présente la TopBar permanente en en-tête transverse (56 px, fond ink, bordure deep).
 * 2. Enveloppe les routes authentifiées (/cases, etc.).
 * 3. /login et la page 404 restent strictement en dehors de ce layout.
 * 4. Aucun contenu métier : la liste des dossiers et la barre latérale du dossier relèvent des stories suivantes.
 * 5. Aucun lien vers un écran d'audit (DP-02).
 */
export function AuthenticatedLayout({ children }: AuthenticatedLayoutProps) {
  return (
    <div className="flex min-h-screen flex-col bg-ink text-mist">
      <TopBar />
      <main className="flex-1 bg-ink" role="main">
        {children ?? <Outlet />}
      </main>
    </div>
  )
}
