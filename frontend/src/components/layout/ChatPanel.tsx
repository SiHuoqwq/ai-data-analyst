import { useState, useCallback, useEffect, type Dispatch, type SetStateAction } from 'react';
import type { AppStage, FileDetail } from '../../types';
import { streamChat } from '../../api/chat';
import { getConversation } from '../../api/conversations';
import MessageList, { type Message } from '../chat/MessageList';
import ChatInput from '../chat/ChatInput';

interface ToolCall {
  name: string;
  args: Record<string, unknown>;
  status: 'running' | 'done';
}

interface Props {
  activeFile: FileDetail | null;
  stage: AppStage;
  setStage: (stage: AppStage) => void;
  setToolCalls: (
    calls: { name: string; args: Record<string, unknown>; status: 'pending' | 'running' | 'done' }[]
  ) => void;
  setChartPaths: Dispatch<SetStateAction<string[]>>;
  activeConversationId: string | null;
  setActiveConversationId: (id: string | null) => void;
  markConversationsDirty: () => void;
}

export default function ChatPanel({
  activeFile,
  stage,
  setStage,
  setToolCalls: updateParentToolCalls,
  setChartPaths: updateParentChartPaths,
  activeConversationId,
  setActiveConversationId,
  markConversationsDirty,
}: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const isStreaming = stage === 'analyzing';

  // Load conversation messages when activeConversationId changes
  useEffect(() => {
    if (!activeConversationId) {
      setMessages([]);
      return;
    }
    getConversation(activeConversationId)
      .then((conv) => {
        const msgs: Message[] = conv.messages.map((m) => ({
          role: m.role as 'user' | 'assistant',
          content: m.content,
          toolCalls: (m.tool_calls ?? []).map((tc) => ({
            name: tc.name,
            args: tc.args,
            status: 'done' as const,
          })),
          chartPaths: m.chart_ids ?? [],
        }));
        setMessages(msgs);
        setStage('complete');
      })
      .catch(console.error);
  }, [activeConversationId, setStage]);

  const extractChartPaths = useCallback((text: string): string[] => {
    const matches = text.match(/\/storage\/charts\/[a-f0-9-]+\.png/g);
    return matches ? [...new Set(matches)] : [];
  }, []);

  const handleSend = useCallback(
    async (text: string) => {
      if (!activeFile) return;

      const userMsg: Message = { role: 'user', content: text };
      const assistantMsg: Message = { role: 'assistant', content: '', toolCalls: [], chartPaths: [] };

      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setStage('analyzing');

      try {
        const generator = streamChat({
          file_id: activeFile.id,
          message: text,
          conversation_id: activeConversationId,
        });

        for await (const event of generator) {
          switch (event.type) {
            case 'tool': {
              let parsed: ToolCall[];
              try {
                parsed = JSON.parse(event.content) as ToolCall[];
              } catch {
                parsed = [];
              }

              const runningCalls: ToolCall[] = parsed.map((tc) => ({
                ...tc,
                status: 'running' as const,
              }));

              setMessages((prev) => {
                const copy = [...prev];
                const lastIdx = copy.length - 1;
                const last = { ...copy[lastIdx] };
                last.toolCalls = [...(last.toolCalls || []), ...runningCalls];
                copy[lastIdx] = last;
                return copy;
              });

              updateParentToolCalls(
                parsed.map((tc) => ({ ...tc, status: 'running' as const }))
              );
              break;
            }

            case 'text': {
              setMessages((prev) => {
                const copy = [...prev];
                const lastIdx = copy.length - 1;
                const last = { ...copy[lastIdx] };
                last.content += event.content;
                copy[lastIdx] = last;
                return copy;
              });
              break;
            }

            case 'done': {
              setActiveConversationId(event.conversation_id);
              markConversationsDirty();

              const backendChartPaths: string[] = (event.chart_paths ?? []).map(
                (p) => p.replace(/^\.\//, '/')
              );

              let finalToolCalls: ToolCall[] = [];
              let finalChartPaths: string[] = backendChartPaths;

              setMessages((prev) => {
                const copy = [...prev];
                const lastIdx = copy.length - 1;
                const last = { ...copy[lastIdx] };

                if (last.toolCalls) {
                  last.toolCalls = last.toolCalls.map((tc) => ({
                    ...tc,
                    status: 'done' as const,
                  }));
                  finalToolCalls = last.toolCalls;
                }

                const contentChartPaths = extractChartPaths(last.content);
                last.chartPaths = [...new Set([...contentChartPaths, ...backendChartPaths])];
                finalChartPaths = last.chartPaths;

                copy[lastIdx] = last;
                return copy;
              });

              if (finalToolCalls.length > 0) {
                updateParentToolCalls(finalToolCalls);
              }
              updateParentChartPaths(finalChartPaths);

              setStage('complete');
              break;
            }

            case 'chart': {
              const normalized = event.path.replace(/^\.\//, '/');
              setMessages((prev) => {
                const copy = [...prev];
                const lastIdx = copy.length - 1;
                const last = { ...copy[lastIdx] };
                last.chartPaths = [...(last.chartPaths || []), normalized];
                copy[lastIdx] = last;
                return copy;
              });
              updateParentChartPaths((prev) => [...prev, normalized]);
              break;
            }

            case 'error': {
              throw new Error(event.message);
            }
          }
        }
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : '请求失败，请重试';

        setMessages((prev) => {
          const copy = [...prev];
          const lastIdx = copy.length - 1;
          const last = { ...copy[lastIdx] };
          if (!last.content) {
            last.content = `请求失败: ${errorMsg}`;
          } else {
            last.content += `\n\n请求失败: ${errorMsg}`;
          }
          if (last.toolCalls) {
            last.toolCalls = last.toolCalls.map((tc) => ({
              ...tc,
              status: 'done' as const,
            }));
          }
          copy[lastIdx] = last;
          return copy;
        });

        setStage('ready');
      }
    },
    [activeFile, activeConversationId, setActiveConversationId, markConversationsDirty, setStage, extractChartPaths, updateParentToolCalls, updateParentChartPaths]
  );

  // Empty state when no messages yet
  if (messages.length === 0) {
    return (
      <main className="flex-1 flex flex-col min-w-0">
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <p className="text-xl mb-2" style={{ color: '#e2e8f0' }}>
              AI Data Analyst
            </p>
            <p className="text-sm" style={{ color: '#64748b' }}>
              {activeFile
                ? `已加载 ${activeFile.filename}，开始提问吧`
                : '上传数据文件开始分析'}
            </p>
          </div>
        </div>
        <ChatInput onSend={handleSend} disabled={!activeFile || isStreaming} />
      </main>
    );
  }

  return (
    <main className="flex-1 flex flex-col min-w-0">
      <MessageList messages={messages} />
      <ChatInput onSend={handleSend} disabled={!activeFile || isStreaming} />
    </main>
  );
}
