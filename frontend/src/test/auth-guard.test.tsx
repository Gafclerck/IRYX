import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { AuthGuard } from '../features/auth/components/AuthGuard'

describe('AuthGuard', () => {
  it('redirige vers /login si lutilisateur nest pas authentifié', () => {
    render(
      <MemoryRouter initialEntries={['/cases']}>
        <Routes>
          <Route path="/login" element={<div>Page de connexion</div>} />
          <Route
            path="/cases"
            element={
              <AuthGuard isAuthenticated={false}>
                <div>Espace protégé</div>
              </AuthGuard>
            }
          />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByText('Page de connexion')).toBeInTheDocument()
    expect(screen.queryByText('Espace protégé')).not.toBeInTheDocument()
  })

  it('rend les enfants si lutilisateur est authentifié', () => {
    render(
      <MemoryRouter initialEntries={['/cases']}>
        <Routes>
          <Route
            path="/cases"
            element={
              <AuthGuard isAuthenticated={true}>
                <div>Espace protégé</div>
              </AuthGuard>
            }
          />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByText('Espace protégé')).toBeInTheDocument()
  })
})
