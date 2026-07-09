import type { AppStage } from '../../types';

interface Props {
  stage: AppStage;
}

export default function StageIndicator({ stage }: Props) {
  const stages = [
    { label: '上传', active: stage === 'empty' || stage === 'upload' || stage === 'ready' },
    { label: '分析', active: stage === 'analyzing' },
    { label: '结果', active: stage === 'complete' },
  ];

  return (
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
  );
}
