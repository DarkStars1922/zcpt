from collections.abc import Generator

from sqlmodel import SQLModel, Session, create_engine

from app.core.config import settings

Base = SQLModel
engine = None


def _build_engine(database_url: str):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(
        database_url,
        connect_args=connect_args,
        echo=settings.sql_echo,
        pool_pre_ping=True,
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
