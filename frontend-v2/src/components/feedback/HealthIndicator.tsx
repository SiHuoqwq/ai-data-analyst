import { useHealth } from '../../features/health/use-health'

export function HealthIndicator() {
  const health = useHealth()
  const state = health.isPending ? 'checking' : health.isError ? 'offline' : 'online'
  const label = state === 'checking' ? '后端检查中' : state === 'offline' ? '后端离线' : '后端正常'
  return <span className={`health health-${state}`} role="status"><span className="health-dot" />{label}</span>
}
