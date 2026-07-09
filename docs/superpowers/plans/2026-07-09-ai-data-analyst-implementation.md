# AI Data Analyst Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an AI Data Analyst app where users upload CSV/Excel files, then chat with an AI Agent to analyze data, generate charts, and produce reports.

**Architecture:** FastAPI backend with LangGraph Agent Controller using Tool Calling. Analysis tools are pre-defined Python functions (no sandbox). LLM provider is abstracted behind a common interface. SQLite stores files, conversations, messages, and charts.

**Tech Stack:** FastAPI, LangGraph, LangChain @tool, DeepSeek API (default), pandas, matplotlib/seaborn, SQLAlchemy + SQLite, Pydantic v2

---

### Task 1: Project Skeleton

**Files:**
- Create: `D:\claude\ai-data-analyst\.gitignore`
- Create: `D:\claude\ai-data-analyst\.env.example`
- Create: `D:\claude\ai-data-analyst\requirements.txt`
- Create: `D:\claude\ai-data-analyst\app\__init__.py`
- Create: `D:\claude\ai-data-analyst\app\config.py`
- Create: `D:\claude\ai-data-analyst\app\main.py`
- Create: `D:\claude\ai-data-analyst\storage\uploads\.gitkeep`
- Create: `D:\claude\ai-data-analyst\storage\charts\.gitkeep`

- [ ] **Step 1: Create directory structure**

Run:
```bash
cd /d/claude/ai-data-analyst
mkdir -p app/api app/services/tools app/services/llm app/models app/db storage/uploads storage/charts tests
touch app/__init__.py app/api/__init__.py app/services/__init__.py app/services/tools/__init__.py app/services/llm/__init__.py app/models/__init__.py app/db/__init__.py tests/__init__.py storage/uploads/.gitkeep storage/charts/.gitkeep
```

- [ ] **Step 2: Write .gitignore**

```gitignore
__pycache__/
*.pyc
.env
storage/uploads/*
storage/charts/*
!storage/uploads/.gitkeep
!storage/charts/.gitkeep
app.db
.venv/
```

- [ ] **Step 3: Write .env.example**

```
DEEPSEEK_API_KEY=sk-your-key-here
DEEPSEEK_BASE_URL=https://api.deepseek.com
LLM_PROVIDER=deepseek
DATABASE_URL=sqlite:///./app.db
UPLOAD_DIR=./storage/uploads
CHART_DIR=./storage/charts
```

- [ ] **Step 4: Write requirements.txt**

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
python-multipart==0.0.20
pydantic-settings==2.7.1
langgraph==0.2.61
langchain==0.3.15
httpx==0.28.1
sqlalchemy==2.0.36
pandas==2.2.3
numpy==2.0.2
openpyxl==3.1.5
matplotlib==3.9.3
seaborn==0.13.2
pytest==8.3.4
pytest-asyncio==0.25.0
```

- [ ] **Step 5: Write app/config.py**

```python
import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    deepseek_api_key: str
    deepseek_base_url: str = "https://api.deepseek.com"
    llm_provider: str = "deepseek"
    database_url: str = "sqlite:///./app.db"
    upload_dir: str = "./storage/uploads"
    chart_dir: str = "./storage/charts"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
os.makedirs(settings.upload_dir, exist_ok=True)
os.makedirs(settings.chart_dir, exist_ok=True)
```

- [ ] **Step 6: Write app/main.py**

```python
from fastapi import FastAPI
from app.db.database import init_db

app = FastAPI(title="AI Data Analyst", version="0.1.0")


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 7: Install dependencies and verify**

Run:
```bash
cd /d/claude/ai-data-analyst
pip install -r requirements.txt
cp .env.example .env
py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Expected: Server starts, `curl http://127.0.0.1:8000/health` returns `{"status":"ok"}`

- [ ] **Step 8: Commit**

```bash
cd /d/claude/ai-data-analyst && git init && git add -A && git commit -m "feat: project skeleton with FastAPI app and config"
```

---

### Task 2: Database Layer

**Files:**
- Create: `D:\claude\ai-data-analyst\app\db\database.py`
- Create: `D:\claude\ai-data-analyst\app\db\models.py`

- [ ] **Step 1: Write app/db/database.py**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db():
    Base.metadata.create_all(bind=engine)
```

- [ ] **Step 2: Write app/db/models.py**

```python
import datetime
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.db.database import Base


class FileModel(Base):
    __tablename__ = "files"

    id = Column(String, primary_key=True)
    filename = Column(String, nullable=False)
    filepath = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    row_count = Column(Integer, default=0)
    col_count = Column(Integer, default=0)
    columns_info = Column(JSON, default=list)
    profile_report = Column(Text, default="")
    uploaded_at = Column(DateTime, default=datetime.datetime.utcnow)

    conversations = relationship("ConversationModel", back_populates="file", cascade="all, delete-orphan")


class ConversationModel(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True)
    file_id = Column(String, ForeignKey("files.id"), nullable=False)
    title = Column(String, default="新对话")
    mode = Column(String, default="agent")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    file = relationship("FileModel", back_populates="conversations")
    messages = relationship("MessageModel", back_populates="conversation", cascade="all, delete-orphan")


class MessageModel(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True)
    conv_id = Column(String, ForeignKey("conversations.id"), nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, default="")
    tool_calls = Column(JSON, default=None)
    chart_ids = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    conversation = relationship("ConversationModel", back_populates="messages")
    charts = relationship("ChartModel", back_populates="message", cascade="all, delete-orphan")


class ChartModel(Base):
    __tablename__ = "charts"

    id = Column(String, primary_key=True)
    message_id = Column(String, ForeignKey("messages.id"), nullable=False)
    chart_type = Column(String, nullable=False)
    title = Column(String, default="")
    filepath = Column(String, nullable=False)
    config = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    message = relationship("MessageModel", back_populates="charts")
```

- [ ] **Step 3: Verify tables create on startup**

Run: `py -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
Expected: `app.db` file created with 4 tables.

- [ ] **Step 4: Commit**

```bash
cd /d/claude/ai-data-analyst && git add -A && git commit -m "feat: add SQLite database layer with File, Conversation, Message, Chart models"
```

---

### Task 3: Pydantic Models

**Files:**
- Create: `D:\claude\ai-data-analyst\app\models\file.py`
- Create: `D:\claude\ai-data-analyst\app\models\chat.py`
- Create: `D:\claude\ai-data-analyst\app\models\chart.py`

- [ ] **Step 1: Write app/models/file.py**

```python
from pydantic import BaseModel


class ColumnInfo(BaseModel):
    name: str
    dtype: str
    null_count: int = 0
    null_rate: float = 0.0
    unique_count: int = 0
    sample_values: list = []


class FileDetail(BaseModel):
    id: str
    filename: str
    file_type: str
    row_count: int
    col_count: int
    columns: list[ColumnInfo]
    profile_report: str = ""


class FileListItem(BaseModel):
    id: str
    filename: str
    file_type: str
    row_count: int
    col_count: int
    uploaded_at: str


class FilePreview(BaseModel):
    columns: list[str]
    rows: list[list]
    total_rows: int
```

