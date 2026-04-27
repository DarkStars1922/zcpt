from collections.abc import Generator

from sqlmodel import SQLModel, Session, create_engine

from app.core.config import settings

Base = SQLModel
engine = None


def _build_engine(database_url: str):
    is_sqlite = database_url.startswith("sqlite")
    connect_args = {"check_same_thread": False} if is_sqlite else {}
    pool_options = {}
    if not is_sqlite:
        pool_options = {
            "pool_size": settings.db_pool_size,
            "max_overflow": settings.db_max_overflow,
            "pool_recycle": settings.db_pool_recycle_seconds,
            "pool_timeout": settings.db_pool_timeout_seconds,
        }
    return create_engine(
        database_url,
        connect_args=connect_args,
        echo=settings.sql_echo,
        pool_pre_ping=True,
        **pool_options,
    )


def configure_engine(database_url: str | None = None):
    global engine
    engine = _build_engine(database_url or settings.database_url)
    return engine


def get_engine():
    global engine
    if engine is None:
        engine = configure_engine()
    return engine


def get_db() -> Generator[Session, None, None]:
    with Session(get_engine()) as db:
        yield db


def create_db_and_tables() -> None:
    Base.metadata.create_all(get_engine())


configure_engine()
