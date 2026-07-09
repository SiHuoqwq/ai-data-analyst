import { useState } from 'react';
import { generateReport } from '../../api/report';

interface Props {
  chartPaths: string[];
  activeFileId: string | null;
}

export default function ResultsView({ chartPaths, activeFileId }: Props) {
  const [generating, setGenerating] = useState(false);

  const handleGenerateReport = async () => {
    if (!activeFileId || generating) return;
    setGenerating(true);
    try {
      const report = await generateReport(activeFileId);
      const blob = new Blob([report], { type: 'text/plain;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank');
    } catch (e) {
      console.error('Failed to generate report:', e);
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      {/* Chart thumbnails */}
      {chartPaths.length > 0 && (
        <div className="flex flex-col gap-1">
          <p
            className="text-[10px] font-medium uppercase tracking-wider px-1"
            style={{ color: '#64748b' }}
          >
            图表结果
          </p>
          <div className="grid grid-cols-2 gap-2">
            {chartPaths.map((path, i) => (
              <img
                key={i}
                src={path}
                alt={`Chart ${i + 1}`}
                className="w-full h-auto rounded cursor-pointer transition-opacity hover:opacity-80"
                style={{ border: '1px solid #1e293b' }}
                onClick={() => window.open(path, '_blank')}
              />
            ))}
          </div>
        </div>
      )}

      {/* Generate report button */}
      <button
        onClick={handleGenerateReport}
        disabled={!activeFileId || generating}
        className="w-full py-2 rounded-lg text-xs font-medium transition-opacity"
        style={{
          background: '#2563eb',
          color: 'white',
          opacity: !activeFileId || generating ? 0.5 : 1,
        }}
      >
        {generating ? '生成中...' : '生成分析报告'}
      </button>
    </div>
  );
}
