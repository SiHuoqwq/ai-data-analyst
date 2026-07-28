import { apiRequest } from './client'
import { parseCreateRun, parseRun, parseSteps } from './v2-contracts'
import type { AnalysisRun, CreateRunInput, CreateRunResult, RunStep } from '../types/v2'

export async function createAnalysisRun(
  conversationId: string,
  input: CreateRunInput,
  idempotencyKey: string,
): Promise<CreateRunResult> {
  const response = await apiRequest<unknown>(
    `/api/v2/conversations/${encodeURIComponent(conversationId)}/runs`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': idempotencyKey,
      },
      body: JSON.stringify(input),
    },
  )
  return parseCreateRun(response)
}

export async function getAnalysisRun(runId: string): Promise<AnalysisRun> {
  return parseRun(await apiRequest<unknown>(`/api/v2/runs/${encodeURIComponent(runId)}`))
}

export async function listAnalysisRunSteps(runId: string): Promise<RunStep[]> {
  return parseSteps(await apiRequest<unknown>(`/api/v2/runs/${encodeURIComponent(runId)}/steps`))
}

export async function cancelAnalysisRun(runId: string): Promise<AnalysisRun> {
  return parseRun(await apiRequest<unknown>(`/api/v2/runs/${encodeURIComponent(runId)}/cancel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason: 'user_requested' }),
  }))
}
