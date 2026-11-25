import { useState, useId } from 'react'
import { Save, RotateCcw, AlertTriangle, Calendar, Server, Info } from 'lucide-react'
import type { CaseDetail, UpdateCasePayload } from '../../../api/cases-types'
import { CONTRACT_ALIGNMENT_REQUIRED_LABEL } from '../../../api/cases-types'
import { formatUtcDateTime } from '../../../lib/date'
import { updateCaseSchema } from '../schemas/updateCaseSchema'
import { CasesStatusBadge } from './CasesStatusBadge'

export interface CaseContextEditFormProps {
  readonly caseData: CaseDetail
  readonly onCancel: () => void
  readonly onSave: (payload: UpdateCasePayload) => Promise<void>
  readonly isSaving: boolean
  readonly saveError: Error | null
  readonly onRetrySave: () => void
}

/**
 * Formulaire de modification en ligne du contexte d'un dossier (Story F2.1).
 *
 * RÈGLES DE CONCEPTION :
 * 1. Seuls le titre et la description sont éditables.
 * 2. Validation Zod en français avant soumission.
 * 3. Boutons « Enregistrer » et « Annuler ».
 * 4. Champs non présents au contrat (date incident, systèmes concernés) : affichés « à réaligner »
 *    et non éditables tant que le contrat OpenAPI ne les prévoit pas.
 * 5. Statut en lecture seule (F2.2 hors périmètre).
 * 6. En cas d'erreur 5xx ou réseau : notification d'échec avec bouton « Réessayer »,
 *    les saisies en cours restent conservées (NFR-ERR-02).
 */
