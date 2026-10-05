"""SQLAlchemy engine/session setup. Works with SQLite (default, zero-config,
works fine on Windows) or any DATABASE_URL (Postgres etc.) in production."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """Import every model module so they register on Base.metadata, then create tables.
    Real production deployments should use Alembic migrations (see backend/alembic/)."""
    from app.auth import models as _auth_models  # noqa
    from app.servers import models as _server_models  # noqa
    from app.connections import models as _connection_models  # noqa
    from app.chat import models as _chat_models  # noqa
    from app.memory import models as _memory_models  # noqa
    from app.jobs import models as _job_models  # noqa
    from app.approval import models as _approval_models  # noqa
    from app.audit import models as _audit_models  # noqa
    from app.automations import models as _automation_models  # noqa
    from app.files import models as _file_models  # noqa
    from app.monitoring import models as _monitoring_models  # noqa
    from app.rollback import models as _rollback_models  # noqa

    Base.metadata.create_all(bind=engine)