- [ ] **Step 2: Write app/models/chat.py**

```python
from pydantic import BaseModel


class ChatRequest(BaseModel):
    file_id: str
    message: str
    conversation_id: str | None = None


class ToolCallInfo(BaseModel):
    name: str
    args: dict
    result: str


class ChatResponse(BaseModel):
    conversation_id: str
    message_id: str
    answer: str
    tool_calls: list[ToolCallInfo] = []
    chart_ids: list[str] = []
```

- [ ] **Step 3: Write app/models/chart.py**

```python
from pydantic import BaseModel


class ChartInfo(BaseModel):
    id: str
    chart_type: str
    title: str
    filepath: str
    config: dict = {}
```

- [ ] **Step 4: Verify models import cleanly**

Run: `py -c "from app.models.file import FileDetail, FileListItem, FilePreview; from app.models.chat import ChatRequest, ChatResponse; from app.models.chart import ChartInfo; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
cd /d/claude/ai-data-analyst && git add -A && git commit -m "feat: add Pydantic models for file, chat, and chart schemas"
```

---

### Task 4: LLM Provider Abstraction

**Files:**
- Create: `D:\claude\ai-data-analyst\app\services\llm\base.py`
- Create: `D:\claude\ai-data-analyst\app\services\llm\deepseek.py`
- Create: `D:\claude\ai-data-analyst\app\services\llm\openai.py`
- Create: `D:\claude\ai-data-analyst\app\services\llm\factory.py`
- Create: `D:\claude\ai-data-analyst\tests\test_llm.py`

- [ ] **Step 1: Write app/services/llm/base.py**

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator


class BaseLLM(ABC):
    @abstractmethod
    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """Return {"content": str, "tool_calls": list | None}"""
        ...

    @abstractmethod
    async def chat_stream(self, messages: list[dict]) -> AsyncIterator[str]:
        """Yield content chunks"""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        ...
```

- [ ] **Step 2: Write app/services/llm/deepseek.py**

```python
import json as json_module
import httpx
from app.config import settings
from app.services.llm.base import BaseLLM


