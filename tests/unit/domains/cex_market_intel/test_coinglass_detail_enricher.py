from __future__ import annotations

import pytest

from parallax.domains.cex_market_intel.services.coinglass_detail_enricher import (
    enrich_rows_with_coinglass,
)


def test_enrich_rows_with_coinglass_maps_derivatives_and_levels_for_top_k() -> None:
    rows = [
        {"base_symbol": "BTC", "native_market_id": "BTCUSDT"},
        {"base_symbol": "ETH", "native_market_id": "ETHUSDT"},
    ]

    enriched = enrich_rows_with_coinglass(
        rows,
        client=_Client(),
        now_ms=1_800_000_000_000,
        limit=1,
        level_limit=6,
    )

    assert enriched[0]["coinglass_status"] == "ready"
    assert enriched[0]["oi_change_pct_1h"] == 10.0
    assert enriched[0]["oi_change_pct_4h"] == 25.0
    assert enriched[0]["oi_change_pct_24h"] == 50.0
    assert enriched[0]["cvd_delta_4h"] == 125.0
    assert enriched[0]["long_short_ratio"] == 1.3
    assert enriched[0]["top_trader_position_ratio"] == 1.6
    assert enriched[0]["level_bands"][0]["kind"] == "resistance"
    assert enriched[1]["coinglass_status"] == "unavailable"


def test_enrich_rows_with_coinglass_marks_all_rows_unavailable_without_client() -> None:
    rows = [
        {"base_symbol": "BTC", "native_market_id": "BTCUSDT"},
        {"base_symbol": "ETH", "native_market_id": "ETHUSDT"},
    ]

    enriched = enrich_rows_with_coinglass(
        rows,
        client=None,
        now_ms=1_800_000_000_000,
        limit=1,
        level_limit=6,
    )

    assert [row["coinglass_status"] for row in enriched] == ["unavailable", "unavailable"]


def test_enrich_rows_with_coinglass_requires_base_symbol_before_provider_io() -> None:
    client = _CallRecordingClient()

    try:
        enrich_rows_with_coinglass(
            [{"base_symbol": " ", "native_market_id": "BTCUSDT"}],
            client=client,
            now_ms=1_800_000_000_000,
            limit=1,
            level_limit=6,
        )
    except ValueError as exc:
        assert str(exc) == "coinglass_detail_identity_required:base_symbol"
    else:
        raise AssertionError("missing CoinGlass base symbol must fail before provider calls")

    assert client.calls == []


@pytest.mark.parametrize(
    ("degraded_reasons", "match"),
    (
        ("legacy", "coinglass_detail_degraded_reasons_invalid"),
        ({"reason": "legacy"}, "coinglass_detail_degraded_reasons_invalid"),
        ([123], "coinglass_detail_degraded_reason_invalid:item"),
        ([""], "coinglass_detail_degraded_reason_invalid:item"),
    ),
)
def test_enrich_rows_with_coinglass_requires_formal_degraded_reasons_shape(degraded_reasons, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        enrich_rows_with_coinglass(
            [{"base_symbol": "BTC", "native_market_id": "BTCUSDT", "degraded_reasons": degraded_reasons}],
            client=None,
            now_ms=1_800_000_000_000,
            limit=1,
            level_limit=6,
        )


def test_enrich_rows_with_coinglass_preserves_formal_degraded_reasons_when_partial() -> None:
    enriched = enrich_rows_with_coinglass(
        [{"base_symbol": "BTC", "native_market_id": "BTCUSDT", "degraded_reasons": ["baseline_stale"]}],
        client=_LevelsFailingClient(),
        now_ms=1_800_000_000_000,
        limit=1,
        level_limit=6,
    )

    assert enriched[0]["coinglass_status"] == "partial"
    assert enriched[0]["degraded_reasons"] == ["baseline_stale", "coinglass_levels_RuntimeError"]


class _Client:
    def fetch_oi_history(self, *, symbol, time_type, lookback):
        values = {"1": (100, 110), "2": (100, 125), "4": (100, 150)}[time_type]
        return {"data": [{"timestamp": 1, "usd": values[0]}, {"timestamp": 2, "usd": values[1]}]}

    def fetch_cvd_history(self, *, symbol, time_type, lookback):
        deltas = {"1": [10, -5], "2": [100, 25], "4": [300, -50]}[time_type]
        return {"data": [{"timestamp": index, "delta": delta} for index, delta in enumerate(deltas)]}

    def fetch_long_short_ratio_history(self, *, symbol, time_type, lookback):
        return {"data": [{"timestamp": 1, "longShortRatio": 1.1}, {"timestamp": 2, "longShortRatio": 1.3}]}

    def fetch_top_trader_position_history(self, *, symbol, time_type, lookback):
        return {"data": [{"timestamp": 1, "longShortRatio": 1.4}, {"timestamp": 2, "longShortRatio": 1.6}]}

    def fetch_liquidation_levels(self, *, symbol, range):
        return {
            "levels": [
                {"price": 72_000, "size": 2_000_000_000, "side": 2},
                {"price": 64_000, "size": 1_000_000_000, "side": 1},
            ]
        }


class _LevelsFailingClient(_Client):
    def fetch_liquidation_levels(self, *, symbol, range):
        raise RuntimeError("levels down")


class _CallRecordingClient(_Client):
    def __init__(self) -> None:
        self.calls: list[str] = []

    def fetch_oi_history(self, *, symbol, time_type, lookback):
        self.calls.append("fetch_oi_history")
        return super().fetch_oi_history(symbol=symbol, time_type=time_type, lookback=lookback)

    def fetch_cvd_history(self, *, symbol, time_type, lookback):
        self.calls.append("fetch_cvd_history")
        return super().fetch_cvd_history(symbol=symbol, time_type=time_type, lookback=lookback)

    def fetch_long_short_ratio_history(self, *, symbol, time_type, lookback):
        self.calls.append("fetch_long_short_ratio_history")
        return super().fetch_long_short_ratio_history(symbol=symbol, time_type=time_type, lookback=lookback)

    def fetch_top_trader_position_history(self, *, symbol, time_type, lookback):
        self.calls.append("fetch_top_trader_position_history")
        return super().fetch_top_trader_position_history(symbol=symbol, time_type=time_type, lookback=lookback)

    def fetch_liquidation_levels(self, *, symbol, range):
        self.calls.append("fetch_liquidation_levels")
        return super().fetch_liquidation_levels(symbol=symbol, range=range)
