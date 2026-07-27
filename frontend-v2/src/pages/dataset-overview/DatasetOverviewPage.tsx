import { ArrowLeft, ArrowRight, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useDataset, useDatasetPreview, useDeleteDataset } from '../../features/datasets/queries'
import { useDatasetConversations } from '../../features/conversations/queries'
import { calculateDatasetMetrics } from '../../features/datasets/dataset-utils'
import { formatDate, formatNumber, formatPercent } from '../../utils/format'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/Button'
import { Card } from '../../components/ui/Card'
import { LoadingState } from '../../components/feedback/LoadingState'
import { ErrorState } from '../../components/feedback/ErrorState'
import { EmptyState } from '../../components/feedback/EmptyState'
import { ConfirmDialog } from '../../components/feedback/ConfirmDialog'
import { DataTable } from '../../components/data-table/DataTable'
import { MarkdownContent } from '../../components/feedback/MarkdownContent'

export function DatasetOverviewPage() {
  const { fileId = '' } = useParams()
  const navigate = useNavigate()
  const dataset = useDataset(fileId)
  const preview = useDatasetPreview(fileId)
  const conversations = useDatasetConversations(fileId)
  const remove = useDeleteDataset()
  const [confirming, setConfirming] = useState(false)
  if (dataset.isPending) return <div className="page"><LoadingState label="正在加载数据集" /></div>
  if (dataset.isError) return <div className="page"><ErrorState error={dataset.error} onRetry={() => void dataset.refetch()} /></div>
  const data = dataset.data
  const metrics = calculateDatasetMetrics(data.columns)
  const removeDataset = async () => {
    try { await remove.mutateAsync(fileId); navigate('/') } catch { /* mutation error shown */ }
  }
  const fieldRows = data.columns.map((column) => [
    column.name, column.dtype, formatNumber(column.null_count), formatPercent(column.null_rate),
    formatNumber(column.unique_count), column.sample_values.map(String).join('、') || '—',
  ])
  return <div className="page">
    <Link className="back-link" to="/"><ArrowLeft size={15} />返回工作区</Link>
    <PageHeader eyebrow={`${data.file_type.toUpperCase()} 数据集`} title={data.filename}
      description={`${formatNumber(data.row_count)} 行 · ${formatNumber(data.col_count)} 列`}
      actions={<><Button variant="secondary" onClick={() => setConfirming(true)}><Trash2 size={16} />删除</Button><Button onClick={() => navigate(`/datasets/${fileId}/analysis`)}>开始分析 <ArrowRight size={16} /></Button></>} />
    <div className="metrics-grid">
      {[['总行数', data.row_count], ['总列数', data.col_count], ['缺失值', metrics.missingValues], ['含缺失字段', metrics.fieldsWithMissing]].map(([label, value]) =>
        <Card className="metric-card" key={label}><span>{label}</span><strong>{formatNumber(Number(value))}</strong></Card>)}
    </div>
    <div className="overview-layout">
      <div className="overview-main">
        <Card><div className="card-heading"><div><span className="eyebrow">字段质量</span><h2>字段信息</h2></div><span>{data.columns.length} 个字段</span></div>
          {data.columns.length ? <DataTable caption="字段质量信息" columns={['字段名', '类型', '缺失数', '缺失率', '唯一值', '示例值']} rows={fieldRows} /> : <EmptyState title="没有字段信息" description="服务端没有返回可展示的字段。" />}</Card>
        <Card><details><summary><span><span className="eyebrow">数据画像</span><strong>查看 Markdown 质量报告</strong></span><span>展开</span></summary><MarkdownContent content={data.profile_report} /></details></Card>
        <Card><div className="card-heading"><div><span className="eyebrow">数据预览</span><h2>前 20 行</h2></div>{preview.data && <span>共 {formatNumber(preview.data.total_rows)} 行</span>}</div>
          {preview.isPending && <LoadingState label="正在读取数据预览" />}
          {preview.isError && <ErrorState error={preview.error} onRetry={() => void preview.refetch()} />}
          {preview.data && preview.data.rows.length === 0 && <EmptyState title="预览为空" description="数据集没有可展示的数据行。" />}
          {preview.data && preview.data.rows.length > 0 && <><DataTable caption="数据集前 20 行" columns={preview.data.columns} rows={preview.data.rows} /><p className="table-note">当前仅展示前 20 行，不代表服务端分页。</p></>}</Card>
      </div>
      <aside className="overview-aside"><Card><div className="card-heading"><div><span className="eyebrow">分析记录</span><h2>最近会话</h2></div></div>
        {conversations.isPending && <LoadingState label="正在读取会话" />}
        {conversations.isError && <ErrorState error={conversations.error} onRetry={() => void conversations.refetch()} />}
        {conversations.data?.length === 0 && <EmptyState title="还没有会话" description="新版分析工作台开放后，可从这里继续分析。" />}
        {conversations.data?.map((conversation) => <Link className="conversation-row" key={conversation.id} to={`/datasets/${fileId}/analysis?conversationId=${conversation.id}`}><strong>{conversation.title}</strong><span>{formatDate(conversation.created_at)} · {formatNumber(conversation.message_count)} 条消息</span></Link>)}
      </Card></aside>
    </div>
    {remove.isError && <div className="inline-error" role="alert">{remove.error.message}</div>}
    <ConfirmDialog open={confirming} title="删除数据集" filename={data.filename} busy={remove.isPending} onCancel={() => setConfirming(false)} onConfirm={() => void removeDataset()} />
  </div>
}
