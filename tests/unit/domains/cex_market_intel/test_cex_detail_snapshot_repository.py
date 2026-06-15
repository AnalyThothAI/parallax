from __future__ import annotations

import inspect
from decimal import Decimal

import pytest

from parallax.domains.cex_market_intel.repositories.cex_detail_snapshot_repository import (
    CexDetailSnapshotRepository,
    _detail_payload_hash,
)


def test_detail_payload_hash_ignores_computed_at_and_computed_source_ref_timestamps():
    first = _snapshot(computed_at_ms=1_778_000_000_000, observed_at_ms=None)
    second = _snapshot(computed_at_ms=1_778_000_999_999, observed_at_ms=None)

    assert _detail_payload_hash(first) == _detail_payload_hash(second)


def test_detail_payload_hash_ignores_computed_fallback_observed_timestamps():
    first = _snapshot(
        computed_at_ms=1_778_000_000_000,
        observed_at_ms=1_778_000_000_000,
        observed_at_source="computed",
    )
    second = _snapshot(
        computed_at_ms=1_778_000_999_999,
        observed_at_ms=1_778_000_999_999,
        observed_at_source="computed",
    )

    assert _detail_payload_hash(first) == _detail_payload_hash(second)


def test_detail_payload_hash_keeps_provider_observed_market_freshness():
    first = _snapshot(
        computed_at_ms=1_778_000_000_000,
        observed_at_ms=1_778_000_000_123,
        observed_at_source="provider",
    )
    second = _snapshot(
        computed_at_ms=1_778_000_000_000,
        observed_at_ms=1_778_000_000_456,
        observed_at_source="provider",
    )

    assert _detail_payload_hash(first) != _detail_payload_hash(second)


def test_detail_payload_hash_does_not_keep_legacy_decimal_float_compatibility():
    decimal_snapshot = _snapshot(
        computed_at_ms=1_778_000_000_000,
        price_usd=Decimal("72000.0"),
        mark_price=Decimal("72001.0"),
        funding_rate=Decimal("0.000100"),
        volume_24h_usd=Decimal("1000000.0"),
        open_interest_usd=Decimal("2000000.0"),
        level_price=Decimal("73000.0"),
        level_size=Decimal("2000000.0"),
    )
    float_snapshot = _snapshot(
        computed_at_ms=1_778_000_000_000,
        price_usd=72000.0,
        mark_price=72001.0,
        funding_rate=0.0001,
        volume_24h_usd=1_000_000.0,
        open_interest_usd=2_000_000.0,
        level_price=73_000.0,
        level_size=2_000_000.0,
    )

    assert _detail_payload_hash(decimal_snapshot) != _detail_payload_hash(float_snapshot)


def test_detail_payload_hash_keeps_timestamp_rules_without_migration_golden():
    computed_runtime_snapshot = _snapshot(
        computed_at_ms=1_778_000_999_999,
        observed_at_ms=1_778_000_999_999,
        observed_at_source="computed",
        price_usd=72000.0,
        mark_price=72001.0,
        funding_rate=0.0001,
        volume_24h_usd=1_000_000.0,
        open_interest_usd=2_000_000.0,
        level_price=73_000.0,
        level_size=2_000_000.0,
    )
    provider_runtime_snapshot = _snapshot(
        computed_at_ms=1_778_000_999_999,
        observed_at_ms=1_778_000_123_456,
        observed_at_source="provider",
        price_usd=72000.0,
        mark_price=72001.0,
        funding_rate=0.0001,
        volume_24h_usd=1_000_000.0,
        open_interest_usd=2_000_000.0,
        level_price=73_000.0,
        level_size=2_000_000.0,
    )
    changed_provider_runtime_snapshot = _snapshot(
        computed_at_ms=1_778_000_999_999,
        observed_at_ms=1_778_000_654_321,
        observed_at_source="provider",
        price_usd=72000.0,
        mark_price=72001.0,
        funding_rate=0.0001,
        volume_24h_usd=1_000_000.0,
        open_interest_usd=2_000_000.0,
        level_price=73_000.0,
        level_size=2_000_000.0,
    )

    computed_hash = _detail_payload_hash(computed_runtime_snapshot)
    provider_hash = _detail_payload_hash(provider_runtime_snapshot)

    assert provider_hash != computed_hash
    assert _detail_payload_hash(changed_provider_runtime_snapshot) != provider_hash


