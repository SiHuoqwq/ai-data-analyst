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

  it('分析路由进入真实工作台的数据恢复流程', () => {
    renderRoute('/datasets/file-1/analysis')
    expect(screen.getByText('正在加载数据集')).toBeInTheDocument()
    expect(screen.queryByText('分析工作台正在升级')).not.toBeInTheDocument()
    expect(screen.queryByText(/V2|AnalysisRun|Artifact/)).not.toBeInTheDocument()
  })
})
