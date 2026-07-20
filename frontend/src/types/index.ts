export interface ColumnInfo {
  name: string;
  dtype: string;
  null_count: number;
  null_rate: number;
  unique_count: number;
  sample_values: string[];
}

export interface FileDetail {
  id: string;
  filename: string;
  file_type: string;
  row_count: number;
  col_count: number;
  columns: ColumnInfo[];
  profile_report: string;
}

export interface FileListItem {
  id: string;
  filename: string;
  file_type: string;
  row_count: number;
  col_count: number;
  uploaded_at: string;
}

export interface FilePreview {
  columns: string[];
  rows: (string | number)[][];
  total_rows: number;
}

export interface SSEToolEvent {
  type: 'tool';
  content: string;
}

export interface SSETextEvent {
  type: 'text';
  content: string;
}

export interface SSEToolResultEvent {
  type: 'tool_result';
  content: string;
}

export interface SSEChartEvent {
  type: 'chart';
  path: string;
}

export interface SSEDoneEvent {
  type: 'done';
  conversation_id: string;
  chart_paths?: string[];
}

export interface SSEErrorEvent {
  type: 'error';
  message: string;
}

export type SSEEvent = SSEToolEvent | SSETextEvent | SSEToolResultEvent | SSEChartEvent | SSEDoneEvent | SSEErrorEvent;

export type AppStage = 'empty' | 'upload' | 'ready' | 'analyzing' | 'complete';

export interface MessageItem {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  tool_calls: { name: string; args: Record<string, unknown> }[] | null;
  chart_ids: string[] | null;
  created_at: string;
}

export interface ConversationItem {
  id: string;
  file_id: string;
  title: string;
  mode: string;
  created_at: string;
  message_count: number;
}

export interface ConversationDetail extends ConversationItem {
  messages: MessageItem[];
}
