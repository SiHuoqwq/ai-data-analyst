import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { HealthIndicator } from './HealthIndicator'

let healthState: Record<string, unknown>

vi.mock('../../features/health/use-health', () => ({
  useHealth: () => healthState,
}))

describe('HealthIndicator', () => {
  beforeEach(() => {
    healthState = {
      isPending: false,
      isError: false,
      data: {
        status: 'ok',
        provider: {
          mode: 'fake',
          display_name: '后端返回的 Provider 名称',
          description: '后端返回的模式说明',
        },
      },
    }
  })

  it('renders provider identity and description from the health response', () => {
    render(<HealthIndicator />)

    expect(screen.getByText('后端正常')).toBeInTheDocument()
    expect(screen.getByText('后端返回的 Provider 名称')).toBeInTheDocument()
    expect(screen.getByText('后端返回的模式说明')).toBeInTheDocument()
  })

  it('does not invent a provider label while the backend is unavailable', () => {
    healthState = { isPending: false, isError: true, data: undefined }
    render(<HealthIndicator />)

    expect(screen.getByText('后端离线')).toBeInTheDocument()
    expect(screen.queryByText(/Fake|DeepSeek|Provider 名称/)).not.toBeInTheDocument()
  })
})
