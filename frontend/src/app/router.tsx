import { createBrowserRouter } from 'react-router-dom'
import { LoginPage } from '../pages/LoginPage'
import { NotFoundPage } from '../pages/NotFoundPage'
import { CasesPage } from '../pages/CasesPage'
import { CaseContextPage } from '../pages/CaseContextPage'
import { EvidencePage } from '../pages/EvidencePage'
import { PlanPage } from '../pages/PlanPage'
import { RunPage } from '../pages/RunPage'
import { ResultsPage } from '../pages/ResultsPage'
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
      {
        path: '/cases/:caseId/evidence',
        element: <EvidencePage />,
      },
      {
        path: '/cases/:caseId/evidence/:evidenceId',
        element: <EvidencePage />,
      },
      {
        path: '/cases/:caseId/plan',
        element: <PlanPage />,
      },
      {
        path: '/cases/:caseId/run',
        element: <RunPage />,
      },
      {
        path: '/cases/:caseId/results',
        element: <ResultsPage />,
      },
    ],
  },
  {
    path: '*',
    element: <NotFoundPage />,
  },
])
