import { useState, useCallback } from 'react';
import TopBar from './components/layout/TopBar';
import LeftSidebar from './components/layout/LeftSidebar';
import ChatPanel from './components/layout/ChatPanel';
import ContextPanel from './components/layout/ContextPanel';
import type { AppStage, FileDetail, FileListItem, ConversationItem } from './types';

function App() {
  const [files, setFiles] = useState<FileListItem[]>([]);
  const [activeFile, setActiveFile] = useState<FileDetail | null>(null);
  const [stage, setStage] = useState<AppStage>('empty');
  const [toolCalls, setToolCalls] = useState<
    { name: string; args: Record<string, unknown>; status: 'pending' | 'running' | 'done' }[]
  >([]);
  const [chartPaths, setChartPaths] = useState<string[]>([]);
  const [conversations, setConversations] = useState<ConversationItem[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [conversationsDirty, setConversationsDirty] = useState(0);

  const markConversationsDirty = useCallback(() => {
    setConversationsDirty((n) => n + 1);
  }, []);

  return (
    <div className="h-screen flex flex-col" style={{ background: '#0f172a' }}>
      <TopBar activeFile={activeFile} stage={stage} />
      <div className="flex flex-1 overflow-hidden">
        <LeftSidebar
          files={files}
          setFiles={setFiles}
          activeFile={activeFile}
          setActiveFile={setActiveFile}
          setStage={setStage}
          setToolCalls={setToolCalls}
          setChartPaths={setChartPaths}
          conversations={conversations}
          setConversations={setConversations}
          activeConversationId={activeConversationId}
          setActiveConversationId={setActiveConversationId}
          conversationsDirty={conversationsDirty}
        />
        <ChatPanel
          activeFile={activeFile}
          stage={stage}
          setStage={setStage}
          setToolCalls={setToolCalls}
          setChartPaths={setChartPaths}
          activeConversationId={activeConversationId}
          setActiveConversationId={setActiveConversationId}
          markConversationsDirty={markConversationsDirty}
        />
        <ContextPanel
          activeFile={activeFile}
          stage={stage}
          toolCalls={toolCalls}
          chartPaths={chartPaths}
          activeConversationId={activeConversationId}
        />
      </div>
    </div>
  );
}

export default App;
