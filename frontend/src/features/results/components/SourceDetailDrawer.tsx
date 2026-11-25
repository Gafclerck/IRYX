import { useEffect, useRef, useState } from 'react'
import {
  AlertTriangle,
  Check,
  Copy,
  Download,
  FileText,
  FolderX,
  RotateCw,
  ShieldAlert,
  X,
} from 'lucide-react'
import {
  SOURCE_CONFIDENTIALITY_NOTE,
  SOURCE_EMPTY_MESSAGE,
  SOURCE_FORBIDDEN_MESSAGE,
  SOURCE_NOT_FOUND_MESSAGE,
  SOURCE_PANEL_TITLE,
  SOURCE_REACTIVITY_NOTE,
  SOURCE_TRUNCATION_MESSAGE,
  SOURCE_UNAVAILABLE_MESSAGE,
  TO_REALIGN,
} from '../constants'
import { useSourceDetail } from '../hooks/useSourceDetail'
import { buildSourceDownloadUrl } from '../services/sourcePanelService'
import type { TimelineEntry } from '../types'
import { buildSourceExcerpt, readSourceProof, readSourceStatus } from '../utils/sourcePanel'

export interface SourceDetailDrawerProps {
  readonly isOpen: boolean
  readonly caseId: string
  readonly entry: TimelineEntry | null
  readonly onClose: () => void
}

/**
 * Tiroir latéral d'inspection de la source d'un événement (Story F4.7, FR-RES-03).
 *
 * RÈGLES :
 * 1. Ouverture à droite sans quitter la page : la chronologie reste visible.
 * 2. C2 : aucune attente artificielle à l'ouverture ; le squelette s'affiche
 *    immédiatement pendant la consultation ponctuelle de la route contractuelle.
 * 3. DP-04 : aperçu tronqué à 500 lignes / 64 Ko, bannière explicite et
 *    téléchargement direct sur action utilisateur uniquement. Le contenu
 *    intégral n'est jamais chargé pour l'affichage du panneau.
 * 4. États : chargement, nominal, vide, erreur avec « Réessayer », 403, 404,
 *    statut inconnu (actions dépendantes désactivées).
 * 5. Fermeture par bouton « Fermer » ou Échap ; le focus revient à l'élément
 *    d'origine, géré par la page (aucune navigation, aucun stockage local).
 * 6. Palette stricte (ink, deep, teal, cyan, mist), aucun log de contenu.
 */
