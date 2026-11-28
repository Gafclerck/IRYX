import { Trash2 } from 'lucide-react'
import type { InvestigationPlanStep } from '../types'

export interface PlanStepListProps {
  readonly steps: readonly InvestigationPlanStep[]
  readonly readOnly?: boolean
  readonly onRemove?: (stepId: number) => void
  readonly removeDisabled?: boolean
}

/**
 * Liste numérotée des étapes forensiques proposées par le Planner (Stories F4.1 et F4.2).
 *
 * Chaque étape expose : numéro d'ordre (step_id), objectif (rationale), agent responsable,
 * outil forensique (tool_name) et preuves visées (target_evidence_id).
 *
 * Le contrat InvestigationPlanStep de openapi.json ne porte aucun champ d'agent assigné :
 * la valeur est affichée « à réaligner » plutôt que d'être inventée (docs/frontend/14).
 *
 * Le bouton « Retirer » n'est rendu que lorsque l'arbitrage est autorisé (F4.2).
 * Aucun ajout d'étape n'est proposé (exclu du MVP).
 */
export function PlanStepList({
  steps,
  readOnly = false,
  onRemove,
  removeDisabled = false,
}: PlanStepListProps) {
  return (
    <section aria-labelledby="plan-steps-heading" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="plan-steps-heading" className="text-base font-bold text-mist">
          Séquence proposée par le Planner
        </h2>
        <span className="text-xs font-semibold uppercase tracking-wider text-teal">
          {readOnly ? 'Lecture seule' : 'Pour consultation'}
        </span>
      </div>

      <ol className="space-y-3" data-testid="plan-step-list">
        {steps.map((step, index) => (
          <li
            key={`${step.step_id}-${index}`}
            className="rounded-lg border border-deep bg-deep/10 p-4"
            data-testid={`plan-step-${step.step_id}`}
          >
            <div className="flex items-start gap-3">
              <span
                className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-cyan font-mono text-sm font-bold text-ink"
                aria-label={`Étape ${step.step_id}`}
                data-testid={`plan-step-number-${step.step_id}`}
              >
                {step.step_id}
              </span>

              <dl className="grid flex-1 grid-cols-1 gap-x-6 gap-y-2 text-sm md:grid-cols-2">
                <div className="md:col-span-2">
                  <dt className="text-xs font-semibold uppercase tracking-wider text-teal">
                    Objectif d’analyse
                  </dt>
                  <dd
                    className="mt-0.5 text-mist"
                    data-testid={`plan-step-objective-${step.step_id}`}
                  >
                    {step.rationale || 'à réaligner'}
                  </dd>
                </div>

                <div>
                  <dt className="text-xs font-semibold uppercase tracking-wider text-teal">
                    Agent responsable
                  </dt>
                  <dd className="mt-0.5 text-mist" data-testid={`plan-step-agent-${step.step_id}`}>
                    à réaligner
                  </dd>
                </div>

                <div>
                  <dt className="text-xs font-semibold uppercase tracking-wider text-teal">
                    Outil forensique requis
                  </dt>
                  <dd
                    className="mt-0.5 font-mono text-mist"
                    data-testid={`plan-step-tool-${step.step_id}`}
                  >
                    {step.tool_name}
                  </dd>
                </div>

                <div className="md:col-span-2">
                  <dt className="text-xs font-semibold uppercase tracking-wider text-teal">
                    Preuves visées
                  </dt>
                  <dd
                    className="mt-0.5 break-all font-mono text-xs text-mist"
                    data-testid={`plan-step-evidence-${step.step_id}`}
                  >
                    {step.target_evidence_id}
                  </dd>
                </div>
              </dl>

              {onRemove && (
                <button
                  type="button"
                  onClick={() => onRemove(step.step_id)}
                  disabled={removeDisabled}
                  aria-label={`Retirer l’étape ${step.step_id}`}
                  className="inline-flex flex-shrink-0 items-center gap-1.5 rounded border border-teal bg-deep px-2.5 py-1.5 text-xs font-semibold text-cyan hover:bg-deep/80 focus:outline-none focus:ring-2 focus:ring-cyan disabled:cursor-not-allowed disabled:opacity-50"
                  data-testid={`plan-remove-step-${step.step_id}`}
                >
                  <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                  Retirer
                </button>
              )}
            </div>
          </li>
        ))}
      </ol>

      {steps.length === 0 && (
        <p className="text-sm text-teal" data-testid="plan-step-list-empty">
          Aucune étape d’analyse disponible.
        </p>
      )}
    </section>
  )
}
