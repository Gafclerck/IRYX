import { useState, useEffect } from 'react'
import { SEARCH_DEBOUNCE_DELAY_MS } from '../../../api/cases-types'

/**
 * Hook de temporisation pour la saisie différée de recherche (Story F1.6).
 * Durée de pause de frappe : point d'architecture à décider (SEARCH_DEBOUNCE_DELAY_MS).
 */
export function useDebounce<T>(value: T, delay: number = SEARCH_DEBOUNCE_DELAY_MS): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value)

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value)
    }, delay)

    return () => {
      clearTimeout(handler)
    }
  }, [value, delay])

  return debouncedValue
}
