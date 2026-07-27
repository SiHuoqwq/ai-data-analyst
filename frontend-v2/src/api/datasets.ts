import { apiRequest } from './client'
import type { FileDetail, FileListItem, FilePreview } from '../types/api'

export const listDatasets = () => apiRequest<FileListItem[]>('/api/v1/files')
export const getDataset = (fileId: string) => apiRequest<FileDetail>(`/api/v1/files/${encodeURIComponent(fileId)}`)
export const getDatasetPreview = (fileId: string) =>
  apiRequest<FilePreview>(`/api/v1/files/${encodeURIComponent(fileId)}/preview?rows=20`)
export const uploadDataset = (file: File) => {
  const form = new FormData()
  form.append('file', file)
  return apiRequest<FileDetail>('/api/v1/files/upload', { method: 'POST', body: form })
}
export const deleteDataset = (fileId: string) =>
  apiRequest<{ ok: boolean }>(`/api/v1/files/${encodeURIComponent(fileId)}`, { method: 'DELETE' })
