from __future__ import annotations

import pytest

from parallax.domains.cex_market_intel.services.cex_detail_snapshot_builder import (
    build_cex_detail_snapshot,
)


def test_build_cex_detail_snapshot_keeps_non_hourly_oi_delta_out_of_1h_slot() -> None:
    snapshot = build_cex_detail_snapshot(
        row={
            "target_id": "binance:BTCUSDT",
            "cex_token_id": "cex_token:BTC",
            "native_market_id": "BTCUSDT",
            "base_symbol": "BTC",
            "quote_symbol": "USDT",
            "pricefeed_id": "pricefeed:cex:binance:swap:BTCUSDT",
            "mark_price": 101.0,
            "open_interest_usd": 1100.0,
            "open_interest_change_pct_1h": 10.0,
            "volume_24h_usd": 10_000_000.0,
            "funding_rate": 0.0001,
            "coinglass_status": "unavailable",
            "observed_at_ms": 1_778_000_000_000,
            "observed_at_source": "computed",
        },
        computed_at_ms=1_778_000_000_000,
        period="5m",
        exchange="binance",
    )

    assert snapshot["target_type"] == "CexToken"
    assert snapshot["target_id"] == "cex_token:BTC"
    assert snapshot["baseline_status"] == "ready"
    assert snapshot["coinglass_status"] == "unavailable"
    assert snapshot["oi_change_pct_1h"] is None
    assert snapshot["observed_at_source"] == "computed"
    assert "oi_change_period_5m_not_1h" in snapshot["degraded_reasons"]
    assert "metric:cex:open_interest_usd:BTCUSDT" in [ref["ref_id"] for ref in snapshot["source_refs"]]


def test_build_cex_detail_snapshot_requires_period_before_oi_delta_mapping() -> None:
    with pytest.raises(ValueError, match="cex_detail_snapshot_identity_required:period"):
        build_cex_detail_snapshot(
            row={
                "target_id": "binance:BTCUSDT",
                "cex_token_id": "cex_token:BTC",
                "native_market_id": "BTCUSDT",
                "base_symbol": "BTC",
                "quote_symbol": "USDT",
                "open_interest_usd": 1100.0,
                "open_interest_change_pct_1h": 10.0,
                "coinglass_status": "unavailable",
                "observed_at_ms": 1_778_000_000_000,
                "observed_at_source": "computed",
            },
            computed_at_ms=1_778_000_000_000,
            period=" ",
            exchange="binance",
        )


def test_build_cex_detail_snapshot_rejects_legacy_level_bands_json_alias() -> None:
    with pytest.raises(ValueError, match="cex_detail_snapshot_legacy_json_alias:level_bands_json"):
        build_cex_detail_snapshot(
            row={
                "target_id": "binance:BTCUSDT",
                "cex_token_id": "cex_token:BTC",
                "native_market_id": "BTCUSDT",
                "base_symbol": "BTC",
                "quote_symbol": "USDT",
                "open_interest_usd": 1100.0,
                "coinglass_status": "ready",
                "level_bands_json": [{"kind": "resistance", "price": 120.0, "size": 10_000.0}],
                "observed_at_ms": 1_778_000_000_000,
                "observed_at_source": "provider",
            },
            computed_at_ms=1_778_000_000_000,
            period="1h",
            exchange="binance",
        )


