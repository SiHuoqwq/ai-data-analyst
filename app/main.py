from fastapi import FastAPI
from app.db.database import init_db
from app.api.files import router as files_router

app = FastAPI(title="AI Data Analyst", version="0.1.0")

app.include_router(files_router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}
