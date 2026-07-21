from __future__ import annotations

import math
from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest

from parallax.domains.macro_intel._constants import (
    MACRO_CORE_CONCEPTS,
    MACRO_EVENT_CONCEPTS,
    MACRO_OPTIONAL_HISTORY_CONCEPTS,
)
from parallax.domains.macro_intel.observation_identity import (
    macro_observation_fact_payload_hash,
    macro_observation_id,
)
from parallax.domains.macro_intel.services.macrodata_bundle_importer import (
    import_macrodata_bundle,
    parse_macrodata_bundle,
    write_macrodata_bundle_import,
)

NOW_MS = 1_779_000_000_000

ENVELOPE = {
    "ok": True,
    "command": "bundle.macro-core",
    "data": {
        "snapshot": {
            "bundle": "macro-core",
            "asof": "2026-05-21",
            "observations": [
                {
                    "series_key": "nyfed:SOFR",
                    "provider": "nyfed",
                    "dataset": "SOFR",
                    "observed_at": "2026-05-19",
                    "value": 3.51,
                    "unit": "percent",
                    "frequency": "daily",
                    "source_ts": "2026-05-19",
                    "data_quality": "ok",
                    "provenance": [{"provider": "nyfed", "source_url": "https://markets.newyorkfed.org"}],
                }
            ],
            "coverage": {"requested": 20, "available": 1},
            "missing_series": ["fred:WALCL"],
            "series_errors": [{"series_key": "fred:WALCL", "provider": "fred", "code": "missing_api_key"}],
            "source_chain": ["nyfed"],
            "data_quality": "partial",
            "reason_codes": ["missing_series", "missing_api_key"],
        }
    },
}


def test_import_macrodata_bundle_upserts_observation_and_records_run() -> None:
    repos = FakeRepositorySession()

    summary = import_macrodata_bundle(ENVELOPE, repos=repos, now_ms=NOW_MS)

    assert repos.conn.commits == 0
    assert repos.transaction_events == ["commit"]
    assert repos.macro_intel.observations == [
        {
            "source_name": "nyfed",
            "concept_key": "liquidity:sofr",
            "series_key": "nyfed:SOFR",
            "source_priority": 100,
            "observed_at": date(2026, 5, 19),
            "value_numeric": 3.51,
            "unit": "percent",
            "frequency": "daily",
            "data_quality": "ok",
            "source_ts": "2026-05-19",
            "raw_payload": ENVELOPE["data"]["snapshot"]["observations"][0],
            "ingested_at_ms": NOW_MS,
        }
    ]
    assert len(repos.macro_intel.sync_runs) == 1
    sync_run = repos.macro_intel.sync_runs[0]
    assert sync_run["source_name"] == "macrodata-cli"
    assert sync_run["bundle_name"] == "macro-core"
    assert sync_run["sync_window_id"] is None
    assert sync_run["asof_date"] == date(2026, 5, 21)
    assert sync_run["status"] == "partial"
    assert sync_run["observations_count"] == 1
    assert sync_run["seen_observation_count"] == 1
    assert sync_run["inserted_observation_count"] == 1
    assert sync_run["changed_observation_count"] == 0
    assert sync_run["noop_observation_count"] == 0
    assert sync_run["coverage_json"] == {"requested": 20, "available": 1}
    assert sync_run["missing_series_json"] == ["fred:WALCL"]
    assert sync_run["series_errors_json"] == [
        {"series_key": "fred:WALCL", "provider": "fred", "code": "missing_api_key"}
    ]
    assert sync_run["reason_codes_json"] == ["missing_series", "missing_api_key"]
    assert sync_run["started_at_ms"] == NOW_MS
    assert sync_run["completed_at_ms"] == NOW_MS
    assert summary["bundle_name"] == "macro-core"
    assert summary["asof"] == "2026-05-21"
    assert summary["max_observed_at"] == date(2026, 5, 19)
    assert summary["observations_count"] == 1
    assert summary["seen_observation_count"] == 1
    assert summary["inserted_observation_count"] == 1
    assert summary["changed_observation_count"] == 0
    assert summary["noop_observation_count"] == 0
    assert summary["imported_observation_count"] == 1
    assert summary["imported_observation_ids"] == [macro_observation_id(repos.macro_intel.observations[0])]
    assert summary["sync_run_id"] == sync_run["sync_run_id"]
    assert summary["status"] == "partial"
    assert summary["data_quality"] == "partial"
    assert summary["coverage"] == {"requested": 20, "available": 1}
    assert summary["missing_series"] == ["fred:WALCL"]
    assert summary["series_errors"] == [{"series_key": "fred:WALCL", "provider": "fred", "code": "missing_api_key"}]
    assert summary["reason_codes"] == ["missing_series", "missing_api_key"]
    assert summary["dirty_targets_enqueued"] == 1
    assert repos.macro_intel.enqueued_dirty_targets == [
        {
            "changed_observations": [
                {
                    "observation_id": macro_observation_id(repos.macro_intel.observations[0]),
                    "status": "inserted",
                    "concept_key": "liquidity:sofr",
                    "observed_at": date(2026, 5, 19),
                    "fact_payload_hash": macro_observation_fact_payload_hash(repos.macro_intel.observations[0]),
                }
            ],
            "projection_name": "macro_view",
            "projection_version": "macro_regime_v4",
            "now_ms": NOW_MS,
            "due_at_ms": NOW_MS,
            "reason": "macro_observations_changed",
        }
    ]


