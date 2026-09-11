const numberFormatter = new Intl.NumberFormat('zh-CN')
const percentFormatter = new Intl.NumberFormat('zh-CN', { style: 'percent', maximumFractionDigits: 2 })
const dateFormatter = new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })

export const formatNumber = (value: number) => numberFormatter.format(value)
export const formatPercent = (value: number) => percentFormatter.format(value)
export const formatDate = (value: string) => {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '时间未知' : dateFormatter.format(date)
}
export const formatCell = (value: unknown, unit?: string) => {
  if (value === '' || value === null || value === undefined) return '—'
  if (typeof value === 'number') return unit === 'percentage' ? formatPercent(value) : formatNumber(value)
  if (typeof value === 'boolean') return value ? '是' : '否'
  return String(value)
}
