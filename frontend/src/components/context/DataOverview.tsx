import type { FileDetail } from '../../types';

interface Props {
  file: FileDetail;
}

export default function DataOverview({ file }: Props) {
  return (
    <div className="flex flex-col gap-3">
      {/* Summary grid: row count, col count, file type */}
      <div
        className="grid grid-cols-3 gap-2 p-3 rounded-lg text-xs"
        style={{ background: '#1a2744' }}
      >
        <div className="text-center">
          <p className="text-lg font-bold" style={{ color: '#e2e8f0' }}>
            {file.row_count.toLocaleString()}
          </p>
          <p style={{ color: '#94a3b8' }}>行数</p>
        </div>
        <div className="text-center">
          <p className="text-lg font-bold" style={{ color: '#e2e8f0' }}>
            {file.col_count}
          </p>
          <p style={{ color: '#94a3b8' }}>列数</p>
        </div>
        <div className="text-center">
          <p className="text-lg font-bold uppercase" style={{ color: '#e2e8f0' }}>
            {file.file_type}
          </p>
          <p style={{ color: '#94a3b8' }}>类型</p>
        </div>
      </div>

      {/* Field info card */}
      <div className="flex flex-col gap-1">
        <p
          className="text-[10px] font-medium uppercase tracking-wider px-1"
          style={{ color: '#64748b' }}
        >
          字段信息
        </p>
        {file.columns.map((col) => (
          <div
            key={col.name}
            className="flex items-center justify-between gap-2 p-2 rounded text-xs"
            style={{ background: '#1a2744', color: '#e2e8f0' }}
          >
            <div className="flex items-center gap-2 min-w-0">
              <span className="truncate font-medium">{col.name}</span>
              <span
                className="text-[10px] px-1 py-0.5 rounded flex-shrink-0"
                style={{ background: '#0c1324', color: '#60a5fa' }}
              >
                {col.dtype}
              </span>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <span style={{ color: '#94a3b8' }}>
                {col.unique_count}
                <span className="text-[10px]"> 唯一</span>
              </span>
              {col.null_count > 0 && (
                <span
                  className="text-[10px] px-1 py-0.5 rounded"
                  style={{
                    background:
                      col.null_rate > 0.1
                        ? 'rgba(245,158,11,0.15)'
                        : 'rgba(100,116,139,0.15)',
                    color: col.null_rate > 0.1 ? '#f59e0b' : '#64748b',
                  }}
                >
                  空 {col.null_count}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Profile report card */}
      {file.profile_report && (
        <div className="flex flex-col gap-1">
          <p
            className="text-[10px] font-medium uppercase tracking-wider px-1"
            style={{ color: '#64748b' }}
          >
            数据画像
          </p>
          <pre
            className="p-3 rounded text-xs overflow-x-auto whitespace-pre-wrap"
            style={{ background: '#1a2744', color: '#94a3b8' }}
          >
            {file.profile_report}
          </pre>
        </div>
      )}
    </div>
  );
}
