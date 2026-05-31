from __future__ import annotations

from hashlib import sha256
from typing import Any

from parallax.domains.asset_market.repositories.token_image_source_dirty_target_repository import (
    TokenImageSourceDirtyTargetRepository,
)

SOURCE_URL = "https://gmgn.ai/external-res/token-alpha.png"


def test_existing_by_source_targets_loads_exact_dirty_target_keys() -> None:
    source_url_hash = sha256(SOURCE_URL.encode("utf-8")).hexdigest()
    row = {
        "source_url_hash": source_url_hash,
        "source_url": SOURCE_URL,
        "target_type": "asset_profile",
        "target_id": "solana:alpha",
    }
    conn = _ScriptedConnection([[row]])
    repo = TokenImageSourceDirtyTargetRepository(conn)

    result = repo.existing_by_source_targets(
        [
            {
                "source_url": SOURCE_URL,
                "target_type": "asset_profile",
                "target_id": "solana:alpha",
            }
        ]
    )

    assert "JOIN incoming" in conn.sql
    assert conn.params == {
        "source_url_hashes": [source_url_hash],
        "target_types": ["asset_profile"],
        "target_ids": ["solana:alpha"],
    }
    assert result == {(source_url_hash, "asset_profile", "solana:alpha"): row}


class _ScriptedConnection:
    def __init__(self, results: list[Any]) -> None:
        self.results = list(results)
        self.sql = ""
        self.params: Any = None

    def execute(self, sql: str, params: Any | None = None) -> _ScriptedConnection:
        self.sql = str(sql)
        self.params = params
        return self

    def fetchall(self) -> list[Any]:
        return self.results.pop(0)
