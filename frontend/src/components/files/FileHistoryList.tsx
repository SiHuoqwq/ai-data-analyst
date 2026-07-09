import FileHistoryItem from './FileHistoryItem';
import type { FileListItem } from '../../types';

interface Props {
  files: FileListItem[];
  activeFileId: string | null;
  onSelect: (fileId: string) => void;
}

export default function FileHistoryList({ files, activeFileId, onSelect }: Props) {
  return (
    <div className="flex flex-col gap-1">
      <p
        className="text-[10px] font-medium uppercase tracking-wider px-1"
        style={{ color: '#64748b' }}
      >
        历史文件
      </p>
      {files.map((f) => (
        <FileHistoryItem
          key={f.id}
          file={f}
          isActive={f.id === activeFileId}
          onClick={() => onSelect(f.id)}
        />
      ))}
    </div>
  );
}