def test_import_macrodata_bundle_validates_all_observations_before_writing() -> None:
    envelope = deepcopy(ENVELOPE)
    envelope["data"]["snapshot"]["observations"].append({"provider": "fred", "observed_at": "2026-05-19"})
    repos = FakeRepositorySession()

    with pytest.raises(ValueError, match="series_key"):
        import_macrodata_bundle(envelope, repos=repos, now_ms=NOW_MS)

    assert repos.transaction_events == []
    assert repos.macro_intel.observations == []
    assert repos.macro_intel.sync_runs == []


def test_parse_macrodata_bundle_validates_all_observations_before_write() -> None:
    envelope = deepcopy(ENVELOPE)
    envelope["data"]["snapshot"]["observations"].append({"provider": "fred", "observed_at": "2026-05-19"})

    with pytest.raises(ValueError, match="series_key"):
        parse_macrodata_bundle(envelope, now_ms=NOW_MS)


def test_parse_macrodata_bundle_requires_snapshot_bundle() -> None:
    envelope = deepcopy(ENVELOPE)
    del envelope["data"]["snapshot"]["bundle"]

    with pytest.raises(ValueError, match="macrodata snapshot missing bundle"):
        parse_macrodata_bundle(envelope, now_ms=NOW_MS)


def test_parse_macrodata_bundle_requires_snapshot_data_quality() -> None:
    envelope = deepcopy(ENVELOPE)
    del envelope["data"]["snapshot"]["data_quality"]

    with pytest.raises(ValueError, match="macrodata snapshot missing data_quality"):
        parse_macrodata_bundle(envelope, now_ms=NOW_MS)


def test_parse_macrodata_bundle_requires_observation_provider() -> None:
    envelope = deepcopy(ENVELOPE)
    del envelope["data"]["snapshot"]["observations"][0]["provider"]

    with pytest.raises(ValueError, match="macrodata observation missing provider:nyfed:SOFR"):
        parse_macrodata_bundle(envelope, now_ms=NOW_MS)


def test_parse_macrodata_bundle_requires_observation_data_quality() -> None:
    envelope = deepcopy(ENVELOPE)
    del envelope["data"]["snapshot"]["observations"][0]["data_quality"]

    with pytest.raises(ValueError, match="macrodata observation missing data_quality:nyfed:SOFR"):
        parse_macrodata_bundle(envelope, now_ms=NOW_MS)


