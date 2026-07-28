import { useRef, useState } from 'react'
import { FileUp, UploadCloud } from 'lucide-react'
import { Button } from '../../components/ui/Button'
import { validateUploadFile } from './dataset-utils'
import { asAppError, type AppError } from '../../api/errors'

export function FileUploadZone({ busy, onUpload }: { busy: boolean; onUpload: (file: File) => Promise<void> }) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState<AppError | null>(null)
  const select = async (file?: File) => {
    if (!file || busy) return
    const validation = validateUploadFile(file)
    if (validation) return setError(validation)
    setError(null)
    try { await onUpload(file) } catch (caught) { setError(asAppError(caught)) }
  }
  return <div className={`upload-zone ${dragging ? 'is-dragging' : ''}`}
    onDragEnter={(event) => { event.preventDefault(); setDragging(true) }}
    onDragOver={(event) => event.preventDefault()}
    onDragLeave={() => setDragging(false)}
    onDrop={(event) => { event.preventDefault(); setDragging(false); void select(event.dataTransfer.files[0]) }}>
    <input ref={inputRef} id="dataset-file" type="file" accept=".csv,.xlsx" hidden
      onChange={(event) => void select(event.target.files?.[0])} />
    <UploadCloud size={28} aria-hidden="true" />
    <div><strong>{busy ? '正在上传并检查数据' : '将 CSV 或 XLSX 文件拖到这里'}</strong><p>支持 CSV、XLSX，不支持旧版 XLS</p></div>
    <Button type="button" disabled={busy} onClick={() => inputRef.current?.click()}><FileUp size={16} />{busy ? '上传中' : '选择文件'}</Button>
    {error && <p className="inline-error" role="alert">{error.message}</p>}
  </div>
}
