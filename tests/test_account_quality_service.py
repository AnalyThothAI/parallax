from gmgn_twitter_intel.retrieval.account_quality_service import AccountQualityService
from gmgn_twitter_intel.storage.account_quality_repository import AccountQualityRepository
from tests.test_token_rolling_flow import open_runtime, token_event


def test_account_quality_service_backfills_first_token_mentions(tmp_path):
    conn, ingest, signals, _tokens = open_runtime(tmp_path)
    try:
        now_ms = 1_700_000_123_456
        ingest.ingest_event(
            token_event("event-dog-first", received_at_ms=now_ms - 10_000, author_handle="early"),
            is_watched=True,
        )
        ingest.ingest_event(
            token_event("event-dog-repeat", received_at_ms=now_ms - 5_000, author_handle="early"),
            is_watched=True,
        )
        service = AccountQualityService(signals=signals, repository=AccountQualityRepository(conn))
        result = service.backfill_account_token_call_stats(limit=100)
        account = service.account_quality("early")
    finally:
        conn.close()

    assert result["stats_upserted"] == 1
    assert account["profile"]["handle"] == "early"
    assert account["token_call_stats"][0]["mention_count"] == 2
    assert account["token_call_stats"][0]["outcome_status"] == "insufficient_market_history"
