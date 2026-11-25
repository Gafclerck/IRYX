import { describe, it, expect } from 'vitest'
import { queryClient } from '../app/queryClient'

describe('Configuration TanStack Query', () => {
  it('est monté avec staleTime 30s et gcTime 5min', () => {
    const defaultOptions = queryClient.getDefaultOptions().queries
    expect(defaultOptions?.staleTime).toBe(30 * 1000)
    expect(defaultOptions?.gcTime).toBe(5 * 60 * 1000)
  })
})
