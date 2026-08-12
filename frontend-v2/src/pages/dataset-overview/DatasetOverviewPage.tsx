import { ArrowLeft, CircleDashed, Columns3, Rows3, ScanSearch, Trash2 } from 'lucide-react'
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
import { getPreviewMessage } from '../../features/datasets/preview-message'
import type { LucideIcon } from 'lucide-react'
import type { ConversationItem } from '../../types/api'

type MetricDefinition = [label: string, value: number, icon: LucideIcon, note: string]

function ConversationRow({ conversation, fileId }: { conversation: ConversationItem, fileId: string }) {
  const [expanded, setExpanded] = useState(false)
  const questions = expanded ? conversation.user_questions : conversation.user_questions.slice(0, 4)
  return <article className="conversation-row">
    <Link className="conversation-row-link" to={`/datasets/${fileId}/analysis?conversationId=${conversation.id}`}>
      <div className="conversation-row-heading">
        <strong>{conversation.title}</strong>
        <span>{formatDate(conversation.created_at)} · {formatNumber(conversation.message_count)} 条消息</span>
      </div>
      {questions.length > 0
        ? <ol className="conversation-questions">{questions.map((question, index) => <li key={`${index}-${question}`}>{question}</li>)}</ol>
        : <p className="conversation-empty">暂无可展示的问题</p>}
    </Link>
    {conversation.user_questions.length > 4 && <button
      className="conversation-toggle"
      type="button"
      aria-expanded={expanded}
      onClick={() => setExpanded((value) => !value)}
    >{expanded ? '收起问题' : `查看全部 ${conversation.user_questions.length} 个问题`}</button>}
  </article>
}

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
  return <div className="page dataset-page">
    <Link className="back-link" to="/"><ArrowLeft size={15} />返回工作区</Link>
    <PageHeader eyebrow={`${data.file_type.toUpperCase()} 数据集`} title={data.filename}
      description={`${formatNumber(data.row_count)} 行 · ${formatNumber(data.col_count)} 列`}
      actions={<><Button variant="secondary" onClick={() => setConfirming(true)}><Trash2 size={16} />删除</Button><Button onClick={() => navigate(`/datasets/${fileId}/analysis`)}>分析工作台</Button></>} />
    <div className="metrics-grid">
      {([
        ['总行数', data.row_count, Rows3, '文件中的记录数量'],
        ['总列数', data.col_count, Columns3, '可用于分析的字段'],
        ['缺失值', metrics.missingValues, CircleDashed, '所有字段缺失值合计'],
        ['含缺失字段', metrics.fieldsWithMissing, ScanSearch, '需要关注的字段'],
      ] satisfies MetricDefinition[]).map(([label, value, Icon, note]) =>
        <Card className="metric-card" key={label}><div className="metric-label"><Icon size={17} /><span>{label}</span></div><strong>{formatNumber(value)}</strong><small>{note}</small></Card>)}
    </div>
    <div className="overview-flow">
      <Card><div className="card-heading"><div><span className="eyebrow">字段质量</span><h2>字段信息</h2></div><span>{data.columns.length} 个字段</span></div>
        {data.columns.length ? <DataTable caption="字段质量信息" columns={['字段名', '类型', '缺失数', '缺失率', '唯一值', '示例值']} rows={fieldRows} numericColumns={[2, 3, 4]} emphasizeFirstColumn /> : <EmptyState title="没有字段信息" description="当前没有可展示的字段信息。" />}</Card>
      <Card className="compact-section"><div className="card-heading"><div><span className="eyebrow">分析记录</span><h2>最近会话</h2></div></div>
        {conversations.isPending && <LoadingState label="正在读取会话" />}
        {conversations.isError && <ErrorState error={conversations.error} onRetry={() => void conversations.refetch()} />}
        {conversations.data?.length === 0 && <EmptyState title="暂无分析记录" description="分析工作台开放后，可以在这里继续之前的分析。" compact />}
        {conversations.data?.map((conversation) => <ConversationRow conversation={conversation} fileId={fileId} key={conversation.id} />)}
      </Card>
      <Card><details><summary><span><span className="eyebrow">数据质量报告</span><strong>查看报告详情</strong></span><span>展开</span></summary><MarkdownContent content={data.profile_report} /></details></Card>
      <Card><div className="card-heading"><div><span className="eyebrow">数据预览</span><h2>前 20 行</h2></div></div>
        {preview.isPending && <LoadingState label="正在读取数据预览" />}
        {preview.isError && <ErrorState error={preview.error} onRetry={() => void preview.refetch()} />}
        {preview.data && preview.data.rows.length === 0 && <EmptyState title="预览为空" description="数据集没有可展示的数据行。" />}
        {preview.data && preview.data.rows.length > 0 && <><DataTable caption="数据集前 20 行" columns={preview.data.columns} rows={preview.data.rows} /><p className="table-note">{getPreviewMessage(preview.data.rows.length, preview.data.total_rows)}</p></>}
      </Card>
    </div>
    {remove.isError && <div className="inline-error" role="alert">{remove.error.message}</div>}
    <ConfirmDialog open={confirming} title="删除数据集" filename={data.filename} busy={remove.isPending} onCancel={() => setConfirming(false)} onConfirm={() => void removeDataset()} />
  </div>
}
