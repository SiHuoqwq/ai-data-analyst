import type { ConversationItem, ConversationDetail } from '../types';

export async function listConversations(fileId: string): Promise<ConversationItem[]> {
  const res = await fetch(`/api/v1/files/${fileId}/conversations`);
  if (!res.ok) throw new Error('Failed to fetch conversations');
  return res.json();
}

export async function getConversation(convId: string): Promise<ConversationDetail> {
  const res = await fetch(`/api/v1/conversations/${convId}`);
  if (!res.ok) throw new Error('Failed to fetch conversation');
  return res.json();
}
