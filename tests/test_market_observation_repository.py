from __future__ import annotations

from gmgn_twitter_intel.pipeline.token_attribution import TokenAttributionBuilder
from gmgn_twitter_intel.pipeline.token_identity_resolver import TokenMention
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.storage.market_observation_repository import MarketObservationRepository
from gmgn_twitter_intel.storage.signal_repository import SignalRepository
from gmgn_twitter_intel.storage.sqlite_client import connect_sqlite
from gmgn_twitter_intel.storage.sqlite_schema import migrate
from gmgn_twitter_intel.storage.token_repository import TokenRepository
from tests.test_sqlite_repositories import make_event

TOKEN_ID = "token:eth:0xd0667d0618Dc9B6d2a0A55f428b47C64Bcf00416"
TOKEN_ADDRESS = "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416"
CHECKSUM_TOKEN_ADDRESS = "0xd0667d0618Dc9B6d2a0A55f428b47C64Bcf00416"


def open_repositories(tmp_path):
    conn = connect_sqlite(tmp_path / "twitter_intel.sqlite3", read_only=False)
    migrate(conn)
    return (
        conn,
        EvidenceRepository(conn),
        SignalRepository(conn),
        TokenRepository(conn),
        MarketObservationRepository(conn),
    )


def insert_direct_attribution(
    evidence: EvidenceRepository,
    signals: SignalRepository,
    tokens: TokenRepository,
    *,
    event_id: str = "event-dog",
    received_at_ms: int = 1_700_000_000_000,
) -> dict:
    event = make_event(
        event_id,
        text=f"$DOG {TOKEN_ADDRESS}",
        received_at_ms=received_at_ms,
    )
    evidence.insert_event(event, is_watched=True)
    identity = tokens.upsert_ca(
        event_id=event_id,
        chain="eth",
        address=TOKEN_ADDRESS,
        symbol="DOG",
        received_at_ms=received_at_ms,
        commit=False,
    )
    signals.insert_event_token_mentions(
        event_id=event_id,
        token_mentions=[
            TokenMention(
                identity_key=identity.token_id or TOKEN_ID,
                token_id=identity.token_id,
                identity_status=identity.identity_status,
                chain=identity.chain,
                address=identity.address,
                symbol=identity.symbol or "DOG",
                source="regex",
            )
        ],
        received_at_ms=received_at_ms,
        author_handle="toly",
        author_followers=100,
        is_watched=True,
        commit=False,
    )
    rows = signals.token_mentions_for_event(event_id)
    attributions = TokenAttributionBuilder(signals=signals, tokens=tokens).build_for_rows(rows)
    signals.replace_token_attributions(
        mention_ids=[str(row["mention_id"]) for row in rows],
        attributions=attributions,
        commit=True,
    )
    return signals.token_attributions_for_event(event_id)[0]


def test_enqueue_for_direct_attribution_creates_pending_observation(tmp_path):
    conn, evidence, signals, tokens, observations = open_repositories(tmp_path)
    try:
        attribution = insert_direct_attribution(evidence, signals, tokens)

        inserted = observations.enqueue_for_attributions([attribution], now_ms=1_700_000_001_000)
        row = conn.execute("SELECT * FROM token_market_observations").fetchone()
    finally:
        conn.close()

    assert inserted == 1
    assert row["attribution_id"] == attribution["attribution_id"]
    assert row["event_id"] == "event-dog"
    assert row["token_id"] == TOKEN_ID
    assert row["chain"] == "eth"
    assert row["address"] == CHECKSUM_TOKEN_ADDRESS
    assert row["symbol"] == "DOG"
    assert row["target_received_at_ms"] == 1_700_000_000_000
    assert row["status"] == "pending"
    assert row["next_run_at_ms"] == 1_700_000_001_000


