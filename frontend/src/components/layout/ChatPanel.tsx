import type { AppStage, FileDetail } from '../../types';

interface Props {
  activeFile: FileDetail | null;
  stage: AppStage;
  setStage: (stage: AppStage) => void;
  setToolCalls: (calls: never[]) => void;
  setChartPaths: (paths: string[]) => void;
}

export default function ChatPanel({ activeFile }: Props) {
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
    </main>
  );
}
