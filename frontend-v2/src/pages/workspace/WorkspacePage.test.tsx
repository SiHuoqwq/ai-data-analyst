import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { WorkspacePage } from './WorkspacePage'

vi.mock('../../features/datasets/queries', () => ({
  useDatasets: () => ({ isPending: false, isError: false, data: [], refetch: vi.fn() }),
  useUploadDataset: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useDeleteDataset: () => ({ isPending: false, isError: false, mutateAsync: vi.fn() }),
}))

describe('WorkspacePage', () => {
  const renderPage = () => render(
    <MemoryRouter initialEntries={['/']}>
      <WorkspacePage />
    </MemoryRouter>,
  )

  it('以房地产销售经营分析为首页定位', () => {
    renderPage()
    expect(screen.getByRole('heading', { name: '房地产销售经营分析' })).toBeInTheDocument()
    expect(screen.getByText(/上传销售数据/)).toBeInTheDocument()
    expect(screen.getByText(/线索、渠道、项目、置业顾问/)).toBeInTheDocument()
  })

  it('能力行展示销售分析方向，不再出现教育课程文案', () => {
    renderPage()
    expect(screen.getByText(/渠道分析/)).toBeInTheDocument()
    expect(screen.getByText(/销售漏斗/)).toBeInTheDocument()
    expect(screen.queryByText(/课程|报名|学习|教育|完成率|退款/)).not.toBeInTheDocument()
  })
})
