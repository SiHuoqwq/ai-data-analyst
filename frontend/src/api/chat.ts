import type { SSEEvent } from '../types';

export async function* streamChat(req: {
  file_id: string;
  message: string;
  conversation_id?: string | null;
}): AsyncGenerator<SSEEvent> {
  const response = await fetch('/api/v1/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });

  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.detail || 'Chat request failed');
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const json = line.slice(6);
        if (json) {
          yield JSON.parse(json) as SSEEvent;
        }
      }
    }
  }
}
