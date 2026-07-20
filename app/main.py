from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.db.database import init_db
from app.api.files import router as files_router

app = FastAPI(title="AI Data Analyst", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(files_router)

from app.api.chat import router as chat_router
app.include_router(chat_router)

from app.api.report import router as report_router
app.include_router(report_router)

from app.api.conversations import router as conversations_router
app.include_router(conversations_router)

app.mount("/storage/charts", StaticFiles(directory=settings.chart_dir), name="charts")


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}
