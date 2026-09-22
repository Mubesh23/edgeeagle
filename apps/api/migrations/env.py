"""Migration-only database access; importing the HTTP app never connects."""

import os

from alembic import context
from sqlalchemy import Connection, create_engine, pool

config = context.config


def migrate(connection: Connection) -> None:
    # Domain metadata arrives with Phase 2; there are no authoritative tables yet.
    context.configure(connection=connection, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(
        url=os.environ["EDGEEAGLE_DATABASE_URL"],
        target_metadata=None,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    supplied_connection = config.attributes.get("connection")
    if isinstance(supplied_connection, Connection):
        migrate(supplied_connection)
    else:
        engine = create_engine(
            os.environ["EDGEEAGLE_DATABASE_URL"],
            poolclass=pool.NullPool,
            connect_args={"connect_timeout": 5},
        )
        try:
            with engine.connect() as connection:
                migrate(connection)
        finally:
            engine.dispose()
