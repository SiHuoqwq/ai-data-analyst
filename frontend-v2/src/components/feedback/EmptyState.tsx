import { Database } from 'lucide-react'
import type { ReactNode } from 'react'

export function EmptyState({ title, description, action, compact = false }: { title: string; description: string; action?: ReactNode; compact?: boolean }) {
  return <div className={`state-panel empty-state ${compact ? 'state-panel-compact' : ''}`}><Database size={compact ? 20 : 24} /><div><strong>{title}</strong><p>{description}</p></div>{action}</div>
}
