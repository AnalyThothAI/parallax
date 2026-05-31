from __future__ import annotations

from hashlib import sha256

from parallax.domains.asset_market.repositories.token_image_source_dirty_target_repository import (
    TokenImageSourceDirtyTargetRepository,
)
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate

NOW_MS = 1_779_000_000_000
SOURCE_URL = "https://gmgn.ai/external-res/token-alpha.png"


def test_existing_by_source_targets_returns_only_exact_target_tuples(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = TokenImageSourceDirtyTargetRepository(conn)
        repo.enqueue_targets(
            [
                _target_row("Asset", "asset-1"),
                _target_row("Asset", "asset-2"),
                _target_row("CexToken", "asset-1"),
                _target_row("CexToken", "asset-2"),
            ],
            reason="token_profile_logo_candidate",
            now_ms=NOW_MS,
        )

        rows = repo.existing_by_source_targets(
            [
                _target_row("Asset", "asset-1"),
                _target_row("Asset", "asset-1"),
                _target_row("CexToken", "asset-2"),
            ]
        )
    finally:
        conn.close()

    source_url_hash = sha256(SOURCE_URL.encode("utf-8")).hexdigest()
    assert set(rows) == {
        (source_url_hash, "Asset", "asset-1"),
        (source_url_hash, "CexToken", "asset-2"),
    }
    assert {row["target_type"] for row in rows.values()} == {"Asset", "CexToken"}
    assert {row["target_id"] for row in rows.values()} == {"asset-1", "asset-2"}
    assert len(rows) == 2


def _target_row(target_type: str, target_id: str) -> dict[str, object]:
    return {
        "source_url": SOURCE_URL,
        "source_provider": "gmgn_dex_profile",
        "source_kind": "asset_profile.logo_url",
        "target_type": target_type,
        "target_id": target_id,
        "raw_ref_json": {"source": "test"},
    }
