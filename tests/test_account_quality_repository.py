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
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'account_profiles'
              AND indexname = 'account_profiles_gmgn_followers_idx'
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
