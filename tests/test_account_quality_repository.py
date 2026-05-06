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
