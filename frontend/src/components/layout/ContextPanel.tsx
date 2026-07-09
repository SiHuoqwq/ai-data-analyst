import type { AppStage, FileDetail } from '../../types';

interface Props {
  activeFile: FileDetail | null;
  stage: AppStage;
  toolCalls: { name: string; args: Record<string, unknown>; status: string }[];
  chartPaths: string[];
}

export default function ContextPanel({ stage }: Props) {
  const stages = [
    { label: '上传', active: stage === 'empty' || stage === 'upload' || stage === 'ready' },
    { label: '分析', active: stage === 'analyzing' },
    { label: '结果', active: stage === 'complete' },
  ];

  return (
    <aside
      className="w-[22%] min-w-[240px] flex-shrink-0 flex flex-col gap-3 p-3 border-l overflow-y-auto"
      style={{ background: '#0c1324', borderColor: '#1e293b' }}
    >
      <h2 className="text-xs font-semibold uppercase tracking-wider" style={{ color: '#60a5fa' }}>
        上下文面板
      </h2>

      <div className="flex gap-1.5 text-[10px]">
        {stages.map((s) => (
          <span
            key={s.label}
            className="px-2 py-0.5 rounded-full font-medium"
            style={{
              background: s.active ? '#2563eb' : '#1a2744',
              color: s.active ? 'white' : '#64748b',
            }}
          >
            {s.label}
          </span>
        ))}
      </div>

      <p className="text-xs mt-8 text-center" style={{ color: '#64748b' }}>
        上传或选择一个数据文件
      </p>
    </aside>
  );
}
