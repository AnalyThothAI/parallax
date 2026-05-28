from __future__ import annotations

from types import SimpleNamespace

from gmgn_twitter_intel.domains.pulse_lab.services.evidence_completeness_gate import EvidenceCompletenessGate
from gmgn_twitter_intel.domains.pulse_lab.services.evidence_packet_builder import PulseEvidenceBuilder

NOW_MS = 1_800_000_000_000


class FakeEvidenceSourceRepository:
    def __init__(
        self,
        *,
        events: list[dict[str, object]] | None = None,
        enriched_events: list[dict[str, object]] | None = None,
        market_facts: list[dict[str, object]] | None = None,
        identity_facts: list[dict[str, object]] | None = None,
        discussion_digest: dict[str, object] | None = None,
    ) -> None:
        self.events = events or []
        self.enriched_events = enriched_events or []
        self.market_facts = market_facts or []
        self.identity_facts = identity_facts or []
        self.discussion_digest = discussion_digest

    def list_source_events(self, event_ids: list[str]) -> list[dict[str, object]]:
        return [row for row in self.events if row["event_id"] in set(event_ids)]

    def list_enriched_events(self, event_ids: list[str]) -> list[dict[str, object]]:
        return [row for row in self.enriched_events if row["event_id"] in set(event_ids)]

    def list_market_facts(self, context: object, *, max_age_ms: int, now_ms: int) -> list[dict[str, object]]:
        return list(self.market_facts)

    def list_identity_facts(self, context: object) -> list[dict[str, object]]:
        return list(self.identity_facts)

    def get_current_discussion_digest(
        self,
        *,
        target_type: str,
        target_id: str,
        window: str,
        scope: str,
        schema_version: str,
    ) -> dict[str, object] | None:
        return self.discussion_digest


def test_builds_partial_cex_packet_with_pricefeed_id_and_no_venue_id() -> None:
    context = _context(
        target_type="cex_token",
        target_id="cex_token:BTC",
        source_event_ids=["event-1"],
        factor_snapshot={"market": {"decision_latest": {"price_usd": 99_999}}},
    )
    repo = FakeEvidenceSourceRepository(
        events=[_event("event-1")],
        market_facts=[
            {
                "route": "cex",
                "target_market_type": "perpetual",
                "price_usd": 67_000,
                "pricefeed_id": "pricefeed:cex:binance:swap:BTCUSDT",
                "source_provider": "binance_cex_rest",
                "observed_at_ms": NOW_MS - 30_000,
            }
        ],
        identity_facts=[{"source_id": "identity:btc", "symbol": "BTC", "observed_at_ms": NOW_MS - 60_000}],
    )

    packet = PulseEvidenceBuilder(repo).build(context, run_id="run-1", now_ms=NOW_MS)

    market = _model_dump(packet.market_evidence)
    assert market["instrument_ref"] == "pricefeed:cex:binance:swap:BTCUSDT"
    assert market["venue_ref"] == "venue:binance_cex_rest"
    assert market["price_usd"] == 67_000
    assert "event:event-1" in _ref_ids(packet)
    assert "metric:market:price_usd" in _ref_ids(packet)
    assert packet.admission_context["factor_snapshot"]["market"]["decision_latest"]["price_usd"] == 99_999


def test_builds_cex_snapshot_packet_with_derivatives_and_level_refs() -> None:
    context = _context(
        target_type="cex_token",
        target_id="cex_token:BTC",
        source_event_ids=["event-1"],
    )
    repo = FakeEvidenceSourceRepository(
        events=[_event("event-1")],
        market_facts=[
            {
                "source_table": "cex_detail_snapshots",
                "route": "cex",
                "target_market_type": "perpetual",
                "price_usd": 67_000,
                "mark_price": 67_050,
                "open_interest_usd": 12_000_000_000,
                "oi_change_pct_24h": 3.5,
                "cvd_delta_4h": -1_250_000,
                "funding_rate": 0.0001,
                "native_market_id": "BTCUSDT",
                "pricefeed_id": "pricefeed:cex:binance:swap:BTCUSDT",
                "source_provider": "binance",
                "coinglass_status": "ready",
                "level_bands": [
                    {"kind": "resistance", "price": 72_000, "score": 0.82},
                    {"kind": "support", "price": 64_000, "score": 0.7},
                ],
                "degraded_reasons": [],
                "observed_at_ms": NOW_MS - 30_000,
            }
        ],
        identity_facts=[{"source_id": "identity:btc", "symbol": "BTC", "observed_at_ms": NOW_MS - 60_000}],
    )

    packet = PulseEvidenceBuilder(repo).build(context, run_id="run-1", now_ms=NOW_MS)
    gate = EvidenceCompletenessGate().evaluate(packet)

    market = _model_dump(packet.market_evidence)
    assert market["cex_snapshot"]["native_market_id"] == "BTCUSDT"
    assert market["derivatives"]["oi_change_pct_24h"] == 3.5
    assert market["derivatives"]["cvd_delta_4h"] == -1_250_000
    assert market["levels"][0]["kind"] == "resistance"
    assert "metric:cex:oi_change_pct_24h:BTCUSDT" in _ref_ids(packet)
    assert "level:cex:BTCUSDT:resistance:72000" in _ref_ids(packet)
    assert gate.max_decision_status == "trade_candidate"


