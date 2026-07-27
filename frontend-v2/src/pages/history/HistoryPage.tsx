import { ArrowRight, History } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useDatasets } from '../../features/datasets/queries'
import { PageHeader } from '../../components/layout/PageHeader'
import { LoadingState } from '../../components/feedback/LoadingState'
import { ErrorState } from '../../components/feedback/ErrorState'
import { EmptyState } from '../../components/feedback/EmptyState'
import { formatNumber } from '../../utils/format'

export function HistoryPage() {
  const datasets = useDatasets()
  return <div className="page">
    <PageHeader eyebrow="历史记录" title="按数据集回到分析上下文" description="当前 V1 没有全局会话列表，因此这里不会伪造全局搜索或分页。" />
    {datasets.isPending && <LoadingState label="正在读取数据集" />}
    {datasets.isError && <ErrorState error={datasets.error} onRetry={() => void datasets.refetch()} />}
    {datasets.data?.length === 0 && <EmptyState title="暂无可浏览的历史" description="上传数据集并开始分析后，可从对应数据集查看已有会话。" />}
    <div className="history-grid">{datasets.data?.map((dataset) => <Link className="history-card" key={dataset.id} to={`/datasets/${dataset.id}`}>
      <History size={20} /><div><strong>{dataset.filename}</strong><span>{formatNumber(dataset.row_count)} 行 · {formatNumber(dataset.col_count)} 列</span></div><ArrowRight size={17} />
    </Link>)}</div>
  </div>
}
