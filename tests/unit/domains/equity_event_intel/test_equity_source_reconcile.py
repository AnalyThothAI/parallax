from __future__ import annotations

from types import SimpleNamespace

from gmgn_twitter_intel.domains.equity_event_intel.services.source_reconcile import (
    build_source_reconcile_payloads,
)


def test_source_reconcile_source_payload_is_stable_across_runtime_ticks() -> None:
    settings = SimpleNamespace(
        default_universe="core",
        companies=[
            SimpleNamespace(
                symbol="MSFT",
                cik="0000789019",
                company_name="Microsoft Corporation",
                exchange="NASDAQ",
                enabled=True,
            )
        ],
        expected_events=[],
    )

    first = build_source_reconcile_payloads(settings=settings, registry_lookup=lambda _symbol: None, now_ms=1_000)
    second = build_source_reconcile_payloads(settings=settings, registry_lookup=lambda _symbol: None, now_ms=2_000)

    assert first.sources == second.sources
    assert "reconciled_at_ms" not in first.sources[0]["extra_json"]
