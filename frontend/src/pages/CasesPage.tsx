import { useState } from 'react'
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
} from '../features/cases/components'

/**
 * Écran de consultation paginée et recherche des dossiers d'investigation (Story F1.6).
 * Route : /cases (dans AuthenticatedLayout avec TopBar permanente).
 *
 * RÈGLES DE CONCEPTION :
 * 1. Pagination côté serveur stricte : transmet la page et la taille demandées.
 * 2. Recherche textuelle différée : requête déclenchée après une courte pause de frappe.
 * 3. Interaction : un changement de recherche réinitialise systématiquement la vue à la page 1.
 * 4. Les cinq états obligatoires : chargement, vide, erreur, accès refusé, nominal.
 * 5. Aucun bouton de création pour l'instant (réservé à la modale F1.7).
 * 6. Aucune écriture dans localStorage ni sessionStorage.
 */
export function CasesPage() {
  const [searchInput, setSearchInput] = useState('')
  const [page, setPage] = useState(1)

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

  return (
    <div className="w-full px-4 py-6 sm:px-6 lg:px-8 space-y-6" data-testid="cases-page">
      {/* En-tête de section et barre d'outils */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-mist">Dossiers d'investigation</h1>
          <p className="text-xs text-teal mt-1">
            Panorama et gestion des affaires ouvertes au sein de l'organisation
          </p>
        </div>

        {/* Champ de recherche textuelle */}
        <CasesSearchBar value={searchInput} onChange={handleSearchChange} disabled={isForbidden} />
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
    </div>
  )
}
