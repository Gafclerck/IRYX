import { LoginForm } from '../features/auth/components/LoginForm'

export function LoginPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-ink px-4 py-12">
      <div className="w-full max-w-md space-y-6 border border-deep bg-ink p-8 rounded-lg">
        <div className="text-center space-y-2">
          <h1 className="text-2xl font-bold tracking-tight text-mist">IRYX</h1>
          <p className="text-xs text-teal uppercase tracking-widest font-semibold">
            Plateforme d'investigation numérique
          </p>
          <h2 className="text-lg font-semibold text-mist pt-2">Connexion</h2>
        </div>

        <LoginForm />
      </div>
    </div>
  )
}