def test_write_macrodata_bundle_import_does_not_open_its_own_transaction() -> None:
    repos = FakeRepositorySession()
    parsed = parse_macrodata_bundle(ENVELOPE, now_ms=NOW_MS)

    with repos.transaction():
        summary = write_macrodata_bundle_import(parsed, repos=repos)

    assert repos.transaction_events == ["commit"]
    assert repos.conn.commits == 0
    assert summary["max_observed_at"] == date(2026, 5, 19)
    assert summary["asof"] == "2026-05-21"
    assert repos.macro_intel.sync_runs == []
    assert summary["imported_observation_count"] == 1
    assert summary["dirty_targets_enqueued"] == 1


def test_write_macrodata_bundle_import_requires_external_transaction() -> None:
    repos = FakeRepositorySession()
    parsed = parse_macrodata_bundle(ENVELOPE, now_ms=NOW_MS)

    with pytest.raises(RuntimeError, match="macrodata_bundle_import"):
        write_macrodata_bundle_import(parsed, repos=repos)

    assert repos.macro_intel.observations == []
    assert repos.macro_intel.sync_runs == []


def test_import_macrodata_bundle_requires_repository_session_transaction() -> None:
    repos = MissingUnitOfWorkRepositorySession()

    with pytest.raises(AttributeError, match="transaction"):
        import_macrodata_bundle(ENVELOPE, repos=repos, now_ms=NOW_MS)

    assert repos.conn.transaction_events == []
    assert repos.macro_intel.observations == []
    assert repos.macro_intel.sync_runs == []


def test_write_macrodata_bundle_import_requires_session_transaction_contract() -> None:
    repos = MissingRequireTransactionRepositorySession()
    parsed = parse_macrodata_bundle(ENVELOPE, now_ms=NOW_MS)

    with pytest.raises(AttributeError, match="require_transaction"):
        write_macrodata_bundle_import(parsed, repos=repos)

    assert repos.macro_intel.observations == []
    assert repos.macro_intel.sync_runs == []


def test_import_macrodata_bundle_rejects_unknown_macro_core_series_before_writing() -> None:
    envelope = deepcopy(ENVELOPE)
    envelope["data"]["snapshot"]["observations"][0]["series_key"] = "fred:NOT_A_CORE_SERIES"
    repos = FakeRepositorySession()

    with pytest.raises(ValueError, match="unknown macrodata series_key"):
        import_macrodata_bundle(envelope, repos=repos, now_ms=NOW_MS)

    assert repos.transaction_events == []
    assert repos.macro_intel.observations == []
    assert repos.macro_intel.sync_runs == []


