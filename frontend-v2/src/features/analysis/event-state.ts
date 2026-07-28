import type { RunStatus, V2EventEnvelope } from '../../types/v2'

export interface RunEventState {
  runId: string
  status: RunStatus
  lastSequence: number
  seenEventIds: string[]
  stepEvents: V2EventEnvelope[]
  artifactIds: string[]
  terminal: boolean
}

export const createRunEventState = (runId: string): RunEventState => ({
  runId,
  status: 'queued',
  lastSequence: 0,
  seenEventIds: [],
  stepEvents: [],
  artifactIds: [],
  terminal: false,
})

const terminalStatus = (eventType: V2EventEnvelope['event_type']): RunStatus | null => {
  if (eventType === 'run.completed') return 'completed'
  if (eventType === 'run.failed') return 'failed'
  if (eventType === 'run.cancelled') return 'cancelled'
  return null
}

export function applyRunEvent(state: RunEventState, event: V2EventEnvelope): RunEventState {
  if (event.run_id !== state.runId || event.sequence <= state.lastSequence
    || state.seenEventIds.includes(event.event_id)) return state

  const next = {
    ...state,
    lastSequence: event.sequence,
    seenEventIds: [...state.seenEventIds, event.event_id],
  }
  if (event.event_type === 'run.status'
    && (event.payload.status === 'queued' || event.payload.status === 'running')) {
    next.status = event.payload.status
  }
  const finalStatus = terminalStatus(event.event_type)
  if (finalStatus) {
    next.status = finalStatus
    next.terminal = true
  }
  if (event.event_type === 'step.started' || event.event_type === 'step.completed') {
    next.stepEvents = [...state.stepEvents, event]
  }
  if (event.event_type === 'artifact.created' && typeof event.payload.artifact_id === 'string') {
    next.artifactIds = state.artifactIds.includes(event.payload.artifact_id)
      ? state.artifactIds
      : [...state.artifactIds, event.payload.artifact_id]
  }
  return next
}
