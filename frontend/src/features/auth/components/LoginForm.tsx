import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useNavigate, useLocation } from 'react-router-dom'
import { AlertCircle, Loader2 } from 'lucide-react'
import { loginSchema, type LoginFormValues } from '../schemas/loginSchema'
import { loginApi, AuthError } from '../../../api/auth'

interface LocationState {
  from?: {
    pathname?: string
  }
}

export function LoginForm() {
  const [generalError, setGeneralError] = useState<string | null>(null)
  const navigate = useNavigate()
  const location = useLocation()

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      email: '',
      password: '',
    },
    mode: 'onSubmit',
  })

  const onSubmit = async (values: LoginFormValues) => {
    setGeneralError(null)
    try {
      await loginApi({
        email: values.email,
        password: values.password,
      })

      // Redirection automatique vers /cases après succès
      const locationState = location.state as LocationState | null
      const destination = locationState?.from?.pathname || '/cases'
      navigate(destination, { replace: true })
    } catch (error) {
      if (error instanceof AuthError) {
        setGeneralError(error.message)
      } else {
        setGeneralError('Identifiants incorrects.')
      }
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
      {generalError && (
        <div
          role="alert"
          className="flex items-center gap-2 p-3 rounded bg-cyan text-ink text-sm font-medium"
        >
          <AlertCircle className="w-5 h-5 flex-shrink-0" aria-hidden="true" />
          <div>
            <span className="font-bold">ÉCHEC : </span>
            <span>{generalError}</span>
          </div>
        </div>
      )}

      <div>
        <label htmlFor="login-email" className="block text-sm font-medium text-mist mb-1">
          Adresse électronique
        </label>
        <input
          id="login-email"
          type="email"
          autoComplete="email"
          autoFocus
          disabled={isSubmitting}
          aria-invalid={errors.email ? 'true' : 'false'}
          aria-describedby={errors.email ? 'login-email-error' : undefined}
          className="w-full px-3 py-2 bg-ink border border-deep rounded text-mist placeholder-teal focus:outline-none focus:ring-2 focus:ring-cyan focus:border-cyan disabled:bg-deep disabled:text-teal disabled:cursor-not-allowed"
          placeholder="analyste@iryx.local"
          {...register('email')}
        />
        {errors.email && (
          <p
            id="login-email-error"
            className="mt-1 text-xs text-cyan flex items-center gap-1"
            role="alert"
          >
            <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" aria-hidden="true" />
            <span>{errors.email.message}</span>
          </p>
        )}
      </div>

      <div>
        <label htmlFor="login-password" className="block text-sm font-medium text-mist mb-1">
          Mot de passe
        </label>
        <input
          id="login-password"
          type="password"
          autoComplete="current-password"
          disabled={isSubmitting}
          aria-invalid={errors.password ? 'true' : 'false'}
          aria-describedby={errors.password ? 'login-password-error' : undefined}
          className="w-full px-3 py-2 bg-ink border border-deep rounded text-mist placeholder-teal focus:outline-none focus:ring-2 focus:ring-cyan focus:border-cyan disabled:bg-deep disabled:text-teal disabled:cursor-not-allowed"
          placeholder="••••••••"
          {...register('password')}
        />
        {errors.password && (
          <p
            id="login-password-error"
            className="mt-1 text-xs text-cyan flex items-center gap-1"
            role="alert"
          >
            <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" aria-hidden="true" />
            <span>{errors.password.message}</span>
          </p>
        )}
      </div>

      <button
        type="submit"
        disabled={isSubmitting}
        className="w-full py-2.5 px-4 bg-cyan text-ink font-semibold rounded hover:bg-mist hover:text-ink focus:outline-none focus:ring-2 focus:ring-cyan transition-colors disabled:bg-deep disabled:text-teal disabled:cursor-not-allowed flex items-center justify-center gap-2"
      >
        {isSubmitting ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
            <span>Connexion en cours...</span>
          </>
        ) : (
          <span>Se connecter</span>
        )}
      </button>
    </form>
  )
}
