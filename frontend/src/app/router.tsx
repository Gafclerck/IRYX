import { createBrowserRouter } from 'react-router-dom'
import { LoginPage } from '../pages/LoginPage'
import { NotFoundPage } from '../pages/NotFoundPage'
import { AuthGuard } from '../features/auth/components/AuthGuard'
import { AuthenticatedLayout } from '../components/layout/AuthenticatedLayout'

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
    element: (
      <AuthGuard>
        <AuthenticatedLayout />
      </AuthGuard>
    ),
    children: [
      {
        path: '/cases',
        element: (
          <div className="flex min-h-[calc(100vh-56px)] items-center justify-center bg-ink text-mist">
            <p className="text-sm text-teal">Espace dossiers d'investigation</p>
          </div>
        ),
      },
    ],
  },
  {
    path: '*',
    element: <NotFoundPage />,
  },
])
