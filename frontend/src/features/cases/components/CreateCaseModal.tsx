import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { AlertCircle, FolderPlus, Loader2, RefreshCw, X } from 'lucide-react'
import { createCaseSchema, type CreateCaseFormValues } from '../schemas/createCaseSchema'
import { useCreateCase } from '../hooks/useCreateCase'
import { INCIDENT_TYPE_OPTIONS, type CreateCaseResponse } from '../../../api/cases-types'
import { CaseCreationError } from '../../../api/cases'

export interface CreateCaseModalProps {
  readonly isOpen: boolean
  readonly onClose: () => void
  readonly onSuccess: (createdCase: CreateCaseResponse) => void
}

/**
 * Modale de création d'un nouveau dossier d'investigation (Story F1.7).
 *
 * RÈGLES DE CONCEPTION :
 * 1. Validation Zod avant envoi, tous les messages formulés en français.
 * 2. Focus placé sur le champ titre à l'ouverture, date courante UTC pré-remplie.
 * 3. En cas d'erreur serveur (400, 403, 5xx ou réseau) : modale maintenue ouverte,
 *    textes saisis strictement conservés en mémoire vive (NFR-ERR-02).
 * 4. Erreur 5xx ou réseau : affichage explicite avec bouton « Réessayer ».
 * 5. Respect absolu de la palette stricte à cinq couleurs, aucune couleur en dur.
 * 6. Aucune écriture dans localStorage ni sessionStorage.
 */
