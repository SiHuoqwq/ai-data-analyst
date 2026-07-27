import { LoaderCircle } from 'lucide-react'

export function LoadingState({ label = '正在加载' }: { label?: string }) {
  return <div className="state-panel" role="status"><LoaderCircle className="spin" size={20} />{label}</div>
}
