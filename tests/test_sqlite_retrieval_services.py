from dataclasses import replace

from gmgn_twitter_intel.collector.gmgn_token_payload import parse_gmgn_token_payload
from gmgn_twitter_intel.models import Source
from gmgn_twitter_intel.pipeline.entity_extractor import extract_entities
from gmgn_twitter_intel.pipeline.signal_builder import SignalBuilder
from gmgn_twitter_intel.pipeline.token_identity_resolver import TokenIdentityResolver
from gmgn_twitter_intel.retrieval.account_alert_service import AccountAlertService
from gmgn_twitter_intel.retrieval.search_service import SearchService
from gmgn_twitter_intel.retrieval.token_flow_service import TokenFlowService
from gmgn_twitter_intel.storage.token_repository import TokenRepository
from tests.test_sqlite_repositories import make_event, open_repositories


def seed_event(tmp_path):
    conn, evidence, entity_repo, signal_repo, _ = open_repositories(tmp_path)
    token_repo = TokenRepository(conn)
    snapshot = parse_gmgn_token_payload(
        {
            "tt": "ca",
            "t": {
                "a": "0x6982508145454ce325ddbe47a25d4ec3d2311933",
                "c": "eth",
                "mc": "60490.341996",
                "p": "1.0",
                "s": "PEPE",
            },
        }
    )
    event = replace(
        make_event(text="$PEPE base stablecoin mainnet 0x6982508145454ce325ddbe47a25d4ec3d2311933"),
        source=Source(
            provider="gmgn",
            transport="direct_ws",
            coverage="public_stream",
            channel="twitter_monitor_token",
        ),
        token_snapshot=snapshot,
    )
    evidence.insert_event(event, is_watched=True)
    entities = extract_entities(event.content.text)
    entity_repo.insert_event_entities(event, entities, is_watched=True)
    token_mentions = TokenIdentityResolver(token_repo).resolve_event_mentions(event, entities, commit=True)
    SignalBuilder(signal_repo, token_repo).build_for_event(event, token_mentions, is_watched=True)
    return conn, evidence, entity_repo, signal_repo, token_repo


def test_search_service_uses_exact_entities_and_fts(tmp_path):
    conn, evidence, entity_repo, signal_repo, token_repo = seed_event(tmp_path)
    try:
        service = SearchService(evidence=evidence, signals=signal_repo, tokens=token_repo)
        by_ca = service.search("0x6982508145454ce325ddbe47a25d4ec3d2311933", limit=10)
        by_symbol = service.search("$PEPE", limit=10)
        by_text = service.search("stablecoin", limit=10)
    finally:
        conn.close()

    assert by_ca.items[0]["match_type"] == "token_attribution"
    assert by_symbol.items[0]["match_type"] == "token_attribution"
    assert by_text.items[0]["match_type"] == "fts"


def test_search_service_ca_does_not_fall_back_to_same_symbol_other_ca(tmp_path):
    conn, evidence, entity_repo, signal_repo, _ = open_repositories(tmp_path)
    token_repo = TokenRepository(conn)
    target_ca = "0x6982508145454ce325ddbe47a25d4ec3d2311933"
    other_ca = "0x44b28991b167582f18ba0259e0173176ca125505"
    try:
        for event in [_token_event("event-target-ca", target_ca), _token_event("event-other-ca", other_ca)]:
            evidence.insert_event(event, is_watched=True)
            entities = extract_entities(event.content.text)
            entity_repo.insert_event_entities(event, entities, is_watched=True)
            token_mentions = TokenIdentityResolver(token_repo).resolve_event_mentions(
                event,
                entities,
                commit=True,
            )
            SignalBuilder(signal_repo, token_repo).build_for_event(event, token_mentions, is_watched=True)

        by_ca = SearchService(evidence=evidence, signals=signal_repo, tokens=token_repo).search(target_ca, limit=10)
    finally:
        conn.close()

    assert [item["event"]["event_id"] for item in by_ca.items] == ["event-target-ca"]
    assert {item["match_type"] for item in by_ca.items} == {"token_attribution"}


