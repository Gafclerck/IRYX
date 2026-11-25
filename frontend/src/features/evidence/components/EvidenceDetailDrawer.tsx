import { useState, useEffect, useRef } from 'react'
import {
  X,
  Copy,
  Check,
  ShieldCheck,
  AlertTriangle,
  RotateCw,
  FolderX,
  Download,
  Clock,
  Activity,
  FileText,
} from 'lucide-react'
import type { EvidenceObservationItem } from '../types'
import { formatIngestionStatus } from '../constants'
import { formatFileSize } from '../utils/fileValidation'
import { truncateObservationContent, downloadTextFile } from '../utils/truncation'
import { useEvidenceDetail } from '../hooks/useEvidenceDetail'

export interface EvidenceDetailDrawerProps {
  readonly isOpen: boolean
  readonly caseId: string
  readonly evidenceId?: string
  readonly onClose: () => void
  readonly onForbidden?: () => void
}

/**
 * Formate un horodatage ISO en affichage UTC explicite pour la rigueur forensique.
 */
function formatUtcDate(isoString?: string | null): string {
  if (!isoString) return '—'
  try {
    const d = new Date(isoString)
    if (isNaN(d.getTime())) return isoString
    return d.toISOString().replace('T', ' ').slice(0, 19) + ' UTC'
  } catch {
    return isoString
  }
}

/**
 * Panneau latéral d'inspection détaillée d'une preuve numérique (Story F3.3).
 *
 * RÈGLES DE CONCEPTION (FR-EVI-03, C2, DP-04, 11-ecrans-et-routes.md, 12-parcours-et-etats.md) :
 * 1. Panneau coulissant à droite de l'écran, sans quitter la page (liste des preuves visible à gauche).
 * 2. Réactivité immédiate sans délai artificiel (principe C2).
 * 3. Fermeture par bouton, touche Échap et clic sur l'arrière-plan avec réorientation de l'URL.
 * 4. Contenu : SHA-256 intégrale en typographie à chasse fixe (avec copie), métadonnées complètes,
 *    historique d'ingestion, décompte d'observations et erreurs éventuelles.
 * 5. DP-04 : troncature volumétrique à 500 lignes ou 64 Ko avec téléchargement direct.
 * 6. États obligatoires : chargement, erreur avec « Réessayer », accès refusé (403), introuvable (404), nominal.
 * 7. Palette stricte (ink, deep, teal, cyan, mist) sans aucune couleur hexadécimale en dur.
 */
