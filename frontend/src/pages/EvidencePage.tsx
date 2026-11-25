import { useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  ArrowLeft,
  AlertTriangle,
  ShieldAlert,
  FolderX,
  X,
  ShieldCheck,
  RotateCw,
} from 'lucide-react'
import { useCaseDetail } from '../features/cases/hooks/useCaseDetail'
import { useSessionUser } from '../features/auth/hooks/useSessionUser'
import { CaseSidebar } from '../features/cases/components/CaseSidebar'
import { EvidenceDropZone, EvidenceUploadList, useEvidenceUpload } from '../features/evidence'

/**
 * Page d'acquisition et de téléversement de preuves avec progression en streaming (Story F3.1).
 * Route : /cases/:caseId/evidence (Étape 2 Preuves dans AuthenticatedLayout).
 *
 * RÈGLES DE CONCEPTION (FR-EVI-01, D-38, 11-ecrans-et-routes.md, 12-parcours-et-etats.md) :
 * 1. Intégrée dans AuthenticatedLayout avec la barre latérale CaseSidebar (étape 2 active).
 * 2. Zone de dépôt avec glisser-déposer et sélection multiple.
 * 3. Envoi par XMLHttpRequest individuel (D-38) vers POST /api/v1/cases/:caseId/evidences avec Authorization: Bearer.
 * 4. Chaque fichier affiche son nom, sa taille formatée, sa progression en direct et son statut.
 * 5. Après envoi réussi : statut « en attente d'ingestion » affiché tel quel (sans interrogation Celery ici, réservée à F3.2).
 * 6. Formats refusés immédiatement côté client avec motif explicite sans émission de requête.
 * 7. Aucune limite volumétrique imposée côté client (« à caler C3 ») ; le serveur refuse au-delà et le front affiche son refus.
 * 8. En cas d'échec ou d'interruption : bouton « Réessayer » par fichier.
 * 9. Bouton « Annuler » actif pendant le transfert.
 * 10. Accès lecture seule (viewer) : zone de dépôt désactivée et masquée.
 * 11. Palette stricte (ink, deep, teal, cyan, mist) sans aucun code hexadécimal en dur.
 */
