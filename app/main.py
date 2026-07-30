from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.db import database
from app.db.migration_status import (
    DatabaseRevisionStatus,
    inspect_database_revision,
)
from app.api.files import router as files_router
from app.v2.api.errors import (
    V2APIError,
    error_body,
    v2_error_handler,
    validation_error_handler,
)

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

from app.v2.api.routes import router as v2_router
app.include_router(v2_router)

app.add_exception_handler(V2APIError, v2_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)

app.mount("/storage/charts", StaticFiles(directory=settings.chart_dir), name="charts")


def _migration_error(
    status: DatabaseRevisionStatus,
) -> V2APIError:
    return V2APIError(
        503,
        "DATABASE_MIGRATION_REQUIRED",
        "数据库尚未完成版本迁移，请先运行 alembic upgrade head",
        status.public_details(),
        retryable=False,
    )


@app.middleware("http")
async def require_v2_database_revision(request: Request, call_next):
    status = getattr(
        request.app.state,
        "database_revision_status",
        None,
    )
    if (
        request.url.path.startswith("/api/v2")
        and status is not None
        and not status.ready
    ):
        error = _migration_error(status)
        return JSONResponse(
            status_code=error.status_code,
            content=error_body(error),
        )
    return await call_next(request)


@app.on_event("startup")
def on_startup():
    database.init_db()
    app.state.database_revision_status = inspect_database_revision(
        database.engine
    )


@app.get("/health")
def health():
    status = getattr(app.state, "database_revision_status", None)
    if status is not None and not status.ready:
        error = _migration_error(status)
        return JSONResponse(
            status_code=error.status_code,
            content={
                "status": "degraded",
                **error_body(error),
            },
        )
    return {
        "status": "ok",
        "database": {
            "ready": True,
            "revisions": (
                list(status.current_revisions) if status is not None else []
            ),
        },
    }
