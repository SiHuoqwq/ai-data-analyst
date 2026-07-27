import { DatabaseZap } from 'lucide-react'
import { NavLink, Outlet, useParams } from 'react-router-dom'
import { HealthIndicator } from '../feedback/HealthIndicator'
import { useDataset } from '../../features/datasets/queries'

export function AppShell() {
  const { fileId } = useParams()
  const dataset = useDataset(fileId || '')
  return <div className="app">
    <header className="topbar">
      <div className="topbar-inner">
        <NavLink className="brand" to="/"><DatabaseZap size={21} /><span>析数</span><small>AI 数据工作台</small></NavLink>
        <nav aria-label="主导航">
          <NavLink to="/" end>工作区</NavLink>
          <NavLink to="/history">历史记录</NavLink>
        </nav>
        <div className="topbar-context">
          {fileId && dataset.data && <span className="dataset-context" title={dataset.data.filename}>{dataset.data.filename}</span>}
          <HealthIndicator />
        </div>
      </div>
    </header>
    <main><Outlet /></main>
    <footer>数据留在你的工作区 · 当前连接 V1 数据集能力</footer>
  </div>
}
