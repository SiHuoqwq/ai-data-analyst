# AI Data Analyst Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the AI Data Analyst product frontend — a three-column dark-themed workstation with file management, SSE streaming chat, and a dynamic context panel.

**Architecture:** React 18 + TypeScript SPA built with Vite, styled with Tailwind CSS + shadcn/ui. Communicates with the existing FastAPI backend via axios for REST calls and fetch ReadableStream for SSE streaming. The right panel (ContextPanel) is a stage-driven component that transitions through upload → analyzing → complete phases.

**Tech Stack:** React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui, axios, react-markdown + rehype-highlight, lucide-react icons

---

### Task 0: Backend — Add Chart Static File Mount

**Files:**
- Modify: `D:\claude\ai-data-analyst\app\main.py`

The frontend needs to load chart images. Add a static file mount.

- [ ] **Step 1: Read current main.py**

Current main.py at this point:
```python
from fastapi import FastAPI
from app.db.database import init_db
from app.api.files import router as files_router

app = FastAPI(title="AI Data Analyst", version="0.1.0")

app.include_router(files_router)

from app.api.chat import router as chat_router
app.include_router(chat_router)

from app.api.report import router as report_router
app.include_router(report_router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 2: Add static file mount**

Add `from fastapi.staticfiles import StaticFiles` at top, then add mount after router registrations:

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.db.database import init_db
from app.api.files import router as files_router

app = FastAPI(title="AI Data Analyst", version="0.1.0")

app.include_router(files_router)

from app.api.chat import router as chat_router
app.include_router(chat_router)

from app.api.report import router as report_router
app.include_router(report_router)

app.mount("/storage/charts", StaticFiles(directory="storage/charts"), name="charts")


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 3: Verify**

```bash
cd D:\claude\ai-data-analyst && py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# Quick check: start server, ensure /health still works
curl http://127.0.0.1:8000/health
```

Expected: `{"status":"ok"}`

- [ ] **Step 4: Commit**

```bash
cd D:\claude\ai-data-analyst && git add app/main.py && git commit -m "feat: add static file mount for chart images"
```

---

### Task 1: Project Scaffold — Vite + React + TypeScript + Tailwind

**Files:**
- Create: `D:\claude\ai-data-analyst\frontend\` (entire Vite project)

- [ ] **Step 1: Create Vite project**

```bash
cd D:\claude\ai-data-analyst
npm create vite@latest frontend -- --template react-ts
```

- [ ] **Step 2: Install dependencies**

```bash
cd D:\claude\ai-data-analyst\frontend
npm install
npm install axios react-markdown rehype-highlight remark-gfm lucide-react
npm install -D tailwindcss @tailwindcss/vite
```

- [ ] **Step 3: Configure Tailwind**

Edit `vite.config.ts`:
```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/storage': 'http://127.0.0.1:8000',
    },
  },
})
```

- [ ] **Step 4: Write index.css**

Write to `D:\claude\ai-data-analyst\frontend\src\index.css`:
```css
@import "tailwindcss";

:root {
  --bg-primary: #0f172a;
  --bg-secondary: #0c1324;
  --bg-card: #1a2744;
  --border-color: #1e293b;
  --accent: #2563eb;
  --accent-light: #60a5fa;
  --success: #34d399;
  --warning: #f59e0b;
  --text-primary: #e2e8f0;
  --text-secondary: #94a3b8;
  --text-muted: #64748b;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  background: var(--bg-primary);
  color: var(--text-primary);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

::-webkit-scrollbar {
  width: 6px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: #334155;
  border-radius: 3px;
}
```

- [ ] **Step 5: Update index.html title**

Edit `frontend/index.html` — change `<title>` to "AI Data Analyst"

- [ ] **Step 6: Verify dev server starts**

```bash
cd D:\claude\ai-data-analyst\frontend && npm run dev
```

Expected: Vite dev server starts on http://localhost:5173

- [ ] **Step 7: Commit**

```bash
cd D:\claude\ai-data-analyst && git add frontend/ && git commit -m "feat: scaffold Vite + React + TypeScript + Tailwind frontend"
```

---

### Task 2: TypeScript Types + API Client

**Files:**
- Create: `D:\claude\ai-data-analyst\frontend\src\types\index.ts`
- Create: `D:\claude\ai-data-analyst\frontend\src\api\client.ts`
- Create: `D:\claude\ai-data-analyst\frontend\src\api\files.ts`
- Create: `D:\claude\ai-data-analyst\frontend\src\api\chat.ts`
- Create: `D:\claude\ai-data-analyst\frontend\src\api\report.ts`

- [ ] **Step 1: Write types/index.ts**

```typescript
export interface ColumnInfo {
  name: string;
  dtype: string;
  null_count: number;
  null_rate: number;
  unique_count: number;
  sample_values: string[];
}

export interface FileDetail {
  id: string;
  filename: string;
  file_type: string;
  row_count: number;
  col_count: number;
  columns: ColumnInfo[];
  profile_report: string;
}

export interface FileListItem {
  id: string;
  filename: string;
  file_type: string;
  row_count: number;
  col_count: number;
  uploaded_at: string;
}

export interface FilePreview {
  columns: string[];
  rows: (string | number)[][];
  total_rows: number;
}

export interface ChatRequest {
  file_id: string;
  message: string;
  conversation_id?: string | null;
}

export interface ToolCallInfo {
  name: string;
  args: Record<string, unknown>;
}

export interface SSEToolEvent {
  type: 'tool';
  content: string; // JSON string of ToolCallInfo[]
}

export interface SSETextEvent {
  type: 'text';
  content: string;
}

export interface SSEDoneEvent {
  type: 'done';
  conversation_id: string;
}

export type SSEEvent = SSEToolEvent | SSETextEvent | SSEDoneEvent;

export type AppStage = 'empty' | 'upload' | 'ready' | 'analyzing' | 'complete';
```

- [ ] **Step 2: Write api/client.ts**

```typescript
import axios from 'axios';

export const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
});
```

- [ ] **Step 3: Write api/files.ts**

```typescript
import { apiClient } from './client';
import type { FileDetail, FileListItem, FilePreview } from '../types';

