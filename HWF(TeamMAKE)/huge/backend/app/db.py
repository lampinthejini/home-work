from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import ENV


class Base(DeclarativeBase):
    pass


def makeEngine(url: str):
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=10)


engine = makeEngine(ENV.databaseUrl)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def getDb() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
