import { getAccessToken } from '../../../api/auth-memory'
import { emitAuthSignal } from '../../../api/auth-signal'
import type { EvidenceUploadResponse } from '../types'

/**
 * Erreur survenue lors du téléversement XHR.
 */
export class UploadError extends Error {
  readonly status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'UploadError'
    this.status = status
  }
}

/**
 * Erreur spécifique lors de l'annulation manuelle du téléversement.
 */
export class UploadAbortError extends Error {
  constructor(message = 'Téléversement interrompu par l’opérateur.') {
    super(message)
    this.name = 'UploadAbortError'
  }
}

export interface UploadXHROptions {
  readonly caseId: string
  readonly file: File
  readonly onProgress?: (percent: number, loaded: number, total: number) => void
}

export interface UploadXHRHandle {
  readonly promise: Promise<EvidenceUploadResponse>
  readonly abort: () => void
}

/**
 * Module d'encapsulation XMLHttpRequest pour le téléversement de preuves avec suivi de progression (D-38).
 *
 * RÈGLES DE CONCEPTION (D-38, Story F3.1, openapi.json) :
 * 1. Envoi par XMLHttpRequest multipart vers POST /api/v1/cases/:caseId/evidences.
 * 2. En-tête HTTP Authorization: Bearer <token> à partir du jeton actif en mémoire vive.
 * 3. En l'absence de jeton, requête sans en-tête pour déclencher le signal 401 côté serveur.
 * 4. Mesure en temps réel de la progression par xhr.upload.onprogress.
 * 5. Possibilité d'interruption immédiate via la méthode abort() de l'instance XHR.
 * 6. Code HTTP 202 Accepted attendu au succès, retournant { evidence_id, ingestion_run_id }.
 * 7. Aucune limite de taille n'est imposée côté client (« à caler C3 »). Le serveur retourne 413 au-delà de sa limite.
 */
export function uploadEvidenceFileXHR({
  caseId,
  file,
  onProgress,
}: UploadXHROptions): UploadXHRHandle {
  const xhr = new XMLHttpRequest()
  let aborted = false
  let rejectFn: ((reason?: unknown) => void) | null = null

  const promise = new Promise<EvidenceUploadResponse>((resolve, reject) => {
    rejectFn = reject
    const targetUrl = `/api/v1/cases/${encodeURIComponent(caseId)}/evidences`

    xhr.open('POST', targetUrl, true)

    // Injection du jeton d'accès Bearer en mémoire vive volatile (Story F1.3)
    const token = getAccessToken()
    if (token) {
      xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    }

    // Suivi de la progression en streaming (D-38)
    if (xhr.upload && onProgress) {
      xhr.upload.onprogress = (event: ProgressEvent) => {
        if (event.lengthComputable && event.total > 0) {
          const percent = Math.min(100, Math.round((event.loaded / event.total) * 100))
          onProgress(percent, event.loaded, event.total)
        }
      }
    }

    xhr.onload = () => {
      if (aborted) return

      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const data = JSON.parse(xhr.responseText) as EvidenceUploadResponse
          if (onProgress) {
            onProgress(100, file.size, file.size)
          }
          resolve(data)
        } catch {
          resolve({ evidence_id: '', ingestion_run_id: '' })
        }
      } else {
        if (xhr.status === 401) {
          emitAuthSignal({ url: targetUrl })
        }

        let detail = ''
        try {
          const parsed = JSON.parse(xhr.responseText)
          if (parsed && typeof parsed.detail === 'string') {
            detail = parsed.detail
          } else if (parsed && Array.isArray(parsed.detail) && parsed.detail[0]?.msg) {
            detail = parsed.detail[0].msg
          }
        } catch {
          // Utilisation du message HTTP par défaut
        }

        if (!detail) {
          if (xhr.status === 413) {
            detail = 'Fichier volumineux : dépassement du plafond configuré par le serveur.'
          } else if (xhr.status === 403) {
            detail = "Vous n'avez pas accès à ce dossier."
          } else if (xhr.status === 404) {
            detail = 'Dossier introuvable.'
          } else if (xhr.status === 400) {
            detail = 'Le fichier de preuve est vide ou non valide.'
          } else if (xhr.status >= 500) {
            detail = 'Erreur interne du serveur lors du téléversement.'
          } else {
            detail = `Échec de téléversement (HTTP ${xhr.status}).`
          }
        }

        reject(new UploadError(detail, xhr.status))
      }
    }

    xhr.onerror = () => {
      if (aborted) return
      reject(new UploadError('Erreur réseau lors du téléversement.', 0))
    }

    xhr.onabort = () => {
      aborted = true
      reject(new UploadAbortError())
    }

    const formData = new FormData()
    formData.append('file', file)
    xhr.send(formData)
  })

  return {
    promise,
    abort: () => {
      if (!aborted) {
        aborted = true
        try {
          xhr.abort()
        } catch {
          // Ignoré
        }
        if (rejectFn) {
          rejectFn(new UploadAbortError())
        }
      }
    },
  }
}
