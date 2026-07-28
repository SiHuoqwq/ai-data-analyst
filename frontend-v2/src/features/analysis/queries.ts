import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createV2Conversation, getConversationDetail } from '../../api/v2-conversations'
import { cancelAnalysisRun, createAnalysisRun, getAnalysisRun, listAnalysisRunSteps } from '../../api/v2-runs'
import { listAnalysisRunArtifacts } from '../../api/v2-artifacts'
import type { CreateConversationInput, CreateRunInput } from '../../types/v2'

export const analysisKeys = {
  conversation: (id: string) => ['analysis', 'conversation', id] as const,
  run: (id: string) => ['analysis', 'run', id] as const,
  steps: (id: string) => ['analysis', 'run', id, 'steps'] as const,
  artifacts: (id: string) => ['analysis', 'run', id, 'artifacts'] as const,
}

export const useConversationDetail = (conversationId: string) =>
  useQuery({
    queryKey: analysisKeys.conversation(conversationId),
    queryFn: () => getConversationDetail(conversationId),
    enabled: Boolean(conversationId),
  })

export const useAnalysisRun = (runId: string) =>
  useQuery({
    queryKey: analysisKeys.run(runId),
    queryFn: () => getAnalysisRun(runId),
    enabled: Boolean(runId),
  })

export const useAnalysisRunSteps = (runId: string) =>
  useQuery({
    queryKey: analysisKeys.steps(runId),
    queryFn: () => listAnalysisRunSteps(runId),
    enabled: Boolean(runId),
  })

export const useAnalysisRunArtifacts = (runId: string) =>
  useQuery({
    queryKey: analysisKeys.artifacts(runId),
    queryFn: () => listAnalysisRunArtifacts(runId),
    enabled: Boolean(runId),
  })

export const useCreateConversation = () =>
  useMutation({
    mutationFn: (input: CreateConversationInput) => createV2Conversation(input),
    retry: false,
  })

export const useCreateAnalysisRun = () =>
  useMutation({
    mutationFn: ({
      conversationId,
      input,
      idempotencyKey,
    }: {
      conversationId: string
      input: CreateRunInput
      idempotencyKey: string
    }) => createAnalysisRun(conversationId, input, idempotencyKey),
    retry: false,
  })

export function useCancelAnalysisRun() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (runId: string) => cancelAnalysisRun(runId),
    retry: false,
    onSuccess: (run) => {
      client.setQueryData(analysisKeys.run(run.id), run)
      void client.invalidateQueries({ queryKey: analysisKeys.steps(run.id) })
      void client.invalidateQueries({ queryKey: analysisKeys.artifacts(run.id) })
    },
  })
}

export const refreshRunEvidence = (
  client: ReturnType<typeof useQueryClient>,
  runId: string,
) => Promise.all([
  client.invalidateQueries({ queryKey: analysisKeys.run(runId) }),
  client.invalidateQueries({ queryKey: analysisKeys.steps(runId) }),
  client.invalidateQueries({ queryKey: analysisKeys.artifacts(runId) }),
])
