import { apiRequest } from './client'
import { parseArtifact, parseArtifacts } from './v2-contracts'
import type { AnalysisArtifact } from '../types/v2'

export async function listAnalysisRunArtifacts(runId: string): Promise<AnalysisArtifact[]> {
  return parseArtifacts(
    await apiRequest<unknown>(`/api/v2/runs/${encodeURIComponent(runId)}/artifacts`),
  )
}

export async function getArtifact(artifactId: string): Promise<AnalysisArtifact> {
  return parseArtifact(
    await apiRequest<unknown>(`/api/v2/artifacts/${encodeURIComponent(artifactId)}`),
  )
}
