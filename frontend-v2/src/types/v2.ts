export type RunStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
export type StepStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
export type ArtifactType = 'text' | 'metric' | 'table' | 'chart'

export interface ApiMeta {
  request_id: string
  schema_version: string
  next_cursor?: string | null
  has_more?: boolean | null
}

export interface V2Conversation {
  id: string
  file_id: string
  title: string
  mode: string
  created_at: string
}

export interface ConversationMessage {
  id: string
  role: 'user' | 'assistant' | string
  content: string
  tool_calls: unknown[] | null
  chart_ids: string[] | null
  created_at: string
}

export interface ConversationDetail extends V2Conversation {
  messages: ConversationMessage[]
}

export interface RunProgress {
  completed_steps: number
  total_steps: number | null
}

export interface AnalysisRun {
  id: string
  conversation_id: string
  dataset_version_id: string
  trigger_message_id: string
  answer_message_id: string | null
  input_message_id: string
  output_message_id: string | null
  status: RunStatus
  current_phase: string | null
  progress: RunProgress
  failure: Record<string, unknown> | null
  created_at: string
  updated_at: string
  started_at: string | null
  completed_at: string | null
  finished_at: string | null
  cancelled_at: string | null
  error: Record<string, unknown> | null
  last_event_sequence: number
  allowed_actions: Record<string, boolean>
}

export interface CreatedRun {
  id: string
  conversation_id: string
  status: RunStatus
  dataset_version_id: string
  input_message_id: string
  output_message_id: string | null
}

export interface CreateRunResult {
  message: {
    id: string
    role: string
    content_text: string
    status: string
  }
  run: CreatedRun
  events_url: string
}

export interface RunStep {
  id: string
  plan_step_id: string | null
  sequence: number
  phase: string
  operation: string
  display_name: string
  status: StepStatus
  attempt: number
  max_attempts: number
  output_summary: Record<string, unknown> | null
  error: Record<string, unknown> | null
  artifact_ids: string[]
  started_at: string | null
  finished_at: string | null
}

export interface TextArtifactPayload {
  format: 'markdown' | 'plain_text'
  content: string
}

export interface MetricArtifactPayload {
  label: string
  value: number | string | null
  display_value: string
  unit: string | null
}

export interface TableColumn {
  key: string
  label: string
  data_type: 'string' | 'number' | 'boolean' | 'datetime' | 'null'
  unit?: string
}

export interface TableArtifactPayload {
  columns: TableColumn[]
  rows: Record<string, unknown>[]
}

export interface ChartArtifactPayload {
  renderer: 'static-image'
  chart_type: 'bar' | 'line' | 'scatter' | 'heatmap'
  title: string
  image_url: string
  alt_text: string
}

export interface AnalysisArtifact {
  id: string
  dataset_version_id: string
  run_id: string
  run_step_id: string
  artifact_type: ArtifactType | string
  status: string
  title: string
  content_format: string
  payload: Record<string, unknown>
  size_bytes: number
  row_count: number | null
  download_available: boolean
  created_at: string
}

export type V2EventType =
  | 'run.started'
  | 'run.status'
  | 'step.started'
  | 'step.completed'
  | 'artifact.created'
  | 'answer.completed'
  | 'run.completed'
  | 'run.failed'
  | 'run.cancelled'
  | 'heartbeat'

export interface V2EventEnvelope {
  event_id: string
  event_type: V2EventType
  run_id: string
  sequence: number
  timestamp: string
  schema_version: '1.0'
  payload: Record<string, unknown>
}

export interface CreateConversationInput {
  file_id: string
  title?: string
}

export interface CreateRunInput {
  message: string
  dataset_version_id?: string
  recommendation_id?: string
  confirm_version_switch?: boolean
  reply_to_message_id?: string
  parent_run_id?: string
  retry_of_run_id?: string
  context?: {
    include_message_ids: string[]
    include_artifact_ids: string[]
  }
}
