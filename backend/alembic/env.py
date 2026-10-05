from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.core.database import Base
# Import every model module so autogenerate can see all tables.
from app.auth import models as _m1  # noqa
from app.servers import models as _m2  # noqa
from app.connections import models as _m3  # noqa
from app.chat import models as _m4  # noqa
from app.memory import models as _m5  # noqa
from app.jobs import models as _m6  # noqa
from app.approval import models as _m7  # noqa
from app.audit import models as _m8  # noqa
from app.automations import models as _m9  # noqa
from app.files import models as _m10  # noqa
from app.rollback import models as _m11  # noqa

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
