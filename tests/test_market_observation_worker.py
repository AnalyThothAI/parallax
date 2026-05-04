from __future__ import annotations

import asyncio

from gmgn_twitter_intel.market.gmgn_openapi_client import GmgnOpenApiError, GmgnTokenInfo, GmgnTokenInfoLookup
from gmgn_twitter_intel.pipeline.market_observation_worker import MarketObservationWorker
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.storage.market_observation_repository import MarketObservationRepository
from gmgn_twitter_intel.storage.signal_repository import SignalRepository
from gmgn_twitter_intel.storage.sqlite_client import connect_sqlite
from gmgn_twitter_intel.storage.sqlite_schema import migrate
from gmgn_twitter_intel.storage.token_repository import TokenRepository
from tests.test_market_observation_repository import insert_direct_attribution


class FakeClient:
    provider = "gmgn"

    def __init__(self, results):
        self.results = list(results)
        self.calls: list[tuple[str, str]] = []

    def lookup_token_info(self, *, chain: str, address: str):
        self.calls.append((chain, address))
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def open_worker_runtime(tmp_path):
    conn = connect_sqlite(tmp_path / "twitter_intel.sqlite3", read_only=False)
    migrate(conn)
    evidence = EvidenceRepository(conn)
    signals = SignalRepository(conn)
    tokens = TokenRepository(conn)
    observations = MarketObservationRepository(conn)
    return conn, evidence, signals, tokens, observations


def token_info(*, price: float = 1.25) -> GmgnTokenInfo:
    return GmgnTokenInfo(
        chain="eth",
        address="0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416",
        symbol="DOG",
        name="Dog",
        icon_url=None,
        price=price,
        previous_price=None,
        market_cap=1250000.0,
        raw={"address": "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416", "symbol": "DOG", "price": price},
    )


def enqueue_observation(
    evidence,
    signals,
    tokens,
    observations,
    *,
    event_id="event-dog",
    received_at_ms=1_700_000_000_000,
):
    attribution = insert_direct_attribution(
        evidence,
        signals,
        tokens,
        event_id=event_id,
        received_at_ms=received_at_ms,
    )
    observations.enqueue_for_attributions([attribution], now_ms=received_at_ms + 1)
    return attribution


def test_worker_writes_snapshot_and_marks_observation_ready(tmp_path):
    conn, evidence, signals, tokens, observations = open_worker_runtime(tmp_path)
    try:
        enqueue_observation(evidence, signals, tokens, observations)
        client = FakeClient([GmgnTokenInfoLookup(info=token_info(), cache_status="miss")])
        worker = MarketObservationWorker(observations=observations, tokens=tokens, client=client)

        processed = asyncio.run(worker.process_one(now_ms=1_700_000_000_100))
        observation = conn.execute("SELECT * FROM token_market_observations").fetchone()
        snapshot = conn.execute("SELECT * FROM token_market_snapshots").fetchone()
    finally:
        conn.close()

    assert processed is True
    assert observation["status"] == "ready"
    assert observation["snapshot_id"] == snapshot["snapshot_id"]
    assert snapshot["price"] == 1.25
    assert snapshot["received_at_ms"] == 1_700_000_000_000


def test_worker_writes_event_time_snapshot_for_cache_hit(tmp_path):
    conn, evidence, signals, tokens, observations = open_worker_runtime(tmp_path)
    try:
        enqueue_observation(
            evidence,
            signals,
            tokens,
            observations,
            event_id="event-first",
            received_at_ms=1_700_000_000_000,
        )
        enqueue_observation(
            evidence,
            signals,
            tokens,
            observations,
            event_id="event-second",
            received_at_ms=1_700_000_060_000,
        )
        client = FakeClient(
            [
                GmgnTokenInfoLookup(info=token_info(price=1.0), cache_status="miss"),
                GmgnTokenInfoLookup(info=token_info(price=1.0), cache_status="hit"),
            ]
        )
        worker = MarketObservationWorker(observations=observations, tokens=tokens, client=client)

        assert asyncio.run(worker.process_one(now_ms=1_700_000_000_100))
        assert asyncio.run(worker.process_one(now_ms=1_700_000_060_100))
        rows = [
            dict(row)
            for row in conn.execute(
                "SELECT event_id, status, snapshot_id FROM token_market_observations ORDER BY target_received_at_ms"
            ).fetchall()
        ]
        snapshot_count = conn.execute("SELECT COUNT(*) AS count FROM token_market_snapshots").fetchone()
    finally:
        conn.close()

    assert rows[0]["status"] == "ready"
    assert rows[1]["status"] == "cached"
    assert rows[0]["snapshot_id"] != rows[1]["snapshot_id"]
    assert snapshot_count["count"] == 2


def test_worker_marks_provider_not_configured_without_leaving_pending(tmp_path):
    conn, evidence, signals, tokens, observations = open_worker_runtime(tmp_path)
    try:
        enqueue_observation(evidence, signals, tokens, observations)
        worker = MarketObservationWorker(observations=observations, tokens=tokens, client=None)

        processed = asyncio.run(worker.process_one(now_ms=1_700_000_000_100))
        observation = conn.execute("SELECT * FROM token_market_observations").fetchone()
    finally:
        conn.close()

    assert processed is True
    assert observation["status"] == "provider_not_configured"


def test_worker_marks_provider_not_found(tmp_path):
    conn, evidence, signals, tokens, observations = open_worker_runtime(tmp_path)
    try:
        enqueue_observation(evidence, signals, tokens, observations)
        worker = MarketObservationWorker(
            observations=observations,
            tokens=tokens,
            client=FakeClient([GmgnTokenInfoLookup(info=None, cache_status="miss")]),
        )

        processed = asyncio.run(worker.process_one(now_ms=1_700_000_000_100))
        observation = conn.execute("SELECT * FROM token_market_observations").fetchone()
    finally:
        conn.close()

    assert processed is True
    assert observation["status"] == "provider_not_found"


def test_worker_provider_error_backoffs(tmp_path):
    conn, evidence, signals, tokens, observations = open_worker_runtime(tmp_path)
    try:
        enqueue_observation(evidence, signals, tokens, observations)
        worker = MarketObservationWorker(
            observations=observations,
            tokens=tokens,
            client=FakeClient([GmgnOpenApiError("timeout")]),
        )

        processed = asyncio.run(worker.process_one(now_ms=1_700_000_000_100))
        observation = conn.execute("SELECT * FROM token_market_observations").fetchone()
    finally:
        conn.close()

    assert processed is True
    assert observation["status"] == "provider_error"
    assert observation["attempt_count"] == 1
    assert observation["next_run_at_ms"] == 1_700_000_005_100


def test_worker_rate_limit_uses_rate_limited_status(tmp_path):
    conn, evidence, signals, tokens, observations = open_worker_runtime(tmp_path)
    try:
        enqueue_observation(evidence, signals, tokens, observations)
        worker = MarketObservationWorker(
            observations=observations,
            tokens=tokens,
            client=FakeClient([GmgnOpenApiError("HTTP 429 rate limit")]),
        )

        processed = asyncio.run(worker.process_one(now_ms=1_700_000_000_100))
        observation = conn.execute("SELECT * FROM token_market_observations").fetchone()
    finally:
        conn.close()

    assert processed is True
    assert observation["status"] == "rate_limited"
    assert observation["next_run_at_ms"] == 1_700_000_030_100
