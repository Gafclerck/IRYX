import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from './mocks/server'
import { EvidencePage } from '../pages/EvidencePage'
import { validateEvidenceFile, formatFileSize } from '../features/evidence/utils/fileValidation'
import { EVIDENCE_CAPACITY_NOTE } from '../features/evidence/constants'
import { uploadEvidenceFileXHR } from '../features/evidence/services/evidenceUploadService'
import { setAccessToken, clearAccessToken, setSessionUser } from '../api/auth-memory'

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 0,
        gcTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
  })
}

function renderEvidencePage(initialCaseId = 'case-001') {
  const queryClient = createTestQueryClient()
  return {
    queryClient,
    ...render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/cases/${initialCaseId}/evidence`]}>
          <Routes>
            <Route
              path="/cases"
              element={<div data-testid="cases-list-page">Liste des dossiers</div>}
            />
            <Route path="/cases/:caseId" element={<div>Contexte dossier</div>} />
            <Route path="/cases/:caseId/evidence" element={<EvidencePage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  }
}

describe('Story F3.1 : Dépôt et téléversement de preuves avec progression (FR-EVI-01, D-38)', () => {
  beforeEach(() => {
    clearAccessToken()
    setAccessToken('mock-access-token-bearer-15min')
    setSessionUser({
      userName: 'analyste@iryx.local',
      organizationName: 'CERT National IRYX',
      role: 'analyst',
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('1. Formats autorisés et validation côté client', () => {
    it('accepte tous les formats autorisés par la story F3.1 (EVTX, logs, ruches, Prefetch, images RAM)', () => {
      const validFiles = [
        new File(['evtx content'], 'Security.evtx', { type: 'application/octet-stream' }),
        new File(['log content'], 'auth.log', { type: 'text/plain' }),
        new File(['txt content'], 'syslog.txt', { type: 'text/plain' }),
        new File(['csv content'], 'firewall.csv', { type: 'text/csv' }),
        new File(['pf content'], 'CMD.EXE-A1B2C3D4.pf', { type: 'application/octet-stream' }),
        new File(['hive content'], 'SYSTEM', { type: 'application/octet-stream' }),
        new File(['hive content'], 'SAM', { type: 'application/octet-stream' }),
        new File(['hive content'], 'SOFTWARE.dat', { type: 'application/octet-stream' }),
        new File(['hive content'], 'ntuser.dat', { type: 'application/octet-stream' }),
        new File(['hive content'], 'system.hiv', { type: 'application/octet-stream' }),
        new File(['ram content'], 'memory_dump.raw', { type: 'application/octet-stream' }),
        new File(['ram content'], 'win10.dmp', { type: 'application/octet-stream' }),
        new File(['ram content'], 'ram.mem', { type: 'application/octet-stream' }),
        new File(['ram content'], 'image.vmem', { type: 'application/octet-stream' }),
      ]

      for (const file of validFiles) {
        const result = validateEvidenceFile(file)
        expect(result.valid, `Le fichier ${file.name} devrait être accepté`).toBe(true)
        expect(result.reason).toBeUndefined()
      }
    })

    it('refuse immédiatement côté client les formats non supportés avec un motif descriptif', () => {
      const invalidFiles = [
        new File(['pdf'], 'document.pdf', { type: 'application/pdf' }),
        new File(['exe'], 'malware.exe', { type: 'application/x-msdownload' }),
        new File(['zip'], 'archive.zip', { type: 'application/zip' }),
        new File(['docx'], 'rapport.docx', { type: 'application/vnd.openxmlformats' }),
      ]

      for (const file of invalidFiles) {
        const result = validateEvidenceFile(file)
        expect(result.valid, `Le fichier ${file.name} devrait être rejeté`).toBe(false)
        expect(result.reason).toContain('Format de fichier non supporté')
        expect(result.reason).toContain(file.name)
        expect(result.reason).toContain(
          'EVTX, logs texte, ruches de registre, Prefetch, images RAM',
        )
      }
    })

    it('formate correctement la volumétrie en français (o, Ko, Mo, Go)', () => {
      expect(formatFileSize(0)).toBe('0 o')
      expect(formatFileSize(512)).toBe('512 o')
      expect(formatFileSize(2048)).toBe('2.0 Ko')
      expect(formatFileSize(5 * 1024 * 1024)).toBe('5.0 Mo')
      expect(formatFileSize(1.5 * 1024 * 1024 * 1024)).toBe('1.5 Go')
    })
  })

  describe('2. Règle volumétrique C3 : aucune limite côté client et affichage du motif serveur', () => {
    it('n impose aucun plafond côté client sur de très gros fichiers forensiques', () => {
      const hugeFile = new File(['x'.repeat(100)], 'memory_huge.raw', {
        type: 'application/octet-stream',
      })
      Object.defineProperty(hugeFile, 'size', { value: 64 * 1024 * 1024 * 1024 }) // 64 Go

      const result = validateEvidenceFile(hugeFile)
      expect(result.valid).toBe(true)
    })

    it('affiche le rappel d architecture C3 dans la zone de dépôt', async () => {
      renderEvidencePage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('evidence-capacity-note')).toBeInTheDocument()
      })

      expect(screen.getByText(EVIDENCE_CAPACITY_NOTE)).toBeInTheDocument()
    })
  })

  describe('3. État initial, barre latérale et zone de glisser-déposer', () => {
    it('affiche la barre latérale avec l étape 2 Preuves active', async () => {
      renderEvidencePage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('case-sidebar')).toBeInTheDocument()
      })

      const step2 = screen.getByTestId('sidebar-step-2')
      expect(step2).toHaveTextContent(/Preuves/i)
      expect(step2).toHaveAttribute('href', '/cases/case-001/evidence')
      expect(screen.getByText('Registre et téléversement des preuves')).toBeInTheDocument()
    })

    it('affiche l état vide initial lorsqu aucune preuve n est encore téléversée', async () => {
      renderEvidencePage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('evidence-empty-state')).toBeInTheDocument()
      })

      expect(screen.getByText('Aucune preuve déposée pour ce dossier')).toBeInTheDocument()
    })

    it('met en avant les formats pris en charge dans la zone de dépôt', async () => {
      renderEvidencePage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('evidence-dropzone')).toBeInTheDocument()
      })

      expect(
        screen.getByText(
          /Formats acceptés : EVTX, logs texte, ruches de registre, Prefetch, images RAM/i,
        ),
      ).toBeInTheDocument()
    })
  })

  describe('4. Téléversement nominal avec progression et statut en attente d ingestion', () => {
    it('affiche la ligne du fichier avec nom, taille, progression puis bascule au statut « en attente d ingestion »', async () => {
      renderEvidencePage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('evidence-dropzone')).toBeInTheDocument()
      })

      const testFile = new File(['données forensiques evtx'], 'SecAudit.evtx', {
        type: 'application/octet-stream',
      })

      const fileInput = screen.getByTestId('evidence-file-input')
      fireEvent.change(fileInput, { target: { files: [testFile] } })

      // Le fichier doit apparaître dans la liste des transferts
      await waitFor(() => {
        expect(screen.getByText('SecAudit.evtx')).toBeInTheDocument()
      })

      // Après succès (HTTP 202), le statut passe à « en attente d'ingestion » tel quel
      await waitFor(() => {
        expect(screen.getByText("EN ATTENTE D'INGESTION")).toBeInTheDocument()
      })
      expect(screen.getByText("en attente d'ingestion")).toBeInTheDocument()
    })

    it('gère le dépôt multiple de fichiers valides en parallèle', async () => {
      renderEvidencePage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('evidence-dropzone')).toBeInTheDocument()
      })

      const file1 = new File(['content1'], 'syslog.log', { type: 'text/plain' })
      const file2 = new File(['content2'], 'MEMORY.DMP', { type: 'application/octet-stream' })

      const fileInput = screen.getByTestId('evidence-file-input')
      fireEvent.change(fileInput, { target: { files: [file1, file2] } })

      await waitFor(() => {
        expect(screen.getByText('syslog.log')).toBeInTheDocument()
        expect(screen.getByText('MEMORY.DMP')).toBeInTheDocument()
      })

      await waitFor(() => {
        const statuses = screen.getAllByText("EN ATTENTE D'INGESTION")
        expect(statuses.length).toBe(2)
      })
    })

    it('rejette immédiatement les fichiers non conformes sans créer de ligne dans la liste et affiche le motif', async () => {
      renderEvidencePage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('evidence-dropzone')).toBeInTheDocument()
      })

      const invalidFile = new File(['binary exe'], 'payload.exe', {
        type: 'application/x-msdownload',
      })

      const fileInput = screen.getByTestId('evidence-file-input')
      fireEvent.change(fileInput, { target: { files: [invalidFile] } })

      // L'alerte de rejet immédiat s'affiche
      await waitFor(() => {
        expect(screen.getByTestId('evidence-rejected-banner')).toBeInTheDocument()
      })
      expect(
        screen.getByText(/Format de fichier non supporté pour « payload.exe »/i),
      ).toBeInTheDocument()

      // Aucun enregistrement ni ligne fantôme créée dans la liste
      expect(screen.getByTestId('evidence-empty-state')).toBeInTheDocument()
      expect(screen.queryByTestId(/evidence-upload-item-/)).not.toBeInTheDocument()
    })
  })

  describe('5. Annulation et reprise (Réessayer) sur échec ou refus serveur', () => {
    it('affiche le bouton Annuler et permet d interrompre la requête XHR', async () => {
      // Mock d'un upload lent
      server.use(
        http.post('*/api/v1/cases/:caseId/evidences', async () => {
          await new Promise((r) => setTimeout(r, 2000))
          return HttpResponse.json(
            { evidence_id: 'e-slow', ingestion_run_id: 'r-slow' },
            { status: 202 },
          )
        }),
      )

      renderEvidencePage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('evidence-dropzone')).toBeInTheDocument()
      })

      const testFile = new File(['forensic stream'], 'long_dump.raw', {
        type: 'application/octet-stream',
      })

      const fileInput = screen.getByTestId('evidence-file-input')
      fireEvent.change(fileInput, { target: { files: [testFile] } })

      await waitFor(() => {
        expect(screen.getByText(/Annuler/i)).toBeInTheDocument()
      })

      const cancelBtn = screen.getByText(/Annuler/i)
      fireEvent.click(cancelBtn)

      await waitFor(() => {
        expect(screen.getByText(/ANNULÉ/i)).toBeInTheDocument()
      })
      expect(screen.getByText(/Réessayer/i)).toBeInTheDocument()
    })

    it('affiche la mention « ÉCHEC DE TRANSFERT » et le bouton « Réessayer » en cas d erreur serveur 500', async () => {
      server.use(
        http.post('*/api/v1/cases/:caseId/evidences', () => {
          return HttpResponse.json(
            { detail: 'Erreur interne du serveur lors du téléversement.' },
            { status: 500 },
          )
        }),
      )

      renderEvidencePage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('evidence-dropzone')).toBeInTheDocument()
      })

      const testFile = new File(['data'], 'crash.evtx', { type: 'application/octet-stream' })
      const fileInput = screen.getByTestId('evidence-file-input')
      fireEvent.change(fileInput, { target: { files: [testFile] } })

      await waitFor(() => {
        expect(screen.getByText(/ÉCHEC DE TRANSFERT/i)).toBeInTheDocument()
      })
      expect(screen.getByText(/Erreur interne du serveur/i)).toBeInTheDocument()
      expect(screen.getByText(/Réessayer/i)).toBeInTheDocument()
    })

    it('affiche le refus du serveur en cas de dépassement volumétrique HTTP 413 (C3)', async () => {
      server.use(
        http.post('*/api/v1/cases/:caseId/evidences', () => {
          return HttpResponse.json(
            { detail: 'Fichier volumineux : dépassement du plafond configuré par le serveur.' },
            { status: 413 },
          )
        }),
      )

      renderEvidencePage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('evidence-dropzone')).toBeInTheDocument()
      })

      const testFile = new File(['data'], 'too_heavy.raw', { type: 'application/octet-stream' })
      const fileInput = screen.getByTestId('evidence-file-input')
      fireEvent.change(fileInput, { target: { files: [testFile] } })

      await waitFor(() => {
        expect(screen.getByText(/ÉCHEC DE TRANSFERT/i)).toBeInTheDocument()
      })
      expect(
        screen.getByText(/Fichier volumineux : dépassement du plafond configuré par le serveur/i),
      ).toBeInTheDocument()
    })
  })

  describe('6. Contrôle d accès et profil lecture seule', () => {
    it('désactive et masque la zone de dépôt pour un utilisateur en lecture seule (viewer)', async () => {
      setSessionUser({
        userName: 'auditeur@soc.local',
        organizationName: 'CERT National IRYX',
        role: 'viewer',
      })

      renderEvidencePage('case-001')

      await waitFor(() => {
        expect(screen.getByTestId('evidence-dropzone-disabled')).toBeInTheDocument()
      })
      expect(screen.getByText('Accès en lecture seule')).toBeInTheDocument()
      expect(screen.queryByTestId('evidence-dropzone')).not.toBeInTheDocument()
    })

    it('redirige vers /cases en cas de 403 Forbidden sur le dossier', async () => {
      renderEvidencePage('case-forbidden')

      await waitFor(() => {
        expect(screen.getByTestId('case-forbidden-banner')).toBeInTheDocument()
      })
      expect(screen.getByText(/Vous n'avez pas accès à ce dossier/i)).toBeInTheDocument()

      await waitFor(
        () => {
          expect(screen.getByTestId('cases-list-page')).toBeInTheDocument()
        },
        { timeout: 2500 },
      )
    })

    it('affiche l état dossier introuvable en cas de 404', async () => {
      renderEvidencePage('case-not-found')

      await waitFor(() => {
        expect(screen.getByTestId('case-not-found')).toBeInTheDocument()
      })
      expect(screen.getByText(/Dossier d’investigation introuvable/i)).toBeInTheDocument()
    })
  })

  describe('7. Module XMLHttpRequest (D-38) et injection Authorization: Bearer', () => {
    it('transmet l en-tête Authorization: Bearer <token> dans la requête XHR', async () => {
      let capturedAuth: string | null = null

      server.use(
        http.post('*/api/v1/cases/:caseId/evidences', ({ request }) => {
          capturedAuth = request.headers.get('Authorization')
          return HttpResponse.json(
            { evidence_id: 'evi-auth-ok', ingestion_run_id: 'run-auth-ok' },
            { status: 202 },
          )
        }),
      )

      const file = new File(['content'], 'test.evtx', { type: 'application/octet-stream' })
      const handle = uploadEvidenceFileXHR({ caseId: 'case-001', file })
      const result = await handle.promise

      expect(capturedAuth).toBe('Bearer mock-access-token-bearer-15min')
      expect(result.evidence_id).toBe('evi-auth-ok')
    })
  })
})
