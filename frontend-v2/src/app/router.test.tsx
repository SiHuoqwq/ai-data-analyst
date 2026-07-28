import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { AppRoutes } from './router'

function renderRoute(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('AppRoutes', () => {
  it('未知地址显示 404 页面', () => {
    renderRoute('/not-a-real-page')
    expect(screen.getByRole('heading', { name: '页面没有找到' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '返回工作区' })).toHaveAttribute('href', '/')
  })

  it('分析路由展示用户友好的升级说明且不暴露工程术语', () => {
    renderRoute('/datasets/file-1/analysis')
    expect(screen.getByRole('heading', { name: '分析工作台正在升级' })).toBeInTheDocument()
    expect(screen.getByText(/结构化结论、图表、表格和执行详情/)).toBeInTheDocument()
    expect(screen.queryByText(/V2|AnalysisRun|Artifact/)).not.toBeInTheDocument()
    expect(screen.queryByLabelText('发送分析问题')).not.toBeInTheDocument()
  })
})
