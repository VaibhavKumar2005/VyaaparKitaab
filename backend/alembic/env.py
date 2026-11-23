import asyncio
from logging.config import fileConfig

from alembic import context
from app.cores.database import DATABASE_URL, Base, engine_kwargs
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

config = context.config
config.set_main_option("sqlalchemy.url", DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)

    with context.begin_transaction():
        context.execute("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(128) NOT NULL PRIMARY KEY)")
        context.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)")
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_async_engine(DATABASE_URL, **engine_kwargs)

    async def do_run():
        async with connectable.connect() as conn:
            await conn.run_sync(do_run_migrations)
        await connectable.dispose()

    def do_run_migrations(connection):
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            connection.execute(
                text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(128) NOT NULL PRIMARY KEY)")
            )
            connection.execute(text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)"))
            context.run_migrations()

    asyncio.run(do_run())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()