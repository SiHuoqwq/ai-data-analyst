import { useEffect } from 'react';
import type { AppStage, FileDetail, FileListItem, ConversationItem } from '../../types';
import { listFiles, getFileDetail, deleteFile } from '../../api/files';
import { listConversations } from '../../api/conversations';
import FileUploadZone from '../files/FileUploadZone';
import FileHistoryList from '../files/FileHistoryList';
import { MessageSquare, Plus } from 'lucide-react';

interface Props {
  files: FileListItem[];
  setFiles: (files: FileListItem[]) => void;
  activeFile: FileDetail | null;
  setActiveFile: (file: FileDetail | null) => void;
  setStage: (stage: AppStage) => void;
  setToolCalls: (calls: never[]) => void;
  setChartPaths: (paths: string[]) => void;
  conversations: ConversationItem[];
  setConversations: (convs: ConversationItem[]) => void;
  activeConversationId: string | null;
  setActiveConversationId: (id: string | null) => void;
  conversationsDirty: number;
}

export default function LeftSidebar({
  files, setFiles, activeFile, setActiveFile, setStage, setToolCalls, setChartPaths,
  conversations, setConversations, activeConversationId, setActiveConversationId,
  conversationsDirty,
}: Props) {
  useEffect(() => {
    listFiles().then(setFiles).catch(console.error);
  }, [setFiles]);

  // Fetch conversations when active file or dirty counter changes
  useEffect(() => {
    if (activeFile) {
      listConversations(activeFile.id)
        .then(setConversations)
        .catch(console.error);
    } else {
      setConversations([]);
      setActiveConversationId(null);
    }
  }, [activeFile?.id, conversationsDirty, setConversations, setActiveConversationId]);

  const refreshFiles = () => {
    listFiles().then(setFiles).catch(console.error);
  };

  const handleSelect = async (fileId: string) => {
    setToolCalls([]);
    setChartPaths([]);
    setActiveConversationId(null);
    try {
      const detail = await getFileDetail(fileId);
      setActiveFile(detail);
      setStage('ready');
    } catch (e) {
      console.error('Failed to load file:', e);
    }
  };

  const handleUploaded = (detail: FileDetail) => {
    setActiveFile(detail);
    setStage('ready');
    setActiveConversationId(null);
    refreshFiles();
  };

  const handleDelete = async (fileId: string) => {
    try {
      await deleteFile(fileId);
      if (activeFile?.id === fileId) {
        setActiveFile(null);
        setStage('empty');
        setToolCalls([]);
        setChartPaths([]);
        setActiveConversationId(null);
        setConversations([]);
      }
      refreshFiles();
    } catch (e) {
      console.error('Failed to delete file:', e);
    }
  };

  const handleNewConversation = () => {
    setActiveConversationId(null);
    // ChatPanel will reset its messages when conversationId changes
  };

  return (
    <aside
      className="w-[18%] min-w-[200px] flex-shrink-0 flex flex-col gap-3 p-3 border-r overflow-y-auto"
      style={{ background: '#0c1324', borderColor: '#1e293b' }}
    >
      <h2 className="text-xs font-semibold uppercase tracking-wider" style={{ color: '#60a5fa' }}>
        数据文件
      </h2>

      <FileUploadZone onUploaded={handleUploaded} />

      <FileHistoryList
        files={files}
        activeFileId={activeFile?.id ?? null}
        onSelect={handleSelect}
        onDelete={handleDelete}
      />

      {/* Conversations Section */}
      {activeFile && (
        <>
          <div className="flex items-center justify-between mt-2 pt-3 border-t" style={{ borderColor: '#1e293b' }}>
            <h2 className="text-xs font-semibold uppercase tracking-wider" style={{ color: '#60a5fa' }}>
              对话历史
            </h2>
            <button
              onClick={handleNewConversation}
              className="p-1 rounded hover:opacity-80 transition-opacity"
              style={{ color: '#94a3b8' }}
              title="新对话"
            >
              <Plus size={14} />
            </button>
          </div>

          {conversations.length === 0 ? (
            <p className="text-xs" style={{ color: '#475569' }}>
              暂无对话
            </p>
          ) : (
            <div className="flex flex-col gap-1">
              {conversations.map((conv) => (
                <button
                  key={conv.id}
                  onClick={() => setActiveConversationId(conv.id)}
                  className="flex items-center gap-2 px-2 py-1.5 rounded text-left text-xs transition-colors"
                  style={{
                    background: activeConversationId === conv.id ? '#1e293b' : 'transparent',
                    color: activeConversationId === conv.id ? '#e2e8f0' : '#94a3b8',
                  }}
                >
                  <MessageSquare size={12} className="flex-shrink-0" />
                  <span className="truncate flex-1">{conv.title}</span>
                  <span className="flex-shrink-0" style={{ color: '#475569', fontSize: '10px' }}>
                    {conv.message_count}
                  </span>
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </aside>
  );
}
