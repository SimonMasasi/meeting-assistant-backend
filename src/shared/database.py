from sqlmodel import create_engine
from alembic.config import Config
from alembic import command
from config import SETTINGS

engine = create_engine(SETTINGS.DATABASE_URL)


def run_migrations() -> None:
    """Run all pending Alembic migrations on startup."""
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")