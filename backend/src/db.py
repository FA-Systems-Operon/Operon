"""Database connection: engine, session factory, model base class, and get_db."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.config import settings


def _psycopg_url(url: str) -> str:
    """Use the psycopg 3 driver for plain postgresql:// URLs.

    SQLAlchemy reads "postgresql://" as the old psycopg2 driver, which we don't
    install. Rewriting it here lets the existing env files keep their URLs.
    """
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


# pool_pre_ping tests each connection before use, so a Postgres restart
# doesn't cause errors on the next request.
engine = create_engine(_psycopg_url(settings.DATABASE_URL), pool_pre_ping=True)

# Each request gets its own Session from this factory (see get_db below).
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Parent class for all models. Base.metadata holds every table definition."""


def get_db() -> Iterator[Session]:
    """FastAPI dependency: open a session for one request and always close it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
