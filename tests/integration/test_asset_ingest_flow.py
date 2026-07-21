from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from parallax.app.runtime.repository_session import repositories_for_connection
from parallax.domains.asset_market.services.event_market_capture import CaptureResult
from parallax.domains.asset_market.types import EnrichedEventCapture, MarketTick, market_tick_id
from parallax.domains.evidence.services.ingest_service import IngestService
from parallax.domains.ingestion.types.gmgn_token_payload import parse_gmgn_token_payload
from tests.factories import make_event
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def open_ingest(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    migrate(conn)
    repos = repositories_for_connection(
        conn,
        notification_delivery_running_timeout_ms=300_000,
        notification_delivery_stale_running_terminalization_batch_size=100,
    )
    ingest = IngestService(
        evidence=repos.evidence,
        entities=repos.entities,
        signals=repos.signals,
        registry=repos.registry,
        identity_evidence=repos.identity_evidence,
        token_evidence=repos.token_evidence,
        token_intents=repos.token_intents,
        intent_resolutions=repos.intent_resolutions,
        discovery=repos.discovery,
        market_ticks=repos.market_ticks,
        market_tick_current_dirty_targets=repos.market_tick_current_dirty_targets,
        enriched_events=repos.enriched_events,
        event_anchor_jobs=repos.event_anchor_jobs,
        token_intent_lookup=repos.token_intent_lookup,
        token_radar_source_dirty_events=repos.token_radar_source_dirty_events,
        event_anchor_active_window_ms=300_000,
    )
    return conn, repos, ingest


def test_ingest_mirror_writes_unresolved_token_intent(tmp_path):
    conn, _, ingest = open_ingest(tmp_path)
    try:
        result = ingest.ingest_event(make_event("event-1", text="$mirror is moving"), is_watched=True)
    finally:
        conn.close()

    assert result.inserted is True
    assert result.token_intents[0]["display_symbol"] == "MIRROR"
    assert result.token_resolutions[0]["resolution_status"] == "NIL"
    assert result.token_resolutions[0]["target_id"] is None


def test_ingest_gmgn_payload_writes_identity_without_market_observation(tmp_path):
    conn, repos, ingest = open_ingest(tmp_path)
    address = "0x6982508145454ce325ddbe47a25d4ec3d2311933"
    try:
        snapshot = parse_gmgn_token_payload(
            {
                "tt": "ca",
                "t": {
                    "a": address,
                    "c": "eth",
                    "s": "PEPE",
                    "mc": "1000000",
                    "p": "0.01",
                },
            }
        )
        event = replace(
            make_event("event-gmgn-payload-no-market", text="$PEPE payload identity"),
            token_snapshot=snapshot,
        )
        result = ingest.ingest_event(event, is_watched=True)
        resolution = next(item for item in result.token_resolutions if item["resolution_status"] == "EXACT")
        asset = repos.registry.find_assets_by_address(chain_id="eth", address=address)[0]
        identity_evidence = repos.identity_evidence.list_identity_evidence(asset["asset_id"])
        enriched_events = repos.enriched_events.list_by_event_id(event.event_id)
        market_tick = repos.market_ticks.latest_at_or_before(
            target_type="chain_token",
            target_id=f"eip155:1:{address}",
            at_ms=event.received_at_ms,
            max_lag_ms=60_000,
        )
    finally:
        conn.close()

    assert resolution["resolution_status"] == "EXACT"
    assert resolution["target_type"] == "Asset"
    assert resolution["target_id"] == f"asset:eip155:1:erc20:{address}"
    assert any(item["evidence_kind"] == "gmgn_payload_exact" for item in identity_evidence)
    assert market_tick is None
    assert enriched_events[0]["target_type"] == "chain_token"
    assert enriched_events[0]["target_id"] == f"eip155:1:{address}"
    assert enriched_events[0]["capture_method"] == "unavailable"


def test_ingest_chain_ca_from_gmgn_url_writes_exact_registry_asset(tmp_path):
    conn, repos, ingest = open_ingest(tmp_path)
    address = "0x44b28991b167582f18ba0259e0173176ca125505"
    try:
        result = ingest.ingest_event(
            make_event("event-upic", text=f"https://gmgn.ai/eth/token/{address}"),
            is_watched=True,
        )
        resolution = result.token_resolutions[0]
        asset = repos.registry.find_assets_by_address(chain_id="eth", address=address)[0]
        identity_evidence = repos.identity_evidence.list_identity_evidence(asset["asset_id"])
    finally:
        conn.close()

    assert resolution["resolution_status"] == "EXACT"
    assert resolution["target_type"] == "Asset"
    assert resolution["target_id"] == f"asset:eip155:1:erc20:{address}"
    assert asset["asset_id"] == resolution["target_id"]
    assert len(identity_evidence) == 1
    assert identity_evidence[0]["evidence_kind"] == "tweet_contract_mention"
    assert identity_evidence[0]["confidence"] == "mention_only"
    assert identity_evidence[0]["source_event_id"] == "event-upic"


def test_ingest_unknown_chain_ca_is_retained_as_unresolved_asset(tmp_path):
    conn, _, ingest = open_ingest(tmp_path)
    try:
        result = ingest.ingest_event(
            make_event("event-1", text="watch 0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416"),
            is_watched=True,
        )
    finally:
        conn.close()

    # address_hint is EIP-55 checksummed by entity_extractor.to_checksum_address (intentional canonicalisation).
    assert result.token_intents[0]["address_hint"] == "0xd0667d0618Dc9B6d2a0A55f428b47C64Bcf00416"
    assert result.token_resolutions[0]["resolution_status"] == "NIL"
    assert result.token_resolutions[0]["target_id"] is None


def test_ingest_capture_tick_enqueues_market_tick_current_dirty_target(tmp_path):
    conn, repos, ingest = open_ingest(tmp_path)
    event = make_event(
        "event-capture-dirty",
        text="https://gmgn.ai/eth/token/0x6982508145454ce325ddbe47a25d4ec3d2311933 captured",
        received_at_ms=1_800_000_000_000,
    )
    try:
        prepared, resolutions, capture_result = _prepared_capture(ingest, event)
        result = ingest.commit_prepared_event(prepared, resolutions=resolutions, captures=[capture_result])
        dirty_row = repos.market_tick_current_dirty_targets.get(
            capture_result.tick.target_type,
            capture_result.tick.target_id,
        )
    finally:
        conn.close()

    assert result.inserted is True
    assert dirty_row is not None
    assert dirty_row["dirty_reason"] == "event_capture_tick_inserted"


def test_ingest_capture_tick_and_dirty_target_roll_back_with_event_transaction(tmp_path):
    conn, repos, ingest = open_ingest(tmp_path)
    event = make_event(
        "event-capture-rollback",
        text="https://gmgn.ai/eth/token/0x6982508145454ce325ddbe47a25d4ec3d2311933 rollback",
        received_at_ms=1_800_000_010_000,
    )
    try:
        prepared, resolutions, capture_result = _prepared_capture(ingest, event)
        ingest.event_anchor_jobs = _FailingEventAnchorJobs()
        try:
            ingest.commit_prepared_event(prepared, resolutions=resolutions, captures=[capture_result])
        except RuntimeError as exc:
            assert str(exc) == "event_anchor_enqueue_failed_for_test"
        else:
            raise AssertionError("expected ingest commit to fail after capture tick persistence")

        event_row = conn.execute("SELECT * FROM events WHERE event_id = %s", (event.event_id,)).fetchone()
        tick_row = repos.market_ticks.latest_at_or_before(
            target_type=capture_result.tick.target_type,
            target_id=capture_result.tick.target_id,
            at_ms=capture_result.tick.observed_at_ms,
            max_lag_ms=1,
        )
        dirty_row = repos.market_tick_current_dirty_targets.get(
            capture_result.tick.target_type,
            capture_result.tick.target_id,
        )
    finally:
        conn.close()

    assert event_row is None
    assert tick_row is None
    assert dirty_row is None


def test_ingest_registry_asset_rolls_back_with_failed_event_transaction(tmp_path):
    conn, repos, ingest = open_ingest(tmp_path)
    address = "0x6982508145454ce325ddbe47a25d4ec3d2311933"
    event = make_event(
        "event-registry-rollback",
        text=f"https://gmgn.ai/eth/token/{address} registry rollback",
        received_at_ms=1_800_000_015_000,
    )
    ingest.event_anchor_jobs = _FailingEventAnchorJobs()

    try:
        with pytest.raises(RuntimeError, match="event_anchor_enqueue_failed_for_test"):
            ingest.ingest_event(event, is_watched=True)

        event_row = conn.execute("SELECT event_id FROM events WHERE event_id = %s", (event.event_id,)).fetchone()
        assets = repos.registry.find_assets_by_address(chain_id="eth", address=address)
        intent_rows = conn.execute(
            "SELECT intent_id FROM token_intents WHERE event_id = %s",
            (event.event_id,),
        ).fetchall()
    finally:
        conn.close()

    assert event_row is None
    assert assets == []
    assert intent_rows == []


def test_ingest_rejects_loose_capture_result_contract(tmp_path):
    conn, _, ingest = open_ingest(tmp_path)
    event = make_event(
        "event-loose-capture-result",
        text="https://gmgn.ai/eth/token/0x6982508145454ce325ddbe47a25d4ec3d2311933 loose",
        received_at_ms=1_800_000_020_000,
    )
    try:
        prepared, resolutions, capture_result = _prepared_capture(ingest, event)

        class LooseCaptureResult:
            tick = capture_result.tick
            capture = capture_result.capture

        with pytest.raises(RuntimeError, match="ingest_capture_result_contract_required"):
            ingest.commit_prepared_event(prepared, resolutions=resolutions, captures=[LooseCaptureResult()])
    finally:
        conn.close()


def _prepared_capture(ingest: IngestService, event):
    prepared = ingest.prepare_event(event, is_watched=True)
    ingest.prepare_registry_for_resolution(prepared)
    resolutions = ingest.resolve_prepared(prepared, persist=False)
    market_resolution = next(
        item for decision in resolutions if (item := ingest.market_resolution_for_decision(decision)) is not None
    )
    tick = _capture_tick(market_resolution, observed_at_ms=event.received_at_ms)
    capture = EnrichedEventCapture(
        event_id=event.event_id,
        intent_id=str(market_resolution["intent_id"]),
        resolution_id=str(market_resolution["resolution_id"]),
        target_type=tick.target_type,
        target_id=tick.target_id,
        t_event_ms=event.received_at_ms,
        tick_observed_at_ms=tick.observed_at_ms,
        tick_id=tick.tick_id,
        tick_lag_ms=0,
        capture_method="tier3_inline",
        capture_reason="inline_quote",
        created_at_ms=event.received_at_ms,
    )
    return prepared, resolutions, CaptureResult(tick=tick, capture=capture)


def _capture_tick(market_resolution: dict[str, object], *, observed_at_ms: int) -> MarketTick:
    target_type = str(market_resolution["target_type"])
    target_id = str(market_resolution["target_id"])
    source_provider = "gmgn_dex_quote"
    return MarketTick(
        tick_id=market_tick_id(
            target_type=target_type,
            target_id=target_id,
            source_provider=source_provider,
            observed_at_ms=observed_at_ms,
        ),
        target_type=target_type,  # type: ignore[arg-type]
        target_id=target_id,
        chain=str(market_resolution.get("chain_id") or ""),
        token_address=str(market_resolution.get("token_address") or ""),
        exchange=None,
        instrument=None,
        pricefeed_id=None,
        source_tier="tier3_inline",
        source_provider=source_provider,
        observed_at_ms=observed_at_ms,
        received_at_ms=observed_at_ms,
        price_usd=Decimal("1.23"),
        liquidity_usd=Decimal("1000"),
        volume_24h_usd=Decimal("5000"),
        open_interest_usd=None,
        market_cap_usd=Decimal("1000000"),
        holders=None,
        created_at_ms=observed_at_ms,
        raw_payload_json={"source": "ingest-test"},
    )


class _FailingEventAnchorJobs:
    def enqueue_for_capture(self, *args, **kwargs) -> None:
        raise RuntimeError("event_anchor_enqueue_failed_for_test")
