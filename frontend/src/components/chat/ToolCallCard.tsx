const chineseNameMap: Record<string, string> = {
  describe_data: '统计描述',
  value_counts: '值分布',
  correlation_analysis: '相关性分析',
  group_analysis: '分组聚合',
  filter_data: '数据筛选',
  sort_data: '数据排序',
  trend_analysis: '趋势分析',
  detect_outliers: '异常值检测',
  data_summary: '数据摘要',
  draw_bar_chart: '生成柱状图',
  draw_line_chart: '生成折线图',
  draw_pie_chart: '生成饼图',
  draw_scatter_chart: '生成散点图',
  draw_heatmap_chart: '生成热力图',
};

interface Props {
  name: string;
  args: Record<string, unknown>;
  status: 'running' | 'done';
}

function filteredArgs(args: Record<string, unknown>): [string, unknown][] {
  return Object.entries(args).filter(
    ([, v]) => v !== null && v !== undefined && v !== ''
  );
}

export default function ToolCallCard({ name, args, status }: Props) {
  const chineseName = chineseNameMap[name] || name;
  const borderColor = status === 'running' ? '#f59e0b' : '#34d399';
  const textColor = status === 'running' ? '#f59e0b' : '#34d399';
  const entries = filteredArgs(args);

  return (
    <div
      className="rounded-lg px-3 py-2 text-xs mb-1.5"
      style={{
        background: '#1a2744',
        borderLeft: `3px solid ${borderColor}`,
      }}
    >
      <div className="flex items-center gap-1.5 mb-1">
        <span style={{ color: textColor }}>
          {status === 'running' ? '◷' : '✓'}
        </span>
        <span className="font-medium" style={{ color: '#e2e8f0' }}>
          {chineseName}
        </span>
      </div>
      {entries.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {entries.map(([key, value]) => (
            <span
              key={key}
              className="px-1.5 py-0.5 rounded text-[10px]"
              style={{ background: '#0c1324', color: '#94a3b8' }}
            >
              {key}={JSON.stringify(value)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
