from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings


def _create_engine(database_url: str):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    db_engine = create_engine(database_url, connect_args=connect_args)

    if database_url.startswith("sqlite"):
        @event.listens_for(db_engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return db_engine


engine = _create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db():
    from app.db.models import ChartModel, ConversationModel, FileModel, MessageModel

    Base.metadata.create_all(
        bind=engine,
        tables=[
            FileModel.__table__,
            ConversationModel.__table__,
            MessageModel.__table__,
            ChartModel.__table__,
        ],
    )


def configure_database(database_url: str):
    """Rebind the shared session factory, primarily for isolated integration tests."""
    global engine
    previous_engine = engine
    engine = _create_engine(database_url)
    SessionLocal.configure(bind=engine)
    previous_engine.dispose()
