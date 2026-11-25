import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  Copy,
  Check,
  FileText,
  Database,
  GitBranch,
  BarChart3,
  ShieldCheck,
  Shield,
} from 'lucide-react'

export interface CaseSidebarProps {
  readonly caseId: string
  readonly caseTitle: string
}

/**
 * Barre latérale de navigation du cycle séquentiel de l'enquête (Section 2.2 de 11-ecrans-et-routes.md).
 *
 * RÈGLES DE CONCEPTION :
 * 1. En-tête : Titre du dossier courant et identifiant avec copie presse-papier.
 * 2. Les 5 étapes numérotées du canevas forensique.
 * 3. Consultation d'une étape toujours accessible au clic.
 * 4. Pied de barre : Encart institutionnel rappelant la confidentialité locale et l'environnement contrôlé.
 * 5. Respect strict de la palette (ink, deep, teal, cyan, mist).
 */
export function CaseSidebar({ caseId, caseTitle }: CaseSidebarProps) {
  const [copied, setCopied] = useState(false)
  const location = useLocation()

  const handleCopyId = async () => {
    try {
      if (navigator.clipboard) {
        await navigator.clipboard.writeText(caseId)
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
      }
    } catch {
      // Ignoré si le presse-papier n'est pas disponible
    }
  }

  const steps = [
    {
      number: 1,
      label: 'Contexte',
      path: `/cases/${caseId}`,
      icon: FileText,
      exact: true,
    },
    {
      number: 2,
      label: 'Preuves',
      path: `/cases/${caseId}/evidence`,
      icon: Database,
    },
    {
      number: 3,
      label: 'Plan et agents',
      path: `/cases/${caseId}/plan`,
      icon: GitBranch,
    },
    {
      number: 4,
      label: 'Résultats',
      path: `/cases/${caseId}/results`,
      icon: BarChart3,
    },
    {
      number: 5,
      label: 'Revue et rapport',
      path: `/cases/${caseId}/review`,
      icon: ShieldCheck,
    },
  ]

  const isStepActive = (stepPath: string, exact?: boolean) => {
    if (exact) {
      return location.pathname === stepPath
    }
    return location.pathname.startsWith(stepPath)
  }

  const truncatedId = caseId.length > 12 ? `${caseId.slice(0, 8)}...` : caseId

  return (
    <aside
      className="w-full md:w-64 flex-shrink-0 border-b md:border-b-0 md:border-r border-deep bg-ink flex flex-col justify-between"
      aria-label="Navigation du dossier d'investigation"
      data-testid="case-sidebar"
    >
      <div className="p-4 space-y-6">
        {/* En-tête : Titre et identifiant du dossier avec copie */}
        <div className="space-y-2 border-b border-deep pb-4">
          <div className="text-xs font-semibold uppercase tracking-wider text-teal">
            Dossier actif
          </div>
          <h2
            className="text-sm font-bold text-mist line-clamp-2"
            title={caseTitle}
            data-testid="sidebar-case-title"
          >
            {caseTitle}
          </h2>

          <div className="flex items-center justify-between text-xs font-mono text-teal bg-deep/20 rounded px-2 py-1 border border-deep">
            <span title={caseId} data-testid="sidebar-case-id">
              {truncatedId}
            </span>
            <button
              type="button"
              onClick={handleCopyId}
              className="text-mist hover:text-cyan transition-colors p-0.5 rounded focus:outline-none focus:ring-1 focus:ring-cyan"
              aria-label="Copier l'identifiant du dossier"
              title="Copier l'identifiant du dossier"
              data-testid="copy-case-id-btn"
            >
              {copied ? (
                <Check className="w-3.5 h-3.5 text-cyan" aria-hidden="true" />
              ) : (
                <Copy className="w-3.5 h-3.5" aria-hidden="true" />
              )}
            </button>
          </div>
        </div>

        {/* Navigation des 5 étapes séquentielles */}
        <nav aria-label="Étapes de l'investigation">
          <ul className="space-y-1">
            {steps.map((step) => {
              const active = isStepActive(step.path, step.exact)
              const StepIcon = step.icon

              return (
                <li key={step.number}>
                  <Link
                    to={step.path}
                    className={`flex items-center gap-3 px-3 py-2 rounded text-xs font-medium transition-colors ${
                      active
                        ? 'bg-deep/40 text-cyan border-l-2 border-cyan font-semibold'
                        : 'text-mist hover:text-cyan hover:bg-deep/20'
                    }`}
                    aria-current={active ? 'page' : undefined}
                    data-testid={`sidebar-step-${step.number}`}
                  >
                    <span
                      className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-mono ${
                        active ? 'bg-cyan text-ink font-bold' : 'bg-deep/40 text-mist'
                      }`}
                    >
                      {step.number}
                    </span>
                    <StepIcon className="w-4 h-4 flex-shrink-0" aria-hidden="true" />
                    <span>{step.label}</span>
                  </Link>
                </li>
              )
            })}
          </ul>
        </nav>
      </div>

      {/* Pied de barre latérale : Encart de confidentialité institutionnel */}
      <div className="p-4 border-t border-deep">
        <div className="p-2.5 rounded bg-deep/10 border border-deep text-[11px] text-teal space-y-1">
          <div className="flex items-center gap-1.5 font-semibold text-mist">
            <Shield className="w-3.5 h-3.5 text-cyan flex-shrink-0" aria-hidden="true" />
            <span>Sécurité locale</span>
          </div>
          <p className="leading-relaxed">
            Traitement sécurisé et préservation des preuves en environnement contrôlé DFIR.
          </p>
        </div>
      </div>
    </aside>
  )
}
