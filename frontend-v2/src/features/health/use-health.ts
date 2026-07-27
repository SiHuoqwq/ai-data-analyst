import { useQuery } from '@tanstack/react-query'
import { getHealth } from '../../api/health'

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    retry: false,
    refetchInterval: (query) => (query.state.status === 'error' ? 15_000 : 30_000),
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
  })
}
