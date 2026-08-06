import { invalidResponseError } from './errors'
import type {
  AnalysisArtifact,
  AnalysisRun,
  ConversationDetail,
  CreateRunResult,
  RunStep,
  V2Conversation,
  V2EventEnvelope,
  V2EventType,
} from '../types/v2'

const object = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value)

const string = (value: unknown): value is string => typeof value === 'string'
const nullableString = (value: unknown): value is string | null => value === null || string(value)
const number = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)
const stringArray = (value: unknown): value is string[] => Array.isArray(value) && value.every(string)

export type DatasetRecommendation = {
  id: string
  intent_type: 'group_comparison' | 'monthly_trend'
  label: string
  question: string
  referenced_fields: string[]
}

export type DatasetRecommendationResponse = {
  dataset_version_id: string
  recommendations: DatasetRecommendation[]
  source: 'model' | 'template'
  generated_at: string
}

const unwrap = (value: unknown): Record<string, unknown> => {
  if (!object(value) || !object(value.data)) throw invalidResponseError()
  return value.data
}

export const parseConversation = (value: unknown): V2Conversation => {
  const data = unwrap(value)
  if (![data.id, data.file_id, data.title, data.mode, data.created_at].every(string)) {
    throw invalidResponseError()
  }
  return data as unknown as V2Conversation
}

export const parseConversationDetail = (value: unknown): ConversationDetail => {
  if (!object(value) || !Array.isArray(value.messages)
    || ![value.id, value.file_id, value.title, value.mode, value.created_at].every(string)) {
    throw invalidResponseError()
  }
  for (const message of value.messages) {
    if (!object(message) || ![message.id, message.role, message.content, message.created_at].every(string)) {
      throw invalidResponseError()
    }
  }
  return value as unknown as ConversationDetail
}

const runStatus = (value: unknown) =>
  value === 'queued' || value === 'running' || value === 'completed'
  || value === 'failed' || value === 'cancelled'

export const parseRun = (value: unknown): AnalysisRun => {
  const data = unwrap(value)
  if (![data.id, data.conversation_id, data.dataset_version_id, data.trigger_message_id,
    data.input_message_id, data.status, data.created_at, data.updated_at].every(string)
    || !runStatus(data.status) || !nullableString(data.answer_message_id)
    || !nullableString(data.output_message_id) || !number(data.last_event_sequence)
    || !object(data.progress) || !object(data.allowed_actions)) {
    throw invalidResponseError()
  }
  return data as unknown as AnalysisRun
}

export const parseCreateRun = (value: unknown): CreateRunResult => {
  const data = unwrap(value)
  if (!object(data.message) || !object(data.run) || !string(data.events_url)
    || ![data.message.id, data.message.role, data.message.content_text, data.message.status].every(string)
    || ![data.run.id, data.run.conversation_id, data.run.status, data.run.dataset_version_id,
      data.run.input_message_id].every(string)
    || !runStatus(data.run.status) || !nullableString(data.run.output_message_id)) {
    throw invalidResponseError()
  }
  return data as unknown as CreateRunResult
}

const parseList = <T>(value: unknown, validator: (item: Record<string, unknown>) => boolean): T[] => {
  if (!object(value) || !Array.isArray(value.data) || !value.data.every((item) => object(item) && validator(item))) {
    throw invalidResponseError()
  }
  return value.data as T[]
}

const validStep = (item: Record<string, unknown>) =>
  [item.id, item.phase, item.operation, item.display_name, item.status].every(string)
  && number(item.sequence) && stringArray(item.artifact_ids)

const validArtifact = (item: Record<string, unknown>) =>
  [item.id, item.dataset_version_id, item.run_id, item.run_step_id, item.artifact_type,
    item.status, item.title, item.content_format, item.created_at].every(string)
  && object(item.payload) && number(item.size_bytes)

export const parseSteps = (value: unknown) => parseList<RunStep>(value, validStep)
export const parseArtifacts = (value: unknown) => parseList<AnalysisArtifact>(value, validArtifact)

export const parseArtifact = (value: unknown): AnalysisArtifact => {
  const data = unwrap(value)
  if (!validArtifact(data)) throw invalidResponseError()
  return data as unknown as AnalysisArtifact
}

const validRecommendation = (value: unknown): value is DatasetRecommendation =>
  object(value)
  && [value.id, value.label, value.question].every(string)
  && (value.intent_type === 'group_comparison' || value.intent_type === 'monthly_trend')
  && stringArray(value.referenced_fields)

export const parseDatasetRecommendations = (value: unknown): DatasetRecommendationResponse => {
  const data = unwrap(value)
  if (!string(data.dataset_version_id) || !Array.isArray(data.recommendations)
    || data.recommendations.length > 2 || !data.recommendations.every(validRecommendation)
    || (data.source !== 'model' && data.source !== 'template') || !string(data.generated_at)) {
    throw invalidResponseError()
  }
  return data as unknown as DatasetRecommendationResponse
}

const eventTypes = new Set<V2EventType>([
  'run.started', 'run.status', 'step.started', 'step.completed', 'artifact.created',
  'answer.completed', 'run.completed', 'run.failed', 'run.cancelled', 'heartbeat',
])

export const parseEventEnvelope = (value: unknown): V2EventEnvelope | null => {
  if (!object(value) || !string(value.event_id) || !string(value.event_type)
    || !eventTypes.has(value.event_type as V2EventType) || !string(value.run_id)
    || !number(value.sequence) || value.sequence < 1 || !string(value.timestamp)
    || value.schema_version !== '1.0' || !object(value.payload)) {
    return null
  }
  return value as unknown as V2EventEnvelope
}