def test_detail_payload_hash_rejects_legacy_level_band_keys():
    snapshot = _snapshot(computed_at_ms=1_778_000_000_000)
    snapshot["level_bands"] = [{123: "legacy"}]

    with pytest.raises(ValueError, match="current payload hash payload has non-string keys"):
        _detail_payload_hash(snapshot)


def test_detail_payload_hash_rejects_legacy_source_ref_keys():
    snapshot = _snapshot(
        computed_at_ms=1_778_000_000_000,
        observed_at_ms=1_778_000_000_123,
        observed_at_source="provider",
    )
    snapshot["source_refs"] = [{123: "legacy"}]

    with pytest.raises(ValueError, match="current payload hash payload has non-string keys"):
        _detail_payload_hash(snapshot)


@pytest.mark.parametrize(
    "field",
    ("snapshot_id", "target_type", "target_id", "exchange", "native_market_id", "base_symbol", "quote_symbol"),
)
def test_detail_payload_hash_requires_formal_snapshot_identity_without_defaults(field):
    snapshot = _snapshot(computed_at_ms=1_778_000_000_000)
    snapshot[field] = ""

    with pytest.raises(ValueError, match=f"cex_detail_snapshot_identity_required:{field}"):
        _detail_payload_hash(snapshot)


@pytest.mark.parametrize("field", ("status", "baseline_status", "coinglass_status"))
def test_detail_payload_hash_requires_formal_snapshot_status_without_defaults(field):
    snapshot = _snapshot(computed_at_ms=1_778_000_000_000)
    snapshot[field] = ""

    with pytest.raises(ValueError, match=f"cex_detail_snapshot_status_required:{field}"):
        _detail_payload_hash(snapshot)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("status", "stale"),
        ("baseline_status", "partial"),
        ("coinglass_status", "missing"),
    ),
)
def test_detail_payload_hash_rejects_unknown_snapshot_status_values(field, value):
    snapshot = _snapshot(computed_at_ms=1_778_000_000_000)
    snapshot[field] = value

    with pytest.raises(ValueError, match=f"cex_detail_snapshot_status_invalid:{field}"):
        _detail_payload_hash(snapshot)


@pytest.mark.parametrize(
    ("source", "match"),
    (
        (None, "cex_detail_snapshot_observation_required:observed_at_source"),
        ("clock", "cex_detail_snapshot_observation_invalid:observed_at_source"),
    ),
)
def test_detail_payload_hash_requires_observed_source_when_timestamp_is_present(source, match):
    snapshot = _snapshot(
        computed_at_ms=1_778_000_000_000,
        observed_at_ms=1_778_000_000_123,
        observed_at_source=source,
    )

    with pytest.raises(ValueError, match=match):
        _detail_payload_hash(snapshot)


@pytest.mark.parametrize("field", ("level_bands", "degraded_reasons", "source_refs"))
def test_detail_payload_hash_requires_formal_list_payload_fields_without_defaults(field: str):
    snapshot = _snapshot(computed_at_ms=1_778_000_000_000)
    snapshot.pop(field)

    with pytest.raises(ValueError, match=f"cex_detail_snapshot_payload_required:{field}"):
        _detail_payload_hash(snapshot)


@pytest.mark.parametrize("field", ("level_bands", "degraded_reasons", "source_refs"))
def test_detail_payload_hash_rejects_non_list_payload_fields(field: str):
    snapshot = _snapshot(computed_at_ms=1_778_000_000_000)
    snapshot[field] = {"legacy": True}

    with pytest.raises(ValueError, match=f"cex_detail_snapshot_payload_invalid:{field}"):
        _detail_payload_hash(snapshot)


@pytest.mark.parametrize("field", ("level_bands_json", "degraded_reasons_json", "source_refs_json"))
def test_detail_payload_hash_rejects_legacy_json_writer_aliases(field: str) -> None:
    snapshot = _snapshot(computed_at_ms=1_778_000_000_000)
    snapshot[field] = [{"legacy": True}]

    with pytest.raises(ValueError, match=f"cex_detail_snapshot_legacy_json_alias:{field}"):
        _detail_payload_hash(snapshot)