export async function uploadFile(file: File): Promise<FileDetail> {
  const form = new FormData();
  form.append('file', file);
  const { data } = await apiClient.post<FileDetail>('/files/upload', form);
  return data;
}

export async function listFiles(): Promise<FileListItem[]> {
  const { data } = await apiClient.get<FileListItem[]>('/files');
  return data;
}

export async function getFileDetail(fileId: string): Promise<FileDetail> {
  const { data } = await apiClient.get<FileDetail>(`/files/${fileId}`);
  return data;
}

export async function getFilePreview(fileId: string, rows = 20): Promise<FilePreview> {
  const { data } = await apiClient.get<FilePreview>(`/files/${fileId}/preview`, {
    params: { rows },
  });
  return data;
}
```

- [ ] **Step 4: Write api/chat.ts**

```typescript
import type { ChatRequest, SSEEvent } from '../types';

export async function* streamChat(req: ChatRequest): AsyncGenerator<SSEEvent> {
  const response = await fetch('/api/v1/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });

  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.detail || 'Chat request failed');
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const json = line.slice(6);
        if (json) {
          yield JSON.parse(json) as SSEEvent;
        }
      }
    }
  }
}
```

- [ ] **Step 5: Write api/report.ts**

```typescript
import { apiClient } from './client';

export async function generateReport(fileId: string, conversationId?: string): Promise<string> {
  const { data } = await apiClient.post<{ report: string }>('/report/generate', {
    file_id: fileId,
    conversation_id: conversationId || null,
  });
  return data.report;
}
```

- [ ] **Step 6: Verify TypeScript compiles**

```bash
cd D:\claude\ai-data-analyst\frontend && npx tsc --noEmit
```

Expected: No errors

- [ ] **Step 7: Commit**

```bash
cd D:\claude\ai-data-analyst && git add frontend/src/types frontend/src/api && git commit -m "feat: add TypeScript types and API client layer"
```

---

### Task 3: Layout Shell — TopBar + 3-Column Grid

**Files:**
- Create: `D:\claude\ai-data-analyst\frontend\src\App.tsx`
- Create: `D:\claude\ai-data-analyst\frontend\src\components\layout\TopBar.tsx`
- Create: `D:\claude\ai-data-analyst\frontend\src\components\layout\LeftSidebar.tsx`
- Create: `D:\claude\ai-data-analyst\frontend\src\components\layout\ChatPanel.tsx`
- Create: `D:\claude\ai-data-analyst\frontend\src\components\layout\ContextPanel.tsx`

- [ ] **Step 1: Write App.tsx**

```typescript
import { useState } from 'react';
import TopBar from './components/layout/TopBar';
import LeftSidebar from './components/layout/LeftSidebar';
import ChatPanel from './components/layout/ChatPanel';
import ContextPanel from './components/layout/ContextPanel';
import type { AppStage, FileDetail, FileListItem } from './types';

function App() {
  const [files, setFiles] = useState<FileListItem[]>([]);
  const [activeFile, setActiveFile] = useState<FileDetail | null>(null);
  const [stage, setStage] = useState<AppStage>('empty');
  const [toolCalls, setToolCalls] = useState<{ name: string; args: Record<string, unknown>; status: 'pending' | 'running' | 'done' }[]>([]);
  const [chartPaths, setChartPaths] = useState<string[]>([]);

  return (
    <div className="h-screen flex flex-col bg-[var(--bg-primary)]">
      <TopBar activeFile={activeFile} stage={stage} />
      <div className="flex flex-1 overflow-hidden">
        <LeftSidebar
          files={files}
          setFiles={setFiles}
          activeFile={activeFile}
          setActiveFile={setActiveFile}
          setStage={setStage}
          setToolCalls={setToolCalls}
          setChartPaths={setChartPaths}
        />
        <ChatPanel
          activeFile={activeFile}
          stage={stage}
          setStage={setStage}
          setToolCalls={setToolCalls}
          setChartPaths={setChartPaths}
        />
        <ContextPanel
          activeFile={activeFile}
          stage={stage}
          toolCalls={toolCalls}
          chartPaths={chartPaths}
        />
      </div>
    </div>
  );
}

export default App;
```

- [ ] **Step 2: Write TopBar.tsx**

```typescript
import { FileDetail, AppStage } from '../../types';

interface Props {
  activeFile: FileDetail | null;
  stage: AppStage;
}

const stageLabels: Record<AppStage, { text: string; color: string }> = {
  empty: { text: '等待上传', color: 'var(--text-muted)' },
  upload: { text: '就绪', color: 'var(--success)' },
  ready: { text: '就绪', color: 'var(--success)' },
  analyzing: { text: '分析中', color: 'var(--warning)' },
  complete: { text: '完成', color: 'var(--success)' },
};

