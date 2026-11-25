import { createBrowserRouter } from 'react-router-dom'
import { LoginPage } from '../pages/LoginPage'
import { NotFoundPage } from '../pages/NotFoundPage'
import { CasesPage } from '../pages/CasesPage'
import { CaseContextPage } from '../pages/CaseContextPage'
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
        element: <CasesPage />,
      },
      {
        path: '/cases/:caseId',
        element: <CaseContextPage />,
      },
    ],
  },
  {
    path: '*',
    element: <NotFoundPage />,
  },
])
