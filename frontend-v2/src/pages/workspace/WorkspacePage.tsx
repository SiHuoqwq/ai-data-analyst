import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { FileListItem } from '../../types/api'
import { useDatasets, useDeleteDataset, useUploadDataset } from '../../features/datasets/queries'
import { FileUploadZone } from '../../features/datasets/FileUploadZone'
import { DatasetList } from '../../features/datasets/DatasetList'
import { PageHeader } from '../../components/layout/PageHeader'
import { Card } from '../../components/ui/Card'
import { EmptyState } from '../../components/feedback/EmptyState'
import { ErrorState } from '../../components/feedback/ErrorState'
import { LoadingState } from '../../components/feedback/LoadingState'
import { ConfirmDialog } from '../../components/feedback/ConfirmDialog'

export function WorkspacePage() {
  const navigate = useNavigate()
  const datasets = useDatasets()
  const upload = useUploadDataset()
  const remove = useDeleteDataset()
  const [selected, setSelected] = useState<FileListItem | null>(null)
  const uploadFile = async (file: File) => {
    const created = await upload.mutateAsync(file)
    navigate(`/datasets/${created.id}`)
  }
  const confirmDelete = async () => {
    if (!selected) return
    try { await remove.mutateAsync(selected.id); setSelected(null) } catch { /* mutation state renders below */ }
  }
  return <div className="page">
    <PageHeader eyebrow="数据工作区" title="从数据开始，先看清，再分析" description="上传表格，检查字段与数据质量，然后进入 AI 分析入口。" />
    <Card className="upload-card"><FileUploadZone busy={upload.isPending} onUpload={uploadFile} /></Card>
    <section className="section-block">
      <div className="section-heading"><div><span className="eyebrow">最近数据集</span><h2>你的数据</h2></div>{datasets.data && <span>{datasets.data.length} 个数据集</span>}</div>
      {datasets.isPending && <LoadingState label="正在读取数据集" />}
      {datasets.isError && <ErrorState error={datasets.error} onRetry={() => void datasets.refetch()} />}
      {datasets.data?.length === 0 && <EmptyState title="还没有数据集" description="上传 CSV 或 XLSX 后，可以查看字段质量、缺失情况和前 20 行数据。" />}
      {datasets.data && datasets.data.length > 0 && <DatasetList datasets={datasets.data} onDelete={setSelected} />}
      {remove.isError && <div className="inline-error" role="alert">{remove.error.message}</div>}
    </section>
    <ConfirmDialog open={Boolean(selected)} title="删除数据集" filename={selected?.filename || ''} busy={remove.isPending} onCancel={() => setSelected(null)} onConfirm={() => void confirmDelete()} />
  </div>
}