export default function TopBar({ activeFile, stage }: Props) {
  const status = stageLabels[stage];

  return (
    <header
      className="flex items-center gap-4 px-4 py-2 border-b flex-shrink-0"
      style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border-color)' }}
    >
      <span className="font-bold text-sm" style={{ color: 'var(--accent-light)' }}>
        AI Data Analyst
      </span>
      <div className="flex-1" />
      {activeFile && (
        <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
          {activeFile.filename}
        </span>
      )}
      <span className="text-xs flex items-center gap-1.5">
        <span
          className="inline-block w-2 h-2 rounded-full"
          style={{ background: status.color }}
        />
        <span style={{ color: 'var(--text-secondary)' }}>DeepSeek v4</span>
      </span>
      <span className="text-xs" style={{ color: status.color }}>
        {status.text}
      </span>
    </header>
  );
}
```

- [ ] **Step 3: Write LeftSidebar.tsx (shell, real content in Task 4)**

```typescript
import type { AppStage, FileDetail, FileListItem } from '../../types';

interface Props {
  files: FileListItem[];
  setFiles: (files: FileListItem[]) => void;
  activeFile: FileDetail | null;
  setActiveFile: (file: FileDetail | null) => void;
  setStage: (stage: AppStage) => void;
  setToolCalls: (calls: never[]) => void;
  setChartPaths: (paths: string[]) => void;
}

export default function LeftSidebar(_props: Props) {
  return (
    <aside
      className="w-[18%] min-w-[200px] flex-shrink-0 flex flex-col gap-2 p-3 border-r overflow-y-auto"
      style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border-color)' }}
    >
      <h2 className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--accent-light)' }}>
        数据文件
      </h2>
      {/* FileUploadZone + FileHistoryList will go here in Task 4 */}
    </aside>
  );
}
```

- [ ] **Step 4: Write ChatPanel.tsx (shell, real content in Task 6)**

```typescript
import type { AppStage, FileDetail } from '../../types';

interface Props {
  activeFile: FileDetail | null;
  stage: AppStage;
  setStage: (stage: AppStage) => void;
  setToolCalls: (calls: never[]) => void;
  setChartPaths: (paths: string[]) => void;
}

export default function ChatPanel(_props: Props) {
  return (
    <main className="flex-1 flex flex-col min-w-0">
      <div className="flex-1 flex items-center justify-center">
        <div style={{ color: 'var(--text-muted)' }} className="text-sm text-center">
          <p className="text-lg mb-2">AI Data Analyst</p>
          <p>上传数据文件开始分析</p>
        </div>
      </div>
      {/* ChatInput will go here in Task 6 */}
    </main>
  );
}
```

- [ ] **Step 5: Write ContextPanel.tsx (shell, real content in Task 7)**

```typescript
import type { AppStage, FileDetail } from '../../types';

interface Props {
  activeFile: FileDetail | null;
  stage: AppStage;
  toolCalls: { name: string; args: Record<string, unknown>; status: string }[];
  chartPaths: string[];
}

export default function ContextPanel({ stage }: Props) {
  return (
    <aside
      className="w-[22%] min-w-[240px] flex-shrink-0 flex flex-col gap-3 p-3 border-l overflow-y-auto"
      style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border-color)' }}
    >
      <h2 className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--accent-light)' }}>
        上下文面板
      </h2>
      <div className="flex gap-1.5 text-[10px]">
        <span
          className="px-2 py-0.5 rounded-full font-medium"
          style={{
            background: stage === 'empty' ? 'var(--accent)' : 'var(--bg-card)',
            color: stage === 'empty' ? 'white' : 'var(--text-muted)',
          }}
        >
          上传
        </span>
        <span
          className="px-2 py-0.5 rounded-full font-medium"
          style={{
            background: stage === 'analyzing' ? 'var(--accent)' : 'var(--bg-card)',
            color: stage === 'analyzing' ? 'white' : 'var(--text-muted)',
          }}
        >
          分析
        </span>
        <span
          className="px-2 py-0.5 rounded-full font-medium"
          style={{
            background: stage === 'complete' ? 'var(--accent)' : 'var(--bg-card)',
            color: stage === 'complete' ? 'white' : 'var(--text-muted)',
          }}
        >
          结果
        </span>
      </div>
      {/* DataOverview / TaskProgress / ResultsView will go here in Task 7 */}
    </aside>
  );
}
```

- [ ] **Step 6: Update main.tsx**

```typescript
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

- [ ] **Step 7: Verify dev server renders layout**

```bash
cd D:\claude\ai-data-analyst\frontend && npm run dev
# Open http://localhost:5173 — should show 3-column layout with "上传数据文件开始分析"
```

Expected: Dark 3-column shell with top bar showing "等待上传"

- [ ] **Step 8: Commit**

```bash
cd D:\claude\ai-data-analyst && git add frontend/src/ && git commit -m "feat: add layout shell with TopBar and three-column grid"
```

---

### Task 4: Left Sidebar — File Upload + History

**Files:**
- Modify: `D:\claude\ai-data-analyst\frontend\src\components\layout\LeftSidebar.tsx`
- Create: `D:\claude\ai-data-analyst\frontend\src\components\files\FileUploadZone.tsx`
- Create: `D:\claude\ai-data-analyst\frontend\src\components\files\FileHistoryList.tsx`
- Create: `D:\claude\ai-data-analyst\frontend\src\components\files\FileHistoryItem.tsx`

- [ ] **Step 1: Write FileUploadZone.tsx**

