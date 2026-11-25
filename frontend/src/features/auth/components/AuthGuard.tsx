import { type ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { hasAuthSession } from '../../../api/auth-memory'

interface AuthGuardProps {
  children: ReactNode
  isAuthenticated?: boolean
}

export function AuthGuard({ children, isAuthenticated }: AuthGuardProps) {
  const location = useLocation()
  const isAuth = isAuthenticated !== undefined ? isAuthenticated : hasAuthSession()

  if (!isAuth) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return <>{children}</>
}
