from __future__ import annotations

from hashlib import sha256

from gmgn_twitter_intel.app.runtime.repository_session import repositories_for_connection
from gmgn_twitter_intel.domains.asset_market.repositories.token_image_asset_repository import (
    TokenImageAssetRepository,
)
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate

NOW_MS = 1_779_000_000_000
SOURCE_URL = "https://gmgn.ai/external-res/token-alpha.png"
SECOND_SOURCE_URL = "https://bin.bnbstatic.com/static/images/token-beta.webp"


def test_upsert_pending_sources_is_idempotent_and_hashes_source_url(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = TokenImageAssetRepository(conn)

        first_count = repo.upsert_pending_sources(
            [
                _source_row(SOURCE_URL, raw_ref_json={"asset_id": "asset:alpha"}),
                _source_row(SOURCE_URL, raw_ref_json={"asset_id": "asset:alpha-duplicate"}),
            ],
            now_ms=NOW_MS,
        )
        second_count = repo.upsert_pending_sources(
            [_source_row(SOURCE_URL, raw_ref_json={"asset_id": "asset:alpha-updated"})],
            now_ms=NOW_MS + 1,
        )
        rows = conn.execute("SELECT * FROM token_image_assets").fetchall()
    finally:
        conn.close()

    expected_hash = _sha256(SOURCE_URL)
    assert first_count == 1
    assert second_count == 1
    assert len(rows) == 1
    assert rows[0]["image_id"] == expected_hash
    assert rows[0]["source_url_hash"] == expected_hash
    assert rows[0]["source_url"] == SOURCE_URL
    assert rows[0]["status"] == "pending"
    assert rows[0]["source_provider"] == "gmgn_dex_profile"
    assert rows[0]["source_kind"] == "asset_profile.logo_url"
    assert rows[0]["raw_ref_json"] == {"asset_id": "asset:alpha-updated"}
    assert rows[0]["observed_at_ms"] == NOW_MS + 1
    assert rows[0]["next_refresh_at_ms"] == NOW_MS
    assert rows[0]["created_at_ms"] == NOW_MS
    assert rows[0]["updated_at_ms"] == NOW_MS + 1


def test_claim_due_sources_sets_durable_lease_before_returning_rows(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = TokenImageAssetRepository(conn)
        repo.upsert_pending_sources(
            [
                _source_row(SOURCE_URL),
                _source_row(SECOND_SOURCE_URL, source_provider="binance_cex_profile"),
            ],
            now_ms=NOW_MS,
        )
        repo.mark_error(
            SECOND_SOURCE_URL,
            error="429 rate limited",
            now_ms=NOW_MS + 10,
            retry_ms=5_000,
        )

        claim_now_ms = NOW_MS + 6_000
        claimed = repo.claim_due_sources(now_ms=claim_now_ms, limit=10)
        duplicate_claim = repo.claim_due_sources(now_ms=claim_now_ms + 1, limit=10)
        leased_until_ms = conn.execute(
            "SELECT next_refresh_at_ms FROM token_image_assets WHERE source_url = %s",
            (SOURCE_URL,),
        ).fetchone()["next_refresh_at_ms"]
        after_lease = repo.claim_due_sources(now_ms=leased_until_ms, limit=10)
    finally:
        conn.close()

    assert [row["source_url"] for row in claimed] == [SOURCE_URL, SECOND_SOURCE_URL]
    assert [row["status"] for row in claimed] == ["pending", "pending"]
    assert all(row["next_refresh_at_ms"] > claim_now_ms for row in claimed)
    assert duplicate_claim == []
    assert [row["source_url"] for row in after_lease] == [SOURCE_URL, SECOND_SOURCE_URL]


def test_mark_ready_persists_download_metadata_and_public_url(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = TokenImageAssetRepository(conn)
        repo.upsert_pending_sources([_source_row(SOURCE_URL)], now_ms=NOW_MS)

        row = repo.mark_ready(
            SOURCE_URL,
            media_type="image/png",
            file_extension=".png",
            content_sha256="a" * 64,
            byte_size=1234,
            storage_path="aaaaaaaa.png",
            now_ms=NOW_MS + 100,
        )
        stored = conn.execute(
            "SELECT * FROM token_image_assets WHERE source_url = %s",
            (SOURCE_URL,),
        ).fetchone()
    finally:
        conn.close()

    expected_image_id = _sha256(SOURCE_URL)
    assert row["image_id"] == expected_image_id
    assert row["status"] == "ready"
    assert row["media_type"] == "image/png"
    assert row["file_extension"] == ".png"
    assert row["content_sha256"] == "a" * 64
    assert row["byte_size"] == 1234
    assert row["storage_path"] == "aaaaaaaa.png"
    assert row["public_url"] == f"/api/token-images/{expected_image_id}"
    assert row["last_error"] is None
    assert row["failure_count"] == 0
    assert stored == row


def test_mark_error_increments_failure_count_and_schedules_retry(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = TokenImageAssetRepository(conn)
        repo.upsert_pending_sources([_source_row(SOURCE_URL)], now_ms=NOW_MS)

        repo.mark_error(
            SOURCE_URL,
            error="upstream timeout\x00 with nul",
            now_ms=NOW_MS + 200,
            retry_ms=30_000,
        )
        row = conn.execute(
            "SELECT * FROM token_image_assets WHERE source_url = %s",
            (SOURCE_URL,),
        ).fetchone()
    finally:
        conn.close()

    assert row["status"] == "error"
    assert row["failure_count"] == 1
    assert row["last_error"] == "upstream timeout with nul"
    assert row["next_refresh_at_ms"] == NOW_MS + 30_200
    assert row["updated_at_ms"] == NOW_MS + 200


def test_mark_error_does_not_downgrade_ready_row(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = TokenImageAssetRepository(conn)
        repo.upsert_pending_sources([_source_row(SOURCE_URL)], now_ms=NOW_MS)
        ready_row = repo.mark_ready(
            SOURCE_URL,
            media_type="image/png",
            file_extension=".png",
            content_sha256="a" * 64,
            byte_size=1234,
            storage_path="aaaaaaaa.png",
            now_ms=NOW_MS + 100,
        )

        repo.mark_error(
            SOURCE_URL,
            error="late worker failure",
            now_ms=NOW_MS + 200,
            retry_ms=30_000,
        )
        row = conn.execute(
            "SELECT * FROM token_image_assets WHERE source_url = %s",
            (SOURCE_URL,),
        ).fetchone()
    finally:
        conn.close()

    assert row == ready_row


def test_mark_error_does_not_downgrade_unsupported_row(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = TokenImageAssetRepository(conn)
        repo.upsert_pending_sources([_source_row(SOURCE_URL)], now_ms=NOW_MS)
        repo.mark_unsupported(
            SOURCE_URL,
            error="unsupported_image_bytes: unknown_magic",
            now_ms=NOW_MS + 100,
        )
        unsupported_row = conn.execute(
            "SELECT * FROM token_image_assets WHERE source_url = %s",
            (SOURCE_URL,),
        ).fetchone()

        repo.mark_error(
            SOURCE_URL,
            error="late transient failure",
            now_ms=NOW_MS + 200,
            retry_ms=30_000,
        )
        row = conn.execute(
            "SELECT * FROM token_image_assets WHERE source_url = %s",
            (SOURCE_URL,),
        ).fetchone()
    finally:
        conn.close()

    assert row == unsupported_row


def test_mark_unsupported_is_terminal_and_not_claimed(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = TokenImageAssetRepository(conn)
        repo.upsert_pending_sources([_source_row(SOURCE_URL)], now_ms=NOW_MS)

        repo.mark_unsupported(
            SOURCE_URL,
            error="unsupported_image_bytes: media_type_mismatch",
            now_ms=NOW_MS + 200,
        )
        claimed = repo.claim_due_sources(now_ms=NOW_MS + 1_000_000, limit=10)
        row = conn.execute(
            "SELECT * FROM token_image_assets WHERE source_url = %s",
            (SOURCE_URL,),
        ).fetchone()
    finally:
        conn.close()

    assert claimed == []
    assert row["status"] == "unsupported"
    assert row["failure_count"] == 1
    assert row["last_error"] == "unsupported_image_bytes: media_type_mismatch"
    assert row["next_refresh_at_ms"] == NOW_MS + 200
    assert row["updated_at_ms"] == NOW_MS + 200


def test_mark_unsupported_does_not_downgrade_ready_row(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = TokenImageAssetRepository(conn)
        repo.upsert_pending_sources([_source_row(SOURCE_URL)], now_ms=NOW_MS)
        ready_row = repo.mark_ready(
            SOURCE_URL,
            media_type="image/png",
            file_extension=".png",
            content_sha256="a" * 64,
            byte_size=1234,
            storage_path="aaaaaaaa.png",
            now_ms=NOW_MS + 100,
        )

        repo.mark_unsupported(
            SOURCE_URL,
            error="unsupported_image_bytes: late worker result",
            now_ms=NOW_MS + 200,
        )
        row = conn.execute(
            "SELECT * FROM token_image_assets WHERE source_url = %s",
            (SOURCE_URL,),
        ).fetchone()
    finally:
        conn.close()

    assert row == ready_row


def test_upsert_pending_sources_does_not_update_terminal_ready_or_unsupported_rows(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = TokenImageAssetRepository(conn)
        repo.upsert_pending_sources(
            [
                _source_row(SOURCE_URL, raw_ref_json={"asset_id": "asset:ready"}),
                _source_row(SECOND_SOURCE_URL, raw_ref_json={"asset_id": "asset:unsupported"}),
            ],
            now_ms=NOW_MS,
        )
        ready_row = repo.mark_ready(
            SOURCE_URL,
            media_type="image/png",
            file_extension=".png",
            content_sha256="a" * 64,
            byte_size=1234,
            storage_path="aaaaaaaa.png",
            now_ms=NOW_MS + 100,
        )
        repo.mark_unsupported(
            SECOND_SOURCE_URL,
            error="unsupported_image_bytes: unknown_magic",
            now_ms=NOW_MS + 200,
        )
        unsupported_row = conn.execute(
            "SELECT * FROM token_image_assets WHERE source_url = %s",
            (SECOND_SOURCE_URL,),
        ).fetchone()

        count = repo.upsert_pending_sources(
            [
                _source_row(SOURCE_URL, raw_ref_json={"asset_id": "asset:ready-churn"}),
                _source_row(SECOND_SOURCE_URL, raw_ref_json={"asset_id": "asset:unsupported-churn"}),
            ],
            now_ms=NOW_MS + 300,
        )
        rows = conn.execute("SELECT * FROM token_image_assets ORDER BY source_url").fetchall()
    finally:
        conn.close()

    assert count == 0
    assert rows == sorted([ready_row, unsupported_row], key=lambda row: row["source_url"])


def test_ready_lookup_filters_non_ready_sources_and_supports_image_id(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = TokenImageAssetRepository(conn)
        repo.upsert_pending_sources(
            [
                _source_row(SOURCE_URL),
                _source_row(SECOND_SOURCE_URL, source_provider="binance_cex_profile"),
            ],
            now_ms=NOW_MS,
        )
        ready_row = repo.mark_ready(
            SOURCE_URL,
            media_type="image/webp",
            file_extension=".webp",
            content_sha256="b" * 64,
            byte_size=2048,
            storage_path="bbbbbbbb.webp",
            now_ms=NOW_MS + 100,
        )

        by_source = repo.ready_by_source_urls([SECOND_SOURCE_URL, SOURCE_URL, SOURCE_URL])
        by_image = repo.ready_by_image_id(ready_row["image_id"])
        missing_by_image = repo.ready_by_image_id(_sha256(SECOND_SOURCE_URL))
        repos = repositories_for_connection(conn)
    finally:
        conn.close()

    assert by_source == {SOURCE_URL: ready_row}
    assert by_image == ready_row
    assert missing_by_image is None
    assert isinstance(repos.token_image_assets, TokenImageAssetRepository)


def _source_row(
    source_url: str,
    *,
    source_provider: str = "gmgn_dex_profile",
    source_kind: str = "asset_profile.logo_url",
    raw_ref_json: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "source_url": source_url,
        "source_provider": source_provider,
        "source_kind": source_kind,
        "raw_ref_json": raw_ref_json or {"source": "test"},
    }


def _sha256(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()
