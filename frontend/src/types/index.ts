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

export interface SSEDoneEvent {
  type: 'done';
  conversation_id: string;
  chart_paths?: string[];
}

export type SSEEvent = SSEToolEvent | SSETextEvent | SSEToolResultEvent | SSEDoneEvent;

export type AppStage = 'empty' | 'upload' | 'ready' | 'analyzing' | 'complete';
