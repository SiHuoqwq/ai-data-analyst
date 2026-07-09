import { apiClient } from './client';

export async function generateReport(fileId: string, conversationId?: string): Promise<string> {
  const { data } = await apiClient.post<{ report: string }>('/report/generate', {
    file_id: fileId,
    conversation_id: conversationId || null,
  });
  return data.report;
}