export function EvidencePage() {
  const { caseId } = useParams<{ caseId: string }>()
  const navigate = useNavigate()
  const sessionUser = useSessionUser()

  const safeCaseId = caseId || ''
  const { data: caseData, isLoading, isError, error, refetch } = useCaseDetail(safeCaseId)

  const {
    uploadItems,
    rejectedFiles,
    addFiles,
    cancelUpload,
    retryUpload,
    dismissRejectedFile,
    clearRejectedFiles,
  } = useEvidenceUpload({ caseId: safeCaseId })

  const isForbidden = error?.status === 403
  const isNotFound = error?.status === 404

  // Rôle lecture seule (ex. profil viewer)
  const isReadOnly =
    sessionUser?.role === 'viewer' ||
    Boolean(
      caseData?.members &&
      sessionUser?.userName &&
      caseData.members.some(
        (m) =>
          (m.email === sessionUser.userName || m.name === sessionUser.userName) &&
          m.role === 'viewer',
      ),
    )

  // Redirection automatique vers /cases en cas de 403 Forbidden sur le dossier
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

  return (
    <div className="flex flex-col md:flex-row min-h-[calc(100vh-56px)] bg-ink text-mist">
      {/* Barre latérale du dossier (Étape 2 Preuves) */}
      <CaseSidebar caseId={safeCaseId} caseTitle={caseData?.title || 'Dossier d’investigation'} />

      {/* Zone de contenu principale */}
      <div className="flex-1 overflow-y-auto p-4 md:p-8">
        <div className="mx-auto max-w-5xl space-y-6">
          {/* Fil d'Ariane et retour */}
          <div className="flex items-center space-x-2 text-xs text-mist/70">
            <Link
              to="/cases"
              className="inline-flex items-center gap-1 hover:text-cyan focus:outline-none focus:ring-2 focus:ring-cyan rounded"
              aria-label="Retour à la liste des dossiers"
            >
              <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Dossiers</span>
            </Link>
            <span>/</span>
            <Link
              to={`/cases/${safeCaseId}`}
              className="hover:text-cyan focus:outline-none focus:ring-2 focus:ring-cyan rounded truncate max-w-[200px]"
            >
              {caseData?.title || safeCaseId}
            </Link>
            <span>/</span>
            <span className="text-teal font-medium">Preuves</span>
          </div>

          {/* En-tête de l'étape 2 */}
          <div className="border-b border-deep pb-4">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <span className="inline-block text-xs font-semibold uppercase tracking-wider text-teal">
                  Étape 2 du canevas
                </span>
                <h1 className="text-2xl font-bold tracking-tight text-mist">
                  Registre et téléversement des preuves
                </h1>
              </div>
              <div className="flex items-center gap-2 rounded border border-deep bg-deep/20 px-3 py-1.5 text-xs text-mist">
                <ShieldCheck className="h-4 w-4 text-cyan" aria-hidden="true" />
                <span>Chaîne de possession & scellement SHA-256</span>
              </div>
            </div>
            <p className="mt-2 text-sm text-mist/80">
              Espace d'acquisition, de scellement cryptographique et d'inventaire des éléments
              matériels de l'enquête.
            </p>
          </div>

          {/* État de chargement du dossier */}
          {isLoading && (
            <div
              className="space-y-4 rounded-lg border border-deep bg-deep/10 p-6 animate-pulse"
              data-testid="evidence-page-loading"
              aria-label="Chargement du dossier"
            >
              <div className="h-6 w-1/3 rounded bg-deep"></div>
              <div className="h-32 rounded bg-deep/40"></div>
              <div className="h-24 rounded bg-deep/40"></div>
            </div>
          )}

          {/* État 403 Forbidden sur le dossier */}
          {isForbidden && (
            <div
              role="alert"
              className="rounded-lg border border-deep bg-deep/40 p-6 text-mist shadow-lg"
              data-testid="case-forbidden-banner"
            >
              <div className="flex items-start space-x-3">
                <ShieldAlert
                  className="h-6 w-6 flex-shrink-0 text-cyan mt-0.5"
                  aria-hidden="true"
                />
                <div className="space-y-1">
                  <h3 className="text-base font-bold text-mist uppercase tracking-wide">
                    Accès non autorisé
                  </h3>
                  <p className="text-sm text-mist/90">
                    Vous n'avez pas accès à ce dossier. Redirection en cours vers la liste des
                    dossiers...
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* État 404 Dossier introuvable */}
          {isNotFound && (
            <div
              role="alert"
              className="rounded-lg border border-deep bg-deep/20 p-8 text-center space-y-4"
              data-testid="case-not-found"
            >
              <div className="flex justify-center">
                <FolderX className="h-12 w-12 text-teal" aria-hidden="true" />
              </div>
              <h2 className="text-lg font-bold text-mist">Dossier d’investigation introuvable</h2>
              <p className="text-sm text-mist/80 max-w-md mx-auto">
                Le dossier demandé n'existe pas ou a été déplacé.
              </p>
              <div>
                <Link
                  to="/cases"
                  className="inline-flex items-center gap-2 rounded bg-teal px-4 py-2 text-sm font-semibold text-ink hover:bg-cyan focus:outline-none focus:ring-2 focus:ring-cyan"
                >
                  <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                  <span>Retour aux dossiers</span>
                </Link>
              </div>
            </div>
          )}

          {/* État Erreur 5xx / Réseau sur le dossier */}
          {isError && !isForbidden && !isNotFound && (
            <div
              role="alert"
              className="rounded-lg border border-deep bg-deep/40 p-6 text-mist space-y-3"
              data-testid="case-detail-error"
            >
              <div className="flex items-start space-x-3">
                <AlertTriangle
                  className="h-6 w-6 flex-shrink-0 text-cyan mt-0.5"
                  aria-hidden="true"
                />
                <div>
                  <h3 className="text-base font-bold text-mist">Erreur de chargement du dossier</h3>
                  <p className="text-sm text-mist/90">
                    Impossible de charger les données du dossier. Une anomalie réseau ou serveur est
                    survenue.
                  </p>
                </div>
              </div>
              <div>
                <button
                  type="button"
                  onClick={() => refetch()}
                  className="inline-flex items-center gap-1.5 rounded border border-teal bg-deep px-3 py-1.5 text-xs font-semibold text-cyan hover:bg-deep/80 focus:outline-none focus:ring-2 focus:ring-cyan"
                >
                  <RotateCw className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>Réessayer</span>
                </button>
              </div>
            </div>
          )}

          {/* Contenu nominal du téléversement de preuves */}
          {!isLoading && !isForbidden && !isNotFound && (
            <div className="space-y-6">
              {/* Alerte sur les formats rejetés immédiatement sans émission réseau */}
              {rejectedFiles.length > 0 && (
                <div
                  role="alert"
                  className="rounded-lg border border-teal bg-deep/30 p-4 text-mist space-y-2"
                  data-testid="evidence-rejected-banner"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <AlertTriangle className="h-4 w-4 text-cyan" aria-hidden="true" />
                      <h4 className="text-xs font-bold uppercase tracking-wider text-mist">
                        Fichier(s) refusé(s) à l’ingestion ({rejectedFiles.length})
                      </h4>
                    </div>
                    <button
                      type="button"
                      onClick={clearRejectedFiles}
                      className="rounded p-1 text-mist/70 hover:text-cyan focus:outline-none focus:ring-2 focus:ring-cyan"
                      aria-label="Fermer l'alerte des fichiers refusés"
                    >
                      <X className="h-4 w-4" aria-hidden="true" />
                    </button>
                  </div>
                  <ul className="space-y-1 text-xs text-mist/90 list-disc list-inside">
                    {rejectedFiles.map((rf, idx) => (
                      <li
                        key={`${rf.name}-${idx}`}
                        className="flex items-start justify-between gap-2"
                      >
                        <span>{rf.reason}</span>
                        <button
                          type="button"
                          onClick={() => dismissRejectedFile(idx)}
                          className="text-mist/60 hover:text-cyan ml-2"
                          aria-label={`Ignorer le rejet de ${rf.name}`}
                        >
                          <X className="h-3 w-3" aria-hidden="true" />
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Zone de glisser-déposer de preuves */}
              <section aria-labelledby="dropzone-heading" className="space-y-2">
                <h2 id="dropzone-heading" className="sr-only">
                  Zone de dépôt des preuves
                </h2>
                <EvidenceDropZone
                  onFilesSelected={addFiles}
                  disabled={isReadOnly}
                  readOnlyMessage="Vous disposez d'un accès en lecture seule à ce dossier. Le dépôt de preuves est désactivé."
                />
              </section>

              {/* Suivi des transferts de la session avec progression */}
              <section aria-labelledby="upload-list-heading" className="space-y-2">
                <h2 id="upload-list-heading" className="sr-only">
                  Suivi des preuves téléversées
                </h2>
                <EvidenceUploadList
                  items={uploadItems}
                  onCancel={cancelUpload}
                  onRetry={retryUpload}
                />
              </section>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