export function EvidenceDetailDrawer({
  isOpen,
  caseId,
  evidenceId,
  onClose,
  onForbidden,
}: EvidenceDetailDrawerProps) {
  const [copiedSha256, setCopiedSha256] = useState(false)
  const drawerRef = useRef<HTMLDivElement>(null)
  const closeButtonRef = useRef<HTMLButtonElement>(null)

  const { evidence, isLoading, isError, error, isForbidden, isNotFound, refetch } =
    useEvidenceDetail({
      caseId,
      evidenceId,
      enabled: isOpen && Boolean(evidenceId),
    })

  // Gestion du cas d'accès refusé (403) : notifie le parent pour affichage du toast et fermeture
  useEffect(() => {
    if (isForbidden && onForbidden) {
      onForbidden()
    }
  }, [isForbidden, onForbidden])

  // Écoute de la touche Échap pour fermer le tiroir
  useEffect(() => {
    if (!isOpen) return

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  // Focus initial sur le bouton de fermeture à l'ouverture du tiroir
  useEffect(() => {
    if (isOpen) {
      closeButtonRef.current?.focus()
    }
  }, [isOpen])

  if (!isOpen || !evidenceId) {
    return null
  }

  const handleCopySha256 = async (hash: string) => {
    try {
      if (navigator.clipboard) {
        await navigator.clipboard.writeText(hash)
        setCopiedSha256(true)
        setTimeout(() => setCopiedSha256(false), 2000)
      }
    } catch {
      // Ignoré si le presse-papier est restreint
    }
  }

  const handleDownloadObservation = (obs: EvidenceObservationItem, evidenceName: string) => {
    const rawContent =
      obs.raw_text ||
      (obs.normalized_content ? JSON.stringify(obs.normalized_content, null, 2) : '')
    const filename = `observation-${evidenceName}-${obs.id}.txt`
    downloadTextFile(filename, rawContent)
  }

  const observationCount = evidence?.observation_count ?? evidence?.observations?.length ?? 0
  const observations = evidence?.observations || []

  return (
    <>
      {/* Arrière-plan semi-transparent pour conserver le tableau visible à gauche */}
      <div
        className="fixed inset-0 z-30 bg-ink/50 backdrop-blur-[1px] transition-opacity"
        onClick={onClose}
        aria-hidden="true"
        data-testid="evidence-drawer-backdrop"
      />

      {/* Panneau coulissant latéral à droite */}
      <div
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="evidence-drawer-title"
        className="fixed inset-y-0 right-0 z-40 w-full max-w-xl bg-ink border-l border-deep shadow-2xl flex flex-col focus:outline-none"
        data-testid="evidence-detail-drawer"
        tabIndex={-1}
      >
        {/* En-tête du tiroir */}
        <div className="flex items-center justify-between border-b border-deep px-6 py-4 bg-deep/20">
          <div className="min-w-0 pr-4">
            <h2
              id="evidence-drawer-title"
              className="text-base font-bold text-mist truncate"
              data-testid="evidence-drawer-title"
            >
              {evidence?.original_name || 'Inspection détaillée de la preuve'}
            </h2>
            <p className="text-xs text-teal font-mono mt-0.5 truncate">{evidenceId}</p>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            className="rounded p-1.5 text-mist/70 hover:bg-deep/40 hover:text-cyan focus:outline-none focus:ring-2 focus:ring-cyan transition-colors"
            aria-label="Fermer le panneau d’inspection"
            title="Fermer le panneau (Échap)"
            data-testid="evidence-drawer-close-btn"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        {/* Corps défilable du tiroir */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {isLoading ? (
            /* État de chargement : squelettes animés */
            <div
              className="space-y-6 animate-pulse"
              data-testid="evidence-drawer-loading"
              aria-label="Chargement des métadonnées détaillées de la preuve"
            >
              <div className="space-y-2">
                <div className="h-4 w-32 rounded bg-deep/40"></div>
                <div className="h-12 rounded bg-deep/20"></div>
              </div>
              <div className="space-y-2">
                <div className="h-4 w-40 rounded bg-deep/40"></div>
                <div className="h-28 rounded bg-deep/20"></div>
              </div>
              <div className="space-y-2">
                <div className="h-4 w-48 rounded bg-deep/40"></div>
                <div className="h-20 rounded bg-deep/20"></div>
              </div>
              <div className="space-y-2">
                <div className="h-4 w-36 rounded bg-deep/40"></div>
                <div className="h-32 rounded bg-deep/20"></div>
              </div>
            </div>
          ) : isNotFound ? (
            /* État introuvable (404, message neutre) */
            <div className="p-8 text-center space-y-4" data-testid="evidence-drawer-not-found">
              <div className="flex justify-center">
                <FolderX className="h-10 w-10 text-teal/60" aria-hidden="true" />
              </div>
              <h3 className="text-base font-semibold text-mist">Preuve introuvable</h3>
              <p className="text-xs text-mist/80 max-w-sm mx-auto">
                Cette preuve numérique est introuvable ou n’existe pas dans ce dossier
                d’investigation.
              </p>
              <div>
                <button
                  type="button"
                  onClick={onClose}
                  className="inline-flex items-center gap-1.5 rounded border border-teal bg-deep px-3 py-1.5 text-xs font-semibold text-cyan hover:bg-deep/80 focus:outline-none focus:ring-2 focus:ring-cyan"
                  data-testid="evidence-drawer-close-not-found-btn"
                >
                  <span>Retour au registre des preuves</span>
                </button>
              </div>
            </div>
          ) : isError && !isForbidden ? (
            /* État d'erreur avec bouton « Réessayer » */
            <div
              className="rounded-lg border border-teal/40 bg-deep/20 p-5 space-y-4"
              data-testid="evidence-drawer-error"
            >
              <div className="flex items-start gap-3">
                <AlertTriangle className="h-5 w-5 text-cyan shrink-0 mt-0.5" aria-hidden="true" />
                <div className="space-y-1">
                  <h3 className="text-sm font-bold text-mist">
                    Erreur de chargement des détails de la preuve
                  </h3>
                  <p className="text-xs text-mist/90">
                    {error?.message ||
                      'Impossible de récupérer les détails forensiques de la preuve.'}
                  </p>
                </div>
              </div>
              <div>
                <button
                  type="button"
                  onClick={() => refetch()}
                  className="inline-flex items-center gap-1.5 rounded border border-teal bg-deep px-3 py-1.5 text-xs font-semibold text-cyan hover:bg-deep/80 focus:outline-none focus:ring-2 focus:ring-cyan"
                  data-testid="retry-evidence-detail-btn"
                >
                  <RotateCw className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>Réessayer</span>
                </button>
              </div>
            </div>
          ) : evidence ? (
            /* État nominal : Affichage complet des sections */
            <>
              {/* 1. Empreinte SHA-256 intégrale en typographie à chasse fixe avec copie */}
              <section
                aria-labelledby="section-sha256-title"
                className="rounded-lg border border-deep bg-deep/20 p-4 space-y-2"
                data-testid="section-sha256"
              >
                <div className="flex items-center justify-between">
                  <h3
                    id="section-sha256-title"
                    className="text-xs font-semibold uppercase tracking-wider text-teal"
                  >
                    Empreinte SHA-256 intégrale
                  </h3>
                  {evidence.sha256 && (
                    <button
                      type="button"
                      onClick={() => handleCopySha256(evidence.sha256!)}
                      className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-mist/80 hover:bg-deep/40 hover:text-cyan focus:outline-none focus:ring-1 focus:ring-cyan transition-colors"
                      data-testid="copy-full-sha256-btn"
                      title="Copier l’empreinte intégrale"
                    >
                      {copiedSha256 ? (
                        <>
                          <Check className="h-3.5 w-3.5 text-cyan" aria-hidden="true" />
                          <span className="text-cyan font-medium">Copié !</span>
                        </>
                      ) : (
                        <>
                          <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                          <span>Copier</span>
                        </>
                      )}
                    </button>
                  )}
                </div>
                <div className="rounded bg-ink/80 p-3 border border-deep">
                  <p
                    className="font-mono text-xs text-teal break-all select-all leading-relaxed"
                    data-testid="evidence-drawer-full-sha256"
                  >
                    {evidence.sha256 || 'Non disponible'}
                  </p>
                </div>
              </section>

              {/* 2. Métadonnées forensiques du conteneur */}
              <section
                aria-labelledby="section-metadata-title"
                className="rounded-lg border border-deep bg-deep/15 p-4 space-y-3"
                data-testid="section-metadata"
              >
                <h3
                  id="section-metadata-title"
                  className="text-xs font-semibold uppercase tracking-wider text-teal"
                >
                  Métadonnées de la preuve
                </h3>
                <dl className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                  <div>
                    <dt className="text-mist/60">Nom de fichier d’origine</dt>
                    <dd
                      className="font-medium text-mist break-all mt-0.5"
                      data-testid="drawer-meta-name"
                    >
                      {evidence.original_name}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-mist/60">Type binaire détecté</dt>
                    <dd
                      className="font-mono text-[11px] text-mist/90 mt-0.5"
                      data-testid="drawer-meta-type"
                    >
                      {evidence.detected_type || '—'}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-mist/60">Taille du fichier</dt>
                    <dd
                      className="font-mono text-[11px] text-mist/90 mt-0.5"
                      data-testid="drawer-meta-size"
                    >
                      {formatFileSize(evidence.file_size)}{' '}
                      <span className="text-mist/60">
                        ({evidence.file_size.toLocaleString('fr-FR')} octets)
                      </span>
                    </dd>
                  </div>
                  <div>
                    <dt className="text-mist/60">Date d’ajout (UTC)</dt>
                    <dd
                      className="font-mono text-[11px] text-mist/90 mt-0.5"
                      data-testid="drawer-meta-date"
                    >
                      {formatUtcDate(evidence.created_at)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-mist/60">Importateur</dt>
                    <dd className="text-mist/90 mt-0.5" data-testid="drawer-meta-importer">
                      {evidence.imported_by || 'Non renseigné'}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-mist/60">Provenance</dt>
                    <dd className="text-mist/90 mt-0.5" data-testid="drawer-meta-provenance">
                      {/* La provenance ne figure pas dans le schéma EvidenceRead du contrat actuel. */}
                      <span
                        className="text-mist/60"
                        title="Champ absent du schéma EvidenceRead du contrat openapi.json"
                      >
                        Non renseignée par le contrat
                      </span>
                    </dd>
                  </div>
                </dl>
              </section>

              {/* 3. Historique des exécutions d'ingestion et erreurs éventuelles */}
              <section
                aria-labelledby="section-ingestion-history-title"
                className="rounded-lg border border-deep bg-deep/15 p-4 space-y-3"
                data-testid="section-ingestion-history"
              >
                <div className="flex items-center justify-between">
                  <h3
                    id="section-ingestion-history-title"
                    className="text-xs font-semibold uppercase tracking-wider text-teal flex items-center gap-1.5"
                  >
                    <Activity className="h-3.5 w-3.5 text-teal" aria-hidden="true" />
                    <span>Historique d’ingestion</span>
                  </h3>
                </div>

                {evidence.ingestion_runs && evidence.ingestion_runs.length > 0 ? (
                  <div className="space-y-3">
                    {evidence.ingestion_runs.map((run, index) => {
                      const runStatus = formatIngestionStatus(run.status)
                      return (
                        <div
                          key={run.id || index}
                          className="rounded border border-deep bg-ink/60 p-3 space-y-2"
                          data-testid={`ingestion-run-item-${run.id || index}`}
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-mono text-[11px] text-mist/80 truncate">
                              ID : {run.id}
                            </span>
                            <span
                              className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 text-[11px] font-semibold ${
                                runStatus.isIntegrity
                                  ? 'border-teal/40 bg-deep/30 text-cyan'
                                  : runStatus.isFailed
                                    ? 'border-teal/40 bg-deep/40 text-mist'
                                    : 'border-deep bg-deep/20 text-teal'
                              }`}
                              data-testid={`drawer-ingestion-badge-${run.id || index}`}
                            >
                              {runStatus.isIntegrity ? (
                                <ShieldCheck className="h-3 w-3 text-cyan" aria-hidden="true" />
                              ) : runStatus.isFailed ? (
                                <AlertTriangle className="h-3 w-3 text-cyan" aria-hidden="true" />
                              ) : (
                                <Clock className="h-3 w-3 text-teal" aria-hidden="true" />
                              )}
                              <span>{runStatus.label}</span>
                            </span>
                          </div>

                          <div className="grid grid-cols-2 gap-2 text-[11px] text-mist/70 font-mono">
                            <div>Début : {formatUtcDate(run.started_at)}</div>
                            <div>
                              Fin :{' '}
                              {run.completed_at ? formatUtcDate(run.completed_at) : 'En cours'}
                            </div>
                          </div>

                          {run.error_message && (
                            <div
                              className="rounded border border-teal/40 bg-deep/30 p-2 text-xs text-mist flex items-start gap-2"
                              data-testid="drawer-ingestion-error-message"
                            >
                              <AlertTriangle
                                className="h-4 w-4 text-cyan shrink-0 mt-0.5"
                                aria-hidden="true"
                              />
                              <div className="space-y-0.5">
                                <span className="font-semibold text-mist">
                                  Erreur d’ingestion :
                                </span>{' '}
                                <span className="text-mist/90">{run.error_message}</span>
                              </div>
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                ) : (
                  /* Aucun historique retourné : mention neutre, sans affirmer un état */
                  <div className="rounded border border-deep bg-ink/60 p-3 text-xs text-mist/80">
                    <p>Aucune exécution d’ingestion retournée par l’API.</p>
                  </div>
                )}

                {/* Erreur éventuelle au niveau supérieur */}
                {evidence.error_message &&
                  !evidence.ingestion_runs?.some((r) => r.error_message) && (
                    <div
                      className="rounded border border-teal/40 bg-deep/30 p-2.5 text-xs text-mist flex items-start gap-2"
                      data-testid="drawer-top-error-message"
                    >
                      <AlertTriangle
                        className="h-4 w-4 text-cyan shrink-0 mt-0.5"
                        aria-hidden="true"
                      />
                      <span>{evidence.error_message}</span>
                    </div>
                  )}
              </section>

              {/* 4. Observations produites & Troncature volumétrique (DP-04) */}
              <section
                aria-labelledby="section-observations-title"
                className="rounded-lg border border-deep bg-deep/15 p-4 space-y-3"
                data-testid="section-observations"
              >
                <div className="flex items-center justify-between">
                  <h3
                    id="section-observations-title"
                    className="text-xs font-semibold uppercase tracking-wider text-teal flex items-center gap-1.5"
                  >
                    <FileText className="h-3.5 w-3.5 text-teal" aria-hidden="true" />
                    <span>Observations produites</span>
                  </h3>
                  <span
                    className="rounded bg-deep/30 px-2 py-0.5 font-mono text-[11px] text-cyan"
                    data-testid="evidence-drawer-observation-count"
                  >
                    Décompte : {observationCount} observation{observationCount > 1 ? 's' : ''}
                  </span>
                </div>

                {observationCount === 0 ? (
                  /* État vide : Mention obligatoire stricte */
                  <div
                    className="rounded-lg border border-deep bg-ink/60 p-6 text-center"
                    data-testid="evidence-drawer-no-observations"
                  >
                    <p className="text-xs text-mist/70 italic">
                      Aucune observation extraite pour cette preuve
                    </p>
                  </div>
                ) : (
                  /* Liste des observations avec application stricte de DP-04 */
                  <div className="space-y-4">
                    {observations.map((obs) => {
                      const rawContent =
                        obs.raw_text ||
                        (obs.normalized_content
                          ? JSON.stringify(obs.normalized_content, null, 2)
                          : '')
                      const truncationResult = truncateObservationContent(rawContent)

                      return (
                        <div
                          key={obs.id}
                          className="rounded border border-deep bg-ink/70 p-3 space-y-2.5"
                          data-testid={`observation-item-${obs.id}`}
                        >
                          <div className="flex items-center justify-between text-xs">
                            <span className="font-semibold text-mist">
                              Outil : <span className="text-cyan font-mono">{obs.tool_name}</span>
                            </span>
                            {obs.timestamp_utc && (
                              <span className="text-[11px] font-mono text-mist/70">
                                {formatUtcDate(obs.timestamp_utc)}
                              </span>
                            )}
                          </div>

                          {obs.source_location && (
                            <p className="text-[11px] text-mist/70 font-mono">
                              Emplacement : {obs.source_location}
                            </p>
                          )}

                          {/* Aperçu textuel tronqué ou complet */}
                          <div className="rounded bg-ink/90 border border-deep p-2.5 overflow-x-auto">
                            <pre
                              className="font-mono text-[11px] text-mist/90 whitespace-pre-wrap break-all max-h-60 overflow-y-auto"
                              data-testid={`observation-preview-${obs.id}`}
                            >
                              {truncationResult.previewText}
                            </pre>
                          </div>

                          {/* Signalement DP-04 et bouton de téléchargement si tronqué */}
                          {truncationResult.isTruncated && (
                            <div
                              className="rounded border border-teal/40 bg-deep/20 p-2.5 flex flex-col sm:flex-row sm:items-center justify-between gap-2"
                              data-testid="dp04-truncation-notice"
                            >
                              <div className="text-[11px] text-mist/80">
                                <span className="font-semibold text-cyan">Aperçu tronqué</span> :
                                dépasse{' '}
                                {truncationResult.truncationReason === 'lines'
                                  ? '500 lignes'
                                  : truncationResult.truncationReason === 'bytes'
                                    ? '64 Ko'
                                    : '500 lignes et 64 Ko'}{' '}
                                ({truncationResult.totalLines} lignes,{' '}
                                {formatFileSize(truncationResult.totalBytes)}) — décision DP-04.
                              </div>
                              <button
                                type="button"
                                onClick={() =>
                                  handleDownloadObservation(obs, evidence.original_name)
                                }
                                className="inline-flex items-center gap-1.5 rounded border border-teal bg-deep px-2.5 py-1 text-xs font-semibold text-cyan hover:bg-deep/80 focus:outline-none focus:ring-1 focus:ring-cyan transition-colors shrink-0"
                                data-testid="download-full-observation-btn"
                                title="Télécharger l’observation brute intégrale"
                              >
                                <Download className="h-3.5 w-3.5" aria-hidden="true" />
                                <span>Télécharger l’observation intégrale</span>
                              </button>
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}
              </section>
            </>
          ) : null}
        </div>
      </div>
    </>
  )
}
