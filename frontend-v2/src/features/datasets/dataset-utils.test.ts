import { describe, expect, it } from 'vitest'
import { calculateDatasetMetrics, validateUploadFile } from './dataset-utils'
import type { ColumnInfo } from '../../types/api'

describe('calculateDatasetMetrics', () => {
  it('从真实字段统计缺失值和缺失字段数', () => {
    const columns: ColumnInfo[] = [
      { name: '地区', dtype: 'object', null_count: 2, null_rate: 0.2, unique_count: 3, sample_values: ['华东'] },
      { name: '销售额', dtype: 'int64', null_count: 0, null_rate: 0, unique_count: 8, sample_values: [100] },
      { name: '渠道', dtype: 'object', null_count: 1, null_rate: 0.1, unique_count: 2, sample_values: ['线上'] },
    ]

    expect(calculateDatasetMetrics(columns)).toEqual({ missingValues: 3, fieldsWithMissing: 2 })
  })
})

describe('validateUploadFile', () => {
  it('拒绝 xls 和其他未支持格式', () => {
    expect(validateUploadFile(new File(['x'], 'legacy.xls'))?.message).toContain('CSV 或 XLSX')
  })

  it('拒绝零字节文件', () => {
    expect(validateUploadFile(new File([], 'empty.csv'))?.message).toContain('空文件')
  })

  it('接受非空 CSV 和 XLSX', () => {
    expect(validateUploadFile(new File(['a,b'], 'data.csv'))).toBeNull()
    expect(validateUploadFile(new File(['binary'], 'data.xlsx'))).toBeNull()
  })
})
