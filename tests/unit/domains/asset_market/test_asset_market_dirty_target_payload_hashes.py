from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from parallax.domains.asset_market.repositories.asset_profile_refresh_target_repository import (
    _payload_hash as asset_profile_refresh_payload_hash,
)
from parallax.domains.asset_market.repositories.token_image_source_dirty_target_repository import (
    TokenImageSourceDirtyTargetRepository,
)
from parallax.domains.asset_market.repositories.token_image_source_dirty_target_repository import (
    _payload_hash as token_image_source_payload_hash,
)
from parallax.domains.asset_market.repositories.token_profile_current_dirty_target_repository import (
    _payload_hash as token_profile_current_payload_hash,
)

DirtyPayloadHasher = Callable[[dict[Any, Any]], str]


@pytest.mark.parametrize(
    "payload_hash",
    [
        asset_profile_refresh_payload_hash,
        token_image_source_payload_hash,
        token_profile_current_payload_hash,
    ],
)
def test_asset_market_dirty_payload_hashes_reject_legacy_non_string_keys(
    payload_hash: DirtyPayloadHasher,
) -> None:
    with pytest.raises(ValueError, match="current payload hash payload has non-string keys"):
        payload_hash({123: "legacy", "target_type": "Asset", "target_id": "asset-1"})


@pytest.mark.parametrize(
    "payload_hash",
    [
        asset_profile_refresh_payload_hash,
        token_image_source_payload_hash,
        token_profile_current_payload_hash,
    ],
)
def test_asset_market_dirty_payload_hashes_ignore_queue_lifecycle_fields(
    payload_hash: DirtyPayloadHasher,
) -> None:
    first = payload_hash(
        {
            "target_type": "Asset",
            "target_id": "asset-1",
            "source_watermark_ms": 123,
            "dirty_reason": "source_changed",
            "priority": 10,
            "due_at_ms": 100,
            "leased_until_ms": 200,
            "lease_owner": "worker-a",
            "attempt_count": 1,
            "last_error": "old",
            "first_dirty_at_ms": 50,
            "updated_at_ms": 300,
        }
    )
    second = payload_hash(
        {
            "target_type": "Asset",
            "target_id": "asset-1",
            "source_watermark_ms": 123,
            "dirty_reason": "source_changed",
            "priority": 90,
            "due_at_ms": 999,
            "leased_until_ms": 888,
            "lease_owner": "worker-b",
            "attempt_count": 3,
            "last_error": "new",
            "first_dirty_at_ms": 51,
            "updated_at_ms": 777,
        }
    )

    assert second == first
    assert first.startswith("sha256:")


def test_token_image_source_dirty_target_rejects_legacy_raw_ref_keys_before_json_safety() -> None:
    conn = _ScriptedConnection()
    repo = TokenImageSourceDirtyTargetRepository(conn)

    with pytest.raises(ValueError, match="current payload hash payload has non-string keys"):
        repo.enqueue_targets(
            [
                {
                    "source_url": "https://gmgn.ai/external-res/token-alpha.png",
                    "source_provider": "gmgn",
                    "source_kind": "logo",
                    "target_type": "Asset",
                    "target_id": "solana:alpha",
                    "raw_ref_json": {123: "legacy"},
                    "source_watermark_ms": 1_700_000_000_000,
                }
            ],
            reason="profile_source_changed",
            now_ms=1_700_000_000_000,
        )

    assert conn.sql == []


class _ScriptedConnection:
    sql: list[str]

    def __init__(self) -> None:
        self.sql = []

    def execute(self, sql: str, params: object | None = None) -> _ScriptedConnection:
        del params
        self.sql.append(str(sql))
        return self

    def commit(self) -> None:
        raise AssertionError("token image source dirty target enqueue should fail before commit")
