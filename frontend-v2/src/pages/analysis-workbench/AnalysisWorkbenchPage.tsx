import { ArrowLeft, Blocks, Database, PanelRight, Send } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { useDataset } from '../../features/datasets/queries'
import { PageHeader } from '../../components/layout/PageHeader'
import { Card } from '../../components/ui/Card'

export function AnalysisWorkbenchPage() {
  const { fileId = '' } = useParams()
  const dataset = useDataset(fileId)
  return <div className="page">
    <Link className="back-link" to={`/datasets/${fileId}`}><ArrowLeft size={15} />返回数据集概览</Link>
    <PageHeader eyebrow="分析工作台 · 结构占位" title="结果画布将在下一阶段接入" description={dataset.data ? `已选择数据集：${dataset.data.filename}` : '正在确认数据集上下文'} />
    <div className="notice"><strong>当前不生成虚假分析。</strong><span>新版工作台正在等待 V2 AnalysisRun 和 Artifact 协议实现，现阶段不会伪造执行步骤、时间线或结构化结果。</span></div>
    <div className="workbench-skeleton">
      <Card className="canvas-boundary"><Blocks size={23} /><span className="eyebrow">未来区域</span><h2>分析结果画布</h2><p>关键指标、表格、图表、结论和证据将在这里成为视觉中心。</p></Card>
      <Card className="context-boundary"><Database size={20} /><h3>数据集上下文</h3><p>{dataset.data?.filename || '读取中'}</p><PanelRight size={18} /><h3>执行详情抽屉</h3><p>只在需要时打开，不长期占据屏幕。</p></Card>
      <div className="input-boundary"><span>自然语言分析输入区将在 V2 协议稳定后启用</span><button disabled aria-label="发送分析问题"><Send size={18} /></button></div>
    </div>
  </div>
}
