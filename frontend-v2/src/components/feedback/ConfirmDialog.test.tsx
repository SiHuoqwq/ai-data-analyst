import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ConfirmDialog } from './ConfirmDialog'

describe('ConfirmDialog', () => {
  it('显示真实文件名和关联数据删除提示', () => {
    render(<ConfirmDialog open title="删除数据集" filename="sales.csv" busy={false} onCancel={() => {}} onConfirm={() => {}} />)
    expect(screen.getByText('sales.csv')).toBeInTheDocument()
    expect(screen.getByText(/关联会话和分析结果/)).toBeInTheDocument()
  })

  it('删除期间禁用取消和重复确认', () => {
    render(<ConfirmDialog open title="删除数据集" filename="sales.csv" busy onCancel={() => {}} onConfirm={() => {}} />)
    expect(screen.getByRole('button', { name: '取消' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '正在删除' })).toBeDisabled()
  })

  it('支持 Escape 关闭', async () => {
    const onCancel = vi.fn()
    render(<ConfirmDialog open title="删除数据集" filename="sales.csv" busy={false} onCancel={onCancel} onConfirm={() => {}} />)
    await userEvent.keyboard('{Escape}')
    expect(onCancel).toHaveBeenCalledOnce()
  })
})
