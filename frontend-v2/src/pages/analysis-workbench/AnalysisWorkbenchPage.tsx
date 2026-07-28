import { ArrowLeft, Sparkles } from 'lucide-react'
import { useParams } from 'react-router-dom'
import { useDataset } from '../../features/datasets/queries'
import { Button } from '../../components/ui/Button'

export function AnalysisWorkbenchPage() {
  const { fileId = '' } = useParams()
  const dataset = useDataset(fileId)
  return <div className="page upgrade-page">
    <div className="upgrade-mark"><Sparkles size={28} /></div>
    <span className="eyebrow">分析工作台</span>
    <h1>分析工作台正在升级</h1>
    <p>新版工作台将支持结构化结论、图表、表格和执行详情。目前可以返回数据集概览继续查看数据。</p>
    <div className="selected-dataset"><span>当前数据集</span><strong title={dataset.data?.filename}>{dataset.data?.filename || '正在读取数据集'}</strong></div>
    <Button onClick={() => window.history.back()}><ArrowLeft size={16} />返回数据集概览</Button>
  </div>
}