def test_upsert_many_returns_changed_rowcount_and_gates_on_payload_hash():
    conn = _RecordingConn(rowcounts=[1, 0])
    first = _snapshot(computed_at_ms=1_778_000_000_000)
    second = _snapshot(computed_at_ms=1_778_000_999_999)

    written = CexDetailSnapshotRepository(conn).upsert_many([first, second])

    assert written == 1
    assert conn.commits == 1
    all_sql = "\n".join(conn.sql_calls)
    assert "payload_hash" in all_sql
    assert "WHERE cex_detail_snapshots.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash" in all_sql


def test_upsert_many_requires_connection_transaction_before_sql_when_committing():
    conn = _NoTransactionConn(rowcounts=[1])
    snapshot = _snapshot(computed_at_ms=1_778_000_000_000)

    with pytest.raises(TypeError, match="cex_detail_snapshot_transaction_required"):
        CexDetailSnapshotRepository(conn).upsert_many([snapshot])

    assert conn.sql_calls == []


def test_upsert_many_accepts_commit_false_without_committing():
    conn = _RecordingConn(rowcounts=[1, 0])
    first = _snapshot(computed_at_ms=1_778_000_000_000)
    second = _snapshot(computed_at_ms=1_778_000_999_999)

    written = CexDetailSnapshotRepository(conn).upsert_many([first, second], commit=False)

    assert written == 1
    assert conn.commits == 0


def test_upsert_many_commit_flag_is_keyword_only_real_repository_api():
    signature = inspect.signature(CexDetailSnapshotRepository.upsert_many)

    assert signature.parameters["commit"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["commit"].default is True


def test_upsert_snapshot_requires_connection_transaction_before_sql_when_committing():
    conn = _NoTransactionConn(rowcounts=[1])
    snapshot = _snapshot(computed_at_ms=1_778_000_000_000)

    with pytest.raises(TypeError, match="cex_detail_snapshot_transaction_required"):
        CexDetailSnapshotRepository(conn).upsert_snapshot(snapshot)

    assert conn.sql_calls == []


@pytest.mark.parametrize(
    "field",
    ("snapshot_id", "target_type", "target_id", "exchange", "native_market_id", "base_symbol", "quote_symbol"),
)
def test_upsert_snapshot_requires_formal_snapshot_identity_before_sql(field):
    conn = _RecordingConn(rowcounts=[1])
    snapshot = _snapshot(computed_at_ms=1_778_000_000_000)
    snapshot[field] = ""

    with pytest.raises(ValueError, match=f"cex_detail_snapshot_identity_required:{field}"):
        CexDetailSnapshotRepository(conn).upsert_snapshot(snapshot, commit=False)

    assert conn.sql_calls == []


@pytest.mark.parametrize("field", ("status", "baseline_status", "coinglass_status"))
def test_upsert_snapshot_requires_formal_snapshot_status_before_sql(field):
    conn = _RecordingConn(rowcounts=[1])
    snapshot = _snapshot(computed_at_ms=1_778_000_000_000)
    snapshot[field] = ""

    with pytest.raises(ValueError, match=f"cex_detail_snapshot_status_required:{field}"):
        CexDetailSnapshotRepository(conn).upsert_snapshot(snapshot, commit=False)

    assert conn.sql_calls == []


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("status", "stale"),
        ("baseline_status", "partial"),
        ("coinglass_status", "missing"),
    ),
)
def test_upsert_snapshot_rejects_unknown_snapshot_status_values_before_sql(field, value):
    conn = _RecordingConn(rowcounts=[1])
    snapshot = _snapshot(computed_at_ms=1_778_000_000_000)
    snapshot[field] = value

    with pytest.raises(ValueError, match=f"cex_detail_snapshot_status_invalid:{field}"):
        CexDetailSnapshotRepository(conn).upsert_snapshot(snapshot, commit=False)

    assert conn.sql_calls == []


@pytest.mark.parametrize(
    ("source", "match"),
    (
        (None, "cex_detail_snapshot_observation_required:observed_at_source"),
        ("clock", "cex_detail_snapshot_observation_invalid:observed_at_source"),
    ),
)
def test_upsert_snapshot_requires_observed_source_when_timestamp_is_present_before_sql(source, match):
    conn = _RecordingConn(rowcounts=[1])
    snapshot = _snapshot(
        computed_at_ms=1_778_000_000_000,
        observed_at_ms=1_778_000_000_123,
        observed_at_source=source,
    )

    with pytest.raises(ValueError, match=match):
        CexDetailSnapshotRepository(conn).upsert_snapshot(snapshot, commit=False)

    assert conn.sql_calls == []


