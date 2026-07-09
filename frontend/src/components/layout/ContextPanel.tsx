import type { AppStage, FileDetail } from '../../types';
import StageIndicator from '../context/StageIndicator';
import DataOverview from '../context/DataOverview';
import TaskProgress from '../context/TaskProgress';
import ResultsView from '../context/ResultsView';

interface Props {
  activeFile: FileDetail | null;
  stage: AppStage;
  toolCalls: { name: string; args: Record<string, unknown>; status: 'pending' | 'running' | 'done' }[];
  chartPaths: string[];
}

export default function ContextPanel({ activeFile, stage, toolCalls, chartPaths }: Props) {
  const hasFile = activeFile !== null;

  return (
    <aside
      className="w-[22%] min-w-[240px] flex-shrink-0 flex flex-col gap-3 p-3 border-l overflow-y-auto"
      style={{ background: '#0c1324', borderColor: '#1e293b' }}
    >
      <h2 className="text-xs font-semibold uppercase tracking-wider" style={{ color: '#60a5fa' }}>
        上下文面板
      </h2>

      <StageIndicator stage={stage} />

      {!hasFile ? (
        <p className="text-xs mt-8 text-center" style={{ color: '#64748b' }}>
          上传或选择一个数据文件
        </p>
      ) : (
        <>
          <DataOverview file={activeFile} />
          {(stage === 'analyzing' || stage === 'complete') && (
            <TaskProgress toolCalls={toolCalls} />
          )}
          {stage === 'complete' && (
            <ResultsView
              chartPaths={chartPaths}
              activeFileId={activeFile?.id ?? null}
            />
          )}
        </>
      )}
    </aside>
  );
}
