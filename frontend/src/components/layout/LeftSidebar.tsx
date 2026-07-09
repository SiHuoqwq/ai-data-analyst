import { useEffect } from 'react';
import type { AppStage, FileDetail, FileListItem } from '../../types';
import { listFiles, getFileDetail } from '../../api/files';

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

  return (
    <aside
      className="w-[18%] min-w-[200px] flex-shrink-0 flex flex-col gap-3 p-3 border-r overflow-y-auto"
      style={{ background: '#0c1324', borderColor: '#1e293b' }}
    >
      <h2 className="text-xs font-semibold uppercase tracking-wider" style={{ color: '#60a5fa' }}>
        数据文件
      </h2>

      {/* Upload zone — will be extracted to FileUploadZone in Phase 2 */}
      <div
        className="border border-dashed rounded-lg p-4 text-center cursor-pointer transition-colors"
        style={{ borderColor: '#1e293b' }}
        onClick={() => {
          const input = document.createElement('input');
          input.type = 'file';
          input.accept = '.csv,.xlsx,.xls';
          input.onchange = async () => {
            const file = input.files?.[0];
            if (!file) return;
            const { uploadFile } = await import('../../api/files');
            try {
              const detail = await uploadFile(file);
              setActiveFile(detail);
              setStage('ready');
              refreshFiles();
            } catch (e) {
              console.error('Upload failed:', e);
            }
          };
          input.click();
        }}
      >
        <span className="text-lg" style={{ color: '#60a5fa' }}>+</span>
        <p className="text-xs mt-1" style={{ color: '#94a3b8' }}>上传 CSV / Excel</p>
      </div>

      {/* File history list */}
      <div className="flex flex-col gap-1">
        <p className="text-[10px] font-medium uppercase tracking-wider px-1" style={{ color: '#64748b' }}>
          历史文件
        </p>
        {files.map((f) => (
          <div
            key={f.id}
            onClick={() => handleSelect(f.id)}
            className="flex items-start gap-2 p-2 rounded-lg cursor-pointer transition-colors text-xs"
            style={{
              background: f.id === activeFile?.id ? '#1a2744' : 'transparent',
              borderLeft: f.id === activeFile?.id ? '2px solid #2563eb' : '2px solid transparent',
              color: f.id === activeFile?.id ? '#e2e8f0' : '#94a3b8',
            }}
          >
            <span className="flex-shrink-0 mt-0.5">📄</span>
            <div className="min-w-0">
              <p className="truncate">{f.filename}</p>
              <p className="text-[10px]" style={{ color: '#64748b' }}>
                {f.col_count}列 · {f.row_count}行
              </p>
            </div>
          </div>
        ))}
      </div>
    </aside>
  );
}