@pytest.mark.parametrize("field", ("level_bands", "degraded_reasons", "source_refs"))
def test_upsert_snapshot_requires_formal_list_payload_fields_before_sql(field: str):
    conn = _RecordingConn(rowcounts=[1])
    snapshot = _snapshot(computed_at_ms=1_778_000_000_000)
    snapshot.pop(field)

    with pytest.raises(ValueError, match=f"cex_detail_snapshot_payload_required:{field}"):
        CexDetailSnapshotRepository(conn).upsert_snapshot(snapshot, commit=False)

    assert conn.sql_calls == []


@pytest.mark.parametrize("field", ("level_bands", "degraded_reasons", "source_refs"))
def test_upsert_snapshot_rejects_non_list_payload_fields_before_sql(field: str):
    conn = _RecordingConn(rowcounts=[1])
    snapshot = _snapshot(computed_at_ms=1_778_000_000_000)
    snapshot[field] = {"legacy": True}

    with pytest.raises(ValueError, match=f"cex_detail_snapshot_payload_invalid:{field}"):
        CexDetailSnapshotRepository(conn).upsert_snapshot(snapshot, commit=False)

    assert conn.sql_calls == []


@pytest.mark.parametrize("field", ("level_bands_json", "degraded_reasons_json", "source_refs_json"))
def test_upsert_snapshot_rejects_legacy_json_writer_aliases_before_sql(field: str) -> None:
    conn = _RecordingConn(rowcounts=[1])
    snapshot = _snapshot(computed_at_ms=1_778_000_000_000)
    snapshot[field] = [{"legacy": True}]

    with pytest.raises(ValueError, match=f"cex_detail_snapshot_legacy_json_alias:{field}"):
        CexDetailSnapshotRepository(conn).upsert_snapshot(snapshot, commit=False)

    assert conn.sql_calls == []


def test_computed_at_change_only_does_not_update_detail_serving_row():
    conn = _RecordingConn(rowcounts=[1, 0])
    repo = CexDetailSnapshotRepository(conn)

    first = _snapshot(computed_at_ms=1_778_000_000_000)
    second = _snapshot(computed_at_ms=1_778_000_999_999)

    first_written = repo.upsert_snapshot(first)
    second_written = repo.upsert_snapshot(second)

    assert _detail_payload_hash(first) == _detail_payload_hash(second)
    assert first_written == 1
    assert second_written == 0


def test_upsert_snapshot_requires_real_cursor_rowcount():
    conn = _MissingRowcountConn()

    with pytest.raises(TypeError, match="cex_detail_snapshot_rowcount_required"):
        CexDetailSnapshotRepository(conn).upsert_snapshot(
            _snapshot(computed_at_ms=1_778_000_000_000),
            commit=False,
        )

    assert "INSERT INTO cex_detail_snapshots" in "\n".join(conn.sql_calls)


@pytest.mark.parametrize("rowcount", ("unknown", True, -1))
def test_upsert_snapshot_rejects_invalid_cursor_rowcount(rowcount: object):
    conn = _RecordingConn(rowcounts=[rowcount])

    with pytest.raises(TypeError, match="cex_detail_snapshot_rowcount_invalid"):
        CexDetailSnapshotRepository(conn).upsert_snapshot(
            _snapshot(computed_at_ms=1_778_000_000_000),
            commit=False,
        )

    assert "INSERT INTO cex_detail_snapshots" in "\n".join(conn.sql_calls)


@pytest.mark.parametrize("field", ("target_type", "target_id"))
def test_latest_snapshot_requires_formal_query_identity_before_sql(field: str) -> None:
    conn = _RecordingConn(rowcounts=[0])
    params = {"target_type": "CexToken", "target_id": "cex_token:BTC"}
    params[field] = " "

    with pytest.raises(ValueError, match=f"cex_detail_snapshot_query_identity_required:{field}"):
        CexDetailSnapshotRepository(conn).latest_snapshot(**params)

    assert conn.sql_calls == []


