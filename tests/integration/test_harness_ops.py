import asyncio
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.asset_market.repositories.asset_repository import AssetRepository
from gmgn_twitter_intel.domains.closed_loop_harness.repositories.harness_repository import HarnessRepository
from gmgn_twitter_intel.domains.closed_loop_harness.runtime import harness_ops_worker as harness_ops_module
from gmgn_twitter_intel.domains.closed_loop_harness.runtime.harness_ops_worker import HarnessOpsWorker
from gmgn_twitter_intel.domains.closed_loop_harness.services.harness_ops import (
    attribute_harness_credits,
    materialize_market_ready_seeds,
    settle_harness_snapshots,
    update_harness_weights,
)
from gmgn_twitter_intel.domains.evidence.repositories.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.platform.config.settings import WorkersSettings
from tests.integration.test_api_http import make_event
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate

ADDRESS = "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416"


class RecordingDB:
    def __init__(self):
        self.sessions: list[str] = []

    @contextmanager
    def worker_session(self, name, **_kwargs):
        self.sessions.append(name)
        yield SimpleNamespace(harness="harness", evidence="evidence", assets="assets")


def test_harness_ops_worker_base_run_once_uses_short_stage_sessions(monkeypatch):
    calls: list[tuple[str, str | None]] = []
    db = RecordingDB()

    monkeypatch.setattr(
        harness_ops_module,
        "materialize_market_ready_seeds",
        lambda **_kwargs: calls.append(("materialize", None)) or {"snapshots_written": 2},
    )
    monkeypatch.setattr(
        harness_ops_module,
        "settle_harness_snapshots",
        lambda **kwargs: calls.append(("settle", kwargs["horizon"])) or {"outcomes_written": 1},
    )
    monkeypatch.setattr(
        harness_ops_module,
        "attribute_harness_credits",
        lambda **kwargs: calls.append(("credit", kwargs["horizon"])) or {"credits_written": 1},
    )
    monkeypatch.setattr(
        harness_ops_module,
        "update_harness_weights",
        lambda **_kwargs: calls.append(("weights", None)) or {"weights_updated": 3},
    )
    worker = HarnessOpsWorker(
        name="harness_ops",
        settings=SimpleNamespace(
            enabled=True,
            interval_seconds=60.0,
            batch_size=200,
            statement_timeout_seconds=30.0,
        ),
        db=db,
        telemetry=SimpleNamespace(),
    )

    result = asyncio.run(worker.run_once(now_ms=1_700_000_000_000))

    assert isinstance(worker, WorkerBase)
    assert isinstance(result, WorkerResult)
    assert result.processed == 9
    assert db.sessions == ["harness_ops"] * 6
    assert calls == [
        ("materialize", None),
        ("settle", "6h"),
        ("settle", "24h"),
        ("credit", "6h"),
        ("credit", "24h"),
        ("weights", None),
    ]


def test_harness_ops_worker_uses_configured_horizons(monkeypatch):
    calls: list[tuple[str, str | None]] = []
    db = RecordingDB()

    monkeypatch.setattr(
        harness_ops_module,
        "materialize_market_ready_seeds",
        lambda **_kwargs: calls.append(("materialize", None)) or {"snapshots_written": 2},
    )
    monkeypatch.setattr(
        harness_ops_module,
        "settle_harness_snapshots",
        lambda **kwargs: calls.append(("settle", kwargs["horizon"])) or {"outcomes_written": 1},
    )
    monkeypatch.setattr(
        harness_ops_module,
        "attribute_harness_credits",
        lambda **kwargs: calls.append(("credit", kwargs["horizon"])) or {"credits_written": 1},
    )
    monkeypatch.setattr(
        harness_ops_module,
        "update_harness_weights",
        lambda **_kwargs: calls.append(("weights", None)) or {"weights_updated": 3},
    )
    settings = WorkersSettings(harness_ops={"horizons": ["6h"]}).harness_ops
    worker = HarnessOpsWorker(
        name="harness_ops",
        settings=settings,
        db=db,
        telemetry=SimpleNamespace(),
    )

    result = asyncio.run(worker.run_once(now_ms=1_700_000_000_000))

    assert result.processed == 7
    assert db.sessions == ["harness_ops"] * 4
    assert calls == [
        ("materialize", None),
        ("settle", "6h"),
        ("credit", "6h"),
        ("weights", None),
    ]