class DeepSeekLLM(BaseLLM):
    def __init__(self):
        self.base_url = settings.deepseek_base_url
        self.api_key = settings.deepseek_api_key
        self._model = "deepseek-chat"
        self._client: httpx.AsyncClient | None = None

    @property
    def model_name(self) -> str:
        return self._model

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=60.0,
            )
        return self._client

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        client = await self._get_client()
        body = {"model": self._model, "messages": messages, "temperature": 0.7}
        if tools:
            body["tools"] = tools

        resp = await client.post("/v1/chat/completions", json=body)
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]
        msg = choice["message"]

        result = {"content": msg.get("content", "") or "", "tool_calls": None}
        if msg.get("tool_calls"):
            result["tool_calls"] = [
                {
                    "id": tc["id"],
                    "name": tc["function"]["name"],
                    "args": json_module.loads(tc["function"]["arguments"]) if isinstance(tc["function"]["arguments"], str) else tc["function"]["arguments"],
                }
                for tc in msg["tool_calls"]
            ]
        return result

    async def chat_stream(self, messages: list[dict]):
        client = await self._get_client()
        body = {"model": self._model, "messages": messages, "temperature": 0.7, "stream": True}

        async with client.stream("POST", "/v1/chat/completions", json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    chunk = line[6:]
                    if chunk == "[DONE]":
                        break
                    try:
                        data = json_module.loads(chunk)
                        delta = data["choices"][0].get("delta", {})
                        if delta.get("content"):
                            yield delta["content"]
                    except (json_module.JSONDecodeError, KeyError, IndexError):
                        continue

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
```

- [ ] **Step 3: Write app/services/llm/openai.py (stub for future)**

```python
from app.services.llm.base import BaseLLM


class OpenAILLM(BaseLLM):
    def __init__(self):
        self._model = "gpt-4o"

    @property
    def model_name(self) -> str:
        return self._model

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        raise NotImplementedError("OpenAI provider not yet implemented")

    async def chat_stream(self, messages: list[dict]):
        raise NotImplementedError("OpenAI provider not yet implemented")
        yield
```

- [ ] **Step 4: Write app/services/llm/factory.py**

```python
from app.config import settings
from app.services.llm.base import BaseLLM


def get_llm(provider: str | None = None) -> BaseLLM:
    provider = provider or settings.llm_provider

    if provider == "deepseek":
        from app.services.llm.deepseek import DeepSeekLLM
        return DeepSeekLLM()
    elif provider == "openai":
        from app.services.llm.openai import OpenAILLM
        return OpenAILLM()
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
```

- [ ] **Step 5: Write a quick smoke test**

Create `tests/test_llm.py`:

```python
import pytest
from app.services.llm.factory import get_llm
from app.services.llm.base import BaseLLM


def test_get_llm_returns_deepseek_by_default():
    llm = get_llm()
    assert isinstance(llm, BaseLLM)
    assert llm.model_name == "deepseek-chat"


def test_get_llm_unknown_provider_raises():
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_llm("unknown")
```

Run: `pytest tests/test_llm.py -v`
Expected: 2 PASS

- [ ] **Step 6: Commit**

```bash
cd /d/claude/ai-data-analyst && git add -A && git commit -m "feat: add LLM provider abstraction with DeepSeek and OpenAI stubs"
```

---

### Task 5: Parser Service

**Files:**
- Create: `D:\claude\ai-data-analyst\app\services\parser.py`
- Create: `D:\claude\ai-data-analyst\tests\test_parser.py`

- [ ] **Step 1: Write app/services/parser.py**

```python
import pandas as pd
from pathlib import Path


def parse_file(filepath: str) -> pd.DataFrame:
    ext = Path(filepath).suffix.lower()
    if ext == ".csv":
        return pd.read_csv(filepath)
    elif ext in (".xlsx", ".xls"):
        return pd.read_excel(filepath)
    else:
        raise ValueError(f"Unsupported file type: {ext}")


def extract_columns_info(df: pd.DataFrame) -> list[dict]:
    info = []
    for col in df.columns:
        null_count = int(df[col].isnull().sum())
        info.append({
            "name": str(col),
            "dtype": str(df[col].dtype),
            "null_count": null_count,
            "null_rate": round(null_count / len(df), 4) if len(df) > 0 else 0.0,
            "unique_count": int(df[col].nunique()),
            "sample_values": [str(v) for v in df[col].dropna().head(5).tolist()],
        })
    return info
```

- [ ] **Step 2: Write tests/test_parser.py**

```python
import os
import pandas as pd
import pytest
from app.services.parser import parse_file, extract_columns_info


def test_parse_csv(tmp_path):
    csv_path = tmp_path / "test.csv"
    df = pd.DataFrame({"name": ["a", "b", "c"], "value": [1, 2, 3]})
    df.to_csv(csv_path, index=False)

    result = parse_file(str(csv_path))
    assert result.shape == (3, 2)
    assert list(result.columns) == ["name", "value"]


def test_parse_excel(tmp_path):
    xlsx_path = tmp_path / "test.xlsx"
    df = pd.DataFrame({"x": [1, 2]})
    df.to_excel(xlsx_path, index=False)

    result = parse_file(str(xlsx_path))
    assert result.shape == (2, 1)


def test_parse_unsupported_raises(tmp_path):
    bad = tmp_path / "test.txt"
    bad.write_text("hello")
    with pytest.raises(ValueError, match="Unsupported"):
        parse_file(str(bad))


def test_extract_columns_info():
    df = pd.DataFrame({"name": ["a", "b", None], "score": [1.0, 2.0, 3.0]})
    info = extract_columns_info(df)
    assert len(info) == 2
    assert info[0]["null_count"] == 1
    assert info[0]["null_rate"] == pytest.approx(1/3, 0.01)
    assert info[1]["dtype"] == "float64"
```

Run: `pytest tests/test_parser.py -v`
Expected: 4 PASS

- [ ] **Step 3: Commit**

```bash
cd /d/claude/ai-data-analyst && git add -A && git commit -m "feat: add CSV/Excel parser service with column info extraction"
```

---

### Task 6: Data Profiler Service

**Files:**
- Create: `D:\claude\ai-data-analyst\app\services\profiler.py`
- Create: `D:\claude\ai-data-analyst\tests\test_profiler.py`

- [ ] **Step 1: Write app/services/profiler.py**

```python
import pandas as pd
import numpy as np


def generate_profile(df: pd.DataFrame) -> str:
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    text_cols = df.select_dtypes(include=["object"]).columns.tolist()

    lines = [
        "# 数据质量报告",
        "",
        f"- **行数**: {len(df)}",
        f"- **列数**: {len(df.columns)}",
        f"- **重复行**: {int(df.duplicated().sum())}",
        f"- **数值列**: {len(numeric_cols)}",
        f"- **文本列**: {len(text_cols)}",
        "",
    ]

    if numeric_cols:
        lines.append("## 数值列统计")
        lines.append("")
        lines.append("| 列名 | 均值 | 标准差 | 最小值 | 25% | 50% | 75% | 最大值 |")
        lines.append("|------|------|--------|--------|-----|-----|-----|--------|")
        for col in numeric_cols:
            stats = df[col].describe()
            lines.append(
                f"| {col} | {stats['mean']:.2f} | {stats['std']:.2f} | {stats['min']:.2f} | "
                f"{stats['25%']:.2f} | {stats['50%']:.2f} | {stats['75%']:.2f} | {stats['max']:.2f} |"
            )
        lines.append("")

    if text_cols:
        lines.append("## 文本列概况")
        lines.append("")
        for col in text_cols:
            unique = int(df[col].nunique())
            missing = int(df[col].isnull().sum())
            lines.append(f"- **{col}**: {unique} 个唯一值, 缺失 {missing} 条")

    return "\n".join(lines)


def detect_outliers_iqr(df: pd.DataFrame, column: str) -> dict:
    q1 = df[column].quantile(0.25)
    q3 = df[column].quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    outliers = df[(df[column] < lower) | (df[column] > upper)]
    return {
        "q1": float(q1), "q3": float(q3), "iqr": float(iqr),
        "lower": float(lower), "upper": float(upper),
        "count": int(len(outliers)),
        "rate": round(len(outliers) / len(df), 4) if len(df) > 0 else 0.0,
    }
```

- [ ] **Step 2: Write tests/test_profiler.py**

```python
import pandas as pd
from app.services.profiler import generate_profile, detect_outliers_iqr


def test_generate_profile():
    df = pd.DataFrame({
        "name": ["a", "b", "a", "c"],
        "score": [10, 20, 30, 100],
    })
    report = generate_profile(df)
    assert "## 数据质量报告" in report
    assert "4" in report  # row count
    assert "score" in report
    assert "name" in report


def test_detect_outliers_iqr():
    df = pd.DataFrame({"val": [1, 2, 3, 4, 5, 100]})
    result = detect_outliers_iqr(df, "val")
    assert result["count"] == 1  # 100 is outlier
    assert result["rate"] > 0
```

Run: `pytest tests/test_profiler.py -v`
Expected: 2 PASS

- [ ] **Step 3: Commit**

```bash
cd /d/claude/ai-data-analyst && git add -A && git commit -m "feat: add Data Profiler with report generation and IQR outlier detection"
```

---

### Task 7: File Upload API

**Files:**
- Create: `D:\claude\ai-data-analyst\app\api\files.py`
- Modify: `D:\claude\ai-data-analyst\app\main.py` — register router

- [ ] **Step 1: Write app/api/files.py**

```python
import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.parser import parse_file, extract_columns_info
from app.services.profiler import generate_profile
from app.config import settings
from app.db.database import SessionLocal
from app.db.models import FileModel
from app.models.file import FileDetail, FileListItem, FilePreview, ColumnInfo
import pandas as pd

router = APIRouter(prefix="/api/v1/files", tags=["files"])


@router.post("/upload", response_model=FileDetail)
async def upload_file(file: UploadFile = File(...)):
    ext = file.filename.split(".")[-1].lower() if "." in file.filename else ""
    if ext not in ("csv", "xlsx", "xls"):
        raise HTTPException(400, f"不支持的文件格式: .{ext}")

    file_id = str(uuid.uuid4())
    filepath = f"{settings.upload_dir}/{file_id}.{ext}"

    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)

    df = parse_file(filepath)
    columns_info = extract_columns_info(df)
    profile = generate_profile(df)

    db = SessionLocal()
    record = FileModel(
        id=file_id, filename=file.filename, filepath=filepath,
        file_type=ext, row_count=len(df), col_count=len(df.columns),
        columns_info=columns_info, profile_report=profile,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    columns = [ColumnInfo(**c) for c in columns_info]

    result = FileDetail(
        id=record.id, filename=record.filename, file_type=record.file_type,
        row_count=record.row_count, col_count=record.col_count,
        columns=columns, profile_report=record.profile_report,
    )
    db.close()
    return result


@router.get("", response_model=list[FileListItem])
def list_files():
    db = SessionLocal()
    records = db.query(FileModel).order_by(FileModel.uploaded_at.desc()).all()
    result = [
        FileListItem(
            id=r.id, filename=r.filename, file_type=r.file_type,
            row_count=r.row_count, col_count=r.col_count,
            uploaded_at=r.uploaded_at.isoformat() if r.uploaded_at else "",
        )
        for r in records
    ]
    db.close()
    return result


@router.get("/{file_id}", response_model=FileDetail)
def get_file(file_id: str):
    db = SessionLocal()
    record = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not record:
        db.close()
        raise HTTPException(404, "文件不存在")
    columns = [ColumnInfo(**c) for c in (record.columns_info or [])]
    result = FileDetail(
        id=record.id, filename=record.filename, file_type=record.file_type,
        row_count=record.row_count, col_count=record.col_count,
        columns=columns, profile_report=record.profile_report or "",
    )
    db.close()
    return result


@router.get("/{file_id}/preview", response_model=FilePreview)
def preview_file(file_id: str, rows: int = 20):
    db = SessionLocal()
    record = db.query(FileModel).filter(FileModel.id == file_id).first()
    db.close()
    if not record:
        raise HTTPException(404, "文件不存在")

    df = parse_file(record.filepath)
    preview_df = df.head(rows)
    return FilePreview(
        columns=list(df.columns),
        rows=preview_df.fillna("").values.tolist(),
        total_rows=len(df),
    )
```

- [ ] **Step 2: Register router in main.py**

Edit `app/main.py`, after `app = FastAPI(...)`:

```python
from app.api.files import router as files_router
app.include_router(files_router)
```

- [ ] **Step 3: Test the upload endpoint**

First restart server, then:

```bash
# Create a test CSV
echo "name,age,score
Alice,25,85
Bob,30,92
Charlie,28,78" > /tmp/test.csv

# Upload
curl -X POST http://127.0.0.1:8000/api/v1/files/upload -F "file=@/tmp/test.csv"
```

Expected: JSON with id, filename, row_count=3, col_count=3, columns array, profile_report markdown

- [ ] **Step 4: Test list and preview**

```bash
curl http://127.0.0.1:8000/api/v1/files
# Replace {id} with the actual file id
curl http://127.0.0.1:8000/api/v1/files/{id}
curl http://127.0.0.1:8000/api/v1/files/{id}/preview?rows=2
```

Expected: List returns array, detail returns full info, preview returns first 2 rows

- [ ] **Step 5: Commit**

```bash
cd /d/claude/ai-data-analyst && git add -A && git commit -m "feat: add file upload API with parse, profile, list, detail, and preview endpoints"
```

---

### Task 8: Analysis Tools — Statistics + Aggregation + Analysis

**Files:**
- Create: `D:\claude\ai-data-analyst\app\services\tools\statistics.py`
- Create: `D:\claude\ai-data-analyst\app\services\tools\aggregation.py`
- Create: `D:\claude\ai-data-analyst\app\services\tools\analysis.py`
- Modify: `D:\claude\ai-data-analyst\app\services\tools\__init__.py`
- Create: `D:\claude\ai-data-analyst\tests\test_tools.py`

- [ ] **Step 1: Write app/services/tools/statistics.py**

```python
from langchain.tools import tool
import pandas as pd


_df_cache: dict[str, pd.DataFrame] = {}


def set_df(file_id: str, df: pd.DataFrame):
    _df_cache[file_id] = df


def get_df(file_id: str) -> pd.DataFrame:
    if file_id not in _df_cache:
        raise ValueError(f"文件 {file_id} 未加载，请先上传文件")
    return _df_cache[file_id]


@tool
def describe_data(file_id: str) -> str:
    """获取数据的整体统计描述，包括数值列的均值、标准差、分位数等。"""
    df = get_df(file_id)
    return df.describe(include="all").to_string()


@tool
def value_counts(file_id: str, column: str, top_n: int = 10) -> str:
    """统计指定列的值分布，返回出现频率最高的前N个值。"""
    df = get_df(file_id)
    if column not in df.columns:
        return f"列 '{column}' 不存在。可用列: {list(df.columns)}"
    counts = df[column].value_counts().head(top_n)
    return counts.to_string()


@tool
def correlation_analysis(file_id: str) -> str:
    """计算数值列之间的相关系数矩阵，判断变量之间的线性关系强度。"""
    df = get_df(file_id)
    numeric = df.select_dtypes(include=["number"])
    if numeric.shape[1] < 2:
        return "数值列不足2列，无法计算相关系数"
    corr = numeric.corr()
    return corr.to_string()
```

- [ ] **Step 2: Write app/services/tools/aggregation.py**

```python
from langchain.tools import tool
import pandas as pd
from app.services.tools.statistics import get_df


@tool
def group_analysis(file_id: str, group_column: str, agg_column: str, method: str = "mean") -> str:
    """按指定列分组，对另一列进行聚合（mean/sum/count/min/max）。"""
    df = get_df(file_id)
    if group_column not in df.columns:
        return f"分组列 '{group_column}' 不存在。可用列: {list(df.columns)}"
    if agg_column not in df.columns:
        return f"聚合列 '{agg_column}' 不存在。可用列: {list(df.columns)}"

    methods = {"mean": "mean", "sum": "sum", "count": "count", "min": "min", "max": "max"}
    if method not in methods:
        return f"不支持的聚合方式: {method}，支持: {list(methods.keys())}"

    result = df.groupby(group_column)[agg_column].agg(method).sort_values(ascending=False)
    return result.to_string()


@tool
def filter_data(file_id: str, column: str, operator: str, value: str) -> str:
    """按条件筛选数据（operator: eq/gt/lt/ge/le/contains），返回筛选后的行数和前10行。"""
    df = get_df(file_id)
    if column not in df.columns:
        return f"列 '{column}' 不存在。可用列: {list(df.columns)}"

    operators = {
        "eq": lambda c, v: df[c] == v,
        "gt": lambda c, v: pd.to_numeric(df[c], errors="coerce") > float(v),
        "lt": lambda c, v: pd.to_numeric(df[c], errors="coerce") < float(v),
        "ge": lambda c, v: pd.to_numeric(df[c], errors="coerce") >= float(v),
        "le": lambda c, v: pd.to_numeric(df[c], errors="coerce") <= float(v),
        "contains": lambda c, v: df[c].astype(str).str.contains(v, na=False),
    }
    if operator not in operators:
        return f"不支持的运算符: {operator}，支持: {list(operators.keys())}"

    try:
        mask = operators[operator](column, value)
        filtered = df[mask]
        return f"筛选结果: {len(filtered)} 行 (共 {len(df)} 行)\n\n{filtered.head(10).to_string()}"
    except Exception as e:
        return f"筛选失败: {str(e)}"


@tool
def sort_data(file_id: str, column: str, order: str = "desc", top_n: int = 10) -> str:
    """按指定列排序，返回前N行。order: asc/desc。"""
    df = get_df(file_id)
    if column not in df.columns:
        return f"列 '{column}' 不存在。可用列: {list(df.columns)}"

    ascending = order.lower() == "asc"
    sorted_df = df.sort_values(column, ascending=ascending).head(top_n)
    return sorted_df.to_string()
```

- [ ] **Step 3: Write app/services/tools/analysis.py**

```python
from langchain.tools import tool
import pandas as pd
from app.services.tools.statistics import get_df


@tool
def trend_analysis(file_id: str, column: str, date_column: str | None = None) -> str:
    """分析指定列的数值趋势。如果有日期列，按日期排序后分析；否则按行序分析。"""
    df = get_df(file_id)
    if column not in df.columns:
        return f"列 '{column}' 不存在。可用列: {list(df.columns)}"

    if not pd.api.types.is_numeric_dtype(df[column]):
        return f"列 '{column}' 不是数值类型，无法分析趋势"

    if date_column and date_column in df.columns:
        df = df.copy()
        df[date_column] = pd.to_datetime(df[date_column], errors="coerce")
        df = df.sort_values(date_column)

    values = df[column].dropna().values
    if len(values) < 3:
        return f"'{column}' 有效数据不足（{len(values)}个值），至少需要3个数据点"

    n = len(values)
    half = n // 2
    first_half_mean = values[:half].mean()
    second_half_mean = values[half:].mean()
    change = ((second_half_mean - first_half_mean) / first_half_mean * 100) if first_half_mean != 0 else 0

    direction = "上升" if change > 0 else "下降"
    return (
        f"## '{column}' 趋势分析\n\n"
        f"- 前半段均值: {first_half_mean:.2f}\n"
        f"- 后半段均值: {second_half_mean:.2f}\n"
        f"- 变化: {change:+.1f}% ({direction}趋势)\n"
        f"- 整体均值: {values.mean():.2f}\n"
        f"- 整体标准差: {values.std():.2f}"
    )


@tool
def detect_outliers(file_id: str, column: str) -> str:
    """使用IQR方法检测指定列的异常值。"""
    df = get_df(file_id)
    if column not in df.columns:
        return f"列 '{column}' 不存在。可用列: {list(df.columns)}"

    if not pd.api.types.is_numeric_dtype(df[column]):
        return f"列 '{column}' 不是数值类型，无法检测异常值"

    q1 = df[column].quantile(0.25)
    q3 = df[column].quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    outliers = df[(df[column] < lower) | (df[column] > upper)]

    lines = [
        f"## '{column}' 异常值检测 (IQR)\n",
        f"- Q1: {q1:.2f}, Q3: {q3:.2f}, IQR: {iqr:.2f}",
        f"- 正常范围: [{lower:.2f}, {upper:.2f}]",
        f"- 异常值: {len(outliers)} 个 ({len(outliers)/len(df)*100:.1f}%)",
    ]
    if len(outliers) > 0:
        lines.append(f"\n异常数据:\n{outliers.head(10).to_string()}")
    return "\n".join(lines)


@tool
def data_summary(file_id: str) -> str:
    """生成数据的综合摘要，包括行列数、缺失值、重复值、各列基本信息。"""
    df = get_df(file_id)
    lines = [
        f"## 数据摘要\n",
        f"- 行数: {len(df)}",
        f"- 列数: {len(df.columns)}",
        f"- 缺失值总计: {int(df.isnull().sum().sum())}",
        f"- 重复行: {int(df.duplicated().sum())}",
        f"\n### 各列信息\n",
    ]
    for col in df.columns:
        dtype = str(df[col].dtype)
        nulls = int(df[col].isnull().sum())
        uniques = int(df[col].nunique())
        sample = df[col].dropna().head(3).tolist()
        lines.append(f"- **{col}** ({dtype}): {nulls} 缺失, {uniques} 唯一值, 样例: {sample}")
    return "\n".join(lines)
```

- [ ] **Step 4: Write app/services/tools/__init__.py**

```python
from app.services.tools.statistics import describe_data, value_counts, correlation_analysis
from app.services.tools.aggregation import group_analysis, filter_data, sort_data
from app.services.tools.analysis import trend_analysis, detect_outliers, data_summary

ANALYSIS_TOOLS = [
    describe_data,
    value_counts,
    correlation_analysis,
    group_analysis,
    filter_data,
    sort_data,
    trend_analysis,
    detect_outliers,
    data_summary,
]
```

- [ ] **Step 5: Write basic test in tests/test_tools.py**

```python
import pandas as pd
from app.services.tools.statistics import set_df, get_df, describe_data, value_counts
from app.services.tools.aggregation import group_analysis, filter_data
from app.services.tools.analysis import trend_analysis, data_summary, detect_outliers


@pytest.fixture
def sample_df():
    df = pd.DataFrame({
        "product": ["A", "B", "A", "C", "B"],
        "sales": [100, 200, 150, 300, 250],
        "date": ["2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01", "2024-05-01"],
    })
    set_df("test_file", df)
    return df


def test_describe_data(sample_df):
    result = describe_data.invoke({"file_id": "test_file"})
    assert "sales" in result


def test_value_counts(sample_df):
    result = value_counts.invoke({"file_id": "test_file", "column": "product"})
    assert "A" in result
    assert "B" in result


def test_group_analysis(sample_df):
    result = group_analysis.invoke({"file_id": "test_file", "group_column": "product", "agg_column": "sales", "method": "sum"})
    assert "250" in result or "300" in result


def test_filter_data(sample_df):
    result = filter_data.invoke({"file_id": "test_file", "column": "sales", "operator": "gt", "value": "150"})
    assert "3" in result or "2" in result  # filtered row count


def test_trend_analysis(sample_df):
    result = trend_analysis.invoke({"file_id": "test_file", "column": "sales"})
    assert "趋势分析" in result


def test_data_summary(sample_df):
    result = data_summary.invoke({"file_id": "test_file"})
    assert "product" in result
```

Run: `pytest tests/test_tools.py -v`
Expected: 6 PASS

- [ ] **Step 6: Commit**

```bash
cd /d/claude/ai-data-analyst && git add -A && git commit -m "feat: add 9 analysis tools (describe, value_counts, correlation, group, filter, sort, trend, outliers, summary)"
```

---

### Task 9: Chart Engine + Visualization Tools

**Files:**
- Create: `D:\claude\ai-data-analyst\app\services\chart_engine.py`
- Create: `D:\claude\ai-data-analyst\app\services\tools\visualization.py`
- Modify: `D:\claude\ai-data-analyst\app\services\tools\__init__.py`

- [ ] **Step 1: Write app/services/chart_engine.py**

```python
import uuid
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
from app.config import settings


def save_chart(fig: plt.Figure) -> str:
    chart_id = str(uuid.uuid4())
    filepath = f"{settings.chart_dir}/{chart_id}.png"
    fig.savefig(filepath, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return filepath


def draw_bar(df: pd.DataFrame, x: str, y: str, title: str = "") -> str:
    fig, ax = plt.subplots(figsize=(10, 5))
    sns.barplot(data=df, x=x, y=y, ax=ax, color="#7c3aed")
    ax.set_title(title or f"{y} by {x}")
    ax.tick_params(axis="x", rotation=45)
    return save_chart(fig)


def draw_line(df: pd.DataFrame, x: str, y: str, title: str = "") -> str:
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df[x], df[y], marker="o", color="#7c3aed")
    ax.set_title(title or f"{y} over {x}")
    ax.tick_params(axis="x", rotation=45)
    return save_chart(fig)


def draw_pie(df: pd.DataFrame, labels_col: str, values_col: str, title: str = "") -> str:
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.pie(df[values_col], labels=df[labels_col], autopct="%1.1f%%", startangle=90)
    ax.set_title(title or f"Distribution of {values_col}")
    return save_chart(fig)


def draw_scatter(df: pd.DataFrame, x: str, y: str, title: str = "") -> str:
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.scatter(df[x], df[y], alpha=0.6, color="#7c3aed")
    ax.set_xlabel(x)
    ax.set_ylabel(y)
    ax.set_title(title or f"{y} vs {x}")
    return save_chart(fig)


def draw_heatmap(corr_df: pd.DataFrame, title: str = "") -> str:
    fig, ax = plt.subplots(figsize=(10, 8))
    sns.heatmap(corr_df, annot=True, cmap="Purples", ax=ax, fmt=".2f")
    ax.set_title(title or "Correlation Heatmap")
    return save_chart(fig)
```

- [ ] **Step 2: Write app/services/tools/visualization.py**

```python
from langchain.tools import tool
import pandas as pd
from app.services.tools.statistics import get_df
from app.services.chart_engine import draw_bar, draw_line, draw_pie, draw_scatter, draw_heatmap


@tool
def draw_bar_chart(file_id: str, x_column: str, y_column: str, title: str = "") -> str:
    """生成柱状图。x_column为横轴（分类），y_column为纵轴（数值）。"""
    df = get_df(file_id)
    if x_column not in df.columns or y_column not in df.columns:
        return f"列不存在。可用列: {list(df.columns)}"
    agg_df = df.groupby(x_column)[y_column].mean().reset_index().sort_values(y_column, ascending=False)
    filepath = draw_bar(agg_df, x_column, y_column, title)
    return f"图表已生成: {filepath}"


@tool
def draw_line_chart(file_id: str, x_column: str, y_column: str, title: str = "") -> str:
    """生成折线图，适合展示趋势变化。"""
    df = get_df(file_id)
    if x_column not in df.columns or y_column not in df.columns:
        return f"列不存在。可用列: {list(df.columns)}"
    filepath = draw_line(df, x_column, y_column, title)
    return f"图表已生成: {filepath}"


@tool
def draw_pie_chart(file_id: str, labels_column: str, values_column: str, title: str = "") -> str:
    """生成饼图，展示各部分占比。"""
    df = get_df(file_id)
    if labels_column not in df.columns or values_column not in df.columns:
        return f"列不存在。可用列: {list(df.columns)}"
    agg_df = df.groupby(labels_column)[values_column].sum().reset_index()
    filepath = draw_pie(agg_df, labels_column, values_column, title)
    return f"图表已生成: {filepath}"


@tool
def draw_scatter_chart(file_id: str, x_column: str, y_column: str, title: str = "") -> str:
    """生成散点图，展示两个数值变量之间的关系。"""
    df = get_df(file_id)
    if x_column not in df.columns or y_column not in df.columns:
        return f"列不存在。可用列: {list(df.columns)}"
    filepath = draw_scatter(df, x_column, y_column, title)
    return f"图表已生成: {filepath}"


@tool
def draw_heatmap_chart(file_id: str, title: str = "") -> str:
    """生成相关系数热力图，展示所有数值列之间的相关性。"""
    df = get_df(file_id)
    numeric = df.select_dtypes(include=["number"])
    if numeric.shape[1] < 2:
        return "数值列不足2列，无法生成热力图"
    filepath = draw_heatmap(numeric.corr(), title)
    return f"图表已生成: {filepath}"
```

- [ ] **Step 3: Update app/services/tools/__init__.py**

Add visualization tools to the list:

```python
from app.services.tools.visualization import draw_bar_chart, draw_line_chart, draw_pie_chart, draw_scatter_chart, draw_heatmap_chart

ANALYSIS_TOOLS = [
    describe_data, value_counts, correlation_analysis,
    group_analysis, filter_data, sort_data,
    trend_analysis, detect_outliers, data_summary,
    draw_bar_chart, draw_line_chart, draw_pie_chart, draw_scatter_chart, draw_heatmap_chart,
]
```

- [ ] **Step 4: Test chart generation**

```bash
py -c "
import pandas as pd
from app.services.chart_engine import draw_bar, draw_line, draw_pie
from app.services.tools.statistics import set_df
df = pd.DataFrame({'cat': ['A','B','C'], 'val': [10,20,15]})
set_df('test', df)
from app.services.tools.visualization import draw_bar_chart
print(draw_bar_chart.invoke({'file_id': 'test', 'x_column': 'cat', 'y_column': 'val'}))
"
```

Expected: prints `图表已生成: ./storage/charts/{uuid}.png` and a PNG file exists

- [ ] **Step 5: Commit**

```bash
cd /d/claude/ai-data-analyst && git add -A && git commit -m "feat: add chart engine (matplotlib/seaborn) and 5 visualization tools"
```

---

### Task 10: Agent Controller (LangGraph)

**Files:**
- Create: `D:\claude\ai-data-analyst\app\services\agent.py`

- [ ] **Step 1: Write app/services/agent.py**

```python
import json as json_module
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from app.services.llm.factory import get_llm
from app.services.tools import ANALYSIS_TOOLS


TOOLS_BY_NAME = {t.name: t for t in ANALYSIS_TOOLS}
TOOLS_DESC = "\n".join(f"- {t.name}: {t.description}" for t in ANALYSIS_TOOLS)

SYSTEM_PROMPT = """你是一个专业的数据分析助手。你可以使用以下工具分析用户上传的数据：

{TOOLS_DESC}

工作流程：
1. 收到分析请求后，先用 data_summary 了解数据结构
2. 选择合适的工具进行分析
3. 用中文回复分析结果，简洁专业
4. 如果数据质量有问题（缺失值、异常值），主动提醒用户
5. 如果需要画图，选择合适的图表类型

注意：
- 所有工具都需要传入 file_id 参数
- file_id 会在对话开始时提供"""


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    file_id: str


class AgentController:
    def __init__(self):
        self.llm = get_llm()
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(AgentState)

        workflow.add_node("agent", self._agent_node)
        workflow.add_node("tools", self._tool_node)

        workflow.set_entry_point("agent")
        workflow.add_conditional_edges(
            "agent",
            self._should_continue,
            {"tools": "tools", "end": END},
        )
        workflow.add_edge("tools", "agent")

        return workflow.compile()

    async def _agent_node(self, state: AgentState) -> dict:
        messages = state["messages"]
        file_id = state.get("file_id", "")

        system_content = SYSTEM_PROMPT.format(TOOLS_DESC=TOOLS_DESC)
        if file_id:
            system_content += f"\n\n当前数据文件的 file_id 是: {file_id}"

        formatted = [{"role": "system", "content": system_content}]

        for msg in messages:
            if isinstance(msg, HumanMessage):
                formatted.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                content = msg.content or ""
                tool_calls = []
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        args = tc.get("args", {})
                        if isinstance(args, str):
                            try:
                                args = json_module.loads(args)
                            except (json_module.JSONDecodeError, TypeError):
                                args = {}
                        tool_calls.append({
                            "id": tc.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json_module.dumps(args, ensure_ascii=False),
                            },
                        })
                formatted.append(
                    {"role": "assistant", "content": content, "tool_calls": tool_calls}
                    if tool_calls
                    else {"role": "assistant", "content": content}
                )
            elif isinstance(msg, ToolMessage):
                formatted.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id,
                    "content": msg.content,
                })

        tools_schema = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            k: {"type": "string", "description": v.description or ""}
                            for k, v in t.args_schema.model_fields.items()
                        } if hasattr(t, "args_schema") and t.args_schema else {},
                        "required": [],
                    },
                },
            }
            for t in ANALYSIS_TOOLS
        ]

        result = await self.llm.chat(formatted, tools=tools_schema)

        ai_message = AIMessage(content=result["content"])
        if result.get("tool_calls"):
            ai_message.tool_calls = result["tool_calls"]

        return {"messages": [ai_message]}

    async def _tool_node(self, state: AgentState) -> dict:
        last_msg = state["messages"][-1]
        results = []
        for tc in last_msg.tool_calls:
            tool = TOOLS_BY_NAME.get(tc["name"])
            if tool:
                try:
                    result = tool.invoke(tc["args"])
                except Exception as e:
                    result = f"工具执行错误: {str(e)}"
                results.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
        return {"messages": results}

    def _should_continue(self, state: AgentState) -> str:
        last_msg = state["messages"][-1]
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            return "tools"
        return "end"

    async def run(self, file_id: str, user_input: str, chat_history: list | None = None) -> str:
        messages = []
        if chat_history:
            messages = list(chat_history)
        messages.append(HumanMessage(content=user_input))

        initial = {"messages": messages, "file_id": file_id}
        result = await self.graph.ainvoke(initial)
        last_msg = result["messages"][-1]
        return last_msg.content

    async def run_stream(self, file_id: str, user_input: str):
        """Yield (event_type, content) tuples: ('thinking', '...'), ('tool', '...'), ('text', '...'), ('done', '')"""
        messages = [HumanMessage(content=user_input)]
        initial = {"messages": messages, "file_id": file_id}

        last_message_count = 0
        async for event in self.graph.astream(initial, stream_mode="values"):
            msgs = event.get("messages", [])
            new_msgs = msgs[last_message_count:]
            last_message_count = len(msgs)

            for msg in new_msgs:
                if isinstance(msg, AIMessage):
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        yield ("tool", json_module.dumps(msg.tool_calls, ensure_ascii=False))
                    if msg.content:
                        yield ("text", msg.content)
                elif isinstance(msg, ToolMessage):
                    yield ("tool_result", msg.content)

        yield ("done", "")
