import { formatCell } from '../../utils/format'

export function DataTable({ columns, rows, caption }: { columns: string[]; rows: unknown[][]; caption: string }) {
  return <div className="table-scroll"><table><caption className="sr-only">{caption}</caption><thead><tr>{columns.map((column) => <th key={column} scope="col">{column}</th>)}</tr></thead><tbody>{rows.map((row, rowIndex) => <tr key={rowIndex}>{columns.map((column, columnIndex) => <td key={`${rowIndex}-${column}`} title={formatCell(row[columnIndex])}>{formatCell(row[columnIndex])}</td>)}</tr>)}</tbody></table></div>
}
