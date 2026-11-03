from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings


def create_database_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    if database_url.startswith("sqlite:///") and ":memory:" not in database_url:
        database_path = database_url.removeprefix("sqlite:///").split("?", maxsplit=1)[0]
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)


def create_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def create_engine_from_settings(settings: Settings) -> Engine:
    return create_database_engine(settings.database_url)

