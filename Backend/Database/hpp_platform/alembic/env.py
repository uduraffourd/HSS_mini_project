# alembic/env.py
from __future__ import annotations

from logging.config import fileConfig
import os
import sys
import pathlib

from sqlalchemy import engine_from_config, pool
from alembic import context
from dotenv import load_dotenv

# --- Alembic config object (DOIT être défini avant utilisation) ---
config = context.config

# --- Logging depuis alembic.ini ---
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- Rendre importable "app.*" (chemin du projet) ---
BASE_DIR = pathlib.Path(__file__).resolve().parents[1]  # dossier racine du projet
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

# --- Charger les variables d'env (.env à la racine du projet) ---
load_dotenv()
db_url = os.getenv("DATABASE_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

# --- Importer les modèles pour autogenerate ---
from app.db.models import Base  # noqa: E402

target_metadata = Base.metadata  # <<< IMPORTANT: ne pas écraser plus bas


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()