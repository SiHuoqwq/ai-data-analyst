import { ArrowLeft, Compass } from 'lucide-react'
import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return <div className="page not-found"><Compass size={34} /><span className="eyebrow">404</span><h1>页面没有找到</h1><p>这个地址不存在，或页面已经移动。</p><Link className="button button-primary" to="/"><ArrowLeft size={16} />返回工作区</Link></div>
}