def test_import_macrodata_bundle_accepts_event_bundles_without_expanding_numeric_macro_core() -> None:
    event_envelope = {
        "ok": True,
        "command": "bundle.macro-calendar-core",
        "data": {
            "snapshot": {
                "bundle": "macro-calendar-core",
                "asof": "2026-06-16",
                "observations": [
                    {
                        "series_key": "official_calendar:fomc_decision_next",
                        "provider": "official_calendar",
                        "dataset": "fomc",
                        "observed_at": "2026-06-17",
                        "value": 1,
                        "unit": "days",
                        "frequency": "event",
                        "source_ts": "2026-06-16T14:00:00Z",
                        "data_quality": "ok",
                        "provenance": [
                            {
                                "provider": "official_calendar",
                                "source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
                                "event_title": "FOMC decision",
                                "event_time": "14:00 ET",
                            }
                        ],
                    },
                    {
                        "series_key": "treasury_auction:10y_bid_to_cover",
                        "provider": "treasury_auction",
                        "dataset": "10y_bid_to_cover",
                        "observed_at": "2026-06-10",
                        "value": 2.52,
                        "unit": "ratio",
                        "frequency": "event",
                        "source_ts": "2026-06-10",
                        "data_quality": "ok",
                        "provenance": [
                            {
                                "provider": "treasury_auction",
                                "source_url": "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query",
                                "security_term": "10-Year",
                                "cusip": "91282CQQ9",
                            }
                        ],
                    },
                    {
                        "series_key": "treasury_auction:10y_next_auction_days",
                        "provider": "treasury_auction",
                        "dataset": "10y_next_auction_days",
                        "observed_at": "2026-07-08",
                        "value": 22,
                        "unit": "days_until",
                        "frequency": "event",
                        "source_ts": "2026-06-16",
                        "data_quality": "ok",
                        "provenance": [
                            {
                                "provider": "treasury_auction",
                                "source_url": "https://home.treasury.gov/system/files/221/Tentative-Auction-Schedule.xml",
                                "security_type": "NOTE",
                                "security_term": "10-Year",
                                "announcement_date": "2026-07-02",
                                "auction_date": "2026-07-08",
                                "settlement_date": "2026-07-15",
                                "reopening": True,
                                "tips": False,
                                "floating_rate": False,
                            }
                        ],
                    },
                ],
                "coverage": {"requested": 3, "available": 3},
                "missing_series": [],
                "series_errors": [],
                "source_chain": ["official_calendar", "treasury_auction"],
                "data_quality": "ok",
                "reason_codes": [],
            }
        },
    }
    repos = FakeRepositorySession()

    summary = import_macrodata_bundle(event_envelope, repos=repos, now_ms=NOW_MS)

    assert "event:fomc_decision_next" not in MACRO_CORE_CONCEPTS
    assert "event:treasury_auction_10y_bid_to_cover" not in MACRO_CORE_CONCEPTS
    assert "event:treasury_auction_10y_next" not in MACRO_CORE_CONCEPTS
    assert [row["concept_key"] for row in repos.macro_intel.observations] == [
        "event:fomc_decision_next",
        "event:treasury_auction_10y_bid_to_cover",
        "event:treasury_auction_10y_next",
    ]
    assert [row["frequency"] for row in repos.macro_intel.observations] == ["event", "event", "event"]
    assert repos.macro_intel.observations[0]["source_name"] == "official_calendar"
    assert repos.macro_intel.observations[1]["source_name"] == "treasury_auction"
    assert repos.macro_intel.observations[2]["source_name"] == "treasury_auction"
    assert repos.macro_intel.sync_runs[0]["bundle_name"] == "macro-calendar-core"
    assert summary["imported_observation_count"] == 3
    assert summary["dirty_targets_enqueued"] == 1
    assert [item["concept_key"] for item in repos.macro_intel.enqueued_dirty_targets[0]["changed_observations"]] == [
        "event:fomc_decision_next",
        "event:treasury_auction_10y_bid_to_cover",
        "event:treasury_auction_10y_next",
    ]


