from __future__ import annotations

from datetime import date, datetime

import pytest

from gmgn_twitter_intel.domains.macro_intel.observation_identity import (
    macro_observation_fact_payload_hash,
    macro_observation_id,
    macro_series_current_row_payload_hash,
    normalize_macro_date,
)


def _observation(**overrides: object) -> dict[str, object]:
    return {
        "source_name": "nyfed",
        "concept_key": "liquidity:sofr",
        "series_key": "nyfed:SOFR",
        "source_priority": 100,
        "observed_at": "2026-05-28",
        "value_numeric": 3.51,
        "unit": "percent",
        "frequency": "daily",
        "data_quality": "ok",
        "source_ts": "2026-05-28",
        "raw_payload_json": {"series_key": "nyfed:SOFR", "value": 3.51},
        "ingested_at_ms": 1_779_000_000_000,
        **overrides,
    }


def test_normalize_macro_date_accepts_only_dates_and_yyyy_mm_dd_strings() -> None:
    assert normalize_macro_date(date(2026, 5, 28)) == date(2026, 5, 28)
    assert normalize_macro_date("2026-05-28") == date(2026, 5, 28)

    for value in (
        "20260528",
        "2026-W22-4",
        "2026-05-28T00:00:00Z",
        "2026-05-28 00:00:00+00:00",
        datetime(2026, 5, 28),
    ):
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            normalize_macro_date(value)


def test_macro_observation_id_normalizes_observed_at_date_representation() -> None:
    assert macro_observation_id(_observation(observed_at="2026-05-28")) == macro_observation_id(
        _observation(observed_at=date(2026, 5, 28))
    )


def test_macro_observation_fact_payload_hash_ignores_import_runtime_metadata() -> None:
    base_hash = macro_observation_fact_payload_hash(
        _observation(
            ingested_at_ms=1,
            raw_payload_json={
                "series_key": "nyfed:SOFR",
                "value": 3.51,
                "provider_fetch_ts": "2026-05-28T00:00:00Z",
            },
        )
    )

    assert base_hash == macro_observation_fact_payload_hash(
        _observation(
            ingested_at_ms=2,
            import_run_id="macro-import:runtime",
            sync_run_id="macro-sync:runtime",
            provider_fetch_ts="2026-05-28T01:02:03Z",
            raw_payload_json={
                "series_key": "nyfed:SOFR",
                "value": 3.51,
                "provider_fetch_ts": "2026-05-28T01:02:03Z",
            },
        )
    )
    assert base_hash != macro_observation_fact_payload_hash(_observation(value_numeric=3.52))
    assert base_hash.startswith("sha256:")


def test_macro_series_current_row_payload_hash_ignores_projection_runtime_metadata() -> None:
    row = _observation(projection_version="macro_regime_v4", series_rank=1)
    base_hash = macro_series_current_row_payload_hash(row)

    assert base_hash == macro_series_current_row_payload_hash(
        row | {"ingested_at_ms": 2, "projected_at_ms": 3, "run_id": "runtime"}
    )
    assert base_hash != macro_series_current_row_payload_hash(row | {"series_rank": 2})
    assert base_hash.startswith("sha256:")
