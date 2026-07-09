import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import ToolCallCard from './ToolCallCard';
import ChartInline from './ChartInline';

interface ToolCall {
  name: string;
  args: Record<string, unknown>;
  status: 'running' | 'done';
}

interface Props {
  content: string;
  toolCalls?: ToolCall[];
  chartPaths?: string[];
}

export default function AssistantMessage({ content, toolCalls, chartPaths }: Props) {
  return (
    <div className="flex gap-3 mb-4">
      {/* AI Avatar */}
      <div
        className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 text-xs font-bold"
        style={{ background: '#2563eb', color: '#ffffff' }}
      >
        AI
      </div>

      <div
        className="rounded-2xl px-4 py-3 max-w-[80%] text-sm leading-relaxed min-w-0"
        style={{ background: '#1a2744', color: '#e2e8f0' }}
      >
        {/* Tool calls above content */}
        {toolCalls && toolCalls.length > 0 && (
          <div className="mb-2">
            {toolCalls.map((tc, i) => (
              <ToolCallCard
                key={i}
                name={tc.name}
                args={tc.args}
                status={tc.status}
              />
            ))}
          </div>
        )}

        {/* Markdown content */}
        {content && (
          <div className="prose prose-sm max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {content}
            </ReactMarkdown>
          </div>
        )}

        {/* Chart images below content */}
        {chartPaths && chartPaths.length > 0 && (
          <div className="mt-2">
            {chartPaths.map((path, i) => (
              <ChartInline key={i} path={path} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