```

- [ ] **Step 2: Test Agent manually**

Restart server, then via Python REPL or write a quick script:

```bash
cd /d/claude/ai-data-analyst
py -c "
import asyncio
import pandas as pd
from app.services.agent import AgentController
from app.services.tools.statistics import set_df

df = pd.DataFrame({'product': ['A','B','A','C'], 'sales': [100,200,150,300]})
set_df('test_file', df)

async def main():
    agent = AgentController()
    reply = await agent.run('test_file', '这个数据里哪个产品卖得最好？')
    print(reply)

asyncio.run(main())
"
```

Expected: AI responds in Chinese identifying product B/C as the best seller based on the data.

- [ ] **Step 3: Commit**

```bash
cd /d/claude/ai-data-analyst && git add -A && git commit -m "feat: add Agent Controller with LangGraph and 14-tool Tool Calling"
```

---

### Task 11: Chat API with SSE

**Files:**
- Create: `D:\claude\ai-data-analyst\app\api\chat.py`
- Modify: `D:\claude\ai-data-analyst\app\main.py`
- Create: `D:\claude\ai-data-analyst\app\db\conversation_store.py`

- [ ] **Step 1: Write app/db/conversation_store.py**

```python
import uuid
import datetime
from app.db.database import SessionLocal
from app.db.models import ConversationModel, MessageModel, ChartModel


