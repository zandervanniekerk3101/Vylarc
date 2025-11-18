import os
import sys  # <--- ADDED
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

# --- THIS IS THE FIX ---
# Add the project root to the Python path
sys.path.append(os.getcwd())
# -------------------------

# Load .env file for local migration runs
load_dotenv()

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
from src.app.models import models
target_metadata = models.Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise EnvironmentError("DATABASE_URL environment variable not set")
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
    
    # --- FIX 2: Use config_ini_section ---
    ini_section = config.get_section(config.config_ini_section, {})
    
    # Set DATABASE_URL from environment variable
    db_url = os.environ.get("DATABASE_URL")
    
    if db_url:
        ini_section["sqlalchemy.url"] = db_url
    
    connectable = engine_from_config(
        ini_section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()