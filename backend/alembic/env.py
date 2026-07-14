import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
from app.core.config import settings
from app.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_sync_url() -> str:
    """Return the synchronous (psycopg2) URL for offline migrations."""
    return settings.DATABASE_URL_SYNC


def get_async_url() -> str:
    """
    FIX C8: async_engine_from_config requires an async driver.
    DATABASE_URL uses postgresql+asyncpg://, which is correct.
    The previous code passed DATABASE_URL_SYNC (postgresql+psycopg2://)
    to async_engine_from_config, causing:
        ArgumentError: Could not load backend 'psycopg2'
    at migration time.
    """
    return settings.DATABASE_URL


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (uses sync URL)."""
    url = get_sync_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    # Use the asyncpg URL so async_engine_from_config works correctly.
    configuration["sqlalchemy.url"] = get_async_url()
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
