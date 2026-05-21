from __future__ import annotations

import pytest

from gmgn_twitter_intel.integrations.macrodata import quote_provider as quote_module
from gmgn_twitter_intel.integrations.macrodata.quote_provider import MacrodataQuoteProvider


class FakeObservation:
    def __init__(self, *, value: float, observed_at: str) -> None:
        self.value = value
        self.observed_at = observed_at
        self.provider = "yahoo"
        self.dataset = "AAPL"
        self.latency_class = "daily"


class FakeYahooProvider:
    calls = 0

    def __init__(self, *, timeout_sec: float) -> None:
        self.timeout_sec = timeout_sec

    def get_range(self, dataset: str, *, start: str, end: str):
        FakeYahooProvider.calls += 1
        assert dataset == "AAPL"
        assert start < end
        return [
            FakeObservation(value=190.0, observed_at="2026-05-19"),
            FakeObservation(value=200.0, observed_at="2026-05-20"),
        ]


def test_macrodata_quote_provider_uses_yahoo_provider_and_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeYahooProvider.calls = 0
    monkeypatch.setattr(quote_module, "YahooPriceProvider", FakeYahooProvider)
    provider = MacrodataQuoteProvider(timeout_seconds=3, cache_ttl_seconds=60)

    quote = provider.quote(" aapl ")
    cached = provider.quote("AAPL")

    assert quote == cached
    assert FakeYahooProvider.calls == 1
    assert quote == {
        "status": "ready",
        "price": 200.0,
        "reference_close_price": 190.0,
        "change_pct": pytest.approx(0.0526315789),
        "asof": "2026-05-20",
        "provider": "yahoo",
        "provider_symbol": "AAPL",
        "latency_class": "daily",
        "freshness_class": "daily",
        "error": None,
    }