def test_import_macrodata_bundle_accepts_fed_text_events_with_stable_document_series_keys() -> None:
    fed_text_envelope = {
        "ok": True,
        "command": "bundle.fed-text-core-history",
        "data": {
            "snapshot": {
                "bundle": "fed-text-core",
                "asof": "2026-05-08",
                "observations": [
                    {
                        "series_key": "official_fed_text:speech_latest",
                        "provider": "official_fed_text",
                        "dataset": "speech_latest",
                        "observed_at": "2026-05-08T23:30:00Z",
                        "value": "Bowman, When Regulation Reshapes Markets",
                        "unit": "document",
                        "frequency": "event",
                        "source_ts": "2026-05-08T23:30:00Z",
                        "data_quality": "ok",
                        "provenance": [
                            {
                                "provider": "official_fed_text",
                                "source_url": "https://www.federalreserve.gov/newsevents/speech/bowman20260508a.htm",
                                "source_page_url": "https://www.federalreserve.gov/feeds/speeches.xml",
                                "document_type": "speech",
                                "document_title": "Bowman, When Regulation Reshapes Markets",
                                "published_at": "2026-05-08T23:30:00Z",
                            }
                        ],
                    },
                    {
                        "series_key": "official_fed_text:speech_latest",
                        "provider": "official_fed_text",
                        "dataset": "speech_latest",
                        "observed_at": "2026-05-08T23:30:01Z",
                        "value": "Waller, Update On Federal Reserve Bank Operations",
                        "unit": "document",
                        "frequency": "event",
                        "source_ts": "2026-05-08T23:30:00Z",
                        "data_quality": "ok",
                        "provenance": [
                            {
                                "provider": "official_fed_text",
                                "source_url": "https://www.federalreserve.gov/newsevents/speech/waller20260508a.htm",
                                "source_page_url": "https://www.federalreserve.gov/feeds/speeches.xml",
                                "document_type": "speech",
                                "document_title": "Waller, Update On Federal Reserve Bank Operations",
                                "published_at": "2026-05-08T23:30:00Z",
                            }
                        ],
                    },
                ],
                "coverage": {"requested": 4, "available": 1},
                "missing_series": [],
                "series_errors": [],
                "source_chain": ["official_fed_text"],
                "data_quality": "partial",
                "reason_codes": [],
            }
        },
    }
    repos = FakeRepositorySession()

    summary = import_macrodata_bundle(fed_text_envelope, repos=repos, now_ms=NOW_MS)

    assert "event:fed_speech" in MACRO_EVENT_CONCEPTS
    assert "event:fed_speech" not in MACRO_CORE_CONCEPTS
    assert [row["concept_key"] for row in repos.macro_intel.observations] == [
        "event:fed_speech",
        "event:fed_speech",
    ]
    assert [row["observed_at"] for row in repos.macro_intel.observations] == [
        date(2026, 5, 8),
        date(2026, 5, 8),
    ]
    assert [row["source_ts"] for row in repos.macro_intel.observations] == [
        "2026-05-08T23:30:00Z",
        "2026-05-08T23:30:00Z",
    ]
    assert repos.macro_intel.observations[0]["series_key"].startswith("official_fed_text:speech_latest#")
    assert repos.macro_intel.observations[1]["series_key"].startswith("official_fed_text:speech_latest#")
    assert repos.macro_intel.observations[0]["series_key"] != repos.macro_intel.observations[1]["series_key"]
    assert repos.macro_intel.observations[0]["raw_payload"]["series_key"] == "official_fed_text:speech_latest"
    assert len({macro_observation_id(row) for row in repos.macro_intel.observations}) == 2
    assert summary["imported_observation_count"] == 2
    assert summary["dirty_targets_enqueued"] == 1


