from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config


def alembic_config() -> Config:
    root = Path(__file__).resolve().parents[3]
    return Config(str(root / "alembic.ini"))


def upgrade_head(database_url: str | None = None) -> None:
    config = alembic_config()
    if database_url is not None:
        config.attributes["database_url"] = database_url
    command.upgrade(config, "head")
