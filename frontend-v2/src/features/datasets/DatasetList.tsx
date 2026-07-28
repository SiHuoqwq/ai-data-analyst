import { ArrowRight, FileSpreadsheet, Trash2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { FileListItem } from '../../types/api'
import { formatDate, formatNumber } from '../../utils/format'

export function DatasetList({ datasets, onDelete }: { datasets: FileListItem[]; onDelete: (dataset: FileListItem) => void }) {
  return <div className="dataset-list">
    <div className="dataset-list-head" aria-hidden="true"><span>数据集名称</span><span>数据规模</span><span>上传时间</span><span>操作</span></div>
    {datasets.map((dataset) => <article className="dataset-row" key={dataset.id}>
      <div className="dataset-identity">
        <div className="file-symbol"><FileSpreadsheet size={20} /></div>
        <div className="dataset-name">
          <Link to={`/datasets/${dataset.id}`} title={dataset.filename}>{dataset.filename}</Link>
          <span>{dataset.file_type.toUpperCase()}</span>
        </div>
      </div>
      <div className="dataset-scale"><strong>{formatNumber(dataset.row_count)} 行 · {formatNumber(dataset.col_count)} 列</strong><span>数据规模</span></div>
      <time dateTime={dataset.uploaded_at}>{formatDate(dataset.uploaded_at)}</time>
      <div className="dataset-actions">
        <button className="icon-button" aria-label={`删除 ${dataset.filename}`} onClick={() => onDelete(dataset)}><Trash2 size={17} /></button>
        <Link className="text-link" to={`/datasets/${dataset.id}`}>查看 <ArrowRight size={15} /></Link>
      </div>
    </article>)}
  </div>
}
