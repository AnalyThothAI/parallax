from __future__ import annotations

from typing import Any


class AssetSignalRepository:
    def __init__(self, conn: Any):
        self.conn = conn
