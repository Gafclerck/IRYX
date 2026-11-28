import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-ink text-mist p-6">
      <div className="text-center max-w-md border border-deep p-8 rounded">
        <h1 className="text-4xl font-display font-bold text-cyan">404</h1>
        <h2 className="mt-2 text-lg text-mist">Page non trouvée</h2>
        <p className="mt-2 text-sm text-teal">
          La ressource demandée n'existe pas ou a été déplacée.
        </p>
        <div className="mt-6">
          <Link
            to="/"
            className="inline-flex items-center justify-center px-4 py-2 border border-cyan text-cyan hover:bg-deep focus:outline-none focus:ring-2 focus:ring-cyan text-sm font-medium rounded"
          >
            Retour à l'accueil
          </Link>
        </div>
      </div>
    </div>
  )
}
