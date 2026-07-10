import asyncio
from logging.config import fileConfig

from alembic import context
from app.core.config import get_settings
from app.db.base import Base
from app.models import (
    ApiKey,
    App,
    Attachment,
    AuditLog,
    Bot,
    Event,
    EventOutbox,
    IncomingWebhook,
    Membership,
    Message,
    MessageReaction,
    Room,
    RoomMember,
    RoomReadState,
    User,
    UserContact,
    Workspace,
)
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata
_models = (
    ApiKey,
    App,
    Attachment,
    AuditLog,
    Bot,
    Event,
    EventOutbox,
    IncomingWebhook,
    Membership,
    Message,
    MessageReaction,
    Room,
    RoomMember,
    RoomReadState,
    User,
    UserContact,
    Workspace,
)


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
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


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
