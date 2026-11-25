"""Database engine and session management loaded strictly from environment variables."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
import os
from urllib.parse import quote_plus
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def build_database_url() -> str:
    load_dotenv()
    explicit_url = os.getenv("DATABASE_URL", "").strip()
    if explicit_url:
        return explicit_url

    host = os.getenv("DB_HOST", "localhost").strip()
    port = os.getenv("DB_PORT", "5432").strip()
    db_name = os.getenv("DB_NAME", "zomato_analytics").strip()
    user = os.getenv("DB_USER", "postgres").strip()
    password = os.getenv("DB_PASSWORD", "").strip()

    if not password:
        raise ValueError("DB_PASSWORD (or DATABASE_URL) must be set in environment / .env file.")

    encoded_pwd = quote_plus(password)
    return f"postgresql+psycopg://{user}:{encoded_pwd}@{host}:{port}/{db_name}"


def get_engine(database_url: str | None = None) -> Engine:
    url = database_url or build_database_url()
    return create_engine(url, pool_pre_ping=True, future=True)


def get_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    eng = engine or get_engine()
    return sessionmaker(bind=eng, autoflush=False, autocommit=False, expire_on_commit=False, future=True)


@contextmanager
def session_scope(session_factory: sessionmaker[Session] | None = None) -> Generator[Session, None, None]:
    factory = session_factory or get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
