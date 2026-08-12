import { Maximize2, RotateCcw, X } from 'lucide-react'
import { useState } from 'react'
import { apiUrl } from '../../api/client'
import { MarkdownContent } from '../../components/feedback/MarkdownContent'
import { Button } from '../../components/ui/Button'
import { formatCell } from '../../utils/format'
import type {
  AnalysisArtifact,
  ChartArtifactPayload,
  MetricArtifactPayload,
  TableArtifactPayload,
  TextArtifactPayload,
} from '../../types/v2'

const isObject = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value)

const invalidArtifact = <div className="artifact-fallback" role="status">暂不支持展示此分析结果。</div>

function textPayload(payload: Record<string, unknown>): TextArtifactPayload | null {
  return (payload.format === 'markdown' || payload.format === 'plain_text')
    && typeof payload.content === 'string'
    ? payload as unknown as TextArtifactPayload
    : null
}

function metricPayload(payload: Record<string, unknown>): MetricArtifactPayload | null {
  return typeof payload.label === 'string' && typeof payload.display_value === 'string'
    ? payload as unknown as MetricArtifactPayload
    : null
}

function tablePayload(payload: Record<string, unknown>): TableArtifactPayload | null {
  if (!Array.isArray(payload.columns) || !Array.isArray(payload.rows)) return null
  const columnsValid = payload.columns.every((column) =>
    isObject(column) && typeof column.key === 'string' && typeof column.label === 'string'
    && typeof column.data_type === 'string')
  return columnsValid && payload.rows.every(isObject)
    ? payload as unknown as TableArtifactPayload
    : null
}

function chartPayload(payload: Record<string, unknown>): ChartArtifactPayload | null {
  return payload.renderer === 'static-image' && typeof payload.image_url === 'string'
    && payload.image_url.startsWith('/') && typeof payload.title === 'string'
    && typeof payload.alt_text === 'string'
    ? payload as unknown as ChartArtifactPayload
    : null
}

export function TextArtifactView({ artifact }: { artifact: AnalysisArtifact }) {
  const payload = textPayload(artifact.payload)
  if (!payload) return invalidArtifact
  return <section className="artifact artifact-text" aria-label={artifact.title}>
    {payload.format === 'markdown'
      ? <MarkdownContent content={payload.content} />
      : <p className="plain-answer">{payload.content}</p>}
  </section>
}

export function MetricArtifactView({ artifact }: { artifact: AnalysisArtifact }) {
  const payload = metricPayload(artifact.payload)
  if (!payload) return invalidArtifact
  return <article className="artifact metric-result">
    <span>{payload.label}</span>
    <div>
      <strong>{payload.display_value || '—'}</strong>
      {payload.unit && <small>{payload.unit}</small>}
    </div>
  </article>
}

export function TableArtifactView({ artifact }: { artifact: AnalysisArtifact }) {
  const payload = tablePayload(artifact.payload)
  if (!payload) return invalidArtifact
  if (!payload.rows.length) {
    return <div className="artifact-empty">这项分析没有返回可展示的数据行</div>
  }
  const singleRow = payload.rows.length === 1 ? payload.rows[0] : null
  const identityColumns = singleRow
    ? payload.columns.filter((column) => column.data_type !== 'number')
    : []
  const metricColumns = singleRow
    ? payload.columns.filter((column) => column.data_type === 'number')
    : []
  const identity = identityColumns.length
    ? identityColumns.map((column) => formatCell(singleRow?.[column.key])).join(' / ')
    : '当前对象'
  return <section className="artifact artifact-table">
    <div className="artifact-heading"><h3>{artifact.title}</h3><span>{payload.rows.length} 行</span></div>
    {singleRow && <section className="single-object-summary" aria-labelledby={`single-object-${artifact.id}`}>
      <div className="single-object-heading">
        <div><span>当前对象</span><strong>{identity}</strong></div>
        <h4 id={`single-object-${artifact.id}`}>单对象概览</h4>
      </div>
      {metricColumns.length > 0 && <dl className="single-object-metrics">
        {metricColumns.map((column) => <div key={column.key}>
          <dt>{column.label}</dt>
          <dd>{formatCell(singleRow[column.key])}</dd>
        </div>)}
      </dl>}
      <p>当前结果仅包含 1 个对象，无法进行组间比较。</p>
    </section>}
    <div className="table-scroll">
      <table>
        <caption className="sr-only">{artifact.title}</caption>
        <thead><tr>{payload.columns.map((column) =>
          <th className={column.data_type === 'number' ? 'numeric-cell' : ''} key={column.key} scope="col">{column.label}</th>)}</tr></thead>
        <tbody>{payload.rows.map((row, rowIndex) =>
          <tr key={rowIndex}>{payload.columns.map((column) =>
            <td
              className={column.data_type === 'number' ? 'numeric-cell' : ''}
              key={`${rowIndex}-${column.key}`}
              title={formatCell(row[column.key])}
            >
              {formatCell(row[column.key])}
            </td>)}</tr>)}</tbody>
      </table>
    </div>
  </section>
}

export function ChartArtifactView({ artifact }: { artifact: AnalysisArtifact }) {
  const payload = chartPayload(artifact.payload)
  const [failed, setFailed] = useState(false)
  const [retry, setRetry] = useState(0)
  const [expanded, setExpanded] = useState(false)
  if (!payload) return invalidArtifact
  const source = apiUrl(payload.image_url)
  const retryImage = () => {
    setFailed(false)
    setRetry((value) => value + 1)
  }
  return <section className="artifact artifact-chart">
    <div className="artifact-heading"><h3>{payload.title || artifact.title}</h3><span>图表</span></div>
    {failed
      ? <div className="chart-error" role="status">
          <span>图表暂时无法加载</span>
          <Button variant="secondary" onClick={retryImage}><RotateCcw size={15} />重新加载图表</Button>
        </div>
      : <button className="chart-image-button" type="button" onClick={() => setExpanded(true)} aria-label={`放大查看${payload.title}`}>
          <img key={retry} src={source} alt={payload.alt_text} onError={() => setFailed(true)} />
          <span><Maximize2 size={15} />放大查看</span>
        </button>}
    {expanded && <div className="chart-lightbox" role="dialog" aria-modal="true" aria-label={payload.title}>
      <button className="icon-button" type="button" aria-label="关闭图表" onClick={() => setExpanded(false)}><X /></button>
      <img src={source} alt={payload.alt_text} />
    </div>}
  </section>
}

export function ArtifactView({ artifact }: { artifact: AnalysisArtifact }) {
  if (artifact.artifact_type === 'text') return <TextArtifactView artifact={artifact} />
  if (artifact.artifact_type === 'metric') return <MetricArtifactView artifact={artifact} />
  if (artifact.artifact_type === 'table') return <TableArtifactView artifact={artifact} />
  if (artifact.artifact_type === 'chart') return <ChartArtifactView artifact={artifact} />
  return invalidArtifact
}
