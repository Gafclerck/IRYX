import { useNavigate } from 'react-router-dom'
import type { CaseItem } from '../../../api/cases-types'
import { formatUtcDateTime } from '../../../lib/date'
import { CasesStatusBadge } from './CasesStatusBadge'

export interface CasesTableProps {
  readonly items: CaseItem[]
}

/**
 * Tableau récapitulatif paginé des dossiers d'investigation (Story F1.6).
 *
 * RÈGLES DE CONCEPTION :
 * 1. Affiche exclusivement les dossiers de la page courante (pagination serveur).
 * 2. Colonnes requises : Titre, Statut, Date de détection UTC, Nombre de preuves scellées.
 * 3. Navigation : le clic ou l'activation clavier sur une ligne oriente vers /cases/:caseId.
 * 4. Respect strict de la palette : texte principal mist, texte secondaire teal, bordures deep.
 */
export function CasesTable({ items }: CasesTableProps) {
  const navigate = useNavigate()

  const handleRowClick = (caseId: string) => {
    navigate(`/cases/${caseId}`)
  }

  const handleKeyDown = (e: React.KeyboardEvent, caseId: string) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      navigate(`/cases/${caseId}`)
    }
  }

  return (
    <div className="w-full overflow-x-auto rounded border border-deep bg-ink">
      <table className="w-full text-left text-sm text-mist border-collapse" role="table">
        <thead className="border-b border-deep bg-ink text-xs font-semibold uppercase text-teal">
          <tr>
            <th scope="col" className="px-4 py-3">
              Titre du dossier
            </th>
            <th scope="col" className="px-4 py-3">
              Statut
            </th>
            <th scope="col" className="px-4 py-3">
              Date de détection UTC
            </th>
            <th scope="col" className="px-4 py-3 text-right">
              Preuves scellées
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-deep bg-ink" data-testid="cases-table-body">
          {items.map((c) => (
            <tr
              key={c.id}
              onClick={() => handleRowClick(c.id)}
              onKeyDown={(e) => handleKeyDown(e, c.id)}
              tabIndex={0}
              role="row"
              aria-label={`Dossier ${c.title}`}
              className="cursor-pointer transition-colors hover:bg-deep/20 focus:bg-deep/20 focus:outline-none focus:ring-1 focus:ring-cyan"
              data-testid={`case-row-${c.id}`}
            >
              <td className="px-4 py-3 font-medium text-mist">
                <div className="flex flex-col">
                  <span>{c.title}</span>
                  {c.description && (
                    <span className="text-xs text-teal line-clamp-1">{c.description}</span>
                  )}
                </div>
              </td>
              <td className="px-4 py-3 whitespace-nowrap">
                <CasesStatusBadge status={c.status} />
              </td>
              <td className="px-4 py-3 whitespace-nowrap text-xs text-teal font-mono">
                {formatUtcDateTime(c.created_at)}
              </td>
              <td className="px-4 py-3 whitespace-nowrap text-right text-xs font-mono text-mist">
                <span data-testid={`case-evidence-count-${c.id}`}>{c.evidence_count}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
