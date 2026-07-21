from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CEX_OI_REPOSITORY = ROOT / "src/parallax/domains/cex_market_intel/repositories/cex_oi_radar_repository.py"
CEX_DETAIL_REPOSITORY = ROOT / "src/parallax/domains/cex_market_intel/repositories/cex_detail_snapshot_repository.py"
CEX_DETAIL_BUILDER = ROOT / "src/parallax/domains/cex_market_intel/services/cex_detail_snapshot_builder.py"
CEX_BINANCE_OI_BUILDER = ROOT / "src/parallax/domains/cex_market_intel/services/binance_oi_radar_builder.py"
CEX_COINGLASS_DETAIL_ENRICHER = ROOT / "src/parallax/domains/cex_market_intel/services/coinglass_detail_enricher.py"
CEX_OI_WORKER = ROOT / "src/parallax/domains/cex_market_intel/runtime/cex_oi_radar_board_worker.py"


def test_cex_oi_board_publish_uses_row_level_serving_updates() -> None:
    text = CEX_OI_REPOSITORY.read_text(encoding="utf-8")

    assert "AND NOT (row_id = ANY(%s::text[]))" in text
    assert "WHERE cex_oi_radar_rows.rank IS DISTINCT FROM excluded.rank" in text
    assert "computed_at_ms IS DISTINCT FROM excluded.computed_at_ms" not in text
    assert "def _cursor_rowcount(cursor: Any, *, default: int)" not in text
    assert 'getattr(cursor, "rowcount", default)' not in text
    assert "except (TypeError, ValueError):\n        return default" not in text
    assert "return max(0, int(rowcount))" not in text
    assert "isinstance(rowcount, bool)" in text
    assert "_cursor_rowcount(delete_cursor, default=" not in text
    assert "_cursor_rowcount(upsert_cursor, default=" not in text
    assert "_cursor_rowcount(delete_cursor)" in text
    assert "_cursor_rowcount(upsert_cursor)" in text


def test_cex_oi_board_payload_hash_ignores_computed_runtime_timestamps() -> None:
    text = CEX_OI_REPOSITORY.read_text(encoding="utf-8")

    assert '"observed_at_ms": row.get("observed_at_ms")' not in text
    assert "_provider_observed_at_ms(row)" in text
    assert "_board_hash_source_frontier_ms(" in text
    assert "source_frontier_ms=source_frontier_ms" in text


def test_cex_oi_board_repository_requires_formal_current_identity_without_defaults() -> None:
    text = CEX_OI_REPOSITORY.read_text(encoding="utf-8")
    forbidden = (
        "board_period = str(period)",
        '_row_id(board_period, str(row["target_id"]))',
        '"target_id": row["target_id"]',
        '"native_market_id": row["native_market_id"]',
        '"base_symbol": row["base_symbol"]',
        '"quote_symbol": row["quote_symbol"]',
        'row["base_symbol"]',
        'row["quote_symbol"]',
        'int(row.get("observed_at_ms") or computed_at)',
        'return str(row.get("observed_at_source") or "").strip().lower()',
        'Jsonb(row.get("score_components") or {})',
        '"score_components": row.get("score_components") or {}',
    )
    required = (
        '_required_board_text(period, "period")',
        '_required_board_row_text(row, "target_id")',
        '_required_board_row_text(row, "native_market_id")',
        '_required_board_row_text(row, "base_symbol")',
        '_required_board_row_text(row, "quote_symbol")',
        "_required_observed_at_ms(row)",
        "_required_observed_at_source(row)",
        "_required_score_components(row)",
    )

    assert [token for token in forbidden if token in text] == []
    assert [token for token in required if token not in text] == []


def test_cex_read_model_repositories_require_explicit_transactions() -> None:
    repository_paths = (
        CEX_OI_REPOSITORY,
        CEX_DETAIL_REPOSITORY,
    )

    for path in repository_paths:
        text = path.read_text(encoding="utf-8")
        assert "self.conn.commit()" not in text
        assert "def _transaction(conn: Any)" in text
        assert "transaction = conn.transaction" in text
        assert 'getattr(conn, "transaction", None)' not in text
        assert "nullcontext" not in text

    worker_text = CEX_OI_WORKER.read_text(encoding="utf-8")
    assert worker_text.count("repos.transaction()") >= 4
    assert "repos.cex_oi_radar.publish_board(\n" in worker_text
    assert "repos.cex_oi_radar.record_attempt_failure(\n" in worker_text
    assert "commit=False" in worker_text


