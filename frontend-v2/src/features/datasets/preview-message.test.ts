import { describe, expect, it } from 'vitest'
import { getPreviewMessage } from './preview-message'

describe('getPreviewMessage', () => {
  it('总行数不超过二十时说明已全部展示', () => {
    expect(getPreviewMessage(12, 12)).toBe('当前文件共 12 行，已全部展示')
  })

  it('总行数超过二十时说明当前范围和总数', () => {
    expect(getPreviewMessage(20, 200)).toBe('当前展示前 20 行，共 200 行')
  })
})
