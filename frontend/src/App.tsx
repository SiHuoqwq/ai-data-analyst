import { useState } from 'react';
import TopBar from './components/layout/TopBar';
import LeftSidebar from './components/layout/LeftSidebar';
import ChatPanel from './components/layout/ChatPanel';
import ContextPanel from './components/layout/ContextPanel';
import type { AppStage, FileDetail, FileListItem } from './types';

function App() {
  const [files, setFiles] = useState<FileListItem[]>([]);
  const [activeFile, setActiveFile] = useState<FileDetail | null>(null);
  const [stage, setStage] = useState<AppStage>('empty');
  const [toolCalls, setToolCalls] = useState<
    { name: string; args: Record<string, unknown>; status: 'pending' | 'running' | 'done' }[]
  >([]);
  const [chartPaths, setChartPaths] = useState<string[]>([]);

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
        />
        <ChatPanel
          activeFile={activeFile}
          stage={stage}
          setStage={setStage}
          setToolCalls={setToolCalls}
          setChartPaths={setChartPaths}
        />
        <ContextPanel
          activeFile={activeFile}
          stage={stage}
          toolCalls={toolCalls}
          chartPaths={chartPaths}
        />
      </div>
    </div>
  );
}

export default App;
