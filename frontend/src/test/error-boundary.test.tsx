import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ErrorBoundary } from '../components/feedback/ErrorBoundary'

function FaultyComponent(): never {
  throw new Error('Défaillance simulée du composant racine')
}

describe('ErrorBoundary', () => {
  it('rend les enfants normalement en absence derreur', () => {
    render(
      <ErrorBoundary>
        <div>Contenu nominal</div>
      </ErrorBoundary>,
    )
    expect(screen.getByText('Contenu nominal')).toBeInTheDocument()
  })

  it('capture une exception et affiche le message générique invitant au rechargement', () => {
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    render(
      <ErrorBoundary>
        <FaultyComponent />
      </ErrorBoundary>,
    )

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('Une erreur inattendue est survenue')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /recharger la page/i })).toBeInTheDocument()

    consoleErrorSpy.mockRestore()
  })
})
