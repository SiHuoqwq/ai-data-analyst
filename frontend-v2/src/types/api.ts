export interface ColumnInfo {
  name: string
  dtype: string
  null_count: number
  null_rate: number
  unique_count: number
  sample_values: unknown[]
}

export interface FileDetail {
  id: string
  filename: string
  file_type: string
  row_count: number
  col_count: number
  columns: ColumnInfo[]
  profile_report: string
}

export interface FileListItem {
  id: string
  filename: string
  file_type: string
  row_count: number
  col_count: number
  uploaded_at: string
}

export interface FilePreview {
  columns: string[]
  rows: unknown[][]
  total_rows: number
}

export interface ConversationItem {
  id: string
  file_id: string
  title: string
  mode: string
  created_at: string
  message_count: number
}

export interface HealthResponse {
  status: string
  provider: {
    mode: string
    display_name: string
    description: string
  }
}