```typescript
import { useRef, useState } from 'react';
import { Upload } from 'lucide-react';

interface Props {
  onUploaded: () => void;
}

export default function FileUploadZone({ onUploaded }: Props) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = async (file: File) => {
    setUploading(true);
    const { uploadFile } = await import('../../api/files');
    try {
      await uploadFile(file);
      onUploaded();
    } catch (e) {
      console.error('Upload failed:', e);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        const file = e.dataTransfer.files[0];
        if (file) handleFile(file);
      }}
      onClick={() => inputRef.current?.click()}
      className="border border-dashed rounded-lg p-4 text-center cursor-pointer transition-colors"
      style={{
        borderColor: dragging ? 'var(--accent)' : 'var(--border-color)',
        background: dragging ? 'var(--bg-card)' : 'transparent',
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".csv,.xlsx,.xls"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
        }}
      />
      <Upload size={18} style={{ color: 'var(--accent-light)', margin: '0 auto 4px' }} />
      <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
        {uploading ? '上传中...' : '上传 CSV / Excel'}
      </p>
    </div>
  );
}
```

- [ ] **Step 2: Write FileHistoryItem.tsx**

```typescript
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
      className="flex items-start gap-2 p-2 rounded-lg cursor-pointer transition-colors"
      style={{
        background: isActive ? 'var(--bg-card)' : 'transparent',
        borderLeft: isActive ? '2px solid var(--accent)' : '2px solid transparent',
      }}
    >
      <FileText size={14} style={{ color: isActive ? 'var(--accent-light)' : 'var(--text-muted)', flexShrink: 0, marginTop: 2 }} />
      <div className="min-w-0">
        <p className="text-xs truncate" style={{ color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)' }}>
          {file.filename}
        </p>
        <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
          {file.col_count}列 · {file.row_count}行
        </p>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Write FileHistoryList.tsx**

```typescript
import type { FileListItem } from '../../types';
import FileHistoryItem from './FileHistoryItem';

interface Props {
  files: FileListItem[];
  activeFileId: string | null;
  onSelect: (fileId: string) => void;
}

export default function FileHistoryList({ files, activeFileId, onSelect }: Props) {
  return (
    <div className="flex flex-col gap-1">
      <p className="text-[10px] font-medium uppercase tracking-wider px-1" style={{ color: 'var(--text-muted)' }}>
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
```

- [ ] **Step 4: Update LeftSidebar.tsx with real content**

Replace the shell with:

```typescript
import { useEffect } from 'react';
import FileUploadZone from '../files/FileUploadZone';
import FileHistoryList from '../files/FileHistoryList';
import { listFiles, getFileDetail } from '../../api/files';
import type { AppStage, FileDetail, FileListItem } from '../../types';

interface Props {
  files: FileListItem[];
  setFiles: (files: FileListItem[]) => void;
  activeFile: FileDetail | null;
  setActiveFile: (file: FileDetail | null) => void;
  setStage: (stage: AppStage) => void;
  setToolCalls: (calls: never[]) => void;
  setChartPaths: (paths: string[]) => void;
}

export default function LeftSidebar({ files, setFiles, activeFile, setActiveFile, setStage, setToolCalls, setChartPaths }: Props) {
  useEffect(() => {
    listFiles().then(setFiles).catch(console.error);
  }, [setFiles]);

  const refreshFiles = () => {
    listFiles().then(setFiles).catch(console.error);
  };

  const handleSelect = async (fileId: string) => {
    setToolCalls([]);
    setChartPaths([]);
    try {
      const detail = await getFileDetail(fileId);
      setActiveFile(detail);
      setStage('ready');
    } catch (e) {
      console.error('Failed to load file:', e);
    }
  };

  return (
    <aside
      className="w-[18%] min-w-[200px] flex-shrink-0 flex flex-col gap-3 p-3 border-r overflow-y-auto"
      style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border-color)' }}
    >
      <h2 className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--accent-light)' }}>
        数据文件
      </h2>
      <FileUploadZone onUploaded={refreshFiles} />
      <FileHistoryList
        files={files}
        activeFileId={activeFile?.id ?? null}
        onSelect={handleSelect}
      />
    </aside>
  );
}
```

- [ ] **Step 5: Verify — start backend and frontend, upload a file**

```bash
# Terminal 1: Backend
cd D:\claude\ai-data-analyst && py -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Terminal 2: Frontend
cd D:\claude\ai-data-analyst\frontend && npm run dev
```

Open http://localhost:5173, upload a CSV. Expected: file appears in left sidebar, clicking it highlights it.

- [ ] **Step 6: Commit**

```bash
cd D:\claude\ai-data-analyst && git add frontend/src/ && git commit -m "feat: add file upload zone and history list in left sidebar"
```

---

### Task 5: Context Panel — Three-Stage Dynamic Content

**Files:**
- Modify: `D:\claude\ai-data-analyst\frontend\src\components\layout\ContextPanel.tsx`
- Create: `D:\claude\ai-data-analyst\frontend\src\components\context\DataOverview.tsx`
- Create: `D:\claude\ai-data-analyst\frontend\src\components\context\TaskProgress.tsx`
- Create: `D:\claude\ai-data-analyst\frontend\src\components\context\ResultsView.tsx`
- Create: `D:\claude\ai-data-analyst\frontend\src\components\context\StageIndicator.tsx`

- [ ] **Step 1: Write StageIndicator.tsx**

```typescript
import type { AppStage } from '../../types';

