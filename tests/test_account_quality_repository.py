from gmgn_twitter_intel.storage.account_quality_repository import AccountQualityRepository
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
