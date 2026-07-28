import { DatabaseZap } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'
import { HealthIndicator } from '../feedback/HealthIndicator'

export function AppShell() {
  return <div className="app">
    <header className="topbar">
      <div className="topbar-inner">
        <NavLink className="brand" to="/"><span className="brand-mark"><DatabaseZap size={22} /></span><span className="brand-copy"><strong>析数</strong><small>AI 数据分析工作台</small></span></NavLink>
        <nav aria-label="主导航">
          <NavLink to="/" end>工作区</NavLink>
          <NavLink to="/history">历史记录</NavLink>
        </nav>
        <div className="topbar-context">
          <HealthIndicator />
        </div>
      </div>
    </header>
    <main><Outlet /></main>
  </div>
}
