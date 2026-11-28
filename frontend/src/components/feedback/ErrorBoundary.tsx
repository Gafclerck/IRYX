import { Component, type ErrorInfo, type ReactNode } from 'react'

interface ErrorBoundaryProps {
  children: ReactNode
  fallback?: ReactNode
}

interface ErrorBoundaryState {
  hasError: boolean
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true }
  }

  override componentDidCatch(_error: Error, _errorInfo: ErrorInfo): void {
    // Exception capturée par la limite d'erreur racine sans rupture d'affichage
  }

  handleReload = (): void => {
    window.location.reload()
  }

  override render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }

      return (
        <div
          role="alert"
          className="flex min-h-screen flex-col items-center justify-center bg-ink text-mist p-6"
        >
          <div className="max-w-md border border-deep p-6 rounded text-center">
            <h1 className="text-lg font-bold text-cyan">Une erreur inattendue est survenue</h1>
            <p className="mt-2 text-sm text-teal">
              L'application a rencontré un problème inattendu. Veuillez recharger la page pour
              poursuivre.
            </p>
            <div className="mt-6">
              <button
                type="button"
                onClick={this.handleReload}
                className="px-4 py-2 border border-cyan text-cyan hover:bg-deep focus:outline-none focus:ring-2 focus:ring-cyan text-sm font-medium rounded"
              >
                Recharger la page
              </button>
            </div>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
