import { useState } from 'react'
import { CheckCircle2, FolderPlus, X } from 'lucide-react'
import { useCases } from '../features/cases/hooks/useCases'
import { useDebounce } from '../features/cases/hooks/useDebounce'
import { SEARCH_DEBOUNCE_DELAY_MS, DEFAULT_PAGE_SIZE } from '../api/cases-types'
import {
  CasesSearchBar,
  CasesTable,
  CasesPagination,
  CasesEmptyState,
  CasesErrorBanner,
  CasesForbiddenBanner,
  CasesLoadingSkeleton,
  CreateCaseModal,
} from '../features/cases/components'

/**
 * Écran de consultation paginée, recherche et création des dossiers d'investigation (Stories F1.6 et F1.7).
 * Route : /cases (dans AuthenticatedLayout avec TopBar permanente).
 *
 * RÈGLES DE CONCEPTION :
 * 1. Pagination côté serveur stricte : transmet la page et la taille demandées.
 * 2. Recherche textuelle différée : requête déclenchée après une courte pause de frappe.
 * 3. Interaction : un changement de recherche réinitialise systématiquement la vue à la page 1.
 * 4. Bouton « Nouveau dossier » ouvrant la modale de création (Story F1.7).
 * 5. Succès de création : fermeture modale, retour page 1, rafraîchissement cache et notification.
 * 6. Les cinq états obligatoires : chargement, vide, erreur, accès refusé, nominal.
 * 7. Aucune écriture dans localStorage ni sessionStorage.
 */
export function CasesPage() {
  const [searchInput, setSearchInput] = useState('')
  const [page, setPage] = useState(1)
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)
  const [successNotification, setSuccessNotification] = useState<string | null>(null)

  // Durée de temporisation de frappe (paramètre d'architecture à décider)
  const debouncedSearch = useDebounce(searchInput, SEARCH_DEBOUNCE_DELAY_MS)

  // Règle d'interaction : un changement de recherche revient à la page 1
  const handleSearchChange = (value: string) => {
    setSearchInput(value)
    setPage(1)
  }

  const { data, isLoading, isError, error, refetch, isFetching } = useCases({
    page,
    limit: DEFAULT_PAGE_SIZE,
    search: debouncedSearch,
  })

  const isForbidden = error?.status === 403

  const handleCreateSuccess = () => {
    setIsCreateModalOpen(false)
    setPage(1)
    setSuccessNotification("Dossier d'investigation créé avec succès.")
  }

  // Présence du bouton « Nouveau dossier » dans la barre d'outils
  const showCreateButton = !isForbidden && (!data || data.items.length > 0)

  return (
    <div className="w-full px-4 py-6 sm:px-6 lg:px-8 space-y-6" data-testid="cases-page">
      {/* Notification de confirmation après création réussie (Story F1.7) */}
      {successNotification && (
        <div
          role="status"
          aria-live="polite"
          className="flex items-center justify-between p-3 rounded bg-cyan text-ink text-sm font-medium"
          data-testid="cases-success-notification"
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

      {/* En-tête de section et barre d'outils */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-mist">Dossiers d'investigation</h1>
          <p className="text-xs text-teal mt-1">
            Panorama et gestion des affaires ouvertes au sein de l'organisation
          </p>
        </div>

        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
          {/* Champ de recherche textuelle */}
          <CasesSearchBar
            value={searchInput}
            onChange={handleSearchChange}
            disabled={isForbidden}
          />

          {/* Bouton Nouveau dossier (Story F1.7) */}
          {showCreateButton && (
            <button
              type="button"
              onClick={() => {
                setSuccessNotification(null)
                setIsCreateModalOpen(true)
              }}
              disabled={isForbidden}
              className="inline-flex items-center justify-center gap-2 px-4 py-2 bg-cyan text-ink text-sm font-semibold rounded hover:bg-mist focus:outline-none focus:ring-2 focus:ring-cyan disabled:bg-deep disabled:text-teal disabled:cursor-not-allowed transition-colors"
              data-testid="create-case-button"
            >
              <FolderPlus className="w-4 h-4" aria-hidden="true" />
              <span>Nouveau dossier</span>
            </button>
          )}
        </div>
      </div>

      {/* Rendu des 5 états obligatoires */}
      {isForbidden ? (
        <CasesForbiddenBanner />
      ) : isError ? (
        <CasesErrorBanner
          message={error?.message || 'Échec du chargement des dossiers.'}
          onRetry={() => refetch()}
        />
      ) : isLoading ? (
        <CasesLoadingSkeleton rowCount={DEFAULT_PAGE_SIZE} />
      ) : !data || data.items.length === 0 ? (
        <CasesEmptyState />
      ) : (
        <div className="space-y-4">
          <CasesTable items={data.items} />
          <CasesPagination
            page={page}
            limit={data.limit}
            total={data.total}
            hasMore={data.has_more}
            onPageChange={setPage}
            disabled={isFetching}
          />
        </div>
      )}

      {/* Modale de création d'un dossier (Story F1.7) */}
      <CreateCaseModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        onSuccess={handleCreateSuccess}
      />
    </div>
  )
}
