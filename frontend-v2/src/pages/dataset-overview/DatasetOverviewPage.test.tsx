import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DatasetOverviewPage } from './DatasetOverviewPage'

const detail = {
  id: 'file-1',
  filename: '一份非常长但不应该破坏页面布局的销售分析数据文件.csv',
  file_type: 'csv',
  row_count: 12,
  col_count: 2,
  columns: [
    { name: '地区', dtype: 'object', null_count: 0, null_rate: 0, unique_count: 2, sample_values: ['华东', '华北'] },
    { name: '销售额', dtype: 'float64', null_count: 1, null_rate: 1 / 12, unique_count: 11, sample_values: [1280.5] },
  ],
  profile_report: '## 数据概况\n字段状态正常。',
}

vi.mock('../../features/datasets/queries', () => ({
  useDataset: () => ({ isPending: false, isError: false, data: detail }),
  useDatasetPreview: () => ({
    isPending: false,
    isError: false,
    data: { columns: ['地区', '销售额'], rows: Array.from({ length: 12 }, () => ['华东', 1280.5]), total_rows: 12 },
  }),
  useDeleteDataset: () => ({ isPending: false, isError: false, mutateAsync: vi.fn() }),
}))

vi.mock('../../features/conversations/queries', () => ({
  useDatasetConversations: () => ({ isPending: false, isError: false, data: [] }),
}))

describe('DatasetOverviewPage', () => {
  beforeEach(() => render(
    <MemoryRouter initialEntries={['/datasets/file-1']}>
      <Routes><Route path="/datasets/:fileId" element={<DatasetOverviewPage />} /></Routes>
    </MemoryRouter>,
  ))

  it('展示完整文件名、紧凑无会话状态和真实预览范围', () => {
    expect(screen.getByRole('heading', { name: detail.filename })).toBeInTheDocument()
    expect(screen.getByText('暂无分析记录')).toBeInTheDocument()
    expect(screen.getByText('当前文件共 12 行，已全部展示')).toBeInTheDocument()
  })

  it('质量报告和用户页面不暴露技术术语', () => {
    expect(screen.getByText('数据质量报告')).toBeInTheDocument()
    expect(screen.getByText('查看报告详情')).toBeInTheDocument()
    expect(screen.queryByText(/Markdown|V1|V2|AnalysisRun|Artifact|服务端分页/)).not.toBeInTheDocument()
  })
})
