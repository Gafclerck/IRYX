import { useState, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { ArrowLeft, CheckCircle2, X, AlertTriangle, ShieldAlert, FolderX } from 'lucide-react'
import type { UpdateCasePayload } from '../api/cases-types'
import { useCaseDetail } from '../features/cases/hooks/useCaseDetail'
import { useUpdateCase } from '../features/cases/hooks/useUpdateCase'
import {
  CaseSidebar,
  CaseContextLoadingSkeleton,
  CaseContextView,
  CaseContextEditForm,
} from '../features/cases/components'

/**
 * Page de consultation et édition du contexte administratif et technique du dossier (Story F2.1).
 * Route : /cases/:caseId (Étape 1 Contexte dans AuthenticatedLayout).
 *
 * RÈGLES DE CONCEPTION :
 * 1. Les 5 états obligatoires :
 *    - Chargement : squelette animé (CaseContextLoadingSkeleton).
 *    - Nominal : fiche complète avec bouton « Modifier ».
 *    - Vide : mentions textuelles par défaut en couleur teal.
 *    - Erreur 5xx / réseau : notification d'échec avec bouton « Réessayer ».
 *    - Accès refusé (403) : bloque l'affichage sensible, affiche la notification
 *      « Vous n'avez pas accès à ce dossier » et redirige vers /cases.
 *    - Dossier introuvable (404) : message neutre avec bouton de retour.
 * 2. Mode d'édition en ligne :
 *    - Modification du titre et de la description avec validation Zod.
 *    - Envoi en PATCH /api/v1/cases/:caseId.
 *    - Conservation des saisies en cas d'erreur de sauvegarde (NFR-ERR-02).
 *    - Champs non prévus au contrat affichés « à réaligner » et non éditables.
 * 3. Aucune écriture dans localStorage ni sessionStorage.
 */
export function CaseContextPage() {
  const { caseId } = useParams<{ caseId: string }>()
  const navigate = useNavigate()

  const [isEditing, setIsEditing] = useState(false)
  const [successNotification, setSuccessNotification] = useState<string | null>(null)
  const [lastSavedPayload, setLastSavedPayload] = useState<UpdateCasePayload | null>(null)

  const { data: caseData, isLoading, isError, error, refetch } = useCaseDetail(caseId)

  const {
    mutateAsync: updateCaseMutation,
    isPending: isSaving,
    error: updateError,
    reset: resetUpdateError,
  } = useUpdateCase()

  const isForbidden = error?.status === 403
  const isNotFound = error?.status === 404

  // Redirection automatique vers /cases en cas de 403 Forbidden
  useEffect(() => {
    if (isForbidden) {
      const timer = setTimeout(() => {
        navigate('/cases', {
          replace: true,
          state: { forbiddenError: "Vous n'avez pas accès à ce dossier" },
        })
      }, 1200)
      return () => clearTimeout(timer)
    }
  }, [isForbidden, navigate])

  const handleSave = async (payload: UpdateCasePayload) => {
    if (!caseId) return
    setLastSavedPayload(payload)
    try {
      await updateCaseMutation({ caseId, payload })
      setIsEditing(false)
      setSuccessNotification("Dossier d'investigation mis à jour avec succès.")
    } catch {
      // L'erreur est gérée via updateError et affichée dans le formulaire
    }
  }

  const handleRetrySave = () => {
    if (lastSavedPayload && caseId) {
      resetUpdateError()
      handleSave(lastSavedPayload)
    }
  }

  const handleCancelEdit = () => {
    resetUpdateError()
    setLastSavedPayload(null)
    setIsEditing(false)
  }

  // 1. ÉTAT D'ACCÈS REFUSÉ (HTTP 403 FORBIDDEN)
  if (isForbidden) {
    return (
      <div
        className="w-full max-w-4xl mx-auto px-4 py-8 space-y-4"
        data-testid="case-forbidden-state"
      >
        <div
          role="alert"
          aria-live="assertive"
          className="p-4 rounded border border-deep bg-deep/20 text-mist flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3"
          data-testid="forbidden-notification"
        >
          <div className="flex items-center gap-2.5">
            <ShieldAlert className="w-5 h-5 text-teal flex-shrink-0" aria-hidden="true" />
            <span className="text-sm font-medium">Vous n'avez pas accès à ce dossier</span>
          </div>
          <button
            type="button"
            onClick={() => navigate('/cases')}
            className="px-3.5 py-1.5 rounded bg-deep text-mist text-xs font-semibold hover:bg-teal hover:text-ink transition-colors focus:outline-none focus:ring-2 focus:ring-cyan"
            data-testid="forbidden-back-btn"
          >
            Retour aux dossiers
          </button>
        </div>
      </div>
    )
  }

  // 2. ÉTAT INTROUVABLE (HTTP 404 NOT FOUND)
  if (isNotFound) {
    return (
      <div
        className="w-full max-w-2xl mx-auto px-4 py-12 text-center space-y-4"
        data-testid="case-not-found-state"
      >
        <div className="p-8 rounded border border-deep bg-ink space-y-4">
          <FolderX className="w-10 h-10 text-teal mx-auto" aria-hidden="true" />
          <div className="space-y-1">
            <h1 className="text-base font-bold text-mist">Dossier introuvable</h1>
            <p className="text-xs text-teal">Le dossier demandé n'existe pas ou a été archivé.</p>
          </div>
          <div>
            <Link
              to="/cases"
              className="inline-flex items-center gap-2 px-4 py-2 rounded bg-deep text-mist text-xs font-semibold hover:bg-teal hover:text-ink focus:outline-none focus:ring-2 focus:ring-cyan transition-colors"
              data-testid="not-found-back-link"
            >
              <ArrowLeft className="w-3.5 h-3.5" aria-hidden="true" />
              <span>Retour aux dossiers</span>
            </Link>
          </div>
        </div>
      </div>
    )
  }

  // 3. ÉTAT D'ERREUR TECHNIQUE DU CHARGEMENT (HTTP 5xx / RÉSEAU)
  if (isError) {
    return (
      <div className="w-full max-w-4xl mx-auto px-4 py-8 space-y-4" data-testid="case-error-state">
        <div
          role="alert"
          aria-live="assertive"
          className="p-4 rounded border border-deep bg-deep/20 text-mist flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3"
          data-testid="case-load-error-banner"
        >
          <div className="flex items-center gap-2.5">
            <AlertTriangle className="w-5 h-5 text-teal flex-shrink-0" aria-hidden="true" />
            <span className="text-xs font-medium">
              {error?.message || 'Erreur lors du chargement des informations du dossier.'}
            </span>
          </div>
          <button
            type="button"
            onClick={() => refetch()}
            className="px-3.5 py-1.5 rounded bg-deep text-mist text-xs font-semibold hover:bg-teal hover:text-ink transition-colors focus:outline-none focus:ring-2 focus:ring-cyan"
            data-testid="retry-load-btn"
          >
            Réessayer
          </button>
        </div>
      </div>
    )
  }

  // 4. ÉTAT DE CHARGEMENT INITIAL (SQUELETTE)
  if (isLoading || !caseData) {
    return (
      <div className="flex flex-col md:flex-row min-h-[calc(100vh-56px)]">
        <aside className="w-full md:w-64 border-b md:border-b-0 md:border-r border-deep bg-ink p-4 space-y-4 animate-pulse">
          <div className="h-4 w-24 bg-deep/30 rounded" />
          <div className="h-6 w-44 bg-deep/40 rounded" />
          <div className="h-8 w-full bg-deep/20 rounded" />
        </aside>
        <div className="flex-1 p-6">
          <CaseContextLoadingSkeleton />
        </div>
      </div>
    )
  }

  // 5. ÉTAT NOMINAL ET ÉDITION
  return (
    <div
      className="flex flex-col md:flex-row min-h-[calc(100vh-56px)]"
      data-testid="case-context-page"
    >
      {/* Barre latérale de navigation séquentielle */}
      <CaseSidebar caseId={caseData.id} caseTitle={caseData.title} />

      {/* Contenu principal de l'étape 1 Contexte */}
      <div className="flex-1 px-4 py-6 sm:px-6 lg:px-8 space-y-6">
        {/* Fil d'Ariane / Retour vers la liste des dossiers */}
        <div className="flex items-center justify-between">
          <Link
            to="/cases"
            className="inline-flex items-center gap-1.5 text-xs text-teal hover:text-cyan focus:outline-none focus:ring-1 focus:ring-cyan rounded transition-colors"
            data-testid="back-to-cases-link"
          >
            <ArrowLeft className="w-3.5 h-3.5" aria-hidden="true" />
            <span>Retour à la liste des dossiers</span>
          </Link>
        </div>

        {/* Notification de confirmation après mise à jour réussie */}
        {successNotification && (
          <div
            role="status"
            aria-live="polite"
            className="flex items-center justify-between p-3 rounded bg-cyan text-ink text-sm font-semibold"
            data-testid="case-update-success-notification"
          >
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5 flex-shrink-0" aria-hidden="true" />
              <span>{successNotification}</span>
            </div>
            <button
              type="button"
              onClick={() => setSuccessNotification(null)}
              className="rounded p-1 text-ink hover:text-deep focus:outline-none"
              aria-label="Fermer la notification"
            >
              <X className="w-4 h-4" aria-hidden="true" />
            </button>
          </div>
        )}

        {/* Bascule entre vue nominale et mode d'édition en ligne */}
        {isEditing ? (
          <CaseContextEditForm
            caseData={caseData}
            onCancel={handleCancelEdit}
            onSave={handleSave}
            isSaving={isSaving}
            saveError={updateError}
            onRetrySave={handleRetrySave}
          />
        ) : (
          <CaseContextView caseData={caseData} onEdit={() => setIsEditing(true)} />
        )}
      </div>
    </div>
  )
}