export function CreateCaseModal({ isOpen, onClose, onSuccess }: CreateCaseModalProps) {
  const [serverError, setServerError] = useState<{
    message: string
    isRetryable: boolean
  } | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
    setError,
    reset,
    setFocus,
  } = useForm<CreateCaseFormValues>({
    resolver: zodResolver(createCaseSchema),
    mode: 'onSubmit',
    defaultValues: {
      title: '',
      incident_date: '',
      incident_type: 'a_decider',
      affected_systems: '',
      description: '',
    },
  })

  // Réinitialisation et positionnement du focus à l'ouverture de la modale
  useEffect(() => {
    if (isOpen) {
      setServerError(null)
      const nowUtcString = new Date().toISOString().slice(0, 16)
      reset({
        title: '',
        incident_date: nowUtcString,
        incident_type: 'a_decider',
        affected_systems: '',
        description: '',
      })
      const timer = setTimeout(() => {
        setFocus('title')
      }, 50)
      return () => clearTimeout(timer)
    }
  }, [isOpen, reset, setFocus])

  const createCaseMutation = useCreateCase()
  const isPending = isSubmitting || createCaseMutation.isPending

  if (!isOpen) {
    return null
  }

  const onSubmit = async (values: CreateCaseFormValues) => {
    setServerError(null)
    try {
      const createdCase = await createCaseMutation.mutateAsync({
        title: values.title.trim(),
        incident_date: values.incident_date.trim(),
        incident_type: values.incident_type.trim(),
        affected_systems: values.affected_systems.trim(),
        description: values.description.trim(),
      })
      onClose()
      onSuccess(createdCase)
    } catch (err) {
      if (err instanceof CaseCreationError) {
        if (err.fieldErrors && Object.keys(err.fieldErrors).length > 0) {
          for (const [field, msg] of Object.entries(err.fieldErrors)) {
            setError(field as keyof CreateCaseFormValues, { message: msg })
          }
        }
        const isRetryable = err.status === 0 || err.status >= 500
        setServerError({
          message: err.message,
          isRetryable,
        })
      } else {
        setServerError({
          message:
            err instanceof Error
              ? err.message
              : 'Une erreur imprévue est survenue lors de la création du dossier.',
          isRetryable: true,
        })
      }
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink"
      role="dialog"
      aria-modal="true"
      aria-labelledby="create-case-modal-title"
      data-testid="create-case-modal"
    >
      <div className="relative w-full max-w-2xl rounded border border-deep bg-ink p-6 shadow-2xl space-y-5 text-mist">
        {/* En-tête de la modale */}
        <div className="flex items-center justify-between border-b border-deep pb-4">
          <div className="flex items-center gap-2">
            <FolderPlus className="w-5 h-5 text-cyan" aria-hidden="true" />
            <h2
              id="create-case-modal-title"
              className="text-lg font-bold text-mist"
              data-testid="create-case-modal-title"
            >
              Nouveau dossier d'investigation
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isPending}
            className="rounded p-1 text-teal hover:text-mist hover:bg-deep focus:outline-none focus:ring-2 focus:ring-cyan disabled:cursor-not-allowed"
            aria-label="Fermer la modale"
            data-testid="create-case-close-button"
          >
            <X className="w-5 h-5" aria-hidden="true" />
          </button>
        </div>

        {/* Bannière d'erreur serveur ou réseau */}
        {serverError && (
          <div
            role="alert"
            className="flex items-center justify-between gap-3 p-3 rounded bg-cyan text-ink text-sm font-medium"
            data-testid="create-case-server-error"
          >
            <div className="flex items-center gap-2">
              <AlertCircle className="w-5 h-5 flex-shrink-0" aria-hidden="true" />
              <div>
                <span className="font-bold">ÉCHEC : </span>
                <span>{serverError.message}</span>
              </div>
            </div>
            {serverError.isRetryable && (
              <button
                type="button"
                onClick={handleSubmit(onSubmit)}
                disabled={isPending}
                className="inline-flex items-center gap-1 px-3 py-1 bg-ink text-cyan text-xs font-semibold rounded border border-cyan hover:bg-deep focus:outline-none focus:ring-2 focus:ring-cyan disabled:cursor-not-allowed flex-shrink-0"
                data-testid="create-case-retry-button"
              >
                <RefreshCw className="w-3.5 h-3.5" aria-hidden="true" />
                <span>Réessayer</span>
              </button>
            )}
          </div>
        )}

        {/* Formulaire de création */}
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          {/* Champ : Titre du dossier */}
          <div>
            <label
              htmlFor="create-case-title"
              className="block text-xs font-semibold uppercase tracking-wide text-mist mb-1"
            >
              Titre du dossier *
            </label>
            <input
              id="create-case-title"
              type="text"
              disabled={isPending}
              aria-invalid={errors.title ? 'true' : 'false'}
              aria-describedby={errors.title ? 'create-case-title-error' : undefined}
              placeholder="ex. Incident Ransomware sur serveurs de fichiers"
              className="w-full px-3 py-2 bg-ink border border-deep rounded text-mist placeholder-teal focus:outline-none focus:ring-2 focus:ring-cyan focus:border-cyan disabled:bg-deep disabled:text-teal disabled:cursor-not-allowed text-sm"
              {...register('title')}
            />
            {errors.title && (
              <p
                id="create-case-title-error"
                className="mt-1 text-xs text-cyan flex items-center gap-1"
                role="alert"
                data-testid="create-case-title-error"
              >
                <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" aria-hidden="true" />
                <span>{errors.title.message}</span>
              </p>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Champ : Date de l'incident (UTC) */}
            <div>
              <label
                htmlFor="create-case-incident-date"
                className="block text-xs font-semibold uppercase tracking-wide text-mist mb-1"
              >
                Date de l'incident (UTC) *
              </label>
              <input
                id="create-case-incident-date"
                type="datetime-local"
                disabled={isPending}
                aria-invalid={errors.incident_date ? 'true' : 'false'}
                aria-describedby={
                  errors.incident_date ? 'create-case-incident-date-error' : undefined
                }
                className="w-full px-3 py-2 bg-ink border border-deep rounded text-mist focus:outline-none focus:ring-2 focus:ring-cyan focus:border-cyan disabled:bg-deep disabled:text-teal disabled:cursor-not-allowed text-sm"
                {...register('incident_date')}
              />
              {errors.incident_date && (
                <p
                  id="create-case-incident-date-error"
                  className="mt-1 text-xs text-cyan flex items-center gap-1"
                  role="alert"
                  data-testid="create-case-incident-date-error"
                >
                  <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" aria-hidden="true" />
                  <span>{errors.incident_date.message}</span>
                </p>
              )}
            </div>

            {/* Champ : Type d'incident (liste contrôlée) */}
            <div>
              <label
                htmlFor="create-case-incident-type"
                className="block text-xs font-semibold uppercase tracking-wide text-mist mb-1"
              >
                Type d'incident *
              </label>
              <select
                id="create-case-incident-type"
                disabled={isPending}
                aria-invalid={errors.incident_type ? 'true' : 'false'}
                aria-describedby={
                  errors.incident_type ? 'create-case-incident-type-error' : undefined
                }
                className="w-full px-3 py-2 bg-ink border border-deep rounded text-mist focus:outline-none focus:ring-2 focus:ring-cyan focus:border-cyan disabled:bg-deep disabled:text-teal disabled:cursor-not-allowed text-sm"
                {...register('incident_type')}
              >
                {INCIDENT_TYPE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              {errors.incident_type && (
                <p
                  id="create-case-incident-type-error"
                  className="mt-1 text-xs text-cyan flex items-center gap-1"
                  role="alert"
                  data-testid="create-case-incident-type-error"
                >
                  <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" aria-hidden="true" />
                  <span>{errors.incident_type.message}</span>
                </p>
              )}
            </div>
          </div>

          {/* Champ : Systèmes concernés */}
          <div>
            <label
              htmlFor="create-case-affected-systems"
              className="block text-xs font-semibold uppercase tracking-wide text-mist mb-1"
            >
              Systèmes concernés *
            </label>
            <input
              id="create-case-affected-systems"
              type="text"
              disabled={isPending}
              aria-invalid={errors.affected_systems ? 'true' : 'false'}
              aria-describedby={
                errors.affected_systems ? 'create-case-affected-systems-error' : undefined
              }
              placeholder="ex. Active Directory DS, Serveurs de fichiers, Postes VIP"
              className="w-full px-3 py-2 bg-ink border border-deep rounded text-mist placeholder-teal focus:outline-none focus:ring-2 focus:ring-cyan focus:border-cyan disabled:bg-deep disabled:text-teal disabled:cursor-not-allowed text-sm"
              {...register('affected_systems')}
            />
            {errors.affected_systems && (
              <p
                id="create-case-affected-systems-error"
                className="mt-1 text-xs text-cyan flex items-center gap-1"
                role="alert"
                data-testid="create-case-affected-systems-error"
              >
                <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" aria-hidden="true" />
                <span>{errors.affected_systems.message}</span>
              </p>
            )}
          </div>

          {/* Champ : Description factuelle */}
          <div>
            <label
              htmlFor="create-case-description"
              className="block text-xs font-semibold uppercase tracking-wide text-mist mb-1"
            >
              Description factuelle *
            </label>
            <textarea
              id="create-case-description"
              rows={4}
              disabled={isPending}
              aria-invalid={errors.description ? 'true' : 'false'}
              aria-describedby={errors.description ? 'create-case-description-error' : undefined}
              placeholder="Décrivez les premiers faits constatés, l'étendue de la compromission et les actions immédiates entreprises..."
              className="w-full px-3 py-2 bg-ink border border-deep rounded text-mist placeholder-teal focus:outline-none focus:ring-2 focus:ring-cyan focus:border-cyan disabled:bg-deep disabled:text-teal disabled:cursor-not-allowed text-sm resize-none"
              {...register('description')}
            />
            {errors.description && (
              <p
                id="create-case-description-error"
                className="mt-1 text-xs text-cyan flex items-center gap-1"
                role="alert"
                data-testid="create-case-description-error"
              >
                <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" aria-hidden="true" />
                <span>{errors.description.message}</span>
              </p>
            )}
          </div>

          {/* Barre d'actions */}
          <div className="flex items-center justify-end gap-3 pt-3 border-t border-deep">
            <button
              type="button"
              onClick={onClose}
              disabled={isPending}
              className="px-4 py-2 border border-deep text-mist hover:bg-deep focus:outline-none focus:ring-2 focus:ring-cyan text-sm font-medium rounded disabled:text-teal disabled:cursor-not-allowed"
              data-testid="create-case-cancel-button"
            >
              Annuler
            </button>
            <button
              type="submit"
              disabled={isPending}
              className="inline-flex items-center gap-2 px-4 py-2 bg-cyan text-ink hover:bg-mist focus:outline-none focus:ring-2 focus:ring-cyan text-sm font-semibold rounded disabled:bg-deep disabled:text-teal disabled:cursor-not-allowed"
              data-testid="create-case-submit-button"
            >
              {isPending ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                  <span>Création en cours...</span>
                </>
              ) : (
                <span>Créer le dossier</span>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
