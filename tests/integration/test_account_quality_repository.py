from parallax.domains.account_quality.repositories import account_quality_repository as account_quality_module
from parallax.domains.account_quality.repositories.account_quality_repository import AccountQualityRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def test_account_quality_repository_upserts_profiles_stats_and_snapshots(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = AccountQualityRepository(conn)
        repo.upsert_profile(
            handle="toly",
            first_seen_ms=100,
            latest_seen_ms=200,
            follower_max=1000,
            watched_status="watched",
        )
        repo.upsert_profile(
            handle="toly",
            first_seen_ms=50,
            latest_seen_ms=300,
            follower_max=2000,
            watched_status="watched",
        )
        repo.upsert_token_call_stat(
            handle="toly",
            token_id="token:eth:0xdog",
            first_mention_ms=120,
            mention_count=3,
            was_early_author=True,
            outcome_status="insufficient_market_history",
        )
        repo.insert_quality_snapshot(
            handle="toly",
            window="30d",
            precision_score=None,
            early_call_score=72.0,
            spam_risk_score=8.0,
            avg_realized_return=None,
            sample_size=1,
        )
        account = repo.account_quality("toly")
    finally:
        conn.close()

    assert account["profile"]["first_seen_ms"] == 50
    assert account["profile"]["latest_seen_ms"] == 300
    assert account["profile"]["follower_max"] == 2000
    assert account["token_call_stats"][0]["token_id"] == "token:eth:0xdog"
    assert account["token_call_stats"][0]["was_early_author"] == 1
    assert account["quality_snapshots"][0]["sample_size"] == 1


def test_quality_snapshot_identity_is_stable_per_handle_window(tmp_path, monkeypatch):
    now_values = iter([1_700_000_000_000, 1_700_000_060_000])
    monkeypatch.setattr(account_quality_module, "_now_ms", lambda: next(now_values))
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = AccountQualityRepository(conn)

        first_changed = repo.insert_quality_snapshot(
            handle="@Toly",
            window="30d",
            precision_score=40.0,
            early_call_score=72.0,
            spam_risk_score=8.0,
            avg_realized_return=1.5,
            sample_size=1,
        )
        second_changed = repo.insert_quality_snapshot(
            handle="toly",
            window="30d",
            precision_score=55.0,
            early_call_score=80.0,
            spam_risk_score=5.0,
            avg_realized_return=2.5,
            sample_size=3,
        )
        rows = conn.execute(
            """
            SELECT handle, "window", precision_score, early_call_score,
                   spam_risk_score, avg_realized_return, sample_size, updated_at_ms
              FROM account_quality_snapshots
             ORDER BY handle, "window"
            """
        ).fetchall()
    finally:
        conn.close()

    assert first_changed == 1
    assert second_changed == 1
    assert [dict(row) for row in rows] == [
        {
            "handle": "toly",
            "window": "30d",
            "precision_score": 55.0,
            "early_call_score": 80.0,
            "spam_risk_score": 5.0,
            "avg_realized_return": 2.5,
            "sample_size": 3,
            "updated_at_ms": 1_700_000_060_000,
        }
    ]


def test_account_profiles_has_gmgn_directory_columns(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        rows = conn.execute(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'account_profiles'
              AND column_name IN (
                'gmgn_user_id',
                'gmgn_user_tags',
                'gmgn_platform_followers',
                'gmgn_directory_observed_at_ms'
              )
            ORDER BY column_name
            """
        ).fetchall()
        actual = {row["column_name"]: (row["data_type"], row["is_nullable"]) for row in rows}
        index_rows = conn.execute(
            """
            SELECT indexname, indexdef FROM pg_indexes
            WHERE tablename = 'account_profiles'
              AND indexname = 'idx_account_profiles_gmgn_followers'
            """
        ).fetchall()
    finally:
        conn.close()

    assert actual == {
        "gmgn_user_id": ("text", "YES"),
        "gmgn_user_tags": ("ARRAY", "YES"),
        "gmgn_platform_followers": ("bigint", "YES"),
        "gmgn_directory_observed_at_ms": ("bigint", "YES"),
    }
    assert len(index_rows) == 1
    assert "gmgn_platform_followers DESC NULLS LAST" in index_rows[0]["indexdef"]


def test_upsert_directory_entry_inserts_then_updates_directory_fields_only(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = AccountQualityRepository(conn)
        repo.upsert_profile(
            handle="cz",
            first_seen_ms=100,
            latest_seen_ms=200,
            follower_max=1234,
            watched_status="public",
        )
        cz_initial = repo.account_quality("cz")["profile"]
        cz_initial_updated_at = cz_initial["updated_at_ms"]
        cz_initial_created_at = cz_initial["created_at_ms"]
        repo.upsert_directory_entry(
            handle="cz",
            gmgn_user_id="dxCeCLOM7uOFJKX8EnS3Kw",
            user_tags=("binance_square",),
            platform_followers=18548,
            observed_at_ms=1_700_000_000_000,
        )
        repo.upsert_directory_entry(
            handle="elonmusk",
            gmgn_user_id="44196397",
            user_tags=("founder", "kol"),
            platform_followers=29396,
            observed_at_ms=1_700_000_000_001,
        )
        repo.upsert_directory_entry(
            handle="cz",
            gmgn_user_id="dxCeCLOM7uOFJKX8EnS3Kw",
            user_tags=("binance_square", "founder"),
            platform_followers=18999,
            observed_at_ms=1_700_000_000_999,
        )
        cz = repo.account_quality("cz")["profile"]
        elon = repo.account_quality("elonmusk")["profile"]
    finally:
        conn.close()

    assert cz["follower_max"] == 1234
    assert cz["first_seen_ms"] == 100
    assert cz["latest_seen_ms"] == 200
    assert cz["watched_status"] == "public"
    assert cz["gmgn_user_id"] == "dxCeCLOM7uOFJKX8EnS3Kw"
    assert list(cz["gmgn_user_tags"]) == ["binance_square", "founder"]
    assert cz["gmgn_platform_followers"] == 18999
    assert cz["gmgn_directory_observed_at_ms"] == 1_700_000_000_999

    assert elon["gmgn_user_id"] == "44196397"
    assert list(elon["gmgn_user_tags"]) == ["founder", "kol"]
    assert elon["gmgn_platform_followers"] == 29396
    assert elon["follower_max"] is None
    assert elon["watched_status"] == "public"
    assert elon["first_seen_ms"] == 1_700_000_000_001
    assert elon["latest_seen_ms"] == 1_700_000_000_001

    assert cz["updated_at_ms"] >= cz_initial_updated_at  # may be equal if all calls land in same ms
    assert cz["created_at_ms"] == cz_initial_created_at  # never changes after first INSERT
    assert elon["updated_at_ms"] >= elon["created_at_ms"]