export function CaseContextEditForm({
  caseData,
  onCancel,
  onSave,
  isSaving,
  saveError,
  onRetrySave,
}: CaseContextEditFormProps) {
  const [title, setTitle] = useState(caseData.title)
  const [description, setDescription] = useState(caseData.description ?? '')
  const [validationErrors, setValidationErrors] = useState<{
    title?: string
    description?: string
  }>({})

  const titleId = useId()
  const descriptionId = useId()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    // Validation Zod avant tout envoi réseau
    const parseResult = updateCaseSchema.safeParse({
      title,
      description,
    })

    if (!parseResult.success) {
      const fieldErrors: { title?: string; description?: string } = {}
      for (const issue of parseResult.error.issues) {
        if (issue.path[0] === 'title' && !fieldErrors.title) {
          fieldErrors.title = issue.message
        }
        if (issue.path[0] === 'description' && !fieldErrors.description) {
          fieldErrors.description = issue.message
        }
      }
      setValidationErrors(fieldErrors)
      return
    }

    setValidationErrors({})
    await onSave({
      title: parseResult.data.title,
      description: parseResult.data.description?.trim() || null,
    })
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-6"
      data-testid="case-context-edit-form"
      noValidate
    >
      {/* En-tête et actions d'enregistrement / annulation */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-deep pb-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-mist">
            Modifier le contexte du dossier
          </h1>
          <p className="text-xs text-teal mt-1">
            Mettez à jour le titre et la description en ligne avec validation immédiate
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={isSaving}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded border border-deep bg-ink text-mist text-xs font-semibold hover:bg-deep/30 focus:outline-none focus:ring-2 focus:ring-cyan transition-colors disabled:opacity-50"
            data-testid="cancel-edit-btn"
          >
            <RotateCcw className="w-3.5 h-3.5" aria-hidden="true" />
            <span>Annuler</span>
          </button>

          <button
            type="submit"
            disabled={isSaving}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded bg-cyan text-ink text-xs font-bold hover:bg-cyan/90 focus:outline-none focus:ring-2 focus:ring-cyan transition-colors disabled:opacity-50"
            data-testid="save-case-btn"
          >
            <Save className="w-3.5 h-3.5" aria-hidden="true" />
            <span>{isSaving ? 'Enregistrement...' : 'Enregistrer'}</span>
          </button>
        </div>
      </div>

      {/* Notification d'échec serveur ou réseau avec conservation de saisie (NFR-ERR-02) */}
      {saveError && (
        <div
          role="alert"
          aria-live="assertive"
          className="p-4 rounded border border-deep bg-deep/20 text-mist flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3"
          data-testid="case-update-error-banner"
        >
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-teal flex-shrink-0" aria-hidden="true" />
            <span className="text-xs">
              {saveError.message || 'Erreur lors de la mise à jour du dossier.'}
            </span>
          </div>
          <button
            type="button"
            onClick={onRetrySave}
            disabled={isSaving}
            className="px-3 py-1.5 rounded bg-deep text-mist text-xs font-semibold hover:bg-teal hover:text-ink transition-colors focus:outline-none focus:ring-2 focus:ring-cyan"
            data-testid="retry-update-btn"
          >
            Réessayer
          </button>
        </div>
      )}

      {/* Formulaire des champs éditables et non éditables */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Colonne gauche : Titre et Description (éditables) */}
        <div className="p-5 rounded border border-deep bg-ink space-y-4">
          <h2 className="text-sm font-semibold text-mist">Informations modifiables</h2>

          {/* Champ Titre */}
          <div className="space-y-1.5">
            <label htmlFor={titleId} className="block text-xs font-medium text-mist">
              Titre du dossier <span className="text-cyan">*</span>
            </label>
            <input
              id={titleId}
              type="text"
              value={title}
              onChange={(e) => {
                setTitle(e.target.value)
                if (validationErrors.title) {
                  setValidationErrors((prev) => ({ ...prev, title: undefined }))
                }
              }}
              disabled={isSaving}
              className={`w-full px-3 py-2 rounded border bg-ink text-xs text-mist focus:outline-none focus:ring-2 focus:ring-cyan transition-colors ${
                validationErrors.title ? 'border-teal' : 'border-deep'
              }`}
              data-testid="edit-title-input"
              aria-invalid={Boolean(validationErrors.title)}
              aria-describedby={validationErrors.title ? `${titleId}-error` : undefined}
            />
            {validationErrors.title && (
              <p
                id={`${titleId}-error`}
                role="alert"
                className="text-xs text-teal mt-1"
                data-testid="edit-title-error"
              >
                {validationErrors.title}
              </p>
            )}
          </div>

          {/* Champ Description */}
          <div className="space-y-1.5">
            <label htmlFor={descriptionId} className="block text-xs font-medium text-mist">
              Description de l'incident
            </label>
            <textarea
              id={descriptionId}
              rows={5}
              value={description}
              onChange={(e) => {
                setDescription(e.target.value)
                if (validationErrors.description) {
                  setValidationErrors((prev) => ({ ...prev, description: undefined }))
                }
              }}
              disabled={isSaving}
              placeholder="Décrivez les circonstances et le contexte de l'incident..."
              className={`w-full px-3 py-2 rounded border bg-ink text-xs text-mist focus:outline-none focus:ring-2 focus:ring-cyan transition-colors resize-y ${
                validationErrors.description ? 'border-teal' : 'border-deep'
              }`}
              data-testid="edit-description-input"
              aria-invalid={Boolean(validationErrors.description)}
              aria-describedby={validationErrors.description ? `${descriptionId}-error` : undefined}
            />
            {validationErrors.description && (
              <p
                id={`${descriptionId}-error`}
                role="alert"
                className="text-xs text-teal mt-1"
                data-testid="edit-description-error"
              >
                {validationErrors.description}
              </p>
            )}
          </div>

          {/* Statut (non modifiable ici) */}
          <div className="space-y-1.5 pt-2 border-t border-deep/40">
            <div className="text-xs font-medium text-teal">Statut du dossier (lecture seule)</div>
            <div className="flex items-center gap-3">
              <CasesStatusBadge status={caseData.status} />
              <span className="text-[11px] text-teal italic">
                Modification du statut réservée à la Story F2.2
              </span>
            </div>
          </div>
        </div>

        {/* Colonne droite : Champs non modifiables tant que le contrat OpenAPI ne les prévoit pas */}
        <div className="p-5 rounded border border-deep bg-ink space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-mist">Champs techniques non modifiables</h2>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-deep/30 text-teal border border-deep">
              {CONTRACT_ALIGNMENT_REQUIRED_LABEL}
            </span>
          </div>

          <div className="p-3 rounded bg-deep/10 border border-deep text-xs text-teal flex items-start gap-2">
            <Info className="w-4 h-4 text-cyan flex-shrink-0 mt-0.5" aria-hidden="true" />
            <p>
              Les champs ci-dessous ne sont pas encore déclarés dans la spécification OpenAPI cible.
              Conformément aux règles d'architecture, ils restent en lecture seule et affichés «{' '}
              {CONTRACT_ALIGNMENT_REQUIRED_LABEL} » jusqu'au réalignement back-end.
            </p>
          </div>

          {/* Date de l'incident (non modifiable) */}
          <div className="space-y-1">
            <div className="flex items-center justify-between text-xs text-teal">
              <span className="flex items-center gap-1.5">
                <Calendar className="w-3.5 h-3.5 text-cyan" aria-hidden="true" />
                Date de l'incident (UTC)
              </span>
              <span className="text-[10px] font-mono text-teal">
                {CONTRACT_ALIGNMENT_REQUIRED_LABEL}
              </span>
            </div>
            <input
              type="text"
              disabled
              value={
                caseData.incident_date
                  ? formatUtcDateTime(caseData.incident_date)
                  : 'Non renseignée'
              }
              className="w-full px-3 py-2 rounded border border-deep bg-deep/20 text-xs text-mist font-mono opacity-80 cursor-not-allowed"
              data-testid="edit-incident-date-disabled"
            />
          </div>

          {/* Systèmes concernés (non modifiables) */}
          <div className="space-y-1">
            <div className="flex items-center justify-between text-xs text-teal">
              <span className="flex items-center gap-1.5">
                <Server className="w-3.5 h-3.5 text-cyan" aria-hidden="true" />
                Systèmes concernés
              </span>
              <span className="text-[10px] font-mono text-teal">
                {CONTRACT_ALIGNMENT_REQUIRED_LABEL}
              </span>
            </div>
            <input
              type="text"
              disabled
              value={caseData.affected_systems || 'Aucun système spécifié'}
              className="w-full px-3 py-2 rounded border border-deep bg-deep/20 text-xs text-mist opacity-80 cursor-not-allowed"
              data-testid="edit-affected-systems-disabled"
            />
          </div>
        </div>
      </div>
    </form>
  )
}