def test_builds_dex_packet_with_pair_and_liquidity_evidence() -> None:
    context = _context(target_type="chain_token", target_id="solana:abc", source_event_ids=["event-1"])
    repo = FakeEvidenceSourceRepository(
        events=[_event("event-1")],
        market_facts=[
            {
                "route": "meme",
                "target_market_type": "dex",
                "price_usd": 0.012,
                "liquidity_usd": 250_000,
                "pair_ref": "pair:solana:abc-usdc",
                "observed_at_ms": NOW_MS - 30_000,
                "source_provider": "gmgn",
            }
        ],
        identity_facts=[{"source_id": "identity:abc", "symbol": "ABC", "observed_at_ms": NOW_MS - 60_000}],
    )

    packet = PulseEvidenceBuilder(repo).build(context, run_id="run-1", now_ms=NOW_MS)

    market = _model_dump(packet.market_evidence)
    assert market["instrument_ref"] == "pair:solana:abc-usdc"
    assert market["liquidity_usd"] == 250_000
    assert {"metric:market:price_usd", "metric:market:liquidity_usd"}.issubset(_ref_ids(packet))


def test_marks_market_evidence_stale_without_using_factor_snapshot_as_truth() -> None:
    context = _context(
        target_type="cex_token",
        target_id="cex_token:ETH",
        source_event_ids=["event-1"],
        factor_snapshot={"market": {"decision_latest": {"price_usd": 9_999, "observed_at_ms": NOW_MS}}},
    )
    repo = FakeEvidenceSourceRepository(
        events=[_event("event-1")],
        market_facts=[
            {
                "route": "cex",
                "price_usd": 3_100,
                "pricefeed_id": "pricefeed:cex:binance:spot:ETHUSDT",
                "source_provider": "binance_cex_rest",
                "observed_at_ms": NOW_MS - 3_700_000,
            }
        ],
        identity_facts=[{"source_id": "identity:eth", "symbol": "ETH", "observed_at_ms": NOW_MS - 60_000}],
    )

    packet = PulseEvidenceBuilder(repo, market_freshness_ms=3_600_000).build(
        context,
        run_id="run-1",
        now_ms=NOW_MS,
    )

    market = _model_dump(packet.market_evidence)
    assert market["price_usd"] == 3_100
    assert market["freshness_status"] == "stale"
    assert any(_model_dump(gap)["gap_id"] == "market_stale" for gap in packet.data_gaps)


def test_packet_hash_is_stable_across_input_dict_key_order() -> None:
    context_a = _context(
        target_type="cex_token",
        target_id="cex_token:BTC",
        source_event_ids=["event-1"],
        factor_snapshot={"b": 2, "a": {"z": 3, "y": 4}},
    )
    context_b = _context(
        target_type="cex_token",
        target_id="cex_token:BTC",
        source_event_ids=["event-1"],
        factor_snapshot={"a": {"y": 4, "z": 3}, "b": 2},
    )
    repo = FakeEvidenceSourceRepository(
        events=[_event("event-1")],
        market_facts=[
            {
                "route": "cex",
                "price_usd": 67_000,
                "pricefeed_id": "pricefeed:cex:binance:spot:BTCUSDT",
                "source_provider": "binance_cex_rest",
                "observed_at_ms": NOW_MS - 30_000,
            }
        ],
        identity_facts=[{"source_id": "identity:btc", "symbol": "BTC", "observed_at_ms": NOW_MS - 60_000}],
    )

    builder = PulseEvidenceBuilder(repo)
    packet_a = builder.build(context_a, run_id="run-1", now_ms=NOW_MS)
    packet_b = builder.build(context_b, run_id="run-1", now_ms=NOW_MS)

    assert packet_a.evidence_packet_hash == packet_b.evidence_packet_hash


def test_includes_updating_digest_as_context_with_currentness_and_data_gap_only() -> None:
    context = _context(target_type="chain_token", target_id="solana:abc", source_event_ids=[])
    repo = FakeEvidenceSourceRepository(
        discussion_digest=_digest(
            currentness={
                "display_status": "updating",
                "reason": "digest_updating",
                "delta_source_event_count": 1,
            },
            data_gaps_json=[{"reason": "digest_updating", "delta_source_event_count": 1}],
            evidence_refs_json=[{"ref_id": "event:stale-digest-only"}],
        )
    )

    packet = PulseEvidenceBuilder(repo).build(context, run_id="run-digest", now_ms=NOW_MS)

    compact = packet.admission_context["discussion_digest"]
    assert compact["currentness"]["display_status"] == "updating"
    assert compact["data_gaps"] == [{"reason": "digest_updating", "delta_source_event_count": 1}]
    assert "event:stale-digest-only" not in _ref_ids(packet)
    assert packet.social_evidence.status == "insufficient"


