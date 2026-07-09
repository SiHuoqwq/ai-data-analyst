import { useState, useRef, type DragEvent } from 'react';
import { Upload } from 'lucide-react';
import { uploadFile } from '../../api/files';
import type { FileDetail } from '../../types';

interface Props {
  onUploaded: (file: FileDetail) => void;
}

export default function FileUploadZone({ onUploaded }: Props) {
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = async (file: File) => {
    setUploading(true);
    try {
      const detail = await uploadFile(file);
      onUploaded(detail);
    } catch (e) {
      console.error('Upload failed:', e);
    } finally {
      setUploading(false);
    }
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  };

  const handleDragOver = (e: DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = () => setDragOver(false);

  const handleClick = () => {
    fileInputRef.current?.click();
  };

  return (
    <>
      <div
        className="border border-dashed rounded-lg p-4 text-center cursor-pointer transition-colors"
        style={{
          borderColor: dragOver ? '#60a5fa' : '#1e293b',
          background: dragOver ? '#1a2744' : 'transparent',
        }}
        onClick={handleClick}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
      >
        {uploading ? (
          <p className="text-xs" style={{ color: '#60a5fa' }}>上传中...</p>
        ) : (
          <>
            <Upload className="mx-auto" size={20} style={{ color: '#60a5fa' }} />
            <p className="text-xs mt-1" style={{ color: '#94a3b8' }}>上传 CSV / Excel</p>
          </>
        )}
      </div>
      <input
        ref={fileInputRef}
        type="file"
        accept=".csv,.xlsx,.xls"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
          e.target.value = '';
        }}
      />
    </>
  );
}
