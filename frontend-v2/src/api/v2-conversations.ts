import { apiRequest } from './client'
import { parseConversation, parseConversationDetail } from './v2-contracts'
import type { ConversationDetail, CreateConversationInput, V2Conversation } from '../types/v2'

export async function createV2Conversation(input: CreateConversationInput): Promise<V2Conversation> {
  const response = await apiRequest<unknown>('/api/v2/conversations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  return parseConversation(response)
}

export async function getConversationDetail(conversationId: string): Promise<ConversationDetail> {
  const response = await apiRequest<unknown>(
    `/api/v1/conversations/${encodeURIComponent(conversationId)}`,
  )
  return parseConversationDetail(response)
}
