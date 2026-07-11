import { FileText } from 'lucide-react';
import type { FileListItem } from '../../types';

interface Props {
  file: FileListItem;
  isActive: boolean;
  onClick: () => void;
  onDelete: () => void;
}

export default function FileHistoryItem({ file, isActive, onClick, onDelete }: Props) {
  return (
    <div
      onClick={onClick}
      className="flex items-start gap-2 p-2 rounded-lg cursor-pointer transition-colors text-xs group"
      style={{
        background: isActive ? '#1a2744' : 'transparent',
        borderLeft: isActive ? '2px solid #2563eb' : '2px solid transparent',
        color: isActive ? '#e2e8f0' : '#94a3b8',
      }}
    >
      <FileText
        size={14}
        className="flex-shrink-0 mt-0.5"
        style={{ color: isActive ? '#60a5fa' : '#64748b' }}
      />
      <div className="min-w-0 flex-1">
        <p className="truncate">{file.filename}</p>
        <p className="text-[10px]" style={{ color: '#64748b' }}>
          {file.col_count}列 · {file.row_count}行
        </p>
      </div>
      <button
        onClick={(e) => { e.stopPropagation(); onDelete(); }}
        className="flex-shrink-0 opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-red-500/10 transition-all"
        style={{ color: '#ef4444' }}
        title="删除文件"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 6h18M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2M10 11v6M14 11v6" />
        </svg>
      </button>
    </div>
  );
}
