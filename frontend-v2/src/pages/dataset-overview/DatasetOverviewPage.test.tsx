import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DatasetOverviewPage } from './DatasetOverviewPage'

const conversationState = vi.hoisted(() => ({
  data: [] as Array<Record<string, unknown>>,
}))

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
  useDatasetConversations: () => ({ isPending: false, isError: false, data: conversationState.data }),
}))

describe('DatasetOverviewPage', () => {
  beforeEach(() => {
    conversationState.data = []
  })

  const renderPage = () => render(
    <MemoryRouter initialEntries={['/datasets/file-1']}>
      <Routes>
        <Route path="/datasets/:fileId" element={<DatasetOverviewPage />} />
        <Route path="/datasets/:fileId/analysis" element={<div>分析工作台</div>} />
      </Routes>
    </MemoryRouter>,
  )

  it('展示完整文件名、紧凑无会话状态和真实预览范围', () => {
    renderPage()
    expect(screen.getByRole('heading', { name: detail.filename })).toBeInTheDocument()
    expect(screen.getByText('暂无分析记录')).toBeInTheDocument()
    expect(screen.getByText('当前文件共 12 行，已全部展示')).toBeInTheDocument()
  })

  it('质量报告和用户页面不暴露技术术语', () => {
    renderPage()
    expect(screen.getByText('数据质量报告')).toBeInTheDocument()
    expect(screen.getByText('查看报告详情')).toBeInTheDocument()
    expect(screen.queryByText(/Markdown|V1|V2|AnalysisRun|Artifact|服务端分页/)).not.toBeInTheDocument()
  })

  it('默认展示前四个问题并支持原地展开和收起', () => {
    conversationState.data = [{
      id: 'conversation-1', file_id: 'file-1', title: '多轮课程分析', mode: 'agent',
      created_at: '2026-08-13T09:00:00Z', message_count: 12,
      user_questions: ['问题一', '问题二', '问题三', '问题四', '问题五', '问题六'],
    }]
    renderPage()

    expect(screen.getByText('问题一')).toBeInTheDocument()
    expect(screen.getByText('问题四')).toBeInTheDocument()
    expect(screen.queryByText('问题五')).not.toBeInTheDocument()
    const conversationLink = screen.getByRole('link', { name: /多轮课程分析/ })
    expect(conversationLink).toHaveAttribute(
      'href',
      '/datasets/file-1/analysis?conversationId=conversation-1',
    )

    fireEvent.click(screen.getByRole('button', { name: '查看全部 6 个问题' }))
    expect(screen.getByText('问题五')).toBeInTheDocument()
    expect(screen.getByText('问题六')).toBeInTheDocument()
    expect(screen.getByText(detail.filename)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '收起问题' }))
    expect(screen.queryByText('问题五')).not.toBeInTheDocument()
  })

  it('没有用户问题时保留会话标题并显示安全兜底', () => {
    conversationState.data = [{
      id: 'conversation-empty', file_id: 'file-1', title: '尚未提问的会话', mode: 'agent',
      created_at: '2026-08-13T10:00:00Z', message_count: 0, user_questions: [],
    }]
    renderPage()

    expect(screen.getByText('尚未提问的会话')).toBeInTheDocument()
    expect(screen.getByText('暂无可展示的问题')).toBeInTheDocument()
  })
})
