import { useEffect, useRef } from 'react'
import { Button } from '../ui/Button'

interface Props {
  open: boolean
  title: string
  filename: string
  busy: boolean
  onCancel: () => void
  onConfirm: () => void
}

export function ConfirmDialog({ open, title, filename, busy, onCancel, onConfirm }: Props) {
  const confirmRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!open) return
    confirmRef.current?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) onCancel()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, busy, onCancel])
  if (!open) return null
  return <div className="dialog-backdrop" role="presentation">
    <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title">
      <h2 id="dialog-title">{title}</h2>
      <p>即将删除数据集 <strong>{filename}</strong>。</p>
      <p className="danger-note">此操作还会删除关联会话和分析结果，且无法撤销。</p>
      <div className="dialog-actions">
        <Button variant="secondary" disabled={busy} onClick={onCancel}>取消</Button>
        <Button ref={confirmRef} variant="danger" disabled={busy} onClick={onConfirm}>{busy ? '正在删除' : '确认删除'}</Button>
      </div>
    </div>
  </div>
}
