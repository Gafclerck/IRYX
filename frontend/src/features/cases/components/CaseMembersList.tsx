import { Users } from 'lucide-react'
import type { CaseMember } from '../../../api/cases-types'
import { CONTRACT_ALIGNMENT_REQUIRED_LABEL } from '../../../api/cases-types'

export interface CaseMembersListProps {
  readonly members?: readonly CaseMember[]
}

const ROLE_LABELS: Record<string, string> = {
  admin: 'Administrateur',
  analyst: 'Analyste',
  investigator: 'Enquêteur',
  viewer: 'Observateur',
}

/**
 * Liste des membres autorisés en lecture seule sur le dossier d'investigation (Story F2.1).
 *
 * RÈGLES DE CONCEPTION :
 * 1. Consultation seule au MVP (non éditable).
 * 2. Mention « à réaligner » apposée en en-tête car le rattachement de membres au dossier
 *    n'est pas encore formalisé dans le schéma OpenAPI CaseOut.
 * 3. En l'absence de membre : texte par défaut en couleur teal.
 */
export function CaseMembersList({ members = [] }: CaseMembersListProps) {
  return (
    <section
      className="p-5 rounded border border-deep bg-ink space-y-4"
      aria-labelledby="case-members-heading"
      data-testid="case-members-section"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Users className="w-4 h-4 text-cyan" aria-hidden="true" />
          <h3 id="case-members-heading" className="text-sm font-semibold text-mist">
            Membres autorisés
          </h3>
          <span className="text-[11px] text-teal">(lecture seule)</span>
        </div>
        <span
          className="text-[10px] font-mono px-2 py-0.5 rounded bg-deep/30 text-teal border border-deep"
          title="Le rattachement des membres au dossier est à formaliser au contrat OpenAPI"
          data-testid="case-members-alignment-tag"
        >
          {CONTRACT_ALIGNMENT_REQUIRED_LABEL}
        </span>
      </div>

      {members.length === 0 ? (
        <p className="text-xs text-teal italic" data-testid="empty-members-msg">
          Aucun membre rattaché à ce dossier.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-mist border-collapse" role="table">
            <thead>
              <tr className="border-b border-deep text-teal font-semibold">
                <th scope="col" className="py-2 pr-4">
                  Identité / Adresse électronique
                </th>
                <th scope="col" className="py-2 px-4">
                  Rôle attribué
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-deep" data-testid="case-members-table-body">
              {members.map((member) => (
                <tr key={member.id} className="hover:bg-deep/10">
                  <td className="py-2.5 pr-4 font-medium text-mist">
                    <div className="flex flex-col">
                      <span>{member.name || member.email}</span>
                      {member.name && (
                        <span className="text-[11px] text-teal font-mono">{member.email}</span>
                      )}
                    </div>
                  </td>
                  <td className="py-2.5 px-4">
                    <span className="inline-block px-2 py-0.5 rounded bg-deep/30 text-mist text-[11px] border border-deep">
                      {ROLE_LABELS[member.role] || member.role}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