def test_cex_oi_runtime_limits_are_formal_contracts_without_runtime_repairs() -> None:
    sources = {
        "worker": CEX_OI_WORKER.read_text(encoding="utf-8"),
        "repository": CEX_OI_REPOSITORY.read_text(encoding="utf-8"),
        "builder": CEX_BINANCE_OI_BUILDER.read_text(encoding="utf-8"),
        "enricher": CEX_COINGLASS_DETAIL_ENRICHER.read_text(encoding="utf-8"),
    }
    forbidden = (
        "max(1, int(limit))",
        "max(1, int(self.settings.batch_size))",
        "max(1, min(int(self.settings.universe_limit), batch_size))",
        "universe[: max(1, int(limit))]",
        "bands[: max(0, int(limit))]",
    )
    required = (
        "cex_oi_radar_board_batch_size_required",
        "cex_oi_radar_board_universe_limit_required",
        "cex_oi_radar_universe_limit_required",
        "cex_oi_radar_latest_board_limit_required",
        "cex_oi_radar_limit_required",
        "coinglass_detail_enrichment_limit_required",
        "coinglass_detail_level_limit_required",
        "isinstance(value, bool) or not isinstance(value, int)",
    )

    violations = {name: [token for token in forbidden if token in source] for name, source in sources.items()}
    combined = "\n".join(sources.values())

    assert violations == {name: [] for name in sources}
    assert [token for token in required if token not in combined] == []


def test_cex_detail_snapshot_repository_requires_formal_identity_without_defaults() -> None:
    text = CEX_DETAIL_REPOSITORY.read_text(encoding="utf-8")
    forbidden = (
        'snapshot.get("target_type") or "CexToken"',
        'snapshot.get("exchange") or "binance"',
        'snapshot.get("base_symbol") or ""',
        'snapshot.get("quote_symbol") or "USDT"',
        'snapshot.get("status") or "partial"',
        'snapshot.get("baseline_status") or "missing"',
        'snapshot.get("coinglass_status") or "unavailable"',
        'snapshot.get("level_bands") or snapshot.get("level_bands_json")',
        'snapshot.get("degraded_reasons") or snapshot.get("degraded_reasons_json")',
        'snapshot.get("source_refs") or snapshot.get("source_refs_json")',
        'source = str(snapshot.get("observed_at_source") or "").strip().lower()',
        "computed_at_ms is not None and observed_at_ms == computed_at_ms",
        'Jsonb(list(snapshot.get("level_bands") or []))',
        'Jsonb(list(snapshot.get("degraded_reasons") or []))',
        'Jsonb(list(snapshot.get("source_refs") or []))',
        '"snapshot_id"',
        "(target_type, target_id)",
        "(exchange.lower(), native_market_id.upper())",
    )
    required = (
        '_required_snapshot_text(snapshot, "target_type")',
        '_required_snapshot_text(snapshot, "target_id")',
        '_required_snapshot_text(snapshot, "exchange")',
        '_required_snapshot_text(snapshot, "native_market_id")',
        '_required_snapshot_text(snapshot, "base_symbol")',
        '_required_snapshot_text(snapshot, "quote_symbol")',
        '_required_snapshot_status(snapshot, "status")',
        '_required_snapshot_status(snapshot, "baseline_status")',
        '_required_snapshot_status(snapshot, "coinglass_status")',
        "_reject_legacy_json_aliases(snapshot)",
        "_required_observed_at_source(snapshot)",
        '_required_snapshot_list(snapshot, "level_bands")',
        '_required_snapshot_list(snapshot, "degraded_reasons")',
        '_required_snapshot_list(snapshot, "source_refs")',
        '_required_query_text(target_type, "target_type")',
        '_required_query_text(target_id, "target_id")',
        '_required_query_text(exchange, "exchange")',
        '_required_query_text(native_market_id, "native_market_id")',
    )

    assert [token for token in forbidden if token in text] == []
    assert [token for token in required if token not in text] == []


def test_cex_detail_snapshot_repository_requires_real_cursor_rowcount() -> None:
    text = CEX_DETAIL_REPOSITORY.read_text(encoding="utf-8")

    assert 'getattr(cursor, "rowcount", 0)' not in text
    assert 'int(getattr(cursor, "rowcount", 0) or 0)' not in text
    assert "return max(int(rowcount), 0)" not in text
    assert "isinstance(rowcount, bool)" in text
    assert "_rowcount(cursor)" in text
    assert "cex_detail_snapshot_rowcount_required" in text
    assert "cex_detail_snapshot_rowcount_invalid" in text


