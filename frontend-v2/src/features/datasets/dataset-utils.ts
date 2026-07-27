import { AppError } from '../../api/errors'
import type { ColumnInfo } from '../../types/api'

export function calculateDatasetMetrics(columns: ColumnInfo[]) {
  return columns.reduce(
    (result, column) => ({
      missingValues: result.missingValues + column.null_count,
      fieldsWithMissing: result.fieldsWithMissing + (column.null_count > 0 ? 1 : 0),
    }),
    { missingValues: 0, fieldsWithMissing: 0 },
  )
}

export function validateUploadFile(file: File): AppError | null {
  const extension = file.name.split('.').pop()?.toLowerCase()
  if (extension !== 'csv' && extension !== 'xlsx') {
    return new AppError({ status: null, code: 'unsupported_file', message: '请选择 CSV 或 XLSX 文件' })
  }
  if (file.size === 0) {
    return new AppError({ status: null, code: 'empty_file', message: '不能上传空文件，请重新选择' })
  }
  return null
}
