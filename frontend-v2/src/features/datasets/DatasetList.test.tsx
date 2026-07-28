import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { DatasetList } from './DatasetList'

const dataset = {
  id: 'file-1',
  filename: '一份非常长但仍然需要被完整读取的销售数据文件.csv',
  file_type: 'csv',
  row_count: 12,
  col_count: 9,
  uploaded_at: '2026-07-10T15:13:51.957724',
}

describe('DatasetList', () => {
  it('用明确列结构展示合并后的数据规模', () => {
    render(<MemoryRouter><DatasetList datasets={[dataset]} onDelete={() => {}} /></MemoryRouter>)

    const header = document.querySelector('.dataset-list-head')
    expect(header).not.toBeNull()
    expect(within(header as HTMLElement).getByText('数据集名称')).toBeInTheDocument()
    expect(within(header as HTMLElement).getByText('数据规模')).toBeInTheDocument()
    expect(within(header as HTMLElement).getByText('上传时间')).toBeInTheDocument()
    expect(within(header as HTMLElement).getByText('操作')).toBeInTheDocument()
    expect(screen.getByText('12 行 · 9 列')).toBeInTheDocument()
  })

  it('长文件名仍作为可访问链接完整呈现', () => {
    render(<MemoryRouter><DatasetList datasets={[dataset]} onDelete={() => {}} /></MemoryRouter>)

    expect(screen.getByRole('link', { name: dataset.filename })).toHaveAttribute('href', '/datasets/file-1')
  })
})
