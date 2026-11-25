import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { NotFoundPage } from '../pages/NotFoundPage'

describe('NotFoundPage', () => {
  it('affiche un écran 404 neutre avec lien vers la racine sans page daudit', () => {
    render(
      <MemoryRouter>
        <NotFoundPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('404')).toBeInTheDocument()
    expect(screen.getByText('Page non trouvée')).toBeInTheDocument()
    const link = screen.getByRole('link', { name: /retour à l'accueil/i })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', '/')

    // Vérifie qu'aucun lien vers un écran d'audit n'est exposé (DP-02)
    expect(screen.queryByText(/audit/i)).not.toBeInTheDocument()
  })
})