def test_search_service_exact_symbol_respects_limit_after_combining_sources(tmp_path):
    conn, evidence, entity_repo, signal_repo, _ = open_repositories(tmp_path)
    token_repo = TokenRepository(conn)
    try:
        for index in range(3):
            event = make_event(
                f"event-dog-symbol-{index}",
                text=f"$DOG text-only evidence {index}",
                received_at_ms=1_700_000_000_000 + index,
            )
            evidence.insert_event(event, is_watched=True)
            entities = extract_entities(event.content.text)
            entity_repo.insert_event_entities(event, entities, is_watched=True)
            token_mentions = TokenIdentityResolver(token_repo).resolve_event_mentions(
                event,
                entities,
                commit=True,
            )
            SignalBuilder(signal_repo, token_repo).build_for_event(event, token_mentions, is_watched=True)

        snapshot = parse_gmgn_token_payload(
            {
                "tt": "ca",
                "t": {
                    "a": "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416",
                    "c": "eth",
                    "mc": "60490.341996",
                    "p": "1.0",
                    "s": "DOG",
                },
            }
        )
        for index in range(3):
            event = replace(
                make_event(
                    f"event-dog-token-{index}",
                    text=f"structured token evidence {index}",
                    received_at_ms=1_700_000_001_000 + index,
                ),
                source=Source(
                    provider="gmgn",
                    transport="direct_ws",
                    coverage="public_stream",
                    channel="twitter_monitor_token",
                ),
                token_snapshot=snapshot,
            )
            evidence.insert_event(event, is_watched=True)
            entities = extract_entities(event.content.text)
            entity_repo.insert_event_entities(event, entities, is_watched=True)
            token_mentions = TokenIdentityResolver(token_repo).resolve_event_mentions(
                event,
                entities,
                commit=True,
            )
            SignalBuilder(signal_repo, token_repo).build_for_event(event, token_mentions, is_watched=True)

        results = SearchService(evidence=evidence, signals=signal_repo, tokens=token_repo).search("$DOG", limit=3)
    finally:
        conn.close()

    assert len(results.items) == 3
    assert [item["event"]["event_id"] for item in results.items] == [
        "event-dog-token-2",
        "event-dog-token-1",
        "event-dog-token-0",
    ]


def _token_event(event_id: str, address: str):
    snapshot = parse_gmgn_token_payload(
        {
            "tt": "ca",
            "t": {
                "a": address,
                "c": "eth",
                "mc": "60490.341996",
                "p": "1.0",
                "s": "PEPE",
            },
        }
    )
    return replace(
        make_event(event_id, text=f"$PEPE structured token evidence {address}", received_at_ms=1_700_000_001_000),
        source=Source(
            provider="gmgn",
            transport="direct_ws",
            coverage="public_stream",
            channel="twitter_monitor_token",
        ),
        token_snapshot=snapshot,
    )


def test_unknown_chain_ca_is_alert_evidence_but_not_token_flow(tmp_path):
    conn, evidence, entity_repo, signal_repo, _ = open_repositories(tmp_path)
    token_repo = TokenRepository(conn)
    try:
        event = make_event(text="$PEPE mainnet 0x6982508145454ce325ddbe47a25d4ec3d2311933")
        evidence.insert_event(event, is_watched=True)
        entities = extract_entities(event.content.text)
        entity_repo.insert_event_entities(event, entities, is_watched=True)
        token_mentions = TokenIdentityResolver(token_repo).resolve_event_mentions(event, entities, commit=True)
        SignalBuilder(signal_repo, token_repo).build_for_event(event, token_mentions, is_watched=True)
        latest_ms = conn.execute("SELECT MAX(received_at_ms) AS latest_ms FROM event_token_mentions").fetchone()[
            "latest_ms"
        ]
        token_flow = TokenFlowService(signals=signal_repo, tokens=token_repo).token_flow(
            window="5m",
            limit=10,
            now_ms=int(latest_ms) + 1,
        )
        alerts = AccountAlertService(signal_repo).account_alerts(window="24h", limit=10, handles={"toly"})
    finally:
        conn.close()

    assert token_flow == []
    assert {alert["alert_type"] for alert in alerts} == {"account_token"}
    assert alerts[0]["entity_key"].startswith("token:evm_unknown:")
    assert alerts[0]["token_resolution_status"] == "unresolved_chain_ca"