def test_import_macrodata_bundle_accepts_crypto_derivatives_core_without_page_shell() -> None:
    crypto_derivatives = [
        (
            "okx:BTC-USDT-SWAP:open_interest_usd",
            "okx",
            "BTC-USDT-SWAP:open_interest_usd",
            1_939_251_795.54,
            "usd",
            "crypto_derivatives:okx_btc_oi_usd",
        ),
        (
            "okx:BTC-USDT-SWAP:funding_rate",
            "okx",
            "BTC-USDT-SWAP:funding_rate",
            0.00012,
            "rate",
            "crypto_derivatives:okx_btc_funding",
        ),
        (
            "okx:BTC-USDT-SWAP:basis_pct",
            "okx",
            "BTC-USDT-SWAP:basis_pct",
            0.5,
            "percent",
            "crypto_derivatives:okx_btc_basis",
        ),
        (
            "okx:ETH-USDT-SWAP:open_interest_usd",
            "okx",
            "ETH-USDT-SWAP:open_interest_usd",
            812_000_000.0,
            "usd",
            "crypto_derivatives:okx_eth_oi_usd",
        ),
        (
            "okx:ETH-USDT-SWAP:funding_rate",
            "okx",
            "ETH-USDT-SWAP:funding_rate",
            0.00008,
            "rate",
            "crypto_derivatives:okx_eth_funding",
        ),
        (
            "okx:ETH-USDT-SWAP:basis_pct",
            "okx",
            "ETH-USDT-SWAP:basis_pct",
            0.4,
            "percent",
            "crypto_derivatives:okx_eth_basis",
        ),
        (
            "deribit:BTC-PERPETUAL:open_interest_usd",
            "deribit",
            "BTC-PERPETUAL:open_interest_usd",
            502_231_260.0,
            "usd",
            "crypto_derivatives:deribit_btc_oi_usd",
        ),
        (
            "deribit:BTC-PERPETUAL:funding_8h",
            "deribit",
            "BTC-PERPETUAL:funding_8h",
            0.00002203,
            "rate",
            "crypto_derivatives:deribit_btc_funding_8h",
        ),
        (
            "deribit:BTC-PERPETUAL:basis_pct",
            "deribit",
            "BTC-PERPETUAL:basis_pct",
            1.0,
            "percent",
            "crypto_derivatives:deribit_btc_basis",
        ),
        (
            "deribit:BTC:volatility_index",
            "deribit",
            "BTC:volatility_index",
            66.2,
            "index",
            "crypto_derivatives:deribit_btc_vol_index",
        ),
        (
            "deribit:ETH-PERPETUAL:open_interest_usd",
            "deribit",
            "ETH-PERPETUAL:open_interest_usd",
            231_000_000.0,
            "usd",
            "crypto_derivatives:deribit_eth_oi_usd",
        ),
        (
            "deribit:ETH-PERPETUAL:funding_8h",
            "deribit",
            "ETH-PERPETUAL:funding_8h",
            0.000018,
            "rate",
            "crypto_derivatives:deribit_eth_funding_8h",
        ),
        (
            "deribit:ETH-PERPETUAL:basis_pct",
            "deribit",
            "ETH-PERPETUAL:basis_pct",
            0.9,
            "percent",
            "crypto_derivatives:deribit_eth_basis",
        ),
        (
            "deribit:ETH:volatility_index",
            "deribit",
            "ETH:volatility_index",
            72.1,
            "index",
            "crypto_derivatives:deribit_eth_vol_index",
        ),
    ]
    envelope = {
        "ok": True,
        "command": "bundle.crypto-derivatives-core",
        "data": {
            "snapshot": {
                "bundle": "crypto-derivatives-core",
                "asof": "2026-05-20",
                "observations": [
                    {
                        "series_key": series_key,
                        "provider": provider,
                        "dataset": dataset,
                        "observed_at": "2026-05-20",
                        "value": value,
                        "unit": unit,
                        "frequency": "intraday",
                        "source_ts": "2026-05-20T00:00:00Z",
                        "data_quality": "ok",
                        "provenance": [{"provider": provider, "source_url": f"https://example.com/{provider}"}],
                    }
                    for series_key, provider, dataset, value, unit, _concept_key in crypto_derivatives
                ],
                "coverage": {"requested": 14, "available": 14},
                "missing_series": [],
                "series_errors": [],
                "source_chain": ["okx", "deribit"],
                "data_quality": "ok",
                "reason_codes": [],
            }
        },
    }
    repos = FakeRepositorySession()

    summary = import_macrodata_bundle(envelope, repos=repos, now_ms=NOW_MS)

    expected_concept_keys = [concept_key for *_unused, concept_key in crypto_derivatives]
    assert [row["concept_key"] for row in repos.macro_intel.observations] == expected_concept_keys
    assert [row["source_name"] for row in repos.macro_intel.observations[:6]] == ["okx"] * 6
    assert [row["source_name"] for row in repos.macro_intel.observations[6:]] == ["deribit"] * 8
    assert {row["frequency"] for row in repos.macro_intel.observations} == {"intraday"}
    assert set(expected_concept_keys).issubset(MACRO_OPTIONAL_HISTORY_CONCEPTS)
    assert repos.macro_intel.sync_runs[0]["bundle_name"] == "crypto-derivatives-core"
    assert repos.macro_intel.sync_runs[0]["observations_count"] == 14
    assert summary["imported_observation_count"] == 14
    assert summary["dirty_targets_enqueued"] == 1


