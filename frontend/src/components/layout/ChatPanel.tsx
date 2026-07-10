import { useState, useRef, useCallback } from 'react';
import type { AppStage, FileDetail } from '../../types';
import { streamChat } from '../../api/chat';
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
  setChartPaths: (paths: string[]) => void;
}

export default function ChatPanel({
  activeFile,
  stage,
  setStage,
  setToolCalls: updateParentToolCalls,
  setChartPaths: updateParentChartPaths,
}: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const conversationIdRef = useRef<string | null>(null);
  const isStreaming = stage === 'analyzing';

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
          conversation_id: conversationIdRef.current,
        });

        for await (const event of generator) {
          switch (event.type) {
            case 'tool': {
              // Parse the JSON array of tool calls
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

              // Update parent state for ContextPanel
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
              conversationIdRef.current = event.conversation_id;

              // Use chart paths from backend if provided, normalize "./" prefix
              const backendChartPaths: string[] = (event.chart_paths ?? []).map(
                (p) => p.replace(/^\.\//, '/')
              );

              // Capture final values for parent state update
              let finalToolCalls: {
                name: string;
                args: Record<string, unknown>;
                status: 'done';
              }[] = [];
              let finalChartPaths: string[] = backendChartPaths;

              setMessages((prev) => {
                const copy = [...prev];
                const lastIdx = copy.length - 1;
                const last = { ...copy[lastIdx] };

                // Mark all tool calls as done
                if (last.toolCalls) {
                  last.toolCalls = last.toolCalls.map((tc) => ({
                    ...tc,
                    status: 'done' as const,
                  }));
                  finalToolCalls = last.toolCalls;
                }

                // Merge content-extracted paths with backend-provided paths
                const contentChartPaths = extractChartPaths(last.content);
                last.chartPaths = [...new Set([...contentChartPaths, ...backendChartPaths])];
                finalChartPaths = last.chartPaths;

                copy[lastIdx] = last;
                return copy;
              });

              // Update parent state for ContextPanel
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
          // Mark any running tool calls as done on error
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
    [activeFile, setStage, extractChartPaths, updateParentToolCalls, updateParentChartPaths]
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