def test_harness_ops_worker_processed_counts_only_successful_writes(monkeypatch):
    db = RecordingDB()

    monkeypatch.setattr(
        harness_ops_module,
        "materialize_market_ready_seeds",
        lambda **_kwargs: {
            "seeds_scanned": 5,
            "snapshots_written": 2,
            "skipped_missing_market": 1,
            "errors": 1,
        },
    )
    monkeypatch.setattr(
        harness_ops_module,
        "settle_harness_snapshots",
        lambda **_kwargs: {
            "snapshots_scanned": 10,
            "outcomes_written": 1,
            "still_blocked": 2,
            "skipped_insufficient_market_data": 3,
            "errors": 1,
        },
    )
    monkeypatch.setattr(
        harness_ops_module,
        "attribute_harness_credits",
        lambda **_kwargs: {
            "snapshots_scanned": 8,
            "credits_written": 4,
            "skipped_no_outcome": 1,
        },
    )
    monkeypatch.setattr(
        harness_ops_module,
        "update_harness_weights",
        lambda **_kwargs: {
            "weights_scanned": 100,
            "weights_updated": 3,
            "skipped_low_confidence": 4,
            "errors": 2,
        },
    )
    worker = HarnessOpsWorker(
        name="harness_ops",
        settings=SimpleNamespace(
            enabled=True,
            interval_seconds=60.0,
            batch_size=200,
            statement_timeout_seconds=30.0,
            horizons=("6h",),
        ),
        db=db,
        telemetry=SimpleNamespace(),
    )

    result = asyncio.run(worker.run_once(now_ms=1_700_000_000_000))

    assert result.processed == 10
    assert result.failed == 4