const stages: { key: AppStage[]; label: string }[] = [
  { key: ['empty', 'upload', 'ready'], label: '上传' },
  { key: ['analyzing'], label: '分析' },
  { key: ['complete'], label: '结果' },
];

export default function StageIndicator({ stage }: { stage: AppStage }) {
  const activeIndex =
    stage === 'analyzing' ? 1 :
    stage === 'complete' ? 2 : 0;

  return (
    <div className="flex gap-1.5 text-[10px]">
      {stages.map((s, i) => {
        const isActive = i === activeIndex;
        return (
          <span
            key={s.label}
            className="px-2 py-0.5 rounded-full font-medium transition-colors"
            style={{
              background: isActive ? 'var(--accent)' : 'var(--bg-card)',
              color: isActive ? 'white' : 'var(--text-muted)',
            }}
          >
            {s.label}
          </span>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Write DataOverview.tsx**

```typescript
import type { FileDetail } from '../../types';

export default function DataOverview({ file }: { file: FileDetail }) {
  return (
    <div className="flex flex-col gap-3">
      <div
        className="rounded-lg p-3 space-y-2"
        style={{ background: 'var(--bg-card)' }}
      >
        <h3 className="text-[10px] font-medium uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
          数据概览
        </h3>
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div>
            <span style={{ color: 'var(--text-muted)' }}>行数</span>
            <p style={{ color: 'var(--text-primary)' }}>{file.row_count.toLocaleString()}</p>
          </div>
          <div>
            <span style={{ color: 'var(--text-muted)' }}>列数</span>
            <p style={{ color: 'var(--text-primary)' }}>{file.col_count}</p>
          </div>
          <div>
            <span style={{ color: 'var(--text-muted)' }}>类型</span>
            <p style={{ color: 'var(--text-primary)' }}>{file.file_type.toUpperCase()}</p>
          </div>
        </div>
      </div>

      <div
        className="rounded-lg p-3 space-y-2"
        style={{ background: 'var(--bg-card)' }}
      >
        <h3 className="text-[10px] font-medium uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
          字段信息
        </h3>
        <div className="space-y-1.5">
          {file.columns.map((col) => (
            <div key={col.name} className="text-xs">
              <div className="flex justify-between">
                <span style={{ color: 'var(--text-primary)' }} className="font-medium">
                  {col.name}
                </span>
                <span style={{ color: 'var(--text-muted)' }}>{col.dtype}</span>
              </div>
              <div className="flex gap-3 text-[10px]" style={{ color: 'var(--text-muted)' }}>
                <span>{col.unique_count} 唯一值</span>
                {col.null_count > 0 && (
                  <span style={{ color: 'var(--warning)' }}>
                    {col.null_count} 缺失 ({(col.null_rate * 100).toFixed(1)}%)
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {file.profile_report && (
        <div
          className="rounded-lg p-3 space-y-1"
          style={{ background: 'var(--bg-card)' }}
        >
          <h3 className="text-[10px] font-medium uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
            数据质量
          </h3>
          <pre
            className="text-[10px] whitespace-pre-wrap leading-relaxed"
            style={{ color: 'var(--text-secondary)', fontFamily: 'inherit' }}
          >
            {file.profile_report}
          </pre>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Write TaskProgress.tsx**

```typescript
interface ToolCall {
  name: string;
  args: Record<string, unknown>;
  status: 'pending' | 'running' | 'done';
}

const statusConfig = {
  pending: { color: 'var(--text-muted)', icon: '○' },
  running: { color: 'var(--warning)', icon: '◷' },
  done: { color: 'var(--success)', icon: '✓' },
};

function toolLabel(name: string): string {
  const labels: Record<string, string> = {
    describe_data: '统计描述',
    value_counts: '值分布统计',
    correlation_analysis: '相关性分析',
    group_analysis: '分组聚合',
    filter_data: '数据筛选',
    sort_data: '数据排序',
    trend_analysis: '趋势分析',
    detect_outliers: '异常值检测',
    data_summary: '数据摘要',
    draw_bar_chart: '生成柱状图',
    draw_line_chart: '生成折线图',
    draw_pie_chart: '生成饼图',
    draw_scatter_chart: '生成散点图',
    draw_heatmap_chart: '生成热力图',
  };
  return labels[name] || name;
}

export default function TaskProgress({ toolCalls }: { toolCalls: ToolCall[] }) {
  if (toolCalls.length === 0) return null;

  return (
    <div className="rounded-lg p-3 space-y-2" style={{ background: 'var(--bg-card)' }}>
      <h3 className="text-[10px] font-medium uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
        AI 任务步骤
      </h3>
      <div className="space-y-1.5">
        {toolCalls.map((tc, i) => {
          const cfg = statusConfig[tc.status];
          return (
            <div key={i} className="flex items-center gap-2 text-xs" style={{ color: cfg.color }}>
              <span className="text-[10px]">{cfg.icon}</span>
              <span>{toolLabel(tc.name)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Write ResultsView.tsx**

```typescript
import { generateReport } from '../../api/report';

interface Props {
  chartPaths: string[];
  activeFileId: string | null;
}

export default function ResultsView({ chartPaths, activeFileId }: Props) {
  const handleGenerateReport = async () => {
    if (!activeFileId) return;
    try {
      const report = await generateReport(activeFileId);
      // Open report in a new tab or modal
      const blob = new Blob([report], { type: 'text/markdown' });
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank');
    } catch (e) {
      console.error('Report generation failed:', e);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      {chartPaths.length > 0 && (
        <div className="rounded-lg p-3 space-y-2" style={{ background: 'var(--bg-card)' }}>
          <h3 className="text-[10px] font-medium uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
            图表 ({chartPaths.length})
          </h3>
          <div className="space-y-2">
            {chartPaths.map((path, i) => (
              <div
                key={i}
                className="rounded overflow-hidden cursor-pointer border"
                style={{ borderColor: 'var(--border-color)' }}
                onClick={() => window.open(path, '_blank')}
              >
                <img
                  src={path}
                  alt={`Chart ${i + 1}`}
                  className="w-full h-auto"
                />
              </div>
            ))}
          </div>
        </div>
      )}

      <button
        onClick={handleGenerateReport}
        disabled={!activeFileId}
        className="w-full py-2.5 rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
        style={{
          background: activeFileId ? 'var(--accent)' : 'var(--bg-card)',
          color: activeFileId ? 'white' : 'var(--text-muted)',
        }}
      >
        生成分析报告
      </button>
    </div>
  );
}
```

- [ ] **Step 5: Update ContextPanel.tsx with dynamic content**

Replace the shell with:

```typescript
import type { AppStage, FileDetail } from '../../types';
import StageIndicator from '../context/StageIndicator';
import DataOverview from '../context/DataOverview';
import TaskProgress from '../context/TaskProgress';
import ResultsView from '../context/ResultsView';

interface Props {
  activeFile: FileDetail | null;
  stage: AppStage;
  toolCalls: { name: string; args: Record<string, unknown>; status: string }[];
  chartPaths: string[];
}

export default function ContextPanel({ activeFile, stage, toolCalls, chartPaths }: Props) {
  return (
    <aside
      className="w-[22%] min-w-[240px] flex-shrink-0 flex flex-col gap-3 p-3 border-l overflow-y-auto"
      style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border-color)' }}
    >
      <h2 className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--accent-light)' }}>
        上下文面板
      </h2>
      <StageIndicator stage={stage} />

      {!activeFile && (
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
          上传或选择一个数据文件以查看详情
        </p>
      )}

      {(stage === 'upload' || stage === 'ready') && activeFile && (
        <DataOverview file={activeFile} />
      )}

      {stage === 'analyzing' && (
        <>
          {activeFile && <DataOverview file={activeFile} />}
          <TaskProgress toolCalls={toolCalls as { name: string; args: Record<string, unknown>; status: 'pending' | 'running' | 'done' }[]} />
        </>
      )}

      {stage === 'complete' && (
        <>
          {activeFile && <DataOverview file={activeFile} />}
          <TaskProgress toolCalls={toolCalls as { name: string; args: Record<string, unknown>; status: 'pending' | 'running' | 'done' }[]} />
          <ResultsView chartPaths={chartPaths} activeFileId={activeFile?.id ?? null} />
        </>
      )}
    </aside>
  );
}
```

- [ ] **Step 6: Verify all stages display correctly**

Upload a file → Context Panel shows stage 1 (DataOverview). Send a chat message → stage switches to "analyzing" with TaskProgress. After done → stage "complete" with ResultsView.

- [ ] **Step 7: Commit**

```bash
cd D:\claude\ai-data-analyst && git add frontend/src/ && git commit -m "feat: add dynamic Context Panel with three-stage content"
```

---

### Task 6: Chat Panel — Messages, Input, SSE Streaming

**Files:**
- Modify: `D:\claude\ai-data-analyst\frontend\src\components\layout\ChatPanel.tsx`
- Create: `D:\claude\ai-data-analyst\frontend\src\components\chat\ChatInput.tsx`
- Create: `D:\claude\ai-data-analyst\frontend\src\components\chat\MessageList.tsx`
- Create: `D:\claude\ai-data-analyst\frontend\src\components\chat\UserMessage.tsx`
- Create: `D:\claude\ai-data-analyst\frontend\src\components\chat\AssistantMessage.tsx`
- Create: `D:\claude\ai-data-analyst\frontend\src\components\chat\ToolCallCard.tsx`
- Create: `D:\claude\ai-data-analyst\frontend\src\components\chat\ChartInline.tsx`

- [ ] **Step 1: Write UserMessage.tsx**

```typescript
export default function UserMessage({ content }: { content: string }) {
  return (
    <div className="flex justify-end mb-4">
      <div
        className="max-w-[75%] rounded-2xl rounded-br-md px-4 py-2.5 text-sm leading-relaxed"
        style={{ background: 'var(--accent)', color: 'white' }}
      >
        {content}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Write ToolCallCard.tsx**

```typescript
const toolNames: Record<string, string> = {
  describe_data: '统计描述',
  value_counts: '值分布统计',
  correlation_analysis: '相关性分析',
  group_analysis: '分组聚合',
  filter_data: '数据筛选',
  sort_data: '数据排序',
  trend_analysis: '趋势分析',
  detect_outliers: '异常值检测',
  data_summary: '数据摘要',
  draw_bar_chart: '生成柱状图',
  draw_line_chart: '生成折线图',
  draw_pie_chart: '生成饼图',
  draw_scatter_chart: '生成散点图',
  draw_heatmap_chart: '生成热力图',
};

export default function ToolCallCard({ name, args, status }: {
  name: string;
  args: Record<string, unknown>;
  status: 'running' | 'done';
}) {
  return (
    <div
      className="rounded-lg px-3 py-2 mb-2 text-xs border"
      style={{
        background: 'var(--bg-card)',
        borderColor: status === 'running' ? 'var(--warning)' : 'var(--success)',
      }}
    >
      <div className="flex items-center gap-2 mb-1">
        <span style={{ color: status === 'running' ? 'var(--warning)' : 'var(--success)' }}>
          {status === 'running' ? '◷' : '✓'}
        </span>
        <span style={{ color: 'var(--accent-light)' }}>{toolNames[name] || name}</span>
      </div>
      <div style={{ color: 'var(--text-muted)', fontSize: '10px' }}>
        {Object.entries(args)
          .filter(([k]) => k !== 'file_id')
          .map(([k, v]) => `${k}=${v}`)
          .join(', ')}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Write ChartInline.tsx**

```typescript
export default function ChartInline({ path }: { path: string }) {
  return (
    <div
      className="rounded-lg overflow-hidden mb-2 cursor-pointer border"
      style={{ borderColor: 'var(--border-color)' }}
      onClick={() => window.open(path, '_blank')}
    >
      <img src={path} alt="Chart" className="w-full max-h-80 object-contain" style={{ background: 'white' }} />
    </div>
  );
}
```

- [ ] **Step 4: Write AssistantMessage.tsx**

```typescript
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import ToolCallCard from './ToolCallCard';
import ChartInline from './ChartInline';

interface ToolCall {
  name: string;
  args: Record<string, unknown>;
  status: 'running' | 'done';
}

interface Props {
  content: string;
  toolCalls: ToolCall[];
  chartPaths: string[];
}

export default function AssistantMessage({ content, toolCalls, chartPaths }: Props) {
  return (
    <div className="flex gap-2 mb-4">
      <div
        className="w-7 h-7 rounded-full flex items-center justify-center text-xs flex-shrink-0"
        style={{ background: '#1e3a5f', color: 'var(--accent-light)' }}
      >
        AI
      </div>
      <div className="max-w-[80%]">
        {toolCalls.length > 0 && (
          <div className="mb-2">
            {toolCalls.map((tc, i) => (
              <ToolCallCard key={i} {...tc} />
            ))}
          </div>
        )}
        {content && (
          <div
            className="rounded-2xl rounded-bl-md px-4 py-2.5 text-sm leading-relaxed prose prose-invert prose-sm max-w-none"
            style={{ background: 'var(--bg-card)', color: 'var(--text-primary)' }}
          >
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {content}
            </ReactMarkdown>
          </div>
        )}
        {chartPaths.map((path, i) => (
          <ChartInline key={i} path={path} />
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Write MessageList.tsx**

```typescript
import UserMessage from './UserMessage';
import AssistantMessage from './AssistantMessage';

export interface Message {
  role: 'user' | 'assistant';
  content: string;
  toolCalls?: { name: string; args: Record<string, unknown>; status: 'running' | 'done' }[];
  chartPaths?: string[];
}

export default function MessageList({ messages }: { messages: Message[] }) {
  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-2">
      {messages.map((msg, i) =>
        msg.role === 'user' ? (
          <UserMessage key={i} content={msg.content} />
        ) : (
          <AssistantMessage
            key={i}
            content={msg.content}
            toolCalls={msg.toolCalls || []}
            chartPaths={msg.chartPaths || []}
          />
        ),
      )}
    </div>
  );
}
```

- [ ] **Step 6: Write ChatInput.tsx**

```typescript
import { useState, useRef, useEffect } from 'react';
import { ArrowUp } from 'lucide-react';

interface Props {
  onSend: (message: string) => void;
  disabled: boolean;
}

export default function ChatInput({ onSend, disabled }: Props) {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + 'px';
    }
  }, [value]);

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="p-3 border-t flex-shrink-0" style={{ borderColor: 'var(--border-color)' }}>
      <div
        className="flex items-end gap-2 rounded-xl px-4 py-2.5 border"
        style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border-color)' }}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入分析问题..."
          rows={1}
          disabled={disabled}
          className="flex-1 bg-transparent border-none outline-none resize-none text-sm placeholder-gray-500 disabled:opacity-50"
          style={{ color: 'var(--text-primary)' }}
        />
        <button
          onClick={handleSend}
          disabled={disabled || !value.trim()}
          className="p-1.5 rounded-lg transition-colors flex-shrink-0 disabled:opacity-30"
          style={{ background: value.trim() && !disabled ? 'var(--accent)' : 'transparent' }}
        >
          <ArrowUp size={16} color={value.trim() && !disabled ? 'white' : 'var(--text-muted)'} />
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 7: Update ChatPanel.tsx with full chat logic**

```typescript
import { useState, useRef, useCallback } from 'react';
import type { AppStage, FileDetail } from '../../types';
import { streamChat } from '../../api/chat';
import MessageList, { type Message } from '../chat/MessageList';
import ChatInput from '../chat/ChatInput';

interface Props {
  activeFile: FileDetail | null;
  stage: AppStage;
  setStage: (stage: AppStage) => void;
  setToolCalls: (calls: { name: string; args: Record<string, unknown>; status: 'pending' | 'running' | 'done' }[]) => void;
  setChartPaths: (paths: string[]) => void;
}

export default function ChatPanel({ activeFile, stage, setStage, setToolCalls, setChartPaths }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [streaming, setStreaming] = useState(false);
  const convIdRef = useRef<string | null>(null);

  const handleSend = useCallback(async (text: string) => {
    if (!activeFile) return;

    const userMsg: Message = { role: 'user', content: text };
    const assistantMsg: Message = {
      role: 'assistant',
      content: '',
      toolCalls: [],
      chartPaths: [],
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setStreaming(true);
    setStage('analyzing');
    setToolCalls([]);
    setChartPaths([]);

    try {
      const seenTools = new Set<string>();
      const localChartPaths: string[] = [];

      for await (const event of streamChat({
        file_id: activeFile.id,
        message: text,
        conversation_id: convIdRef.current,
      })) {
        if (event.type === 'tool') {
          const calls: { name: string; args: Record<string, unknown> }[] = JSON.parse(event.content);
          const newCalls = calls
            .filter((c) => !seenTools.has(c.name))
            .map((c) => {
              seenTools.add(c.name);
              return { ...c, status: 'running' as const };
            });
          if (newCalls.length > 0) {
            setToolCalls((prev) => [...prev, ...newCalls]);
            setMessages((prev) => {
              const last = prev[prev.length - 1];
              if (last.role === 'assistant') {
                last.toolCalls = [...(last.toolCalls || []), ...newCalls];
              }
              return [...prev];
            });
          }
        } else if (event.type === 'text') {
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last.role === 'assistant') {
              last.content += event.content;
            }
            return [...prev];
          });
          setToolCalls((prev) =>
            prev.map((tc) => ({ ...tc, status: 'done' as const })),
          );
        } else if (event.type === 'done') {
          convIdRef.current = event.conversation_id;
          // Check assistant message for chart paths in content
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last.role === 'assistant') {
              const chartRegex = /\/storage\/charts\/[a-f0-9-]+\.png/g;
              const matches = last.content.match(chartRegex) || [];
              for (const m of matches) {
                if (!localChartPaths.includes(m)) localChartPaths.push(m);
              }
            }
            return [...prev];
          });
          setChartPaths(localChartPaths);
          setToolCalls((prev) =>
            prev.map((tc) => ({ ...tc, status: 'done' as const })),
          );
          setStage('complete');
        }
      }
    } catch (e) {
      console.error('Chat error:', e);
      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (last.role === 'assistant') {
          last.content = '抱歉，分析过程出错。请重试。';
        }
        return [...prev];
      });
      setStage('ready');
    } finally {
      setStreaming(false);
    }
  }, [activeFile, setStage, setToolCalls, setChartPaths]);

  return (
    <main className="flex-1 flex flex-col min-w-0">
      {messages.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <p className="text-lg mb-2" style={{ color: 'var(--text-primary)' }}>
              AI Data Analyst
            </p>
            <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
              {activeFile
                ? `已加载 ${activeFile.filename}，开始提问吧`
                : '上传数据文件开始分析'}
            </p>
          </div>
        </div>
      ) : (
        <MessageList messages={messages} />
      )}
      <ChatInput
        onSend={handleSend}
        disabled={streaming || !activeFile}
      />
    </main>
  );
}
```

- [ ] **Step 8: Verify SSE streaming end-to-end**

Start backend + frontend. Upload a file, send a chat message. Expected:
- User message appears immediately
- Assistant bubble appears with loading state
- Tool calls appear as cards in the message and in Context Panel
- Text streams in character by character
- Charts appear inline when generated
- Context Panel transitions through stages

- [ ] **Step 9: Commit**

```bash
cd D:\claude\ai-data-analyst && git add frontend/src/ && git commit -m "feat: add chat panel with SSE streaming, Markdown rendering, and inline charts"
```

---

### Task 7: Final Polish — Welcome Screen + Responsive + Cleanup

**Files:**
- Modify: `D:\claude\ai-data-analyst\frontend\src\App.tsx` (minor)
- Modify: `D:\claude\ai-data-analyst\frontend\src\components\layout\ChatPanel.tsx` (welcome screen already done)

- [ ] **Step 1: Add CORS support check**

Verify the Vite proxy config handles all backend routes. The `vite.config.ts` already proxies `/api` and `/storage`.

Test: `curl http://localhost:5173/api/v1/files` should return file list JSON (via proxy to backend).

- [ ] **Step 2: Add favicon and title**

Edit `frontend/index.html`:
```html
<!DOCTYPE html>
<html lang="zh-CN" class="dark">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📊</text></svg>" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>AI Data Analyst</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 3: Full integration test**

```bash
# Terminal 1
cd D:\claude\ai-data-analyst && py -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Terminal 2
cd D:\claude\ai-data-analyst\frontend && npm run dev
```

Test checklist:
1. Open http://localhost:5173 → dark welcome screen
2. Upload CSV → file appears in left sidebar, details in Context Panel
3. Click file → Context Panel shows data overview + field info + quality report
4. Send message "分析这个数据集" → SSE streams, tool calls visible, text appears
5. Request chart → chart image appears inline in chat
6. Context Panel transitions: ready → analyzing → complete
7. Click "生成分析报告" → report opens in new tab

- [ ] **Step 4: Commit**

```bash
cd D:\claude\ai-data-analyst && git add frontend/ && git commit -m "feat: final polish — welcome screen, favicon, CORS proxy config"
```

---

## Post-MVP (Not in This Plan)

- [ ] shadcn/ui component integration (Button, Card, Dialog, etc.)
- [ ] Chart modal/lightbox for zoom
- [ ] Conversation history management
- [ ] Dark/light theme toggle
- [ ] File delete
- [ ] Responsive breakpoints for mobile/tablet
- [ ] Error toast notifications
- [ ] Keyboard shortcuts
