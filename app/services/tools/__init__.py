from app.services.tools.statistics import describe_data, value_counts, correlation_analysis
from app.services.tools.aggregation import group_analysis, filter_data, sort_data
from app.services.tools.analysis import trend_analysis, detect_outliers, data_summary
from app.services.tools.visualization import draw_bar_chart, draw_line_chart, draw_pie_chart, draw_scatter_chart, draw_heatmap_chart

ANALYSIS_TOOLS = [
    describe_data,
    value_counts,
    correlation_analysis,
    group_analysis,
    filter_data,
    sort_data,
    trend_analysis,
    detect_outliers,
    data_summary,
    draw_bar_chart,
    draw_line_chart,
    draw_pie_chart,
    draw_scatter_chart,
    draw_heatmap_chart,
]
