import { createBrowserRouter } from 'react-router-dom'
import { LoginPage } from '../pages/LoginPage'
import { NotFoundPage } from '../pages/NotFoundPage'
import { AuthGuard } from '../features/auth/components/AuthGuard'

export const router = createBrowserRouter([
  {
    path: '/',
    element: <LoginPage />,
  },
  {
    path: '/login',
    element: <LoginPage />,
  },
  {
    path: '/cases',
    element: (
      <AuthGuard>
        <div className="flex min-h-screen items-center justify-center bg-ink text-mist">
          <p className="text-sm text-teal">Espace dossiers d'investigation</p>
        </div>
      </AuthGuard>
    ),
  },
  {
    path: '*',
    element: <NotFoundPage />,
  },
])