def create_conversation(file_id: str, title: str = "新对话") -> ConversationModel:
    db = SessionLocal()
    conv = ConversationModel(id=str(uuid.uuid4()), file_id=file_id, title=title)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    db.close()
    return conv


def save_message(conv_id: str, role: str, content: str, tool_calls: list | None = None, chart_ids: list | None = None) -> MessageModel:
    db = SessionLocal()
    msg = MessageModel(
        id=str(uuid.uuid4()), conv_id=conv_id, role=role,
        content=content, tool_calls=tool_calls, chart_ids=chart_ids or [],
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    db.close()
    return msg


def save_chart(message_id: str, chart_type: str, title: str, filepath: str, config: dict | None = None) -> ChartModel:
    db = SessionLocal()
    chart = ChartModel(
        id=str(uuid.uuid4()), message_id=message_id,
        chart_type=chart_type, title=title, filepath=filepath, config=config or {},
    )
    db.add(chart)
    db.commit()
    db.refresh(chart)
    db.close()
    return chart


def get_conversation(conv_id: str) -> ConversationModel | None:
    db = SessionLocal()
    conv = db.query(ConversationModel).filter(ConversationModel.id == conv_id).first()
    db.close()
    return conv
```

- [ ] **Step 2: Write app/api/chat.py**

```python
import json as json_module
import uuid
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.models.chat import ChatRequest
from app.services.agent import AgentController
from app.services.tools.statistics import set_df, get_df
from app.services.parser import parse_file
from app.db.database import SessionLocal
from app.db.models import FileModel
from app.db.conversation_store import create_conversation, save_message, save_chart

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

agent = AgentController()


@router.post("/stream")
async def chat_stream(req: ChatRequest):
    # Load file into cache
    db = SessionLocal()
    file_record = db.query(FileModel).filter(FileModel.id == req.file_id).first()
    db.close()
    if not file_record:
        async def error_stream():
            yield f"data: {json_module.dumps({'error': '文件不存在'})}\n\n"
        return StreamingResponse(error_stream(), media_type="text/event-stream")

    df = parse_file(file_record.filepath)
    set_df(req.file_id, df)

    # Create or get conversation
    conv_id = req.conversation_id or create_conversation(req.file_id).id

    # Save user message
    save_message(conv_id, "user", req.message)

    async def event_stream():
        collected_text = ""
        tool_calls_log = []
        chart_ids = []

        async for event_type, content in agent.run_stream(req.file_id, req.message):
            if event_type == "tool":
                tool_calls_log.append(content)
                yield f"data: {json_module.dumps({'type': 'tool', 'content': content}, ensure_ascii=False)}\n\n"
            elif event_type == "text":
                collected_text += content
                yield f"data: {json_module.dumps({'type': 'text', 'content': content}, ensure_ascii=False)}\n\n"
            elif event_type == "tool_result":
                # Check if result contains chart paths
                if "图表已生成:" in content:
                    for line in content.split("\n"):
                        if "图表已生成:" in line:
                            chart_path = line.split("图表已生成:")[-1].strip()
                            chart_id = str(uuid.uuid4())
                            import os
                            chart_name = os.path.basename(chart_path)
                            save_chart(str(uuid.uuid4()), "auto", chart_name, chart_path)
                            chart_ids.append(chart_path)

        yield f"data: {json_module.dumps({'type': 'done', 'conversation_id': conv_id}, ensure_ascii=False)}\n\n"

        # Save assistant message
        save_message(
            conv_id, "assistant", collected_text,
            tool_calls=tool_calls_log if tool_calls_log else None,
            chart_ids=chart_ids if chart_ids else None,
        )

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

- [ ] **Step 3: Register router in app/main.py**

Add after existing router registration:

```python
from app.api.chat import router as chat_router
app.include_router(chat_router)
```

- [ ] **Step 4: Test SSE streaming**

```bash
# First upload a file and get its ID
FILE_ID=$(curl -s -X POST http://127.0.0.1:8000/api/v1/files/upload -F "file=@/tmp/test.csv" | python -c "import sys,json; print(json.load(sys.stdin)['id'])")

# Test chat
curl -N -X POST http://127.0.0.1:8000/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d "{\"file_id\": \"$FILE_ID\", \"message\": \"分析这个数据集\"}"
```

Expected: SSE events streaming with text content chunks, ending with `{"type": "done", "conversation_id": "..."}`

- [ ] **Step 5: Commit**

```bash
cd /d/claude/ai-data-analyst && git add -A && git commit -m "feat: add SSE chat API with conversation persistence and Agent streaming"
```

---

### Task 12: Report Generator

**Files:**
- Create: `D:\claude\ai-data-analyst\app\services\report_generator.py`

- [ ] **Step 1: Write app/services/report_generator.py**

```python
from app.services.llm.factory import get_llm
from app.services.parser import parse_file
from app.services.profiler import generate_profile
from app.db.database import SessionLocal
from app.db.models import FileModel, MessageModel


REPORT_PROMPT = """你是一个专业的数据分析师。请根据以下信息生成一份数据分析报告。

## 数据概览
{profile}

## 分析对话历史
{history}

请按以下结构生成报告（Markdown格式）：

# 数据分析报告

## 1. 数据概览
简要描述数据规模、字段

## 2. 关键发现
列出3-5个核心洞察，用数据支撑

## 3. 数据质量
指出缺失值、异常值等质量问题

## 4. 建议
基于分析结果，给出2-3条可行建议
"""


async def generate_report(file_id: str, conversation_id: str | None = None) -> str:
    db = SessionLocal()
    file_record = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not file_record:
        db.close()
        return "文件不存在"

    profile = file_record.profile_report or generate_profile(parse_file(file_record.filepath))

    history = "无对话记录"
    if conversation_id:
        messages = (
            db.query(MessageModel)
            .filter(MessageModel.conv_id == conversation_id)
            .order_by(MessageModel.created_at)
            .all()
        )
        if messages:
            lines = []
            for m in messages:
                role = "用户" if m.role == "user" else "助手"
                content = (m.content or "")[:500]
                lines.append(f"**{role}**: {content}")
            history = "\n\n".join(lines)

    db.close()

    llm = get_llm()
    prompt = REPORT_PROMPT.format(profile=profile, history=history)
    result = await llm.chat([{"role": "user", "content": prompt}])

    return result["content"]
```

- [ ] **Step 2: Commit**

```bash
cd /d/claude/ai-data-analyst && git add -A && git commit -m "feat: add Report Generator using LLM with data profile and chat history"
```

---

### Task 13: Report API + Integration

**Files:**
- Create: `D:\claude\ai-data-analyst\app\api\report.py`
- Modify: `D:\claude\ai-data-analyst\app\main.py`

- [ ] **Step 1: Write app/api/report.py**

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.report_generator import generate_report

router = APIRouter(prefix="/api/v1/report", tags=["report"])


class ReportRequest(BaseModel):
    file_id: str
    conversation_id: str | None = None


@router.post("/generate")
async def generate(req: ReportRequest):
    try:
        report = await generate_report(req.file_id, req.conversation_id)
        return {"report": report}
    except Exception as e:
        raise HTTPException(500, f"生成报告失败: {str(e)}")
```

- [ ] **Step 2: Register in main.py**

```python
from app.api.report import router as report_router
app.include_router(report_router)
```

- [ ] **Step 3: Full integration test**

```bash
# 1. Upload file
FILE_ID=$(curl -s -X POST http://127.0.0.1:8000/api/v1/files/upload -F "file=@/tmp/test.csv" | python -c "import sys,json; print(json.load(sys.stdin)['id'])")

# 2. Chat
curl -N -X POST http://127.0.0.1:8000/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d "{\"file_id\": \"$FILE_ID\", \"message\": \"给我一个数据摘要\"}"

# 3. Generate report
curl -X POST http://127.0.0.1:8000/api/v1/report/generate \
  -H "Content-Type: application/json" \
  -d "{\"file_id\": \"$FILE_ID\"}"

# 4. Check all endpoints
curl http://127.0.0.1:8000/api/v1/files | python -m json.tool
curl http://127.0.0.1:8000/health
```

Expected: All return 200 with correct data

- [ ] **Step 4: Commit**

```bash
cd /d/claude/ai-data-analyst && git add -A && git commit -m "feat: add report API endpoint and complete Phase 1 integration"
```

---

### Task 14: README + Final Polish

**Files:**
- Create: `D:\claude\ai-data-analyst\README.md`
- Create: `D:\claude\ai-data-analyst\start.bat`

- [ ] **Step 1: Write start.bat**

```bat
@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo Checking port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000.*LISTENING"') do (
    echo Port 8000 occupied by PID %%a, killing...
    taskkill /PID %%a /F >nul 2>&1
)

echo Starting AI Data Analyst...
py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
```

- [ ] **Step 2: Write README.md**

Write to `/d/claude/ai-data-analyst/README.md` (based on RAG Notebook README structure, covering install, config, usage, API endpoints, and the 14 analysis tools).

- [ ] **Step 3: Final verification**

```bash
cd /d/claude/ai-data-analyst
pytest tests/ -v
```

Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
cd /d/claude/ai-data-analyst && git add -A && git commit -m "docs: add README and start.bat, complete Phase 1"
```

---

## Phase 1 Complete

End state: A working AI Data Analyst with:
- File upload (CSV/Excel) with automatic profiling
- SSE streaming chat with Agent using 14 tools
- Chart generation (bar, line, pie, scatter, heatmap)
- Conversation persistence (SQLite)
- Report generation from data profile + chat history
- LLM provider abstraction (DeepSeek default, OpenAI placeholder)
- All accessible via Swagger UI (`/docs`)
