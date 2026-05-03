from gmgn_twitter_intel.collector.gmgn_token_payload import parse_gmgn_token_payload
from gmgn_twitter_intel.market.gmgn_openapi_client import GmgnTokenInfo
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.storage.sqlite_client import connect_sqlite
from gmgn_twitter_intel.storage.sqlite_schema import migrate
from gmgn_twitter_intel.storage.token_repository import TokenRepository
from tests.test_sqlite_repositories import make_event


def open_token_repo(tmp_path):
    conn = connect_sqlite(tmp_path / "twitter_intel.sqlite3", read_only=False)
    migrate(conn)
    return conn, EvidenceRepository(conn), TokenRepository(conn)


def test_token_repository_persists_identity_alias_and_market_snapshot(tmp_path):
    conn, evidence, repo = open_token_repo(tmp_path)
    try:
        evidence.insert_event(make_event("event-1"), is_watched=True)
        snapshot = parse_gmgn_token_payload(
            {
                "tt": "ca",
                "t": {
                    "a": "0xf3525965a4ad3ca0ac13f4d2f237113691194444",
                    "c": "bsc",
                    "mc": "4304699.6",
                    "p": "0.0043046996",
                    "p1": "0.00065198877",
                    "s": "熊猫头",
                },
            }
        )
        identity = repo.upsert_snapshot(
            event_id="event-1",
            snapshot=snapshot,
            received_at_ms=1_700_000_000_000,
            source_channel="twitter_monitor_token",
            commit=True,
        )
        token = repo.get_token(identity.token_id)
        market = repo.latest_market_snapshot(identity.token_id)
        aliases = repo.aliases_for_symbol("熊猫头")
    finally:
        conn.close()

    assert identity.token_id == "token:bsc:0xf3525965a4aD3ca0AC13f4D2F237113691194444"
    assert identity.identity_status == "resolved_ca"
    assert token["chain"] == "bsc"
    assert token["address"] == "0xf3525965a4aD3ca0AC13f4D2F237113691194444"
    assert token["symbol"] == "熊猫头"
    assert market["price"] == 0.0043046996
    assert market["previous_price"] == 0.00065198877
    assert market["market_cap"] == 4304699.6
    assert aliases == [identity.token_id]


def test_token_repository_marks_symbol_ambiguous_when_aliases_conflict(tmp_path):
    conn, evidence, repo = open_token_repo(tmp_path)
    try:
        for event_id, address in [
            ("event-1", "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416"),
            ("event-2", "0x1111111111111111111111111111111111111111"),
        ]:
            evidence.insert_event(make_event(event_id), is_watched=True)
            snapshot = parse_gmgn_token_payload({"tt": "symbol", "t": {"a": address, "c": "eth", "s": "DOG"}})
            repo.upsert_snapshot(
                event_id=event_id,
                snapshot=snapshot,
                received_at_ms=1_700_000_000_000,
                source_channel="twitter_monitor_token",
                commit=True,
            )

        resolved = repo.resolve_symbol("DOG")
    finally:
        conn.close()

    assert resolved.identity_status == "ambiguous_symbol"
    assert resolved.token_id is None
    assert len(resolved.candidate_token_ids) == 2


def test_token_repository_persists_openapi_token_info_market_snapshot(tmp_path):
    conn, evidence, repo = open_token_repo(tmp_path)
    try:
        evidence.insert_event(make_event("event-1"), is_watched=True)
        identity = repo.upsert_openapi_token_info(
            event_id="event-1",
            info=GmgnTokenInfo(
                chain="base",
                address="0x4200000000000000000000000000000000000006",
                symbol="WETH",
                name="Wrapped Ether",
                icon_url="https://example.test/weth.png",
                price=3200.0,
                previous_price=None,
                market_cap=320000000.0,
                raw={"address": "0x4200000000000000000000000000000000000006", "symbol": "WETH"},
            ),
            received_at_ms=1_700_000_000_000,
            source_channel="gmgn_openapi_token_info",
            commit=True,
        )
        token = repo.get_token(identity.token_id)
        market = repo.latest_market_snapshot(identity.token_id)
        aliases = repo.aliases_for_symbol("WETH")
    finally:
        conn.close()

    assert identity.token_id == "token:base:0x4200000000000000000000000000000000000006"
    assert token["symbol"] == "WETH"
    assert token["name"] == "Wrapped Ether"
    assert market["price"] == 3200.0
    assert market["market_cap"] == 320000000.0
    assert market["source_channel"] == "gmgn_openapi_token_info"
    assert aliases == [identity.token_id]


def test_token_repository_canonicalizes_openapi_evm_address_with_existing_token(tmp_path):
    conn, evidence, repo = open_token_repo(tmp_path)
    try:
        evidence.insert_event(make_event("event-payload"), is_watched=True)
        evidence.insert_event(make_event("event-openapi"), is_watched=True)
        snapshot = parse_gmgn_token_payload(
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
        )
        payload_identity = repo.upsert_snapshot(
            event_id="event-payload",
            snapshot=snapshot,
            received_at_ms=1_700_000_000_000,
            source_channel="twitter_monitor_token",
            commit=True,
        )
        openapi_identity = repo.upsert_openapi_token_info(
            event_id="event-openapi",
            info=GmgnTokenInfo(
                chain="eth",
                address="0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416",
                symbol="DOG",
                name="Dog",
                icon_url=None,
                price=1.1,
                previous_price=None,
                market_cap=70000.0,
                raw={"address": "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416", "symbol": "DOG"},
            ),
            received_at_ms=1_700_000_060_000,
            source_channel="gmgn_openapi_token_info",
            commit=True,
        )
        token_count = conn.execute("SELECT COUNT(*) FROM tokens").fetchone()[0]
        market_count = conn.execute(
            "SELECT COUNT(*) FROM token_market_snapshots WHERE token_id = ?",
            (payload_identity.token_id,),
        ).fetchone()[0]
    finally:
        conn.close()

    assert openapi_identity.token_id == payload_identity.token_id
    assert openapi_identity.address == payload_identity.address
    assert token_count == 1
    assert market_count == 2
