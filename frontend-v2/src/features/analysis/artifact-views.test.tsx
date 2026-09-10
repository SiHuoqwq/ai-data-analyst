import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ArtifactView } from './ArtifactView'
import type { AnalysisArtifact } from '../../types/v2'

const artifact = (
  artifactType: string,
  payload: Record<string, unknown>,
): AnalysisArtifact => ({
  id: `${artifactType}-1`,
  dataset_version_id: 'file-1',
  run_id: 'run-1',
  run_step_id: 'step-1',
  artifact_type: artifactType,
  status: 'ready',
  title: '分析结果',
  content_format: 'json',
  payload,
  size_bytes: 10,
  row_count: null,
  download_available: false,
  created_at: '2026-07-28T10:00:00Z',
})

describe('ArtifactView', () => {
  it('renders safe markdown text without raw HTML', () => {
    render(<ArtifactView artifact={artifact('text', {
      format: 'markdown',
      content: '## 结论\n<script>alert(1)</script>销售稳定。',
    })} />)

    expect(screen.getByRole('heading', { name: '结论' })).toBeInTheDocument()
    expect(document.querySelector('script')).not.toBeInTheDocument()
  })

  it('renders metric values without inventing trends', () => {
    render(<ArtifactView artifact={artifact('metric', {
      label: '有效记录',
      value: 12,
      display_value: '12',
      unit: '行',
    })} />)

    expect(screen.getByText('有效记录')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
    expect(screen.getByText('行')).toBeInTheDocument()
    expect(screen.queryByText(/同比|趋势/)).not.toBeInTheDocument()
  })

  it('renders a structured table and an empty state', () => {
    const { rerender } = render(<ArtifactView artifact={artifact('table', {
      columns: [
        { key: 'region', label: '地区', data_type: 'string' },
        { key: 'sales', label: '销售额', data_type: 'number' },
      ],
      rows: [{ region: '华东', sales: 1280 }],
    })} />)

    expect(screen.getByRole('columnheader', { name: '地区' })).toBeInTheDocument()
    expect(screen.getAllByText('1,280')).toHaveLength(2)

    rerender(<ArtifactView artifact={artifact('table', {
      columns: [{ key: 'region', label: '地区', data_type: 'string' }],
      rows: [],
    })} />)
    expect(screen.getByText('这项分析没有返回可展示的数据行')).toBeInTheDocument()
  })

  it('renders a compact summary without claiming a comparison for one row', () => {
    render(<ArtifactView artifact={artifact('table', {
      columns: [
        { key: 'channel', label: '获客渠道', data_type: 'string' },
        { key: 'lead_count', label: '线索数', data_type: 'number' },
        { key: 'deal_rate', label: '成交转化率', data_type: 'number' },
      ],
      rows: [{ channel: '短视频平台', lead_count: 150, deal_rate: 0.0533 }],
    })} />)

    expect(screen.getByRole('heading', { name: '单对象概览' })).toBeInTheDocument()
    expect(screen.getAllByText('短视频平台').length).toBeGreaterThan(0)
    expect(screen.getAllByText('线索数')).toHaveLength(2)
    expect(screen.getAllByText('150')).toHaveLength(2)
    expect(screen.getByText('当前结果仅包含 1 个对象，无法进行组间比较。')).toBeInTheDocument()
    expect(screen.getByRole('table', { name: '分析结果' })).toBeInTheDocument()
  })

  it('renders a chart with accessible enlargement and failure recovery', () => {
    render(<ArtifactView artifact={artifact('chart', {
      renderer: 'static-image',
      chart_type: 'bar',
      title: '地区销售额',
      image_url: '/api/v2/artifacts/chart-1/download',
      alt_text: '各地区销售额柱状图',
    })} />)

    const image = screen.getByRole('img', { name: '各地区销售额柱状图' })
    expect(image).toHaveAttribute('src', '/api/v2/artifacts/chart-1/download')
    fireEvent.error(image)
    expect(screen.getByText('图表暂时无法加载')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '重新加载图表' }))
    expect(screen.getByRole('img', { name: '各地区销售额柱状图' })).toBeInTheDocument()
  })

  it('falls back safely for an unknown artifact type', () => {
    render(<ArtifactView artifact={artifact('future-result', { value: 1 })} />)

    expect(screen.getByText('暂不支持展示此分析结果。')).toBeInTheDocument()
  })
})
