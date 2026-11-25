import { Search } from 'lucide-react'

export interface CasesSearchBarProps {
  readonly value: string
  readonly onChange: (value: string) => void
  readonly disabled?: boolean
}

/**
 * Barre de recherche textuelle par titre de dossier (Story F1.6).
 * Supporte la saisie différée côté conteneur pour déclencher la requête après une pause de frappe.
 */
export function CasesSearchBar({ value, onChange, disabled = false }: CasesSearchBarProps) {
  return (
    <div className="relative w-full max-w-md">
      <label htmlFor="cases-search-input" className="sr-only">
        Rechercher un dossier par titre
      </label>
      <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-teal">
        <Search className="h-4 w-4" aria-hidden="true" />
      </div>
      <input
        id="cases-search-input"
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        placeholder="Rechercher par titre..."
        className="w-full rounded border border-deep bg-ink py-2 pl-9 pr-3 text-sm text-mist placeholder:text-teal focus:border-cyan focus:outline-none focus:ring-2 focus:ring-cyan disabled:cursor-not-allowed disabled:bg-deep disabled:text-teal"
        data-testid="cases-search-input"
      />
    </div>
  )
}