def test_cex_detail_snapshot_builder_requires_identity_before_current_snapshot() -> None:
    builder_text = CEX_DETAIL_BUILDER.read_text(encoding="utf-8")
    worker_text = CEX_OI_WORKER.read_text(encoding="utf-8")
    forbidden = (
        'return target_id or "cex_token:unknown"',
        '"cex_token:unknown"',
        'if row.get("native_market_id")',
        'f"cex-detail:binance:{native_market_id}"',
        '"exchange": str(row.get("exchange") or "binance").lower()',
        'f"market:cex:binance:{native_market_id}"',
        '_symbol(row.get("quote_symbol")) or "USDT"',
        'row.get("coinglass_status") or "unavailable"',
        'row.get("level_bands") or row.get("level_bands_json")',
        '_list_of_dicts(row.get("level_bands"))',
        'str(period or "").strip().lower()',
        'source = str(row.get("observed_at_source") or "").strip().lower()',
        "observed_at_ms is None or observed_at_ms == computed_at_ms",
        'or "unknown"',
        'band.get("kind") or "level"',
        "if price is None:\n            continue",
        '_strings(row.get("degraded_reasons"))',
        "def _strings(value: Any)",
    )
    builder_required = (
        '_required_symbol(row, "native_market_id")',
        '_required_symbol(row, "base_symbol")',
        '_required_symbol(row, "quote_symbol")',
        '_required_status(row, "coinglass_status")',
        "_required_period(period)",
        "_reject_legacy_json_aliases(row)",
        "_required_observed_at_ms(row)",
        "_required_observed_at_source(row)",
        "_required_level_bands(row)",
        "_required_degraded_reasons(row)",
        'raise ValueError("cex_detail_snapshot_identity_required:target_id")',
        '_required_text(exchange, "exchange")',
    )
    worker_required = ('build_cex_detail_snapshot(row=row, computed_at_ms=now, period=period, exchange="binance")',)

    assert [token for token in forbidden if token in builder_text] == []
    assert 'if row.get("native_market_id")' not in worker_text
    assert [token for token in builder_required if token not in builder_text] == []
    assert [token for token in worker_required if token not in worker_text] == []


def test_binance_oi_radar_builder_requires_market_identity_before_provider_io() -> None:
    text = CEX_BINANCE_OI_BUILDER.read_text(encoding="utf-8")
    forbidden = (
        "if not symbol:\n            continue",
        'str(route.get("native_market_id") or "").strip().upper()',
        'str(route.get("base_symbol") or "").strip().upper()',
    )
    required = (
        '_required_symbol(route, "native_market_id")',
        '_required_symbol(route, "base_symbol")',
        "client.list_24h_tickers()",
        "client.list_funding_premium()",
    )

    assert [token for token in forbidden if token in text] == []
    assert text.index('_required_symbol(route, "native_market_id")') < text.index("client.list_24h_tickers()")
    assert text.index('_required_symbol(route, "base_symbol")') < text.index("client.list_24h_tickers()")
    assert [token for token in required if token not in text] == []


def test_binance_oi_radar_builder_requires_formal_provider_dtos_without_attr_fallback() -> None:
    text = CEX_BINANCE_OI_BUILDER.read_text(encoding="utf-8")
    forbidden = (
        "def _attr(value: Any, name: str) -> Any:",
        "getattr(value, name, None)",
        '_attr(latest_oi, "open_interest_value")',
        '_attr(latest_oi, "observed_at_ms")',
        '_attr(previous_oi, "open_interest_value")',
        '_attr(premium, "last_funding_rate")',
        '_attr(ticker, "quote_volume_24h")',
        '"mark_price": _attr(premium, "mark_price") or _attr(ticker, "last_price")',
    )
    required = (
        "_open_interest_value(latest_oi)",
        "_open_interest_observed_at_ms(latest_oi)",
        "_funding_rate(premium)",
        "_quote_volume_24h(ticker)",
        "cex_oi_radar_provider_contract_required:open_interest_value",
        "mark_price = premium_mark_price if premium_mark_price is not None else ticker_last_price",
    )

    assert [token for token in forbidden if token in text] == []
    assert [token for token in required if token not in text] == []


def test_coinglass_detail_enricher_requires_base_symbol_before_provider_io() -> None:
    text = CEX_COINGLASS_DETAIL_ENRICHER.read_text(encoding="utf-8")
    forbidden = (
        'str(row.get("base_symbol") or "").strip().upper()',
        '"coinglass_symbol_missing"',
    )
    required = (
        '_required_symbol(row, "base_symbol")',
        "client.fetch_oi_history(",
    )

    assert [token for token in forbidden if token in text] == []
    assert text.index('_required_symbol(row, "base_symbol")') < text.index("client.fetch_oi_history(")
    assert [token for token in required if token not in text] == []


def test_coinglass_detail_enricher_requires_formal_degraded_reasons_without_list_fallback() -> None:
    text = CEX_COINGLASS_DETAIL_ENRICHER.read_text(encoding="utf-8")
    forbidden = (
        'list(row.get("degraded_reasons") or [])',
        '"degraded_reasons": [*list(',
    )
    required = (
        "_inherited_degraded_reasons(row)",
        "coinglass_detail_degraded_reasons_invalid",
        "coinglass_detail_degraded_reason_invalid:item",
    )

    assert [token for token in forbidden if token in text] == []
    assert [token for token in required if token not in text] == []