def test_import_macrodata_bundle_rolls_back_observations_when_import_run_fails() -> None:
    repos = FakeRepositorySession(fail_record_run=True)

    with pytest.raises(RuntimeError, match="record_run_failed"):
        import_macrodata_bundle(ENVELOPE, repos=repos, now_ms=NOW_MS)

    assert repos.conn.commits == 0
    assert repos.transaction_events == ["rollback"]
    assert repos.macro_intel.observations == []
    assert repos.macro_intel.sync_runs == []


@pytest.mark.parametrize("raw_value", ["n/a", True])
def test_import_macrodata_bundle_stores_none_for_non_numeric_values(raw_value: object) -> None:
    envelope = deepcopy(ENVELOPE)
    envelope["data"]["snapshot"]["observations"][0]["value"] = raw_value
    repos = FakeRepositorySession()

    import_macrodata_bundle(envelope, repos=repos, now_ms=NOW_MS)

    assert repos.macro_intel.observations[0]["value_numeric"] is None


@pytest.mark.parametrize("raw_value", [float("nan"), float("inf"), float("-inf")])
def test_import_macrodata_bundle_sanitizes_non_finite_numbers_before_jsonb_write(
    raw_value: float,
) -> None:
    envelope = deepcopy(ENVELOPE)
    envelope["data"]["snapshot"]["observations"][0]["value"] = raw_value
    envelope["data"]["snapshot"]["observations"][0]["provenance"][0]["raw_metric"] = raw_value
    repos = FakeRepositorySession()

    import_macrodata_bundle(envelope, repos=repos, now_ms=NOW_MS)

    observation = repos.macro_intel.observations[0]
    assert observation["value_numeric"] is None
    assert observation["raw_payload"]["value"] is None
    assert observation["raw_payload"]["provenance"][0]["raw_metric"] is None
    assert json_payload_has_only_finite_numbers(observation["raw_payload"])


def test_import_macrodata_bundle_accepts_numeric_string_values() -> None:
    envelope = deepcopy(ENVELOPE)
    envelope["data"]["snapshot"]["observations"][0]["value"] = "3.51"
    repos = FakeRepositorySession()

    import_macrodata_bundle(envelope, repos=repos, now_ms=NOW_MS)

    assert repos.macro_intel.observations[0]["value_numeric"] == pytest.approx(3.51)


def test_import_macrodata_bundle_accepts_decimal_values() -> None:
    envelope = deepcopy(ENVELOPE)
    envelope["data"]["snapshot"]["observations"][0]["value"] = Decimal("3.51")
    repos = FakeRepositorySession()

    import_macrodata_bundle(envelope, repos=repos, now_ms=NOW_MS)

    assert repos.macro_intel.observations[0]["value_numeric"] == Decimal("3.51")


def test_import_macrodata_bundle_rejects_invalid_envelope() -> None:
    with pytest.raises(ValueError, match=r"data\.snapshot"):
        import_macrodata_bundle({"ok": True, "data": {}}, repos=FakeRepositorySession(), now_ms=NOW_MS)


def json_payload_has_only_finite_numbers(value: object) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(json_payload_has_only_finite_numbers(item) for item in value.values())
    if isinstance(value, list):
        return all(json_payload_has_only_finite_numbers(item) for item in value)
    return True


class FakeRepositorySession:
    def __init__(self, *, fail_record_run: bool = False) -> None:
        self.conn = FakeConnection()
        self.transaction_events: list[str] = []
        self.transaction_depth = 0
        self.macro_intel = FakeMacroIntelRepository(fail_record_run=fail_record_run)

    def transaction(self):
        return FakeTransaction(self)

    def require_transaction(self, *, operation: str) -> None:
        if self.transaction_depth <= 0:
            raise RuntimeError(f"{operation}:transaction_required")


