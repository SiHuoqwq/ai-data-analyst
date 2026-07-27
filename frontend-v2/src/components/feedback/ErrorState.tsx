import { CircleAlert } from 'lucide-react'
import { Button } from '../ui/Button'
import { asAppError } from '../../api/errors'

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const appError = asAppError(error)
  return <div className="state-panel error-state" role="alert"><CircleAlert size={22} /><strong>{appError.message}</strong><p>{appError.status ? `错误代码：${appError.status}` : '请确认后端服务已经启动。'}</p>{onRetry && <Button variant="secondary" onClick={onRetry}>重试</Button>}</div>
}
