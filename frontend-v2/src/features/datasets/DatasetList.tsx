import { ArrowRight, FileSpreadsheet, Trash2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { FileListItem } from '../../types/api'
import { formatDate, formatNumber } from '../../utils/format'

export function DatasetList({ datasets, onDelete }: { datasets: FileListItem[]; onDelete: (dataset: FileListItem) => void }) {
  return <div className="dataset-list">{datasets.map((dataset) => <article className="dataset-row" key={dataset.id}>
    <div className="file-symbol"><FileSpreadsheet size={20} /></div>
    <div className="dataset-name"><strong title={dataset.filename}>{dataset.filename}</strong><span>{dataset.file_type.toUpperCase()} · {formatDate(dataset.uploaded_at)}</span></div>
    <div className="dataset-stat"><strong>{formatNumber(dataset.row_count)}</strong><span>行</span></div>
    <div className="dataset-stat"><strong>{formatNumber(dataset.col_count)}</strong><span>列</span></div>
    <button className="icon-button" aria-label={`删除 ${dataset.filename}`} onClick={() => onDelete(dataset)}><Trash2 size={17} /></button>
    <Link className="text-link" to={`/datasets/${dataset.id}`}>查看数据集 <ArrowRight size={15} /></Link>
  </article>)}</div>
}
