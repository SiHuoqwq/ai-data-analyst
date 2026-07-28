import { formatNumber } from '../../utils/format'

export function getPreviewMessage(visibleRows: number, totalRows: number) {
  if (totalRows <= visibleRows) {
    return `当前文件共 ${formatNumber(totalRows)} 行，已全部展示`
  }
  return `当前展示前 ${formatNumber(visibleRows)} 行，共 ${formatNumber(totalRows)} 行`
}
