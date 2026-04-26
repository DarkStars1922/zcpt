from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, inspect, pool
from sqlmodel import SQLModel

from app.core.config import settings
import app.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.database_url)
target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        _ensure_mysql_version_table(connection)
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

        with context.begin_transaction():
            context.run_migrations()


def _ensure_mysql_version_table(connection) -> None:
    if connection.dialect.name not in {"mysql", "mariadb"}:
        return

    connection.exec_driver_sql(
        "CREATE TABLE IF NOT EXISTS alembic_version ("
        "version_num VARCHAR(128) NOT NULL, "
        "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)"
        ")"
    )
    columns = inspect(connection).get_columns("alembic_version")
    version_column = next((column for column in columns if column["name"] == "version_num"), None)
    current_length = getattr(version_column.get("type"), "length", None) if version_column else None
    if current_length is None or current_length < 128:
        connection.exec_driver_sql("ALTER TABLE alembic_version MODIFY version_num VARCHAR(128) NOT NULL")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
