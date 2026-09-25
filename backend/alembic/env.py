from logging.config import fileConfig
import os
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

from family_finance_hub.database import Base
from family_finance_hub import models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata

database_url = os.environ.get("FAMILY_FINANCE_HUB_DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
else:
    database_url = config.get_main_option("sqlalchemy.url")
    if database_url.startswith("sqlite:///../"):
        db_path = (Path(config.config_file_name).parent.parent / database_url.removeprefix("sqlite:///../")).resolve()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