def test_enqueue_for_same_attribution_is_idempotent(tmp_path):
    conn, evidence, signals, tokens, observations = open_repositories(tmp_path)
    try:
        attribution = insert_direct_attribution(evidence, signals, tokens)

        first = observations.enqueue_for_attributions([attribution], now_ms=1_700_000_001_000)
        second = observations.enqueue_for_attributions([attribution], now_ms=1_700_000_002_000)
        count = conn.execute("SELECT COUNT(*) AS count FROM token_market_observations").fetchone()
    finally:
        conn.close()

    assert first == 1
    assert second == 0
    assert count["count"] == 1


def test_claim_next_marks_pending_observation_running(tmp_path):
    conn, evidence, signals, tokens, observations = open_repositories(tmp_path)
    try:
        attribution = insert_direct_attribution(evidence, signals, tokens)
        observations.enqueue_for_attributions([attribution], now_ms=1_700_000_001_000)

        claimed = observations.claim_next(now_ms=1_700_000_001_500)
        stored = conn.execute("SELECT status FROM token_market_observations").fetchone()
    finally:
        conn.close()

    assert claimed is not None
    assert claimed["attribution_id"] == attribution["attribution_id"]
    assert claimed["status"] == "running"
    assert stored["status"] == "running"


def test_claim_next_reclaims_stale_running_observation(tmp_path):
    conn, evidence, signals, tokens, observations = open_repositories(tmp_path)
    try:
        attribution = insert_direct_attribution(evidence, signals, tokens)
        observations.enqueue_for_attributions([attribution], now_ms=1_700_000_001_000)
        observations.claim_next(now_ms=1_700_000_001_500)

        early = observations.claim_next(now_ms=1_700_000_060_000)
        stale = observations.claim_next(now_ms=1_700_000_130_000)
    finally:
        conn.close()

    assert early is None
    assert stale is not None
    assert stale["attribution_id"] == attribution["attribution_id"]


def test_complete_records_snapshot_and_terminal_status(tmp_path):
    conn, evidence, signals, tokens, observations = open_repositories(tmp_path)
    try:
        attribution = insert_direct_attribution(evidence, signals, tokens)
        observations.enqueue_for_attributions([attribution], now_ms=1_700_000_001_000)
        claimed = observations.claim_next(now_ms=1_700_000_001_500)

        observations.complete(
            claimed,
            snapshot_id="snapshot-ready",
            status="ready",
            provider="gmgn",
            now_ms=1_700_000_002_000,
        )
        row = conn.execute("SELECT * FROM token_market_observations").fetchone()
    finally:
        conn.close()

    assert row["status"] == "ready"
    assert row["snapshot_id"] == "snapshot-ready"
    assert row["provider"] == "gmgn"
    assert row["updated_at_ms"] == 1_700_000_002_000


def test_fail_backoff_and_dead_status(tmp_path):
    conn, evidence, signals, tokens, observations = open_repositories(tmp_path)
    try:
        attribution = insert_direct_attribution(evidence, signals, tokens)
        observations.enqueue_for_attributions([attribution], now_ms=1_700_000_001_000)
        claimed = observations.claim_next(now_ms=1_700_000_001_500)

        observations.fail(claimed, error="timeout", now_ms=1_700_000_002_000)
        first_failure = conn.execute("SELECT * FROM token_market_observations").fetchone()

        next_run_at_ms = int(first_failure["next_run_at_ms"])
        for _ in range(4):
            claimed = observations.claim_next(now_ms=next_run_at_ms + 1)
            observations.fail(claimed, error="timeout", now_ms=next_run_at_ms + 2)
            row = conn.execute("SELECT * FROM token_market_observations").fetchone()
            next_run_at_ms = int(row["next_run_at_ms"])
        dead = conn.execute("SELECT * FROM token_market_observations").fetchone()
    finally:
        conn.close()

    assert first_failure["status"] == "provider_error"
    assert first_failure["attempt_count"] == 1
    assert first_failure["next_run_at_ms"] == 1_700_000_007_000
    assert dead["status"] == "dead"
    assert dead["attempt_count"] == 5
