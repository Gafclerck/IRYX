import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Copy,
  Check,
  ShieldCheck,
  AlertTriangle,
  AlertCircle,
  RotateCw,
  Clock,
  Play,
  WifiOff,
  ShieldAlert,
  FileCode,
} from 'lucide-react'
import type { EvidenceInventoryItem } from '../types'
import { EvidenceApiError } from '../services/evidenceService'
import { formatIngestionStatus } from '../constants'
import { formatFileSize } from '../utils/fileValidation'

export interface EvidenceTableProps {
  readonly caseId: string
  readonly evidences: readonly EvidenceInventoryItem[]
  readonly total: number
  readonly isLoading: boolean
  readonly isFetching: boolean
  readonly isError: boolean
  readonly error: Error | EvidenceApiError | null
  readonly isForbidden: boolean
  readonly isNetworkCutoff: boolean
  readonly hasIntegrityEvidence: boolean
  readonly onRefetch: () => void
  readonly onRetryConnection: () => void
  readonly onLaunchAnalysis?: () => void
}

/**
 * Formate un horodatage ISO en affichage UTC explicite.
 */
function formatUtcDate(isoString: string): string {
  try {
    const d = new Date(isoString)
    if (isNaN(d.getTime())) return isoString
    return d.toISOString().replace('T', ' ').slice(0, 19) + ' UTC'
  } catch {
    return isoString
  }
}

/**
 * Tronque une empreinte SHA-256 pour un affichage condensé à chasse fixe.
 */
function truncateSha256(hash: string): string {
  if (!hash || hash.length <= 16) return hash
  return `${hash.slice(0, 8)}...${hash.slice(-8)}`
}

/**
 * Composant de tableau d'inventaire des preuves avec suivi d'ingestion (Story F3.2).
 *
 * RÈGLES DE CONCEPTION (FR-EVI-02, ADR-0008, DP-05, 11-ecrans-et-routes.md, 12-parcours-et-etats.md) :
 * 1. 7 colonnes : Nom, Type détecté, Taille, SHA-256 tronqué avec copie, Date d'ajout UTC, Provenance, Statut d'ingestion.
 * 2. Statuts stricts : pending, processing, completed (« INTÈGRE »), failed (« ÉCHEC »).
 *    Statut inconnu : affiché « État inconnu (code) ».
 * 3. Copie de l'empreinte dans le presse-papier avec confirmation visuelle.
 * 4. Bouton « Lancer l'analyse » conditionné : actif uniquement si au moins une preuve est intègre (completed).
 * 5. DP-05 : coupure réseau prolongée avec bouton « Réessayer la connexion ».
 * 6. États obligatoires : chargement, vide, erreur avec réessai, accès refusé (403), nominal.
 * 7. Indicateur visuel discret lors de la synchronisation d'arrière-plan sans masquer le tableau.
 * 8. Respect strict de la palette autorisée (ink, deep, teal, cyan, mist) sans aucun hexadécimal en dur.
 */
