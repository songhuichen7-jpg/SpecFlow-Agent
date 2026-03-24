from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from specflow.config import get_settings


def _connect_args(database_url: str) -> dict[str, bool]:
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


@lru_cache(maxsize=4)
def get_engine(database_url: str | None = None) -> Engine:
    settings = get_settings()
    resolved_url = database_url or settings.resolved_database_url
    return create_engine(
        resolved_url,
        echo=settings.debug,
        future=True,
        connect_args=_connect_args(resolved_url),
    )


@lru_cache(maxsize=4)
def get_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_engine(database_url),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )


def create_session(database_url: str | None = None) -> Session:
    return get_session_factory(database_url)()


@contextmanager
def session_scope(
    session_factory: sessionmaker[Session] | None = None,
    database_url: str | None = None,
) -> Iterator[Session]:
    factory = session_factory or get_session_factory(database_url)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_database_cache() -> None:
    get_engine.cache_clear()
    get_session_factory.cache_clear()
