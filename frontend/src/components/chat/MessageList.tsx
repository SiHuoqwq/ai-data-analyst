import UserMessage from './UserMessage';
import AssistantMessage from './AssistantMessage';

interface ToolCall {
  name: string;
  args: Record<string, unknown>;
  status: 'running' | 'done';
}

export interface Message {
  role: 'user' | 'assistant';
  content: string;
  toolCalls?: ToolCall[];
  chartPaths?: string[];
}

interface Props {
  messages: Message[];
}

export default function MessageList({ messages }: Props) {
  return (
    <div className="flex-1 overflow-y-auto px-4 py-4">
      {messages.map((msg, i) =>
        msg.role === 'user' ? (
          <UserMessage key={i} content={msg.content} />
        ) : (
          <AssistantMessage
            key={i}
            content={msg.content}
            toolCalls={msg.toolCalls}
            chartPaths={msg.chartPaths}
          />
        )
      )}
    </div>
  );
}
