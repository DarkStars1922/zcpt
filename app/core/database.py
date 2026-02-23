from sqlmodel import SQLModel, Session, create_engine

from app.core.config import settings

Base = SQLModel

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=connect_args)


def get_db():
    with Session(engine) as db:
        yield db
