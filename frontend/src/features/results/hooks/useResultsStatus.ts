import { useEffect, useState } from 'react'
import { formatInvestigationStatus } from '../../plan/constants'
import { getInvestigationRuns } from '../../plan/services/planService'
import type { InvestigationRunOut, ResultsStatusInfo } from '../types'

export interface UseResultsStatusOptions {
  readonly caseId: string
  readonly enabled?: boolean
}

const INITIAL_STATUS: ResultsStatusInfo = {
  statusLabel: null,
  isUnknown: false,
  failedPhases: [],
}

function selectLatestRun(runs: readonly InvestigationRunOut[]): InvestigationRunOut | null {
  return (
    [...runs].sort((a, b) => String(b.started_at).localeCompare(String(a.started_at)))[0] ?? null
  )
}

/**
 * État de la session d'investigation associée aux résultats (Story F4.6).
 *
 * RÈGLES :
 * 1. Le statut est lu dans la session contractuelle : aucun statut n'est déduit
 *    côté client. Un code non répertorié devient « État inconnu (code_brut) ».
 * 2. Le bandeau de résultats partiels n'apparaît que si le contrat signale une
 *    phase en échec (`PhaseStatus: failed`).
 * 3. Consultation ponctuelle : aucune scrutation n'est ajoutée ici (ADR-0008).
 */
export function useResultsStatus({
  caseId,
  enabled = true,
}: UseResultsStatusOptions): ResultsStatusInfo {
  const [info, setInfo] = useState<ResultsStatusInfo>(INITIAL_STATUS)

  useEffect(() => {
    if (!enabled || !caseId) {
      setInfo(INITIAL_STATUS)
      return
    }

    let active = true
    setInfo(INITIAL_STATUS)

    getInvestigationRuns(caseId)
      .then(({ data }) => {
        if (!active) return
        const run = selectLatestRun(data)
        const status = formatInvestigationStatus(run?.status)
        const failedPhases =
          run?.phases
            ?.filter((phase) => phase.status === 'failed')
            .map((phase) => phase.phase_name) ?? []
        setInfo({
          statusLabel: run ? status.label : null,
          isUnknown: Boolean(run) && !status.isKnown,
          failedPhases,
        })
      })
      .catch(() => {
        if (!active) return
        setInfo(INITIAL_STATUS)
      })

    return () => {
      active = false
    }
  }, [caseId, enabled])

  return info
}
