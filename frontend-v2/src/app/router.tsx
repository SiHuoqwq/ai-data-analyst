import { Route, Routes } from 'react-router-dom'
import { AppShell } from '../components/layout/AppShell'
import { WorkspacePage } from '../pages/workspace/WorkspacePage'
import { DatasetOverviewPage } from '../pages/dataset-overview/DatasetOverviewPage'
import { AnalysisWorkbenchPage } from '../pages/analysis-workbench/AnalysisWorkbenchPage'
import { HistoryPage } from '../pages/history/HistoryPage'
import { NotFoundPage } from '../pages/not-found/NotFoundPage'

export function AppRoutes() {
  return <Routes><Route element={<AppShell />}>
    <Route index element={<WorkspacePage />} />
    <Route path="datasets/:fileId" element={<DatasetOverviewPage />} />
    <Route path="datasets/:fileId/analysis" element={<AnalysisWorkbenchPage />} />
    <Route path="history" element={<HistoryPage />} />
    <Route path="*" element={<NotFoundPage />} />
  </Route></Routes>
}
