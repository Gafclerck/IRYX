import { useState, useRef, type DragEvent, type ChangeEvent, type KeyboardEvent } from 'react'
import { UploadCloud, FileCheck2, Info, Lock } from 'lucide-react'
import {
  ACCEPTED_EXTENSIONS,
  EVIDENCE_ACCEPTED_FORMATS_SUMMARY,
  EVIDENCE_CAPACITY_NOTE,
} from '../constants'

export interface EvidenceDropZoneProps {
  readonly onFilesSelected: (files: File[]) => void
  readonly disabled?: boolean
  readonly readOnlyMessage?: string
}

/**
 * Zone de dépôt de fichiers de preuves par glisser-déposer ou sélection explorateur (Story F3.1).
 *
 * RÈGLES DE CONCEPTION (FR-EVI-01, Section 3.4 de 11-ecrans-et-routes.md) :
 * 1. Supporte le glisser-déposer et la sélection multiple de fichiers.
 * 2. Met en avant les formats de fichiers pris en charge (EVTX, logs texte, ruches de registre, Prefetch, images RAM).
 * 3. Affiche le plafond volumétrique unitaire : « à caler (C3) » sans imposer de limite côté client.
 * 4. Mode désactivé / masqué pour utilisateur sans droit de modification (lecture seule).
 * 5. Navigation intégrale au clavier et anneau cyan (NFR-ACC-03).
 * 6. Palette stricte (ink, deep, teal, cyan, mist) sans aucun code hexadécimal en dur.
 */
export function EvidenceDropZone({
  onFilesSelected,
  disabled = false,
  readOnlyMessage,
}: EvidenceDropZoneProps) {
  const [isDragOver, setIsDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // En mode lecture seule, la zone de dépôt est désactivée et masquée (ou remplacée par un encart informatif)
  if (disabled) {
    return (
      <div
        className="rounded-lg border border-deep bg-deep/20 p-6 text-center"
        data-testid="evidence-dropzone-disabled"
        aria-label="Zone de dépôt de preuves désactivée"
      >
        <div className="flex flex-col items-center justify-center space-y-2">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-deep text-mist">
            <Lock className="h-5 w-5" aria-hidden="true" />
          </div>
          <p className="text-sm font-semibold uppercase tracking-wider text-mist">
            Accès en lecture seule
          </p>
          <p className="text-xs text-mist/80 max-w-md">
            {readOnlyMessage ||
              'La zone de téléversement est désactivée pour votre profil sur ce dossier. Vous pouvez uniquement consulter les éléments scellés.'}
          </p>
        </div>
      </div>
    )
  }

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragOver(true)
  }

  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragOver(false)
  }

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragOver(false)

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const filesArray = Array.from(e.dataTransfer.files)
      onFilesSelected(filesArray)
    }
  }

  const handleInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const filesArray = Array.from(e.target.files)
      onFilesSelected(filesArray)
      // Réinitialisation du champ pour permettre de re-sélectionner le même fichier si besoin
      e.target.value = ''
    }
  }

  const handleClick = () => {
    fileInputRef.current?.click()
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      fileInputRef.current?.click()
    }
  }

  return (
    <div className="space-y-3" data-testid="evidence-dropzone-container">
      <div
        role="button"
        tabIndex={0}
        aria-label="Zone de dépôt de preuves : glissez-déposez des fichiers ou appuyez sur Entrée pour parcourir vos dossiers"
        data-testid="evidence-dropzone"
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={handleClick}
        onKeyDown={handleKeyDown}
        className={`relative flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-cyan ${
          isDragOver
            ? 'border-cyan bg-deep/40'
            : 'border-deep bg-deep/10 hover:border-teal hover:bg-deep/20'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={ACCEPTED_EXTENSIONS.join(',')}
          onChange={handleInputChange}
          className="sr-only"
          tabIndex={-1}
          data-testid="evidence-file-input"
          aria-hidden="true"
        />

        <div className="flex flex-col items-center justify-center space-y-3 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-deep/60 text-cyan">
            <UploadCloud className="h-6 w-6" aria-hidden="true" />
          </div>

          <div className="space-y-1">
            <p className="text-sm font-medium text-mist">
              <span className="font-semibold text-cyan underline underline-offset-4">
                Parcourir vos fichiers
              </span>{' '}
              ou glisser-déposer des preuves numériques ici
            </p>
            <p className="text-xs text-mist/70">
              Sélection multiple autorisée pour le transfert en parallèle
            </p>
          </div>

          <div className="flex flex-wrap items-center justify-center gap-2 pt-2">
            <span className="inline-flex items-center gap-1 rounded bg-deep px-2.5 py-1 text-xs text-mist">
              <FileCheck2 className="h-3.5 w-3.5 text-teal" aria-hidden="true" />
              <span>Formats acceptés : {EVIDENCE_ACCEPTED_FORMATS_SUMMARY}</span>
            </span>
          </div>
        </div>
      </div>

      {/* Mention institutionnelle et rappel d'architecture C3 */}
      <div
        className="flex items-start gap-2 rounded border border-deep/60 bg-ink p-3 text-xs text-mist/80"
        data-testid="evidence-capacity-note"
      >
        <Info className="h-4 w-4 flex-shrink-0 text-teal mt-0.5" aria-hidden="true" />
        <div className="space-y-0.5">
          <p className="font-medium text-mist">{EVIDENCE_CAPACITY_NOTE}</p>
          <p className="text-mist/70">
            Tout transfert volumineux est diffusé en streaming continu (chunks de 64 Ko). En cas de
            dépassement de la capacité serveur, le rejet est notifié immédiatement.
          </p>
        </div>
      </div>
    </div>
  )
}
