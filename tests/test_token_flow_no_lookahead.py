from gmgn_twitter_intel.collector.gmgn_token_payload import parse_gmgn_token_payload
from gmgn_twitter_intel.retrieval.token_flow_service import TokenFlowService
from tests.test_sqlite_repositories import make_event
from tests.test_token_rolling_flow import open_runtime, token_event


def test_token_flow_market_block_never_uses_future_snapshot(tmp_path):
    conn, ingest, signals, tokens = open_runtime(tmp_path)
    try:
        now_ms = 1_700_000_600_000
        social_ms = now_ms - 120_000
        ingest.ingest_event(
            token_event(
                "event-dog-social",
                received_at_ms=social_ms,
                author_handle="seed",
                text="$DOG social before future market",
            ),
            is_watched=True,
        )
        tokens.upsert_snapshot(
            event_id="event-dog-social",
            snapshot=parse_gmgn_token_payload(
                {
                    "tt": "ca",
                    "t": {
                        "a": "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416",
                        "c": "eth",
                        "mc": "60490.341996",
                        "p": "1.0",
                        "p1": None,
                        "s": "DOG",
                    },
                }
            ),
            received_at_ms=social_ms,
            source_channel="gmgn_openapi_token_info",
        )
        future_event = make_event("event-dog-future-market", received_at_ms=now_ms + 60_000)
        ingest.evidence.insert_event(future_event, is_watched=False)
        tokens.upsert_snapshot(
            event_id="event-dog-future-market",
            snapshot=parse_gmgn_token_payload(
                {
                    "tt": "ca",
                    "t": {
                        "a": "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416",
                        "c": "eth",
                        "mc": "99999999",
                        "p": "99.0",
                        "p1": None,
                        "s": "DOG",
                    },
                }
            ),
            received_at_ms=now_ms + 60_000,
            source_channel="gmgn_openapi_token_info",
        )

        item = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="5m",
            limit=10,
            now_ms=now_ms,
        )[0]
    finally:
        conn.close()

    assert item["market"]["price"] == 1.0
    assert item["market"]["snapshot_received_at_ms"] == social_ms
    assert item["market"]["lookahead_risk"] is False
    assert item["tradeability"]["hard_risks"] == []
    assert item["score_versions"]["opportunity"] == "social_opportunity_v2"
    assert item["data_health"]["market"] == "fresh"
