import { apiRequest } from './client'
import type { ConversationItem } from '../types/api'

export const listDatasetConversations = (fileId: string) =>
  apiRequest<ConversationItem[]>(`/api/v1/files/${encodeURIComponent(fileId)}/conversations`)
