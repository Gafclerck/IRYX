import { useState, useCallback, useRef, useEffect } from 'react'
import type { EvidenceUploadItem, RejectedFileInfo } from '../types'
import { validateEvidenceFile } from '../utils/fileValidation'
import {
  uploadEvidenceFileXHR,
  UploadAbortError,
  type UploadXHRHandle,
} from '../services/evidenceUploadService'

export interface UseEvidenceUploadOptions {
  readonly caseId: string
}

export interface UseEvidenceUploadReturn {
  readonly uploadItems: readonly EvidenceUploadItem[]
  readonly rejectedFiles: readonly RejectedFileInfo[]
  readonly isUploading: boolean
  readonly addFiles: (files: File[]) => void
  readonly cancelUpload: (id: string) => void
  readonly retryUpload: (id: string) => void
  readonly dismissRejectedFile: (index: number) => void
  readonly clearRejectedFiles: () => void
  readonly clearCompleted: () => void
}

/**
 * Hook de gestion du téléversement de preuves numériques avec suivi de progression (Story F3.1).
 */
export function useEvidenceUpload({ caseId }: UseEvidenceUploadOptions): UseEvidenceUploadReturn {
  const [uploadItems, setUploadItems] = useState<EvidenceUploadItem[]>([])
  const [rejectedFiles, setRejectedFiles] = useState<RejectedFileInfo[]>([])

  // Référence sur les requêtes actives pour permettre l'annulation et le nettoyage
  const activeHandlesRef = useRef<Map<string, UploadXHRHandle>>(new Map())

  // Nettoyage au démontage
  useEffect(() => {
    const handles = activeHandlesRef.current
    return () => {
      handles.forEach((handle) => {
        handle.abort()
      })
      handles.clear()
    }
  }, [])

  const executeUpload = useCallback(
    (id: string, file: File) => {
      const handle = uploadEvidenceFileXHR({
        caseId,
        file,
        onProgress: (percent) => {
          setUploadItems((prev) =>
            prev.map((item) => (item.id === id ? { ...item, progress: percent } : item)),
          )
        },
      })

      activeHandlesRef.current.set(id, handle)

      setUploadItems((prev) =>
        prev.map((item) =>
          item.id === id
            ? {
                ...item,
                status: 'uploading',
                progress: 0,
                errorMessage: undefined,
                abortFn: () => handle.abort(),
              }
            : item,
        ),
      )

      handle.promise
        .then((response) => {
          activeHandlesRef.current.delete(id)
          setUploadItems((prev) =>
            prev.map((item) =>
              item.id === id
                ? {
                    ...item,
                    status: 'success',
                    progress: 100,
                    evidenceId: response.evidence_id,
                    ingestionRunId: response.ingestion_run_id,
                    abortFn: undefined,
                  }
                : item,
            ),
          )
        })
        .catch((err: unknown) => {
          activeHandlesRef.current.delete(id)
          if (err instanceof UploadAbortError) {
            setUploadItems((prev) =>
              prev.map((item) =>
                item.id === id
                  ? {
                      ...item,
                      status: 'aborted',
                      errorMessage: 'Téléversement interrompu.',
                      abortFn: undefined,
                    }
                  : item,
              ),
            )
          } else {
            const message =
              err instanceof Error
                ? err.message
                : 'Échec du transfert : une anomalie réseau ou serveur est survenue.'
            setUploadItems((prev) =>
              prev.map((item) =>
                item.id === id
                  ? {
                      ...item,
                      status: 'error',
                      errorMessage: message,
                      abortFn: undefined,
                    }
                  : item,
              ),
            )
          }
        })
    },
    [caseId],
  )

  const addFiles = useCallback(
    (files: File[]) => {
      const newRejected: RejectedFileInfo[] = []
      const acceptedFiles: { id: string; file: File }[] = []

      for (const file of files) {
        const validation = validateEvidenceFile(file)
        if (!validation.valid) {
          newRejected.push({
            name: file.name,
            reason: validation.reason || 'Format de fichier non supporté.',
          })
        } else {
          const id =
            typeof crypto !== 'undefined' && crypto.randomUUID
              ? crypto.randomUUID()
              : `upload-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
          acceptedFiles.push({ id, file })
        }
      }

      if (newRejected.length > 0) {
        setRejectedFiles((prev) => [...prev, ...newRejected])
      }

      if (acceptedFiles.length > 0) {
        const newItems: EvidenceUploadItem[] = acceptedFiles.map(({ id, file }) => ({
          id,
          file,
          name: file.name,
          size: file.size,
          progress: 0,
          status: 'pending',
        }))

        setUploadItems((prev) => [...prev, ...newItems])

        // Lancer immédiatement le téléversement de chaque fichier accepté
        for (const { id, file } of acceptedFiles) {
          executeUpload(id, file)
        }
      }
    },
    [executeUpload],
  )

  const cancelUpload = useCallback((id: string) => {
    const handle = activeHandlesRef.current.get(id)
    if (handle) {
      handle.abort()
      activeHandlesRef.current.delete(id)
    }
  }, [])

  const retryUpload = useCallback(
    (id: string) => {
      const targetItem = uploadItems.find((item) => item.id === id)
      if (targetItem) {
        executeUpload(id, targetItem.file)
      }
    },
    [uploadItems, executeUpload],
  )

  const dismissRejectedFile = useCallback((index: number) => {
    setRejectedFiles((prev) => prev.filter((_, i) => i !== index))
  }, [])

  const clearRejectedFiles = useCallback(() => {
    setRejectedFiles([])
  }, [])

  const clearCompleted = useCallback(() => {
    setUploadItems((prev) => prev.filter((item) => item.status !== 'success'))
  }, [])

  const isUploading = uploadItems.some((item) => item.status === 'uploading')

  return {
    uploadItems,
    rejectedFiles,
    isUploading,
    addFiles,
    cancelUpload,
    retryUpload,
    dismissRejectedFile,
    clearRejectedFiles,
    clearCompleted,
  }
}