export function EvidenceTable({
  caseId,
  evidences,
  total,
  isLoading,
  isFetching,
  isError,
  error,
  isForbidden,
  isNetworkCutoff,
  hasIntegrityEvidence,
  onRefetch,
  onRetryConnection,
  onLaunchAnalysis,
}: EvidenceTableProps) {
  const navigate = useNavigate()
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const handleCopySha256 = async (hash: string, id: string) => {
    try {
      if (navigator.clipboard) {
        await navigator.clipboard.writeText(hash)
        setCopiedId(id)
        setTimeout(() => setCopiedId(null), 2000)
      }
    } catch {
      // Ignoré si le presse-papier est inaccessible
    }
  }

  const handleLaunchAnalysis = () => {
    if (!hasIntegrityEvidence) return
    if (onLaunchAnalysis) {
      onLaunchAnalysis()
    } else {
      navigate(`/cases/${caseId}/plan`)
    }
  }

  return (
    <div className="space-y-4" data-testid="evidence-inventory-section">
      {/* En-tête du registre avec indicateur de synchronisation discret */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-deep pb-3">
        <div>
          <h2 className="text-lg font-bold tracking-tight text-mist">
            Inventaire des preuves scellées
          </h2>
          <p className="text-xs text-mist/70">
            {total} preuve{total > 1 ? 's' : ''} enregistrée{total > 1 ? 's' : ''} pour ce dossier
          </p>
        </div>

        {/* Indicateur visuel discret de scrutation / synchronisation sans masquer le tableau */}
        {isFetching && !isLoading && (
          <div
            className="flex items-center gap-1.5 rounded border border-teal/40 bg-deep/20 px-2.5 py-1 text-xs text-cyan animate-pulse"
            data-testid="evidence-polling-indicator"
            aria-live="polite"
          >
            <RotateCw className="h-3 w-3 animate-spin text-cyan" aria-hidden="true" />
            <span>Synchronisation de l’ingestion...</span>
          </div>
        )}
      </div>

      {/* État DP-05 : Arrêt de l'interrogation en cas de coupure prolongée */}
      {isNetworkCutoff && (
        <div
          role="alert"
          className="rounded-lg border border-teal bg-deep/40 p-4 text-mist space-y-3 shadow-md"
          data-testid="dp05-network-cutoff-banner"
        >
          <div className="flex items-start gap-3">
            <WifiOff className="h-5 w-5 flex-shrink-0 text-cyan mt-0.5" aria-hidden="true" />
            <div className="space-y-1">
              <h3 className="text-sm font-bold text-mist uppercase tracking-wide">
                Connexion interrompue
              </h3>
              <p className="text-xs text-mist/90">
                La scrutation de l’ingestion a été interrompue suite à une rupture prolongée de
                connectivité réseau avec le serveur.
              </p>
            </div>
          </div>
          <div>
            <button
              type="button"
              onClick={onRetryConnection}
              className="inline-flex items-center gap-1.5 rounded border border-teal bg-deep px-3 py-1.5 text-xs font-semibold text-cyan hover:bg-deep/80 focus:outline-none focus:ring-2 focus:ring-cyan"
              data-testid="retry-connection-btn"
            >
              <RotateCw className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Réessayer la connexion</span>
            </button>
          </div>
        </div>
      )}

      {/* État 403 Forbidden sur le registre */}
      {isForbidden && (
        <div
          role="alert"
          className="rounded-lg border border-deep bg-deep/40 p-4 text-mist"
          data-testid="evidence-forbidden-banner"
        >
          <div className="flex items-start gap-3">
            <ShieldAlert className="h-5 w-5 flex-shrink-0 text-cyan mt-0.5" aria-hidden="true" />
            <div>
              <h3 className="text-sm font-bold text-mist">Accès non autorisé</h3>
              <p className="text-xs text-mist/90">
                Vous ne disposez pas des habilitations nécessaires pour consulter les preuves de ce
                dossier.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* État d'erreur générique / 5xx avec bouton Réessayer */}
      {isError && !isForbidden && !isNetworkCutoff && (
        <div
          role="alert"
          className="rounded-lg border border-deep bg-deep/40 p-4 text-mist space-y-3"
          data-testid="evidence-table-error"
        >
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 flex-shrink-0 text-cyan mt-0.5" aria-hidden="true" />
            <div>
              <h3 className="text-sm font-bold text-mist">
                Erreur de chargement du registre des preuves
              </h3>
              <p className="text-xs text-mist/90">
                {error?.message ||
                  'Impossible de récupérer les preuves du dossier. Une anomalie est survenue.'}
              </p>
            </div>
          </div>
          <div>
            <button
              type="button"
              onClick={onRefetch}
              className="inline-flex items-center gap-1.5 rounded border border-teal bg-deep px-3 py-1.5 text-xs font-semibold text-cyan hover:bg-deep/80 focus:outline-none focus:ring-2 focus:ring-cyan"
              data-testid="retry-evidence-fetch-btn"
            >
              <RotateCw className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Réessayer</span>
            </button>
          </div>
        </div>
      )}

      {/* Tableau des preuves */}
      {!isForbidden && !isError && (
        <div className="overflow-hidden rounded-lg border border-deep bg-deep/10 shadow">
          {isLoading ? (
            /* État de chargement initial : Squelettes animés */
            <div
              className="p-6 space-y-3 animate-pulse"
              data-testid="evidence-table-loading"
              aria-label="Chargement de l’inventaire des preuves"
            >
              <div className="h-8 rounded bg-deep/40"></div>
              <div className="h-10 rounded bg-deep/20"></div>
              <div className="h-10 rounded bg-deep/20"></div>
              <div className="h-10 rounded bg-deep/20"></div>
            </div>
          ) : evidences.length === 0 ? (
            /* État vide : Message central explicite */
            <div
              className="p-12 text-center space-y-3"
              data-testid="evidence-inventory-empty-state"
            >
              <div className="flex justify-center">
                <FileCode className="h-10 w-10 text-teal/60" aria-hidden="true" />
              </div>
              <h3 className="text-base font-semibold text-mist">
                Aucune preuve déposée pour ce dossier
              </h3>
              <p className="text-xs text-mist/70 max-w-md mx-auto">
                Déposez des artefacts forensiques dans la zone ci-dessus pour initialiser la chaîne de
                possession et l’ingestion cryptographique.
              </p>
            </div>
          ) : (
            /* État nominal : Tableau d'inventaire complet des preuves */
            <div className="overflow-x-auto">
              <table
                className="w-full text-left text-xs text-mist"
                data-testid="evidence-inventory-table"
              >
                <thead className="border-b border-deep bg-deep/30 text-[11px] font-semibold uppercase tracking-wider text-teal">
                  <tr>
                    <th scope="col" className="px-4 py-3">
                      Nom
                    </th>
                    <th scope="col" className="px-4 py-3">
                      Type détecté
                    </th>
                    <th scope="col" className="px-4 py-3">
                      Taille
                    </th>
                    <th scope="col" className="px-4 py-3">
                      Empreinte SHA-256
                    </th>
                    <th scope="col" className="px-4 py-3">
                      Date d’ajout (UTC)
                    </th>
                    <th scope="col" className="px-4 py-3">
                      Provenance
                    </th>
                    <th scope="col" className="px-4 py-3">
                      Statut d’ingestion
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-deep/40">
                  {evidences.map((item) => {
                    const statusInfo = formatIngestionStatus(item.ingestionStatus)
                    const isCopied = copiedId === item.id

                    return (
                      <tr
                        key={item.id}
                        className="hover:bg-deep/20 transition-colors"
                        data-testid={`evidence-row-${item.id}`}
                      >
                        {/* 1. Nom */}
                        <td className="px-4 py-3 font-medium text-mist">
                          <span className="break-all" title={item.original_name}>
                            {item.original_name}
                          </span>
                        </td>

                        {/* 2. Type détecté */}
                        <td className="px-4 py-3 text-mist/80">
                          <span className="font-mono text-[11px]">
                            {item.detected_type || '—'}
                          </span>
                        </td>

                        {/* 3. Taille */}
                        <td className="px-4 py-3 font-mono text-[11px] text-mist/80 whitespace-nowrap">
                          {formatFileSize(item.file_size)}
                        </td>

                        {/* 4. Empreinte SHA-256 tronquée avec bouton de copie */}
                        <td className="px-4 py-3 whitespace-nowrap">
                          {item.sha256 ? (
                            <div className="flex items-center gap-1.5 font-mono text-[11px]">
                              <span
                                className="text-teal"
                                title={item.sha256}
                                data-testid={`sha256-hash-${item.id}`}
                              >
                                {truncateSha256(item.sha256)}
                              </span>
                              <button
                                type="button"
                                onClick={() => handleCopySha256(item.sha256!, item.id)}
                                className="rounded p-1 text-mist/70 hover:text-cyan focus:outline-none focus:ring-1 focus:ring-cyan transition-colors"
                                aria-label="Copier l'empreinte SHA-256"
                                title="Copier l'empreinte SHA-256"
                                data-testid={`copy-sha256-btn-${item.id}`}
                              >
                                {isCopied ? (
                                  <Check className="h-3.5 w-3.5 text-cyan" aria-hidden="true" />
                                ) : (
                                  <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                                )}
                              </button>
                            </div>
                          ) : (
                            <span className="text-mist/50 italic text-[11px]">
                              En cours de calcul...
                            </span>
                          )}
                        </td>

                        {/* 5. Date d'ajout en UTC */}
                        <td className="px-4 py-3 font-mono text-[11px] text-mist/80 whitespace-nowrap">
                          {formatUtcDate(item.created_at)}
                        </td>

                        {/* 6. Provenance */}
                        <td className="px-4 py-3 text-mist/80 whitespace-nowrap">
                          <span>{item.imported_by || 'Dépôt direct'}</span>
                        </td>

                        {/* 7. Statut d'ingestion */}
                        <td className="px-4 py-3 whitespace-nowrap">
                          {statusInfo.isIntegrity ? (
                            /* État completed : Preuve marquée « INTÈGRE » */
                            <span
                              className="inline-flex items-center gap-1 rounded border border-teal/40 bg-deep/30 px-2 py-0.5 text-[11px] font-semibold text-cyan"
                              data-testid={`status-badge-${item.id}`}
                            >
                              <ShieldCheck className="h-3.5 w-3.5 text-cyan" aria-hidden="true" />
                              <span>{statusInfo.label}</span>
                            </span>
                          ) : statusInfo.isFailed ? (
                            /* État failed ou non intègre : « ÉCHEC » ou « NON INTÈGRE » avec icône d'alerte */
                            <span
                              className="inline-flex items-center gap-1 rounded border border-teal/40 bg-deep/40 px-2 py-0.5 text-[11px] font-semibold text-mist"
                              title={item.ingestionErrorMessage || 'Échec de traitement cryptographique'}
                              data-testid={`status-badge-${item.id}`}
                            >
                              <AlertTriangle className="h-3.5 w-3.5 text-cyan" aria-hidden="true" />
                              <span>{statusInfo.label}</span>
                            </span>
                          ) : statusInfo.label === 'EN COURS' ? (
                            /* État processing */
                            <span
                              className="inline-flex items-center gap-1 rounded border border-deep bg-deep/30 px-2 py-0.5 text-[11px] font-medium text-teal"
                              data-testid={`status-badge-${item.id}`}
                            >
                              <RotateCw className="h-3 w-3 animate-spin text-teal" aria-hidden="true" />
                              <span>
                                {statusInfo.label}
                                {item.ingestionProgress > 0 ? ` (${item.ingestionProgress}%)` : ''}
                              </span>
                            </span>
                          ) : statusInfo.label === 'EN ATTENTE' ? (
                            /* État pending */
                            <span
                              className="inline-flex items-center gap-1 rounded border border-deep bg-deep/20 px-2 py-0.5 text-[11px] font-medium text-mist/70"
                              data-testid={`status-badge-${item.id}`}
                            >
                              <Clock className="h-3 w-3 text-mist/60" aria-hidden="true" />
                              <span>{statusInfo.label}</span>
                            </span>
                          ) : (
                            /* Règle de robustesse : Statut inconnu affiché « État inconnu (code) » */
                            <span
                              className="inline-flex items-center gap-1 rounded border border-teal/40 bg-deep/30 px-2 py-0.5 text-[11px] font-medium text-mist/80"
                              data-testid={`status-badge-${item.id}`}
                            >
                              <AlertCircle className="h-3.5 w-3.5 text-teal" aria-hidden="true" />
                              <span>{statusInfo.label}</span>
                            </span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Barre d'action inférieure : Bouton « Lancer l'analyse » conditionné formellement */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-4 border-t border-deep">
        <div className="text-xs text-mist/70">
          {!hasIntegrityEvidence ? (
            <p
              className="text-mist/70 italic"
              data-testid="analysis-disabled-help"
            >
              Le lancement de l’analyse requiert au moins une preuve scellée et confirmée intègre.
            </p>
          ) : (
            <p className="text-cyan font-medium">
              Preuve(s) intègre(s) confirmée(s). Vous pouvez engager l’analyse en étape 3.
            </p>
          )}
        </div>

        <div>
          <button
            type="button"
            onClick={handleLaunchAnalysis}
            disabled={!hasIntegrityEvidence}
            title={
              hasIntegrityEvidence
                ? 'Engager l’analyse forensique vers l’étape 3 Plan'
                : 'Le lancement de l’analyse requiert au moins une preuve scellée et confirmée intègre.'
            }
            aria-disabled={!hasIntegrityEvidence}
            className={`inline-flex items-center gap-2 rounded px-4 py-2 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-cyan ${
              hasIntegrityEvidence
                ? 'bg-teal text-ink hover:bg-cyan cursor-pointer shadow-md'
                : 'bg-deep/40 text-mist/40 border border-deep cursor-not-allowed'
            }`}
            data-testid="launch-analysis-btn"
          >
            <Play className="h-3.5 w-3.5 fill-current" aria-hidden="true" />
            <span>Lancer l’analyse</span>
          </button>
        </div>
      </div>
    </div>
  )
}
