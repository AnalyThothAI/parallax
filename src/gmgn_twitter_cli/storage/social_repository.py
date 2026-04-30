from __future__ import annotations

from typing import Any

from .lancedb_client import LanceDbClient


class SocialRepository:
    def __init__(self, client: LanceDbClient):
        self.client = client

    def upsert_window(self, row: dict[str, Any]) -> None:
        self.client.upsert("token_social_windows", key_fields=("window_id",), row=row)

    def get_window(self, window_id: str) -> dict[str, Any] | None:
        return self.client.get_one("token_social_windows", window_id=window_id)
