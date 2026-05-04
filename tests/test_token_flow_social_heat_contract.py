from gmgn_twitter_intel.collector.gmgn_token_payload import parse_gmgn_token_payload
from gmgn_twitter_intel.retrieval.token_flow_service import TokenFlowService
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from tests.test_sqlite_repositories import make_event
from tests.test_token_rolling_flow import open_runtime, token_event


def test_token_flow_item_uses_social_heat_contract(tmp_path):
    conn, ingest, signals, tokens = open_runtime(tmp_path)
    try:
        now_ms = 1_700_000_123_456
        for index, handle in enumerate(["seed", "amp1", "amp2", "amp3"]):
            ingest.ingest_event(
                token_event(
                    f"event-dog-social-{index}",
                    received_at_ms=now_ms - (index + 1) * 10_000,
                    author_handle=handle,
                    text=f"$DOG 0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416 mcap liquidity breakout {index}",
                ),
                is_watched=index == 0,
            )

        item = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="1h",
            limit=10,
            now_ms=now_ms,
        )[0]
    finally:
        conn.close()

    assert set(item) == {
        "identity",
        "market",
        "flow",
        "social_heat",
        "discussion_quality",
        "propagation",
        "tradeability",
        "timing",
        "opportunity",
        "evidence_total_count",
        "posts_query",
        "timeline_query",
    }
    assert item["social_heat"]["score_version"] == "social_heat_v1"
    assert item["discussion_quality"]["score_version"] == "discussion_quality_v1"
    assert item["propagation"]["score_version"] == "propagation_v1"
    assert item["tradeability"]["score_version"] == "tradeability_v1"
    assert item["timing"]["score_version"] == "timing_v1"
    assert item["opportunity"]["score_version"] == "social_opportunity_v1"
    assert item["opportunity"]["decision"] in {"driver", "watch", "discard"}
    assert item["timeline_query"] == {
        "token_id": item["identity"]["token_id"],
        "chain": "eth",
        "address": item["identity"]["address"],
        "window": "1h",
        "bucket": "1m",
        "scope": "all",
    }


def test_token_flow_timing_flags_price_move_before_social_start(tmp_path):
    conn, ingest, signals, tokens = open_runtime(tmp_path)
    try:
        now_ms = 1_700_000_600_000
        window_start_ms = now_ms - 3_600_000
        evidence = EvidenceRepository(conn)
        for event_id, received_at_ms, price in [
            ("market-start", window_start_ms - 1_000, "1.0"),
            ("market-before-social", window_start_ms + 300_000, "1.35"),
        ]:
            evidence.insert_event(make_event(event_id, received_at_ms=received_at_ms), is_watched=False)
            tokens.upsert_snapshot(
                event_id=event_id,
                snapshot=parse_gmgn_token_payload(
                    {
                        "tt": "ca",
                        "t": {
                            "a": "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416",
                            "c": "eth",
                            "mc": "60490.341996",
                            "p": price,
                            "p1": None,
                            "s": "DOG",
                            "liquidity": "250000",
                            "pool": {"pool_address": "pool-dog"},
                        },
                    }
                ),
                received_at_ms=received_at_ms,
                source_channel="gmgn_openapi_token_info",
            )
        ingest.ingest_event(
            token_event(
                "event-dog-social-start",
                received_at_ms=window_start_ms + 900_000,
                author_handle="seed",
                text="$DOG 0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416 social arrives late",
            ),
            is_watched=True,
        )
        tokens.upsert_snapshot(
            event_id="event-dog-social-start",
            snapshot=parse_gmgn_token_payload(
                {
                    "tt": "ca",
                    "t": {
                        "a": "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416",
                        "c": "eth",
                        "mc": "60490.341996",
                        "p": "1.35",
                        "p1": None,
                        "s": "DOG",
                        "liquidity": "250000",
                        "pool": {"pool_address": "pool-dog"},
                    },
                }
            ),
            received_at_ms=window_start_ms + 900_000,
            source_channel="gmgn_openapi_token_info",
        )

        item = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="1h",
            limit=10,
            now_ms=now_ms,
        )[0]
    finally:
        conn.close()

    assert item["timing"]["status"] == "price_leads_social"
    assert item["timing"]["chase_risk"] is True
    assert item["timing"]["price_change_before_social_pct"] >= 0.3
