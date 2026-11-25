// Fonctions utilitaires pures indépendantes de toute vue
export function formatUtcIso(date: Date): string {
  return date.toISOString()
}

export * from './date'
