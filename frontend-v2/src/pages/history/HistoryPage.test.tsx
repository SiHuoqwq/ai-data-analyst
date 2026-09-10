import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { HistoryPage } from './HistoryPage'

vi.mock('../../features/datasets/queries', () => ({
  useDatasets: () => ({ isPending: false, isError: false, data: [], refetch: vi.fn() }),
}))

describe('HistoryPage', () => {
  it('以通用数据分析语义呈现历史记录', () => {
    render(<MemoryRouter><HistoryPage /></MemoryRouter>)
    expect(screen.getByRole('heading', { name: '回到之前的数据分析' })).toBeInTheDocument()
    expect(screen.getByText('暂无可浏览的历史')).toBeInTheDocument()
  })

  it('不出现教育业务文案', () => {
    render(<MemoryRouter><HistoryPage /></MemoryRouter>)
    expect(screen.queryByText(/课程|报名|学习|教育|完成率|退款/)).not.toBeInTheDocument()
  })
})