export function SourceDetailDrawer({ isOpen, caseId, entry, onClose }: SourceDetailDrawerProps) {
  const [copiedExcerpt, setCopiedExcerpt] = useState(false)
  const [copiedProof, setCopiedProof] = useState(false)
  const closeButtonRef = useRef<HTMLButtonElement>(null)

  const observationId = entry?.id
  const { observation, isLoading, isError, error, isForbidden, isNotFound, refetch } =
    useSourceDetail({
      caseId,
      observationId,
      enabled: isOpen && Boolean(observationId),
    })

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

  useEffect(() => {
    if (isOpen) closeButtonRef.current?.focus()
  }, [isOpen, observationId])

  useEffect(() => {
    setCopiedExcerpt(false)
    setCopiedProof(false)
  }, [observationId])

  if (!isOpen || !entry) return null

  const excerpt = observation ? buildSourceExcerpt(observation) : null
  const proof = observation ? readSourceProof(observation) : null
  const status = observation ? readSourceStatus(observation) : null
  const actionsDisabled = Boolean(status?.isUnknown)

  const copyToClipboard = async (value: string, which: 'excerpt' | 'proof') => {
    if (actionsDisabled || !value || !navigator.clipboard) return
    try {
      await navigator.clipboard.writeText(value)
      if (which === 'excerpt') setCopiedExcerpt(true)
      else setCopiedProof(true)
    } catch {
      // Presse-papier restreint : aucun journal ne contient le contenu copié.
    }
  }

  return (
    <>
      <div
        className="fixed inset-0 z-30 bg-ink/50 backdrop-blur-[1px]"
        onClick={onClose}
        aria-hidden="true"
        data-testid="source-drawer-backdrop"
      />

      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="source-drawer-title"
        className="fixed inset-y-0 right-0 z-40 flex w-full max-w-xl flex-col border-l border-deep bg-ink shadow-2xl focus:outline-none"
        data-testid="source-detail-drawer"
      >
        <div className="flex items-start justify-between gap-3 border-b border-deep bg-deep/20 px-6 py-4">
          <div className="min-w-0 space-y-1">
            <h2
              id="source-drawer-title"
              className="truncate text-base font-bold text-mist"
              data-testid="source-drawer-title"
            >
              {SOURCE_PANEL_TITLE}
            </h2>
            <p className="truncate font-mono text-xs text-teal" data-testid="source-event-id">
              {entry.eventIdLabel}
            </p>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            className="inline-flex flex-shrink-0 items-center gap-1.5 rounded border border-teal bg-deep px-3 py-1.5 text-xs font-semibold text-mist hover:bg-deep/80 focus:outline-none focus:ring-2 focus:ring-cyan"
            aria-label="Fermer le panneau d’inspection de la source"
            title="Fermer (Échap)"
            data-testid="source-drawer-close"
          >
            <X className="h-4 w-4 text-cyan" aria-hidden="true" />
            Fermer
          </button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto p-6">
          {isLoading && (
            <div
              className="animate-pulse space-y-4"
              role="status"
              aria-label="Chargement des détails de la source"
              data-testid="source-drawer-loading"
            >
              <div className="h-4 w-40 rounded bg-deep/40" />
              <div className="h-4 w-56 rounded bg-deep/40" />
              <div className="h-4 w-32 rounded bg-deep/40" />
              <div className="h-28 rounded bg-deep/20" />
              <span className="sr-only">Chargement des détails de la source</span>
            </div>
          )}

          {!isLoading && isForbidden && (
            <div
              className="space-y-3 rounded-lg border border-teal/40 bg-deep/20 p-5"
              data-testid="source-drawer-forbidden"
              role="alert"
            >
              <div className="flex items-center gap-2">
                <ShieldAlert className="h-5 w-5 text-cyan" aria-hidden="true" />
                <h3 className="text-sm font-bold text-mist">Accès refusé</h3>
              </div>
              <p className="text-xs text-mist/90">{SOURCE_FORBIDDEN_MESSAGE}</p>
            </div>
          )}

          {!isLoading && !isForbidden && isNotFound && (
            <div
              className="space-y-3 rounded-lg border border-deep bg-deep/10 p-5 text-center"
              data-testid="source-drawer-not-found"
            >
              <FolderX className="mx-auto h-8 w-8 text-teal/60" aria-hidden="true" />
              <p className="text-xs text-mist/90">{SOURCE_NOT_FOUND_MESSAGE}</p>
            </div>
          )}

          {!isLoading && !isForbidden && !isNotFound && isError && (
            <div
              className="space-y-4 rounded-lg border border-teal/40 bg-deep/20 p-5"
              data-testid="source-drawer-error"
              role="alert"
            >
              <div className="flex items-start gap-3">
                <AlertTriangle
                  className="mt-0.5 h-5 w-5 flex-shrink-0 text-cyan"
                  aria-hidden="true"
                />
                <div className="space-y-1">
                  <h3 className="text-sm font-bold text-mist">{SOURCE_UNAVAILABLE_MESSAGE}</h3>
                  <p className="text-xs text-mist/90" data-testid="source-error-reason">
                    {error?.message ?? SOURCE_UNAVAILABLE_MESSAGE}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => refetch()}
                className="inline-flex items-center gap-1.5 rounded border border-cyan bg-cyan px-3 py-1.5 text-xs font-bold text-ink focus:outline-none focus:ring-2 focus:ring-cyan"
                data-testid="source-drawer-retry"
              >
                <RotateCw className="h-3.5 w-3.5" aria-hidden="true" />
                Réessayer
              </button>
            </div>
          )}

          {!isLoading &&
            !isForbidden &&
            !isNotFound &&
            !isError &&
            observation &&
            excerpt &&
            proof && (
              <>
                {status?.isUnknown && status.label && (
                  <div
                    className="rounded-lg border border-teal/40 bg-deep/20 p-3 text-xs text-cyan"
                    role="status"
                    data-testid="source-unknown-status"
                  >
                    {status.label} — actions dépendantes désactivées.
                  </div>
                )}

                <dl className="space-y-3 rounded-lg border border-deep bg-deep/10 p-4 text-xs">
                  <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
                    <dt className="font-semibold text-teal">Fichier source</dt>
                    <dd className="break-all font-mono text-mist" data-testid="source-file-name">
                      {entry.fileNameLabel}
                    </dd>
                    <dt className="font-semibold text-teal">Identifiant d’événement</dt>
                    <dd
                      className="break-all font-mono text-mist"
                      data-testid="source-event-identifier"
                    >
                      {entry.eventIdLabel}
                    </dd>
                    <dt className="font-semibold text-teal">Ligne / offset interne</dt>
                    <dd className="break-all font-mono text-mist" data-testid="source-line">
                      {entry.lineLabel}
                    </dd>
                    <dt className="font-semibold text-teal">Empreinte de preuve</dt>
                    <dd
                      className="break-all font-mono text-mist"
                      data-testid="source-proof-fingerprint"
                    >
                      {proof.label}
                      {!proof.isAvailable && ` (${TO_REALIGN})`}
                    </dd>
                  </div>
                </dl>

                <div className="space-y-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-teal">
                      Extrait technique brut
                    </h3>
                    <button
                      type="button"
                      disabled={actionsDisabled || excerpt.isEmpty}
                      onClick={() => void copyToClipboard(excerpt.previewText, 'excerpt')}
                      className="inline-flex items-center gap-1.5 rounded border border-teal bg-deep px-2.5 py-1 text-xs text-mist hover:bg-deep/80 focus:outline-none focus:ring-2 focus:ring-cyan disabled:cursor-not-allowed disabled:opacity-60"
                      title={
                        actionsDisabled
                          ? 'Action désactivée : état inconnu'
                          : 'Copier l’extrait affiché'
                      }
                      data-testid="source-copy-excerpt"
                    >
                      {copiedExcerpt ? (
                        <Check className="h-3.5 w-3.5 text-cyan" aria-hidden="true" />
                      ) : (
                        <Copy className="h-3.5 w-3.5 text-cyan" aria-hidden="true" />
                      )}
                      {copiedExcerpt ? 'Copié' : 'Copier l’extrait affiché'}
                    </button>
                  </div>
                  <button
                    type="button"
                    disabled={actionsDisabled || !proof.isAvailable}
                    onClick={() => void copyToClipboard(proof.copyValue, 'proof')}
                    className="inline-flex items-center gap-1.5 rounded border border-teal bg-deep px-2.5 py-1 text-xs text-mist hover:bg-deep/80 focus:outline-none focus:ring-2 focus:ring-cyan disabled:cursor-not-allowed disabled:opacity-60"
                    title={
                      actionsDisabled
                        ? 'Action désactivée : état inconnu'
                        : 'Copier l’empreinte intégrale'
                    }
                    data-testid="source-copy-proof"
                  >
                    {copiedProof ? (
                      <Check className="h-3.5 w-3.5 text-cyan" aria-hidden="true" />
                    ) : (
                      <Copy className="h-3.5 w-3.5 text-cyan" aria-hidden="true" />
                    )}
                    {copiedProof ? 'Copié' : 'Copier l’empreinte'}
                  </button>

                  {excerpt.isEmpty ? (
                    <p
                      className="rounded border border-deep bg-deep/10 p-4 text-xs text-teal"
                      data-testid="source-empty-message"
                    >
                      {SOURCE_EMPTY_MESSAGE}
                    </p>
                  ) : (
                    <pre
                      role="textbox"
                      aria-readonly="true"
                      className="max-h-80 overflow-auto whitespace-pre-wrap rounded border border-deep bg-deep/10 p-4 font-mono text-xs text-mist"
                      data-testid="source-raw-excerpt"
                      aria-label="Extrait brut de l’observation"
                    >
                      {excerpt.previewText}
                    </pre>
                  )}

                  {excerpt.isTruncated && (
                    <div
                      className="flex flex-wrap items-center justify-between gap-3 rounded border border-cyan/40 bg-deep/20 p-3 text-xs text-cyan"
                      role="status"
                      data-testid="source-truncation-banner"
                    >
                      <span data-testid="source-truncation-message">
                        {SOURCE_TRUNCATION_MESSAGE}
                      </span>
                      <a
                        href={buildSourceDownloadUrl(caseId, observation.id)}
                        download
                        aria-disabled={actionsDisabled}
                        className={`inline-flex items-center gap-1.5 rounded border px-3 py-1.5 font-semibold focus:outline-none focus:ring-2 focus:ring-cyan ${
                          actionsDisabled
                            ? 'pointer-events-none border-deep bg-deep/10 text-teal opacity-60'
                            : 'border-cyan bg-cyan text-ink'
                        }`}
                        data-testid="source-download-full"
                        title={actionsDisabled ? 'Action désactivée : état inconnu' : undefined}
                      >
                        <Download className="h-3.5 w-3.5" aria-hidden="true" />
                        Télécharger l'extrait complet
                      </a>
                    </div>
                  )}
                </div>

                <p
                  className="flex items-start gap-2 rounded border border-deep bg-deep/10 p-3 text-xs text-teal"
                  data-testid="source-confidentiality-note"
                >
                  <FileText
                    className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-cyan"
                    aria-hidden="true"
                  />
                  {SOURCE_CONFIDENTIALITY_NOTE}
                </p>
                <p className="text-xs text-teal" data-testid="source-reactivity-note">
                  {SOURCE_REACTIVITY_NOTE}
                </p>
              </>
            )}
        </div>
      </div>
    </>
  )
}
