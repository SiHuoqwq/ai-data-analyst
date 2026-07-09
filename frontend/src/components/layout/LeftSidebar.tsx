import { useEffect } from 'react';
import type { AppStage, FileDetail, FileListItem } from '../../types';
import { listFiles, getFileDetail } from '../../api/files';
import FileUploadZone from '../files/FileUploadZone';
import FileHistoryList from '../files/FileHistoryList';

interface Props {
  files: FileListItem[];
  setFiles: (files: FileListItem[]) => void;
  activeFile: FileDetail | null;
  setActiveFile: (file: FileDetail | null) => void;
  setStage: (stage: AppStage) => void;
  setToolCalls: (calls: never[]) => void;
  setChartPaths: (paths: string[]) => void;
}

export default function LeftSidebar({ files, setFiles, activeFile, setActiveFile, setStage, setToolCalls, setChartPaths }: Props) {
  useEffect(() => {
    listFiles().then(setFiles).catch(console.error);
  }, [setFiles]);

  const refreshFiles = () => {
    listFiles().then(setFiles).catch(console.error);
  };

  const handleSelect = async (fileId: string) => {
    setToolCalls([]);
    setChartPaths([]);
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
    refreshFiles();
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
      />
    </aside>
  );
}