def test_stale_digest_prose_without_current_sources_blocks_non_abstain_packet() -> None:
    context = _context(target_type="chain_token", target_id="solana:abc", source_event_ids=[])
    repo = FakeEvidenceSourceRepository(
        discussion_digest=_digest(
            headline_zh="上一版叙事很强，但已经不是当前来源边界。",
            currentness={"display_status": "stale", "reason": "digest_stale"},
            data_gaps_json=[{"reason": "digest_stale"}],
            evidence_refs_json=[{"ref_id": "event:old-digest"}],
        )
    )

    packet = PulseEvidenceBuilder(repo).build(context, run_id="run-stale", now_ms=NOW_MS)
    gate = EvidenceCompletenessGate().evaluate(packet)

    assert gate.max_decision_status == "abstain"
    assert gate.blocked_reason == "blocked_social_contract"
    assert "event:old-digest" not in _ref_ids(packet)
    assert {ref.ref_type for ref in packet.allowed_evidence_refs} == {"gate"}


def test_current_source_refs_remain_primary_when_digest_is_stale_context() -> None:
    context = _context(target_type="cex_token", target_id="cex_token:BTC", source_event_ids=["event-current"])
    repo = FakeEvidenceSourceRepository(
        events=[_event("event-current")],
        market_facts=[
            {
                "route": "cex",
                "target_market_type": "perpetual",
                "price_usd": 67_000,
                "pricefeed_id": "pricefeed:cex:binance:swap:BTCUSDT",
                "source_provider": "binance_cex_rest",
                "observed_at_ms": NOW_MS - 30_000,
            }
        ],
        identity_facts=[{"source_id": "identity:btc", "symbol": "BTC", "observed_at_ms": NOW_MS - 60_000}],
        discussion_digest=_digest(
            headline_zh="上一版叙事只能作为背景。",
            currentness={"display_status": "stale", "reason": "digest_stale"},
            data_gaps_json=[{"reason": "digest_stale"}],
            evidence_refs_json=[{"ref_id": "event:old-digest"}],
        ),
    )

    packet = PulseEvidenceBuilder(repo).build(context, run_id="run-current", now_ms=NOW_MS)
    gate = EvidenceCompletenessGate().evaluate(packet)

    assert gate.max_decision_status == "token_watch"
    assert {"event:event-current", "metric:market:price_usd", "identity:btc"}.issubset(_ref_ids(packet))
    assert "event:old-digest" not in _ref_ids(packet)


def _context(
    *,
    target_type: str,
    target_id: str,
    source_event_ids: list[str],
    factor_snapshot: dict[str, object] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        candidate_id="candidate-1",
        target_type=target_type,
        target_id=target_id,
        symbol="BTC",
        window="1h",
        scope="all",
        source_event_ids=source_event_ids,
        evidence_event_ids=[],
        factor_snapshot=factor_snapshot or {},
        selected_posts=[],
        gate_result={"pulse_status": "trade_candidate"},
    )


def _event(event_id: str) -> dict[str, object]:
    return {
        "event_id": event_id,
        "observed_at_ms": NOW_MS - 45_000,
        "summary_zh": f"{event_id} 社交事件",
        "url": f"https://example.test/{event_id}",
    }


def _digest(
    *,
    headline_zh: str = "上一版叙事摘要",
    currentness: dict[str, object],
    data_gaps_json: list[dict[str, object]],
    evidence_refs_json: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "digest_id": "digest-last-ready",
        "schema_version": "narrative_intel_v1",
        "computed_at_ms": NOW_MS - 600_000,
        "semantic_coverage": 0.75,
        "headline_zh": headline_zh,
        "dominant_narratives_json": [{"cluster_key": "k", "summary_zh": headline_zh}],
        "bull_view_json": {"summary_zh": "多头背景", "evidence_refs": evidence_refs_json},
        "bear_view_json": {"summary_zh": "风险背景", "evidence_refs": evidence_refs_json},
        "propagation_read_json": {},
        "reflexivity_read_json": {},
        "evidence_refs_json": evidence_refs_json,
        "currentness": currentness,
        "data_gaps_json": data_gaps_json,
    }


def _ref_ids(packet: object) -> set[str]:
    return {str(_model_dump(ref)["ref_id"]) for ref in packet.allowed_evidence_refs}


def _model_dump(value: object) -> dict[str, object]:
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    return dict(value)  # type: ignore[arg-type]
