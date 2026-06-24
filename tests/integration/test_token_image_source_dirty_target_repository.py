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


def test_mark_error_retries_before_attempt_budget_without_terminal_event(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = TokenImageSourceDirtyTargetRepository(conn)
        repo.enqueue_targets([_target_row("Asset", "asset-1")], reason="token_profile_logo_candidate", now_ms=NOW_MS)
        claim = repo.claim_due(now_ms=NOW_MS, limit=1, lease_owner="token_image_mirror", lease_ms=600_000)[0]

        changed = repo.mark_error(
            [claim],
            error="image_fetch_failed",
            retry_ms=30_000,
            max_attempts=2,
            worker_name="token_image_mirror",
            now_ms=NOW_MS + 1,
        )

        row = conn.execute(
            """
            SELECT attempt_count, last_error, due_at_ms, lease_owner, leased_until_ms
            FROM token_image_source_dirty_targets
            """
        ).fetchone()
        terminal_count = conn.execute(
            """
            SELECT count(*) AS count
            FROM worker_queue_terminal_events
            WHERE worker_name = 'token_image_mirror'
              AND source_table = 'token_image_source_dirty_targets'
            """
        ).fetchone()["count"]
    finally:
        conn.close()

    assert changed == 1
    assert row["attempt_count"] == 1
    assert row["last_error"] == "image_fetch_failed"
    assert row["due_at_ms"] == NOW_MS + 30_001
    assert row["lease_owner"] is None
    assert row["leased_until_ms"] is None
    assert terminal_count == 0


def test_mark_error_terminalizes_exhausted_claim_and_deletes_dirty_target(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = TokenImageSourceDirtyTargetRepository(conn)
        repo.enqueue_targets([_target_row("Asset", "asset-1")], reason="token_profile_logo_candidate", now_ms=NOW_MS)
        claim = repo.claim_due(now_ms=NOW_MS, limit=1, lease_owner="token_image_mirror", lease_ms=600_000)[0]

        changed = repo.mark_error(
            [claim],
            error="image_fetch_failed: TLS connect error",
            retry_ms=30_000,
            max_attempts=1,
            worker_name="token_image_mirror",
            now_ms=NOW_MS + 1,
        )

        dirty_count = conn.execute("SELECT count(*) AS count FROM token_image_source_dirty_targets").fetchone()["count"]
        terminal = conn.execute(
            """
            SELECT terminal_id, worker_name, source_table, target_key, final_status, final_reason,
                   final_reason_bucket, attempt_count, payload_hash, source_row_json
            FROM worker_queue_terminal_events
            WHERE worker_name = 'token_image_mirror'
              AND source_table = 'token_image_source_dirty_targets'
            """
        ).fetchone()
        unresolved = repo.unresolved_terminal_by_source_targets(
            [_target_row("Asset", "asset-1")],
            worker_name="token_image_mirror",
        )
    finally:
        conn.close()

    assert changed == 1
    assert dirty_count == 0
    assert terminal is not None
    assert terminal["target_key"] == f"{claim['source_url_hash']}:Asset:asset-1"
    assert terminal["final_status"] == "terminal"
    assert terminal["final_reason"] == "image_mirror_retry_budget_exhausted: image_fetch_failed: TLS connect error"
    assert terminal["final_reason_bucket"] == "retry_budget_exhausted"
    assert terminal["attempt_count"] == 1
    assert terminal["payload_hash"] == claim["payload_hash"]
    assert terminal["source_row_json"]["source_url"] == SOURCE_URL
    assert set(unresolved) == {(claim["source_url_hash"], "Asset", "asset-1")}
    assert unresolved[(claim["source_url_hash"], "Asset", "asset-1")]["terminal_id"] == terminal["terminal_id"]


def _target_row(target_type: str, target_id: str) -> dict[str, object]:
    return {
        "source_url": SOURCE_URL,
        "source_provider": "gmgn_dex_profile",
        "source_kind": "asset_profile.logo_url",
        "target_type": target_type,
        "target_id": target_id,
        "source_watermark_ms": NOW_MS,
        "raw_ref_json": {"source": "test"},
    }
