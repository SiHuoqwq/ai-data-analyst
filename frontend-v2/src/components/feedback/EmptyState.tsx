import { Database } from 'lucide-react'
import type { ReactNode } from 'react'

export function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <div className="state-panel empty-state"><Database size={24} /><strong>{title}</strong><p>{description}</p>{action}</div>
}
