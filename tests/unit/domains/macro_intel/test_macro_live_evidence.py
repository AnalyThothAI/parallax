from __future__ import annotations

from datetime import date

from parallax.domains.macro_intel.services.macro_live_evidence import (
    build_macro_live_evidence,
)

READ_AT_MS = 1_774_300_000_000


def test_live_view_keeps_missing_rows_local_and_uncatalogued_visible() -> None:
    payload = build_macro_live_evidence(
        view_id="dashboard",
        window="90d",
        read_at_ms=READ_AT_MS,
        observations=[
            _row("rates:dgs10", "fred:DGS10", date(2026, 7, 23), 4.22),
            _row("macro:new_fact", "provider:new", date(2026, 7, 24), 12.0),
        ],
        research=None,
    )

    rates = next(view for view in payload["views"] if view["view_id"] == "rates-inflation")
    dgs10 = next(metric for metric in rates["metrics"] if metric["concept_key"] == "rates:dgs10")
    assert dgs10["availability"] == "available"
    assert dgs10["value_numeric"] == 4.22
    assert rates["available_count"] >= 1
    assert payload["unclassified"][0]["concept_key"] == "macro:new_fact"
    assert "sufficiency" not in str(payload)
    assert "no_call" not in str(payload)


def test_live_view_preserves_observation_received_and_source_clocks() -> None:
    payload = build_macro_live_evidence(
        view_id="rates-inflation",
        window="30d",
        read_at_ms=READ_AT_MS,
        observations=[
            _row(
                "rates:dgs10",
                "fred:DGS10",
                date(2026, 6, 1),
                4.1,
                source_ts="2026-06-01T16:00:00-04:00",
                ingested_at_ms=READ_AT_MS - 1_000,
            )
        ],
        research=None,
    )

    metric = next(metric for metric in payload["views"][0]["metrics"] if metric["concept_key"] == "rates:dgs10")
    assert metric["observed_at"] == date(2026, 6, 1)
    assert metric["source_timestamp"] == "2026-06-01T16:00:00-04:00"
    assert metric["received_at_ms"] == READ_AT_MS - 1_000
    assert payload["read_at_ms"] == READ_AT_MS


def test_live_view_exposes_transparent_calculations_without_semantic_labels() -> None:
    rows = [
        _row("liquidity:fed_assets", "fred:WALCL", date(2026, 7, 23), 7_000_000, unit="millions_usd"),
        _row(
            "liquidity:tga",
            "treasury_fiscal:operating_cash_balance",
            date(2026, 7, 23),
            800_000,
            unit="millions_usd",
        ),
        _row(
            "liquidity:on_rrp",
            "fred:RRPONTSYD",
            date(2026, 7, 23),
            100,
            unit="billions_usd",
        ),
        _row("fed:iorb", "fred:IORB", date(2026, 7, 23), 4.4, unit="percent"),
        _row("liquidity:sofr", "nyfed:SOFR", date(2026, 7, 23), 4.43, unit="percent"),
    ]

    payload = build_macro_live_evidence(
        view_id="liquidity-funding",
        window="90d",
        read_at_ms=READ_AT_MS,
        observations=rows,
        research=None,
    )

    metrics = {metric["concept_key"]: metric for metric in payload["views"][0]["metrics"]}
    net = metrics["derived:net_liquidity_accounting_proxy"]
    spread = metrics["derived:sofr_minus_iorb_bps"]
    assert net["value_numeric"] == 6_100_000
    assert net["calculation"]["formula_id"] == "fed_assets_minus_tga_minus_on_rrp_v1"
    assert spread["value_numeric"] == 3.0
    assert spread["calculation"]["sample_size"] == 2
    assert not {
        "confidence",
        "direction",
        "quadrant",
        "readiness",
        "risk_state",
    }.intersection(spread)


def test_cross_asset_view_computes_sampled_rolling_correlations() -> None:
    rows = []
    for index, value in enumerate((100.0, 101.0, 103.0, 102.0), start=20):
        rows.append(_row("asset:spy", "yahoo:SPY", date(2026, 7, index), value))
    for index, value in enumerate((90.0, 90.5, 91.5, 91.0), start=20):
        rows.append(_row("asset:tlt", "yahoo:TLT", date(2026, 7, index), value))

    payload = build_macro_live_evidence(
        view_id="cross-asset",
        window="30d",
        read_at_ms=READ_AT_MS,
        observations=rows,
        research=None,
    )

    correlation = next(
        metric
        for metric in payload["views"][0]["metrics"]
        if metric["concept_key"] == "derived:correlation:asset:spy:asset:tlt"
    )
    assert correlation["availability"] == "available"
    assert correlation["calculation"]["formula_id"] == "pearson_return_correlation_v1"
    assert correlation["calculation"]["sample_size"] == 3


def _row(
    concept_key: str,
    series_key: str,
    observed_at: date,
    value: float,
    *,
    source_ts: str | None = None,
    ingested_at_ms: int = READ_AT_MS - 10_000,
    unit: str = "percent",
) -> dict[str, object]:
    return {
        "observation_id": f"{concept_key}:{series_key}:{observed_at.isoformat()}",
        "concept_key": concept_key,
        "source_name": "fixture",
        "series_key": series_key,
        "source_priority": 100,
        "observed_at": observed_at,
        "value_numeric": value,
        "unit": unit,
        "frequency": "daily",
        "data_quality": "ok",
        "source_ts": source_ts or observed_at.isoformat(),
        "raw_payload_json": {},
        "ingested_at_ms": ingested_at_ms,
    }