@pytest.mark.parametrize(
    ("level_bands", "match"),
    (
        ([{"price": 120.0, "size": 10_000.0}], "cex_detail_snapshot_level_band_required:kind"),
        ([{"kind": "resistance", "size": 10_000.0}], "cex_detail_snapshot_level_band_required:price"),
        (["legacy"], "cex_detail_snapshot_level_band_invalid:item"),
        ({"kind": "resistance", "price": 120.0}, "cex_detail_snapshot_level_bands_invalid"),
    ),
)
def test_build_cex_detail_snapshot_requires_formal_level_band_shape(level_bands, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        build_cex_detail_snapshot(
            row={
                "target_id": "binance:BTCUSDT",
                "cex_token_id": "cex_token:BTC",
                "native_market_id": "BTCUSDT",
                "base_symbol": "BTC",
                "quote_symbol": "USDT",
                "open_interest_usd": 1100.0,
                "coinglass_status": "ready",
                "level_bands": level_bands,
                "observed_at_ms": 1_778_000_000_000,
                "observed_at_source": "provider",
            },
            computed_at_ms=1_778_000_000_000,
            period="1h",
            exchange="binance",
        )


@pytest.mark.parametrize(
    ("degraded_reasons", "match"),
    (
        ("legacy", "cex_detail_snapshot_degraded_reasons_invalid"),
        ({"reason": "legacy"}, "cex_detail_snapshot_degraded_reasons_invalid"),
        ([123], "cex_detail_snapshot_degraded_reason_invalid:item"),
        ([""], "cex_detail_snapshot_degraded_reason_invalid:item"),
    ),
)
def test_build_cex_detail_snapshot_requires_formal_degraded_reasons_shape(degraded_reasons, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        build_cex_detail_snapshot(
            row={
                "target_id": "binance:BTCUSDT",
                "cex_token_id": "cex_token:BTC",
                "native_market_id": "BTCUSDT",
                "base_symbol": "BTC",
                "quote_symbol": "USDT",
                "open_interest_usd": 1100.0,
                "coinglass_status": "partial",
                "degraded_reasons": degraded_reasons,
                "observed_at_ms": 1_778_000_000_000,
                "observed_at_source": "provider",
            },
            computed_at_ms=1_778_000_000_000,
            period="1h",
            exchange="binance",
        )


@pytest.mark.parametrize(
    ("field", "value", "match"),
    (
        ("observed_at_ms", None, "cex_detail_snapshot_observation_required:observed_at_ms"),
        ("observed_at_source", "", "cex_detail_snapshot_observation_required:observed_at_source"),
        ("observed_at_source", "clock", "cex_detail_snapshot_observation_invalid:observed_at_source"),
    ),
)
def test_build_cex_detail_snapshot_requires_formal_observation_contract(field: str, value, match: str) -> None:
    row = {
        "target_id": "binance:BTCUSDT",
        "cex_token_id": "cex_token:BTC",
        "native_market_id": "BTCUSDT",
        "base_symbol": "BTC",
        "quote_symbol": "USDT",
        "open_interest_usd": 1100.0,
        "coinglass_status": "unavailable",
        "observed_at_ms": 1_778_000_000_000,
        "observed_at_source": "provider",
    }
    row[field] = value

    with pytest.raises(ValueError, match=match):
        build_cex_detail_snapshot(
            row=row,
            computed_at_ms=1_778_000_000_000,
            period="1h",
            exchange="binance",
        )


def test_build_cex_detail_snapshot_maps_hourly_period_to_hourly_delta() -> None:
    snapshot = build_cex_detail_snapshot(
        row={
            "target_id": "binance:ETHUSDT",
            "cex_token_id": "cex_token:ETH",
            "native_market_id": "ETHUSDT",
            "base_symbol": "ETH",
            "quote_symbol": "USDT",
            "open_interest_usd": 2000.0,
            "open_interest_change_pct_1h": -2.5,
            "coinglass_status": "unavailable",
            "observed_at_ms": 1_778_000_000_000,
            "observed_at_source": "provider",
        },
        computed_at_ms=1_778_000_000_000,
        period="1h",
        exchange="binance",
    )

    assert snapshot["oi_change_pct_1h"] == -2.5
    assert "oi_change_period_1h_not_1h" not in snapshot["degraded_reasons"]


def test_build_cex_detail_snapshot_requires_native_market_id_for_current_identity() -> None:
    with pytest.raises(ValueError, match="cex_detail_snapshot_identity_required:native_market_id"):
        build_cex_detail_snapshot(
            row={
                "target_id": "binance:BTCUSDT",
                "cex_token_id": "cex_token:BTC",
                "base_symbol": "BTC",
                "open_interest_usd": 2000.0,
            },
            computed_at_ms=1_778_000_000_000,
            period="1h",
            exchange="binance",
        )


@pytest.mark.parametrize("target_id", ("binance:BTCUSDT", "cex_token:" + "unknown", ""))
def test_build_cex_detail_snapshot_requires_cex_target_identity_without_unknown_fallback(target_id: str) -> None:
    with pytest.raises(ValueError, match="cex_detail_snapshot_identity_required:target_id"):
        build_cex_detail_snapshot(
            row={
                "target_id": target_id,
                "native_market_id": "BTCUSDT",
                "quote_symbol": "USDT",
                "open_interest_usd": 2000.0,
            },
            computed_at_ms=1_778_000_000_000,
            period="1h",
            exchange="binance",
        )


def test_build_cex_detail_snapshot_can_derive_cex_target_from_stable_base_symbol() -> None:
    snapshot = build_cex_detail_snapshot(
        row={
            "target_id": "binance:BTCUSDT",
            "native_market_id": "BTCUSDT",
            "base_symbol": "BTC",
            "quote_symbol": "USDT",
            "open_interest_usd": 2000.0,
            "coinglass_status": "unavailable",
            "observed_at_ms": 1_778_000_000_000,
            "observed_at_source": "provider",
        },
        computed_at_ms=1_778_000_000_000,
        period="1h",
        exchange="binance",
    )

    assert snapshot["target_id"] == "cex_token:BTC"


def test_build_cex_detail_snapshot_requires_exchange_for_current_identity() -> None:
    with pytest.raises(ValueError, match="cex_detail_snapshot_identity_required:exchange"):
        build_cex_detail_snapshot(
            row={
                "target_id": "binance:BTCUSDT",
                "cex_token_id": "cex_token:BTC",
                "native_market_id": "BTCUSDT",
                "base_symbol": "BTC",
                "open_interest_usd": 2000.0,
            },
            computed_at_ms=1_778_000_000_000,
            period="1h",
            exchange=" ",
        )


def test_build_cex_detail_snapshot_requires_quote_symbol_without_usdt_default() -> None:
    with pytest.raises(ValueError, match="cex_detail_snapshot_identity_required:quote_symbol"):
        build_cex_detail_snapshot(
            row={
                "target_id": "binance:BTCUSDT",
                "cex_token_id": "cex_token:BTC",
                "native_market_id": "BTCUSDT",
                "base_symbol": "BTC",
                "quote_symbol": " ",
                "open_interest_usd": 2000.0,
            },
            computed_at_ms=1_778_000_000_000,
            period="1h",
            exchange="binance",
        )


def test_build_cex_detail_snapshot_requires_base_symbol_without_empty_current_row() -> None:
    with pytest.raises(ValueError, match="cex_detail_snapshot_identity_required:base_symbol"):
        build_cex_detail_snapshot(
            row={
                "target_id": "binance:BTCUSDT",
                "cex_token_id": "cex_token:BTC",
                "native_market_id": "BTCUSDT",
                "base_symbol": " ",
                "quote_symbol": "USDT",
                "open_interest_usd": 2000.0,
            },
            computed_at_ms=1_778_000_000_000,
            period="1h",
            exchange="binance",
        )


def test_build_cex_detail_snapshot_uses_formal_exchange_for_current_identity_and_sources() -> None:
    snapshot = build_cex_detail_snapshot(
        row={
            "target_id": "okx:BTC-USDT-SWAP",
            "native_market_id": "BTC-USDT-SWAP",
            "base_symbol": "BTC",
            "quote_symbol": "USDT",
            "open_interest_usd": 2000.0,
            "coinglass_status": "unavailable",
            "observed_at_ms": 1_778_000_000_000,
            "observed_at_source": "provider",
        },
        computed_at_ms=1_778_000_000_000,
        period="1h",
        exchange="okx",
    )

    assert snapshot["exchange"] == "okx"
    assert "market:cex:okx:BTC-USDT-SWAP" in [ref["ref_id"] for ref in snapshot["source_refs"]]


def test_build_cex_detail_snapshot_requires_coinglass_status_without_unavailable_default() -> None:
    with pytest.raises(ValueError, match="cex_detail_snapshot_status_required:coinglass_status"):
        build_cex_detail_snapshot(
            row={
                "target_id": "binance:BTCUSDT",
                "cex_token_id": "cex_token:BTC",
                "native_market_id": "BTCUSDT",
                "base_symbol": "BTC",
                "quote_symbol": "USDT",
                "open_interest_usd": 2000.0,
            },
            computed_at_ms=1_778_000_000_000,
            period="1h",
            exchange="binance",
        )


def test_build_cex_detail_snapshot_rejects_unknown_coinglass_status() -> None:
    with pytest.raises(ValueError, match="cex_detail_snapshot_status_invalid:coinglass_status"):
        build_cex_detail_snapshot(
            row={
                "target_id": "binance:BTCUSDT",
                "cex_token_id": "cex_token:BTC",
                "native_market_id": "BTCUSDT",
                "base_symbol": "BTC",
                "quote_symbol": "USDT",
                "open_interest_usd": 2000.0,
                "coinglass_status": "missing",
            },
            computed_at_ms=1_778_000_000_000,
            period="1h",
            exchange="binance",
        )
