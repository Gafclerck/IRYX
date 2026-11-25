import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { LoadingFallback } from '../components/feedback/LoadingFallback'

describe('LoadingFallback', () => {
  it("affiche l'indicateur de chargement stylisé avec le message par défaut", () => {
    render(<LoadingFallback />)
    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.getByText("Chargement de l'application...")).toBeInTheDocument()
  })

  it('affiche un message personnalisé si fourni', () => {
    render(<LoadingFallback message="Chargement des modules..." />)
    expect(screen.getByText('Chargement des modules...')).toBeInTheDocument()
  })
})
