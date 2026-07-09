import type { AppStage, FileDetail } from '../../types';

interface Props {
  activeFile: FileDetail | null;
  stage: AppStage;
}

const stageConfig: Record<AppStage, { text: string; color: string }> = {
  empty: { text: '等待上传', color: '#64748b' },
  upload: { text: '就绪', color: '#34d399' },
  ready: { text: '就绪', color: '#34d399' },
  analyzing: { text: '分析中', color: '#f59e0b' },
  complete: { text: '完成', color: '#34d399' },
};

export default function TopBar({ activeFile, stage }: Props) {
  const status = stageConfig[stage];

  return (
    <header
      className="flex items-center gap-4 px-4 py-2 border-b flex-shrink-0"
      style={{ background: '#0c1324', borderColor: '#1e293b' }}
    >
      <span className="font-bold text-sm flex items-center gap-2" style={{ color: '#60a5fa' }}>
        <span className="text-base">⬡</span> AI Data Analyst
      </span>
      <div className="flex-1" />
      {activeFile && (
        <span className="text-xs px-2 py-0.5 rounded" style={{ background: '#1a2744', color: '#94a3b8' }}>
          {activeFile.filename}
        </span>
      )}
      <span className="text-xs flex items-center gap-1.5">
        <span className="inline-block w-2 h-2 rounded-full" style={{ background: '#34d399' }} />
        <span style={{ color: '#94a3b8' }}>DeepSeek v4</span>
      </span>
      <span className="text-xs flex items-center gap-1.5" style={{ color: status.color }}>
        <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ background: status.color }} />
        {status.text}
      </span>
    </header>
  );
}