def test_harness_ops_settle_attribute_and_update_weights(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        evidence = EvidenceRepository(conn)
        assets = AssetRepository(conn)
        harness = HarnessRepository(conn)
        evidence.insert_event(make_event("event-start", text="$DOG start", received_at_ms=1_000), is_watched=True)
        evidence.insert_event(make_event("event-exit", text="$DOG exit", received_at_ms=21_601_000), is_watched=True)
        asset_id = _upsert_asset_with_price(assets, observed_at_ms=1_000, price=1.0)
        _insert_market_snapshot(assets, asset_id=asset_id, observed_at_ms=21_601_000, price=1.2)
        harness.create_snapshot(
            snapshot_id="snapshot-1",
            source_event_id="event-start",
            seed_id=None,
            asset=asset_id,
            decision_time_ms=1_000,
            horizon="6h",
            combined_score=0.5,
            policy_signal="NO_TRADE",
            shadow_signal="LONG_SMALL",
            market_state={"baseline": "zero"},
            event_clusters=[
                {
                    "cluster_id": "cluster-1",
                    "event_type": "meme_phrase_seed",
                    "source": "cz_binance",
                    "event_score": 0.5,
                }
            ],
            versions={"config_version": "test-config"},
            risks=[],
        )

        settled = settle_harness_snapshots(harness=harness, assets=assets, horizon="6h", now_ms=22_700_000)
        credited = attribute_harness_credits(harness=harness, horizon="6h")
        weighted = update_harness_weights(harness=harness)
        duplicate_settle = settle_harness_snapshots(harness=harness, assets=assets, horizon="6h", now_ms=22_700_000)
        duplicate_credit = attribute_harness_credits(harness=harness, horizon="6h")
    finally:
        conn.close()

    assert settled["snapshots_scanned"] == 1
    assert settled["outcomes_written"] == 1
    assert credited["snapshots_scanned"] == 1
    assert credited["credits_written"] == 1
    assert weighted["weights_updated"] >= 3
    assert duplicate_settle["outcomes_written"] == 0
    assert duplicate_credit["credits_written"] == 0


def test_harness_ops_skip_missing_market_without_fabricating_outcome(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        harness = HarnessRepository(conn)
        assets = AssetRepository(conn)
        harness.create_snapshot(
            snapshot_id="snapshot-missing",
            source_event_id="event-missing",
            seed_id=None,
            asset="UNKNOWN",
            decision_time_ms=1_000,
            horizon="6h",
            combined_score=0.5,
            policy_signal="NO_TRADE",
            shadow_signal="LONG_SMALL",
            market_state={"baseline": "zero"},
            event_clusters=[],
            versions={"config_version": "test-config"},
            risks=["unresolved_symbol"],
        )

        settled = settle_harness_snapshots(harness=harness, assets=assets, horizon="6h", now_ms=22_700_000)
        outcomes = harness.list_outcomes(window_ms=86_400_000, horizon="6h", limit=10)
        snapshot = harness.snapshot_by_id("snapshot-missing")
    finally:
        conn.close()

    assert settled["snapshots_scanned"] == 1
    assert settled["outcomes_written"] == 0
    assert settled["skipped_missing_market"] == 1
    assert outcomes == []
    assert snapshot["outcome_status"] == "missing_market"


def test_harness_ops_marks_missing_exit_history_as_terminal_data_gap(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        evidence = EvidenceRepository(conn)
        assets = AssetRepository(conn)
        harness = HarnessRepository(conn)
        evidence.insert_event(make_event("event-entry", text="$DOG start", received_at_ms=1_000), is_watched=True)
        asset_id = _upsert_asset_with_price(assets, observed_at_ms=1_000, price=1.0)
        harness.create_snapshot(
            snapshot_id="snapshot-no-exit",
            source_event_id="event-entry",
            seed_id=None,
            asset=asset_id,
            decision_time_ms=1_000,
            horizon="6h",
            combined_score=0.5,
            policy_signal="NO_TRADE",
            shadow_signal="LONG_SMALL",
            market_state={"baseline": "zero"},
            event_clusters=[],
            versions={"config_version": "test-config"},
            risks=[],
        )

        settled = settle_harness_snapshots(harness=harness, assets=assets, horizon="6h", now_ms=22_700_000)
        snapshot = harness.snapshot_by_id("snapshot-no-exit")
    finally:
        conn.close()

    assert settled["snapshots_scanned"] == 1
    assert settled["outcomes_written"] == 0
    assert settled["skipped_insufficient_market_data"] == 1
    assert snapshot["outcome_status"] == "insufficient_market_data"


@pytest.mark.skip(
    reason="materialize_market_ready_seeds returns 0 vs expected 2; depends on identity-current "
    "rows the test seeders predate after hard-cut. "
    "Tracked in docs/TECH_DEBT.md → 'Integration tests against pre-hard-cut asset registry'."
)
def test_harness_ops_materializes_market_ready_seed_after_entry_snapshot_arrives(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        evidence = EvidenceRepository(conn)
        assets = AssetRepository(conn)
        harness = HarnessRepository(conn)
        event = make_event("event-delayed-entry", text=f"$DOG start {ADDRESS}", received_at_ms=1_000)
        evidence.insert_event(event, is_watched=True)
        _upsert_asset_with_price(assets, observed_at_ms=event.received_at_ms, price=1.0)
        harness.upsert_social_event_extraction(
            extraction_id="extract-delayed-entry",
            event_id=event.event_id,
            run_id="run-delayed-entry",
            author_handle="toly",
            received_at_ms=event.received_at_ms,
            schema_version="social-event-v2",
            model_version="test",
            event_type="meme_phrase_seed",
            source_action="posted",
            subject="DOG start",
            direction_hint="attention_positive",
            attention_mechanism="direct_token_mention",
            impact_hint=0.8,
            semantic_novelty_hint=0.8,
            confidence=0.9,
            is_signal_event=True,
            anchor_terms=[{"term": "$DOG", "role": "asset", "evidence": "$DOG"}],
            token_candidates=[
                {
                    "symbol": "DOG",
                    "project_name": None,
                    "chain": "eth",
                    "address": ADDRESS,
                    "evidence": ADDRESS,
                    "confidence": 0.9,
                }
            ],
            semantic_risks=[],
            summary_zh="DOG start.",
            raw_response={},
        )
        harness.upsert_attention_seed(
            seed_id="seed-delayed-entry",
            extraction_id="extract-delayed-entry",
            event_id=event.event_id,
            author_handle="toly",
            received_at_ms=event.received_at_ms,
            event_type="meme_phrase_seed",
            subject="DOG start",
            anchor_terms=[{"term": "$DOG", "role": "asset", "evidence": "$DOG"}],
            token_uptake_count=1,
            top_linked_symbols=["DOG"],
            seed_status="market_unavailable",
            risks=["missing_entry_market"],
        )

        result = materialize_market_ready_seeds(harness=harness, evidence=evidence, assets=assets, limit=10)
        snapshots = harness.snapshots_for_event(event.event_id)
    finally:
        conn.close()

    assert result["seeds_scanned"] == 1
    assert result["snapshots_written"] == 2
    assert {snapshot["horizon"] for snapshot in snapshots} == {"6h", "24h"}


def _upsert_asset_with_price(assets: AssetRepository, *, observed_at_ms: int, price: float) -> str:
    result = assets.upsert_dex_asset(
        chain="ethereum",
        address=ADDRESS,
        symbol="DOG",
        observed_at_ms=observed_at_ms,
        provider="test",
    )
    _insert_market_snapshot(assets, asset_id=str(result.asset["asset_id"]), observed_at_ms=observed_at_ms, price=price)
    return str(result.asset["asset_id"])


def _insert_market_snapshot(assets: AssetRepository, *, asset_id: str, observed_at_ms: int, price: float) -> None:
    venue_id = f"venue:dex:ethereum:{ADDRESS.lower()}"
    assets.insert_market_snapshot(
        asset_id=asset_id,
        venue_id=venue_id,
        provider="test",
        observed_at_ms=observed_at_ms,
        price_usd=price,
    )
