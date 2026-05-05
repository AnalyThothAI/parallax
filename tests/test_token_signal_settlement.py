import pytest

from gmgn_twitter_intel.market.gmgn_openapi_client import GmgnTokenInfo
from gmgn_twitter_intel.pipeline.token_signal_settlement import settle_token_signal_snapshots
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.storage.sqlite_client import connect_sqlite
from gmgn_twitter_intel.storage.sqlite_schema import migrate
from gmgn_twitter_intel.storage.token_repository import TokenRepository
from gmgn_twitter_intel.storage.token_signal_repository import TokenSignalRepository
from tests.test_sqlite_repositories import make_event
from tests.test_token_signal_repository import snapshot_payload


def open_settlement_repos(tmp_path):
    conn = connect_sqlite(tmp_path / "twitter_intel.sqlite3", read_only=False)
    migrate(conn)
    evidence = EvidenceRepository(conn)
    tokens = TokenRepository(conn)
    token_signals = TokenSignalRepository(conn)
    return conn, evidence, tokens, token_signals


def add_market(evidence, tokens, *, event_id, token_id_time, price):
    evidence.insert_event(make_event(event_id, received_at_ms=token_id_time), is_watched=True)
    return tokens.upsert_openapi_token_info(
        event_id=event_id,
        info=GmgnTokenInfo(
            chain="eth",
            address="0x1111111111111111111111111111111111111111",
            symbol="DOG",
            name="Dog",
            icon_url=None,
            price=price,
            previous_price=None,
            market_cap=1_000_000,
            raw={"price": price},
        ),
        received_at_ms=token_id_time,
        source_channel="gmgn_openapi_token_info",
        commit=True,
    )


def test_settle_token_signal_uses_vol_floor_for_fractional_outcome(tmp_path):
    conn, evidence, tokens, token_signals = open_settlement_repos(tmp_path)
    try:
        decision_ms = 1_700_000_000_000
        identity = add_market(evidence, tokens, event_id="market-entry", token_id_time=decision_ms + 60_000, price=1.0)
        add_market(evidence, tokens, event_id="market-exit", token_id_time=decision_ms + 6 * 60 * 60_000, price=1.015)
        token_signals.create_snapshot(
            **snapshot_payload(
                snapshot_id="snapshot-settle",
                token_id=identity.token_id,
                identity_key=identity.token_id,
                decision_time_ms=decision_ms,
            )
        )

        result = settle_token_signal_snapshots(
            repository=token_signals,
            tokens=tokens,
            horizon="6h",
            now_ms=decision_ms + 6 * 60 * 60_000 + 1,
            limit=10,
        )
        outcome = token_signals.list_outcomes(horizon="6h", limit=10)[0]
    finally:
        conn.close()

    assert result["outcomes_written"] == 1
    assert outcome["status"] == "settled"
    assert outcome["actual_return"] == pytest.approx(0.015)
    assert outcome["benchmark_return"] == pytest.approx(0.0)
    assert outcome["abnormal_return"] == pytest.approx(0.015)
    assert outcome["realized_vol"] == pytest.approx(0.03)
    assert outcome["normalized_outcome"] == pytest.approx(0.5)


def test_settle_token_signal_records_missing_exit_status(tmp_path):
    conn, evidence, tokens, token_signals = open_settlement_repos(tmp_path)
    try:
        decision_ms = 1_700_000_000_000
        identity = add_market(evidence, tokens, event_id="market-entry", token_id_time=decision_ms + 60_000, price=1.0)
        token_signals.create_snapshot(
            **snapshot_payload(
                snapshot_id="snapshot-missing-exit",
                token_id=identity.token_id,
                identity_key=identity.token_id,
                decision_time_ms=decision_ms,
            )
        )

        result = settle_token_signal_snapshots(
            repository=token_signals,
            tokens=tokens,
            horizon="6h",
            now_ms=decision_ms + 6 * 60 * 60_000 + 1,
            limit=10,
        )
        outcome = token_signals.list_outcomes(horizon="6h", limit=10)[0]
    finally:
        conn.close()

    assert result["missing_exit"] == 1
    assert outcome["status"] == "missing_exit"
    assert outcome["market_coverage_status"] == "missing_exit"
    assert outcome["normalized_outcome"] is None
