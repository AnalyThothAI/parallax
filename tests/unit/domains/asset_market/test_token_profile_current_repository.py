from __future__ import annotations

from typing import Any

import pytest

from parallax.domains.asset_market.repositories.token_profile_current_repository import (
    TokenProfileCurrentRepository,
)


def test_token_profile_current_upsert_returns_false_when_payload_unchanged() -> None:
    conn = _ScriptedConnection([{"changed": True}, None])
    repo = TokenProfileCurrentRepository(conn)
    row = _profile_row(target_id="sol:abc", computed_at_ms=1_000)

    first = repo.upsert_current(row, commit=True)
    first_payload_hash = conn.params[-1][-1]
    second = repo.upsert_current({**row, "computed_at_ms": 2_000, "updated_at_ms": 2_000}, commit=True)
    second_payload_hash = conn.params[-1][-1]

    sql = conn.sql[-1]
    assert first is True
    assert second is False
    assert first_payload_hash == second_payload_hash
    assert "payload_hash IS DISTINCT FROM excluded.payload_hash" in sql
    assert "RETURNING true AS changed" in sql


def test_token_profile_current_payload_hash_rejects_legacy_source_payload_keys() -> None:
    conn = _ScriptedConnection([{"changed": True}])
    repo = TokenProfileCurrentRepository(conn)
    row = _profile_row(target_id="sol:abc", computed_at_ms=1_000)
    row["source_payload_json"] = {123: "legacy"}

    with pytest.raises(ValueError, match="current payload hash payload has non-string keys"):
        repo.upsert_current(row, commit=True)

    assert conn.sql == []
    assert conn.params == []
    assert conn.commits == 0


def _profile_row(*, target_id: str, computed_at_ms: int) -> dict[str, Any]:
    return {
        "target_type": "chain_token",
        "target_id": target_id,
        "status": "ready",
        "profile_provider": "okx_dex_evidence",
        "source_kind": "asset_identity_evidence",
        "source_ref": "okx-1",
        "symbol": "ABC",
        "name": "ABC Token",
        "logo_url": "/api/token-images/image-okx",
        "logo_image_id": "image-okx",
        "logo_source_provider": "okx_dex_evidence",
        "logo_source_url_hash": "hash-okx",
        "banner_url": None,
        "website_url": "https://example.com",
        "twitter_username": "abc",
        "twitter_url": "https://x.com/abc",
        "telegram_url": None,
        "gmgn_url": "https://gmgn.ai/sol/token/abc",
        "geckoterminal_url": None,
        "description": "Profile",
        "quality_flags_json": [],
        "source_payload_json": {"source": "okx", "rank": 1},
        "observed_at_ms": 900,
        "computed_at_ms": computed_at_ms,
        "updated_at_ms": computed_at_ms,
    }


class _ScriptedConnection:
    def __init__(self, results: list[dict[str, Any] | None]) -> None:
        self.results = list(results)
        self.sql: list[str] = []
        self.params: list[tuple[Any, ...]] = []
        self.commits = 0

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> _ScriptedConnection:
        self.sql.append(str(sql))
        self.params.append(tuple(params or ()))
        return self

    def fetchone(self) -> dict[str, Any] | None:
        if not self.results:
            return None
        return self.results.pop(0)

    def commit(self) -> None:
        self.commits += 1
