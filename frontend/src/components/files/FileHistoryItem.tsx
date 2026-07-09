import { FileText } from 'lucide-react';
import type { FileListItem } from '../../types';

interface Props {
  file: FileListItem;
  isActive: boolean;
  onClick: () => void;
}

export default function FileHistoryItem({ file, isActive, onClick }: Props) {
  return (
    <div
      onClick={onClick}
      className="flex items-start gap-2 p-2 rounded-lg cursor-pointer transition-colors text-xs"
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
      <div className="min-w-0">
        <p className="truncate">{file.filename}</p>
        <p className="text-[10px]" style={{ color: '#64748b' }}>
          {file.col_count}列 · {file.row_count}行
        </p>
      </div>
    </div>
  );
}