class FakeTransaction:
    def __init__(self, repos: FakeRepositorySession) -> None:
        self.repos = repos
        self.observations: list[dict[str, object]] = []
        self.sync_runs: list[dict[str, object]] = []
        self.enqueued_dirty_targets: list[dict[str, object]] = []

    def __enter__(self):
        self.repos.transaction_depth += 1
        self.observations = list(self.repos.macro_intel.observations)
        self.observation_index = dict(self.repos.macro_intel._observation_index)
        self.sync_runs = list(self.repos.macro_intel.sync_runs)
        self.enqueued_dirty_targets = list(self.repos.macro_intel.enqueued_dirty_targets)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is not None:
            self.repos.macro_intel.observations = self.observations
            self.repos.macro_intel._observation_index = self.observation_index
            self.repos.macro_intel.sync_runs = self.sync_runs
            self.repos.macro_intel.enqueued_dirty_targets = self.enqueued_dirty_targets
            self.repos.transaction_events.append("rollback")
        else:
            self.repos.transaction_events.append("commit")
        self.repos.transaction_depth -= 1
        return False


class FakeConnection:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


class MissingUnitOfWorkRepositorySession:
    def __init__(self) -> None:
        self.conn = FakeConnectionWithTransaction()
        self.macro_intel = FakeMacroIntelRepository()

    def require_transaction(self, *, operation: str) -> None:
        if not self.conn.transaction_open:
            raise RuntimeError(f"{operation}:transaction_required")


class MissingRequireTransactionRepositorySession:
    def __init__(self) -> None:
        self.conn = FakeConnection()
        self.macro_intel = FakeMacroIntelRepository()


class FakeConnectionWithTransaction:
    def __init__(self) -> None:
        self.transaction_events: list[str] = []
        self.transaction_open = False

    def transaction(self):
        return FakeConnectionTransaction(self)


class FakeConnectionTransaction:
    def __init__(self, conn: FakeConnectionWithTransaction) -> None:
        self.conn = conn

    def __enter__(self):
        self.conn.transaction_open = True
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.conn.transaction_events.append("rollback" if exc_type is not None else "commit")
        self.conn.transaction_open = False
        return False


class FakeMacroIntelRepository:
    def __init__(self, *, fail_record_run: bool = False) -> None:
        self.observations: list[dict[str, object]] = []
        self._observation_index: dict[str, int] = {}
        self.sync_runs: list[dict[str, object]] = []
        self.enqueued_dirty_targets: list[dict[str, object]] = []
        self.fail_record_run = fail_record_run

    def upsert_observation(self, observation: dict[str, object]) -> dict[str, object]:
        observation_id = macro_observation_id(observation)
        fact_payload_hash = macro_observation_fact_payload_hash(observation)
        existing_index = self._observation_index.get(observation_id)
        if existing_index is None:
            self._observation_index[observation_id] = len(self.observations)
            self.observations.append(dict(observation))
            status = "inserted"
        else:
            existing = self.observations[existing_index]
            existing_hash = macro_observation_fact_payload_hash(existing)
            if existing_hash == fact_payload_hash:
                status = "noop"
            else:
                self.observations[existing_index] = dict(observation)
                status = "changed"
        return {
            "observation_id": observation_id,
            "status": status,
            "concept_key": str(observation["concept_key"]),
            "observed_at": observation["observed_at"],
            "fact_payload_hash": fact_payload_hash,
        }

    def record_macro_sync_run(self, sync_run: dict[str, object]) -> None:
        if self.fail_record_run:
            raise RuntimeError("record_run_failed")
        self.sync_runs.append(sync_run)

    def enqueue_macro_projection_dirty_targets_for_changes(self, **kwargs: object) -> int:
        self.enqueued_dirty_targets.append(dict(kwargs))
        return 1
