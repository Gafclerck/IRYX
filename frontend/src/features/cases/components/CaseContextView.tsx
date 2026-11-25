import { Edit3, Calendar, Server, Clock } from 'lucide-react'
import type { CaseDetail } from '../../../api/cases-types'
import { CONTRACT_ALIGNMENT_REQUIRED_LABEL } from '../../../api/cases-types'
import { formatUtcDateTime } from '../../../lib/date'
import { CasesStatusBadge } from './CasesStatusBadge'
import { CaseMembersList } from './CaseMembersList'

export interface CaseContextViewProps {
  readonly caseData: CaseDetail
  readonly onEdit: () => void
}

/**
 * Vue en lecture seule de la fiche de contexte du dossier (Story F2.1).
 *
 * RÈGLES DE CONCEPTION :
 * 1. Restitue l'ensemble des métadonnées du dossier : titre, description, statut,
 *    date de l'incident, systèmes concernés, horodatages UTC et membres autorisés.
 * 2. État vide : la mention textuelle par défaut « Aucune description fournie »
 *    s'affiche en couleur teal.
 * 3. Systèmes concernés non spécifiés : mention « Aucun système spécifié » en couleur teal.
 * 4. Champs non présents au contrat (date de l'incident, systèmes concernés) :
 *    marqués par le badge textuel « à réaligner ».
 * 5. Bouton « Modifier » pour basculer en mode d'édition.
 * 6. Statut en lecture seule (le changement de statut relève de la Story F2.2).
 */
export function CaseContextView({ caseData, onEdit }: CaseContextViewProps) {
  const hasDescription = Boolean(caseData.description && caseData.description.trim().length > 0)
  const hasSystems = Boolean(
    caseData.affected_systems && caseData.affected_systems.trim().length > 0,
  )

  return (
    <div className="space-y-6" data-testid="case-context-view">
      {/* Barre d'actions et titre de la vue */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-deep pb-4">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <h1
              className="text-xl font-bold tracking-tight text-mist"
              data-testid="case-view-title"
            >
              {caseData.title}
            </h1>
            <div data-testid="case-view-status">
              <CasesStatusBadge status={caseData.status} />
            </div>
          </div>
          <p className="text-xs text-teal">
            Étape 1 : Cadrage administratif et technique de l'incident forensique
          </p>
        </div>

        <button
          type="button"
          onClick={onEdit}
          className="inline-flex items-center gap-2 px-3.5 py-2 rounded bg-deep text-mist text-xs font-semibold hover:bg-teal hover:text-ink focus:outline-none focus:ring-2 focus:ring-cyan transition-colors"
          data-testid="edit-case-btn"
          aria-label="Modifier le contexte du dossier"
        >
          <Edit3 className="w-3.5 h-3.5" aria-hidden="true" />
          <span>Modifier</span>
        </button>
      </div>

      {/* Grille principale des informations du contexte */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Encart Informations administratives et descriptives */}
        <section
          className="p-5 rounded border border-deep bg-ink space-y-4"
          aria-labelledby="case-info-heading"
          data-testid="case-info-section"
        >
          <h2 id="case-info-heading" className="text-sm font-semibold text-mist">
            Description de l'incident
          </h2>

          <div className="space-y-2">
            <div className="text-xs font-medium text-teal">Description détaillée</div>
            <div
              className={`text-xs leading-relaxed p-3 rounded bg-deep/10 border border-deep min-h-[90px] whitespace-pre-wrap ${
                hasDescription ? 'text-mist' : 'text-teal italic'
              }`}
              data-testid="case-view-description"
            >
              {hasDescription ? caseData.description : 'Aucune description fournie'}
            </div>
          </div>

          <div className="pt-2 border-t border-deep/40 text-xs text-teal">
            <span className="font-semibold text-mist">Statut du dossier :</span>{' '}
            <span className="italic">
              Modification de cycle de vie en Étape 1 (consultation seule au MVP F2.1)
            </span>
          </div>
        </section>

        {/* Encart Cadrage technique & Horodatages UTC */}
        <section
          className="p-5 rounded border border-deep bg-ink space-y-4"
          aria-labelledby="case-tech-heading"
          data-testid="case-tech-section"
        >
          <h2 id="case-tech-heading" className="text-sm font-semibold text-mist">
            Cadrage technique et temporalité
          </h2>

          <div className="space-y-3">
            {/* Date de détection de l'incident */}
            <div className="space-y-1">
              <div className="flex items-center justify-between text-xs">
                <span className="flex items-center gap-1.5 text-mist font-medium">
                  <Calendar className="w-3.5 h-3.5 text-cyan" aria-hidden="true" />
                  Date de l'incident (UTC)
                </span>
                <span
                  className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-deep/30 text-teal border border-deep"
                  title="Ce champ n'est pas encore formalisé dans le schéma OpenAPI CaseOut"
                  data-testid="incident-date-alignment-tag"
                >
                  {CONTRACT_ALIGNMENT_REQUIRED_LABEL}
                </span>
              </div>
              <div
                className="text-xs font-mono text-mist p-2 rounded bg-deep/10 border border-deep"
                data-testid="case-view-incident-date"
              >
                {caseData.incident_date
                  ? formatUtcDateTime(caseData.incident_date)
                  : 'Non renseignée'}
              </div>
            </div>

            {/* Systèmes concernés */}
            <div className="space-y-1">
              <div className="flex items-center justify-between text-xs">
                <span className="flex items-center gap-1.5 text-mist font-medium">
                  <Server className="w-3.5 h-3.5 text-cyan" aria-hidden="true" />
                  Systèmes concernés
                </span>
                <span
                  className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-deep/30 text-teal border border-deep"
                  title="Ce champ n'est pas encore formalisé dans le schéma OpenAPI CaseOut"
                  data-testid="affected-systems-alignment-tag"
                >
                  {CONTRACT_ALIGNMENT_REQUIRED_LABEL}
                </span>
              </div>
              <div
                className={`text-xs p-2 rounded bg-deep/10 border border-deep ${
                  hasSystems ? 'text-mist' : 'text-teal italic'
                }`}
                data-testid="case-view-affected-systems"
              >
                {hasSystems ? caseData.affected_systems : 'Aucun système spécifié'}
              </div>
            </div>

            {/* Horodatages UTC normalisés */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 border-t border-deep/40">
              <div className="space-y-1">
                <div className="flex items-center gap-1 text-[11px] text-teal">
                  <Clock className="w-3 h-3 text-cyan" aria-hidden="true" />
                  <span>Dernière activité (UTC)</span>
                </div>
                <div className="text-xs font-mono text-mist" data-testid="case-view-updated-at">
                  {formatUtcDateTime(caseData.updated_at)}
                </div>
              </div>

              <div className="space-y-1">
                <div className="flex items-center gap-1 text-[11px] text-teal">
                  <Clock className="w-3 h-3 text-cyan" aria-hidden="true" />
                  <span>Date de création (UTC)</span>
                </div>
                <div className="text-xs font-mono text-mist" data-testid="case-view-created-at">
                  {formatUtcDateTime(caseData.created_at)}
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>

      {/* Section des membres autorisés en lecture seule */}
      <CaseMembersList members={caseData.members} />
    </div>
  )
}