@pytest.mark.parametrize("field", ("exchange", "native_market_id"))
def test_latest_snapshot_by_market_requires_formal_query_identity_before_sql(field: str) -> None:
    conn = _RecordingConn(rowcounts=[0])
    params = {"exchange": "binance", "native_market_id": "BTCUSDT"}
    params[field] = " "

    with pytest.raises(ValueError, match=f"cex_detail_snapshot_query_identity_required:{field}"):
        CexDetailSnapshotRepository(conn).latest_snapshot_by_market(**params)

    assert conn.sql_calls == []


def _snapshot(
    *,
    computed_at_ms: int,
    observed_at_ms: int | None = None,
    observed_at_source: str | None = None,
    price_usd=72_000.0,
    mark_price=72_001.0,
    funding_rate=0.0001,
    volume_24h_usd=1_000_000.0,
    open_interest_usd=2_000_000.0,
    level_price=73_000.0,
    level_size=2_000_000.0,
) -> dict:
    source_observed_at_ms = observed_at_ms or computed_at_ms
    snapshot = {
        "snapshot_id": "cex-detail:binance:BTCUSDT",
        "target_type": "CexToken",
        "target_id": "cex_token:BTC",
        "exchange": "binance",
        "native_market_id": "BTCUSDT",
        "base_symbol": "BTC",
        "quote_symbol": "USDT",
        "status": "ready",
        "baseline_status": "ready",
        "coinglass_status": "ready",
        "price_usd": price_usd,
        "mark_price": mark_price,
        "funding_rate": funding_rate,
        "volume_24h_usd": volume_24h_usd,
        "open_interest_usd": open_interest_usd,
        "oi_change_pct_1h": 10.0,
        "oi_change_pct_4h": 12.0,
        "oi_change_pct_24h": 25.0,
        "cvd_delta_1h": 100.0,
        "cvd_delta_4h": 250.0,
        "cvd_delta_24h": 500.0,
        "long_short_ratio": 1.2,
        "top_trader_position_ratio": 1.4,
        "level_bands": [{"kind": "resistance", "price": level_price, "size": level_size}],
        "degraded_reasons": [],
        "source_refs": [
            {
                "ref_id": "market:cex:binance:BTCUSDT",
                "ref_type": "market",
                "source_table": "cex_detail_snapshots",
                "source_id": "pf-btc",
                "observed_at_ms": source_observed_at_ms,
                "quality": "high",
            }
        ],
        "observed_at_ms": observed_at_ms,
        "computed_at_ms": computed_at_ms,
    }
    if observed_at_source:
        snapshot["observed_at_source"] = observed_at_source
    return snapshot


class _RecordingCursor:
    def __init__(self, rowcount: object, *, row=None) -> None:
        self.rowcount = rowcount
        self.row = row

    def fetchone(self):
        return self.row


class _RecordingConn:
    def __init__(self, *, rowcounts: list[object]) -> None:
        self.sql_calls: list[str] = []
        self.params_calls: list[tuple] = []
        self.rowcounts = list(rowcounts)
        self.commits = 0
        self.rollbacks = 0
        self.transaction_depth = 0

    def execute(self, sql, params=None):
        self.sql_calls.append(str(sql))
        self.params_calls.append(tuple(params or ()))
        return _RecordingCursor(self.rowcounts.pop(0))

    def commit(self):
        self.commits += 1

    def transaction(self):
        return _Transaction(self)


class _NoTransactionConn(_RecordingConn):
    transaction = None


class _MissingRowcountConn(_RecordingConn):
    def __init__(self) -> None:
        super().__init__(rowcounts=[])

    def execute(self, sql, params=None):
        self.sql_calls.append(str(sql))
        self.params_calls.append(tuple(params or ()))
        return _MissingRowcountCursor()


class _MissingRowcountCursor:
    pass


class _Transaction:
    def __init__(self, conn: _RecordingConn) -> None:
        self.conn = conn

    def __enter__(self):
        self.conn.transaction_depth += 1
        return self.conn

    def __exit__(self, exc_type, *_args):
        self.conn.transaction_depth -= 1
        if exc_type is None:
            self.conn.commits += 1
        else:
            self.conn.rollbacks += 1
        return False
