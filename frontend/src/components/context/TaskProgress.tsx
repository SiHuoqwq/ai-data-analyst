interface Props {
  toolCalls: {
    name: string;
    args: Record<string, unknown>;
    status: 'pending' | 'running' | 'done';
  }[];
}

const TOOL_LABELS: Record<string, string> = {
  describe_data: '统计描述',
  value_counts: '值分布统计',
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

const STATUS_ICON: Record<string, string> = {
  pending: '○',
  running: '◷',
  done: '✓',
};

const STATUS_COLOR: Record<string, string> = {
  pending: '#64748b',
  running: '#60a5fa',
  done: '#34d399',
};

export default function TaskProgress({ toolCalls }: Props) {
  if (toolCalls.length === 0) return null;

  return (
    <div className="flex flex-col gap-1">
      <p
        className="text-[10px] font-medium uppercase tracking-wider px-1"
        style={{ color: '#64748b' }}
      >
        分析任务
      </p>
      {toolCalls.map((call, i) => (
        <div
          key={`${call.name}-${i}`}
          className="flex items-center gap-2 p-2 rounded text-xs"
          style={{ background: '#1a2744' }}
        >
          <span className="flex-shrink-0 text-sm" style={{ color: STATUS_COLOR[call.status] }}>
            {STATUS_ICON[call.status]}
          </span>
          <span className="flex-1" style={{ color: '#e2e8f0' }}>
            {TOOL_LABELS[call.name] || call.name}
          </span>
        </div>
      ))}
    </div>
  );
}
