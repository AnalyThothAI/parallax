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
    event = make_event(text="$PEPE base stablecoin mainnet 0x6982508145454ce325ddbe47a25d4ec3d2311933")
    evidence.insert_event(event, is_watched=True)
    entities = extract_entities(event.content.text)
    entity_repo.insert_event_entities(event, entities, is_watched=True)
    token_mentions = TokenIdentityResolver(token_repo).resolve_event_mentions(event, entities, commit=True)
    SignalBuilder(signal_repo).build_for_event(event, token_mentions, is_watched=True)
    return conn, evidence, entity_repo, signal_repo, token_repo


def test_search_service_uses_exact_entities_and_fts(tmp_path):
    conn, evidence, entity_repo, signal_repo, _ = seed_event(tmp_path)
    try:
        service = SearchService(evidence=evidence, entities=entity_repo, signals=signal_repo)
        by_ca = service.search("0x6982508145454ce325ddbe47a25d4ec3d2311933", limit=10)
        by_symbol = service.search("$PEPE", limit=10)
        by_text = service.search("stablecoin", limit=10)
    finally:
        conn.close()

    assert by_ca.items[0]["match_type"] == "exact_ca"
    assert by_symbol.items[0]["match_type"] == "exact_symbol"
    assert by_text.items[0]["match_type"] == "fts"


def test_search_service_ca_does_not_fall_back_to_same_symbol_other_ca(tmp_path):
    conn, evidence, entity_repo, signal_repo, _ = open_repositories(tmp_path)
    target_ca = "0x6982508145454ce325ddbe47a25d4ec3d2311933"
    other_ca = "0x44b28991b167582f18ba0259e0173176ca125505"
    try:
        for event in [
            make_event("event-target-ca", text=f"$PEPE exact target {target_ca}", received_at_ms=1_700_000_001_000),
            make_event(
                "event-other-ca",
                text=f"$PEPE same symbol different ca {other_ca}",
                received_at_ms=1_700_000_002_000,
            ),
        ]:
            evidence.insert_event(event, is_watched=True)
            entities = extract_entities(event.content.text)
            entity_repo.insert_event_entities(event, entities, is_watched=True)
            token_mentions = TokenIdentityResolver(TokenRepository(conn)).resolve_event_mentions(
                event,
                entities,
                commit=True,
            )
            SignalBuilder(signal_repo).build_for_event(event, token_mentions, is_watched=True)

        by_ca = SearchService(evidence=evidence, entities=entity_repo, signals=signal_repo).search(target_ca, limit=10)
    finally:
        conn.close()

    assert [item["event"]["event_id"] for item in by_ca.items] == ["event-target-ca"]
    assert {item["match_type"] for item in by_ca.items} == {"exact_ca"}


def test_token_flow_and_account_alert_services_return_trader_views(tmp_path):
    conn, _, _, signal_repo, token_repo = seed_event(tmp_path)
    try:
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

    assert token_flow[0]["flow"]["mentions"] == 1
    assert token_flow[0]["signal"]["decision"] == "discard"
    assert token_flow[0]["identity"]["identity_key"].startswith("token:evm_unknown:")
    assert {alert["alert_type"] for alert in alerts} == {"account_token"}
