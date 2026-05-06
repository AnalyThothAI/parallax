from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config


def alembic_config() -> Config:
    root = Path(__file__).resolve().parents[3]
    return Config(str(root / "alembic.ini"))


def upgrade_head() -> None:
    command.upgrade(alembic_config(), "head")
