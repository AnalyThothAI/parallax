from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from gmgn_twitter_intel.app.runtime import bootstrap as bootstrap_module
from gmgn_twitter_intel.app.runtime.bootstrap import _PooledIngestStore
from gmgn_twitter_intel.app.runtime.providers_wiring import AssetMarketProviders
from gmgn_twitter_intel.domains.asset_market.providers import DexTokenQuote
from gmgn_twitter_intel.domains.ingestion.interfaces import IngestedEvent
from tests.factories import make_event


def test_pooled_ingest_does_not_call_inline_provider_when_no_fresh_tick(monkeypatch) -> None:
    """After the async-backfill hard cut, the collector inline path must
    never reach a quote provider — pending captures are persisted as
    ``unavailable`` / ``pending_backfill`` and the
    ``event_anchor_backfill`` worker catches up asynchronously.
    """
    state = _FakeState()
    provider = _AssertingDexQuoteProvider(state)
    db = _FakeDB(state, event_exists=False)
    event = make_event("event-provider-outside-db")

    monkeypatch.setattr(bootstrap_module, "IngestService", _FakeIngestService)

    store = _PooledIngestStore(
        db,
        providers=AssetMarketProviders(dex_quote_market=provider),
        now_ms=lambda: event.received_at_ms + 100,
    )

    result = store.ingest_event(event, is_watched=True)

    assert result.inserted is True
    assert provider.calls == []
    assert db.session_names == ["collector", "collector"]


def test_pooled_ingest_duplicate_event_skips_inline_provider(monkeypatch) -> None:
    state = _FakeState()
    provider = _AssertingDexQuoteProvider(state)
    db = _FakeDB(state, event_exists=True)
    event = make_event("event-duplicate")

    monkeypatch.setattr(bootstrap_module, "IngestService", _FakeIngestService)

    store = _PooledIngestStore(
        db,
        providers=AssetMarketProviders(dex_quote_market=provider),
        now_ms=lambda: event.received_at_ms + 100,
    )

    result = store.ingest_event(event, is_watched=True)

    assert result.inserted is False
    assert provider.calls == []
    assert db.session_names == ["collector"]


@dataclass
class _FakeState:
    in_session: bool = False


class _AssertingDexQuoteProvider:
    def __init__(self, state: _FakeState) -> None:
        self._state = state
        self.calls: list[tuple[str, str]] = []

    def token_quotes(self, tokens):
        assert self._state.in_session is False
        self.calls.extend((item.chain_id, item.address) for item in tokens)
        return [
            DexTokenQuote(
                chain_id=tokens[0].chain_id,
                address=tokens[0].address,
                observed_at_ms=1_700_000_000_000,
                price_usd=1.23,
                raw={},
            )
        ]


class _FakeMarketTicks:
    def latest_at_or_before(self, **_: Any) -> None:
        return None


class _FakeRepos:
    def __init__(self, *, event_exists: bool) -> None:
        self.evidence = self
        self.entities = self
        self.signals = self
        self.enrichment = self
        self.registry = self
        self.identity_evidence = self
        self.token_intent_lookup = self
        self.token_evidence = self
        self.token_intents = self
        self.intent_resolutions = self
        self.enriched_events = self
        self.event_exists = event_exists
        self.market_ticks = _FakeMarketTicks()


class _FakeDB:
    def __init__(self, state: _FakeState, *, event_exists: bool) -> None:
        self._state = state
        self._repos = _FakeRepos(event_exists=event_exists)
        self.session_names: list[str] = []

    @contextmanager
    def worker_session(self, name: str) -> Iterator[_FakeRepos]:
        self.session_names.append(name)
        self._state.in_session = True
        try:
            yield self._repos
        finally:
            self._state.in_session = False


class _FakeIngestService:
    def __init__(self, **kwargs: Any) -> None:
        self.repos = kwargs["evidence"]

    @staticmethod
    def prepare_event(event, *, is_watched: bool):
        return {"event": event, "event_id": event.event_id, "event_ms": event.received_at_ms}

    def event_already_exists(self, prepared) -> bool:
        return bool(self.repos.event_exists)

    def prepare_registry_for_resolution(self, prepared) -> None:
        return None

    def resolve_prepared(self, prepared, *, persist: bool = False):
        return [
            {
                "event_id": prepared["event_id"],
                "intent_id": "intent-1",
                "target_type": "Asset",
                "target_id": "asset:eip155:1:erc20:0xabc",
                "pricefeed_id": None,
                "decision_time_ms": prepared["event_ms"],
            }
        ]

    def market_resolution_for_decision(self, decision):
        return {
            "event_id": decision["event_id"],
            "intent_id": decision["intent_id"],
            "resolution_id": "resolution-1",
            "target_type": "chain_token",
            "target_id": "eip155:1:0xabc",
            "chain_id": "eip155:1",
            "token_address": "0xabc",
        }

    def duplicate_result(self, prepared):
        return IngestedEvent(
            event=prepared["event"],
            entities=[],
            alerts=[],
            token_intents=[],
            token_resolutions=[],
            inserted=False,
        )

    def commit_prepared_event(self, prepared, *, resolutions, captures):
        return IngestedEvent(
            event=prepared["event"],
            entities=[],
            alerts=[],
            token_intents=[],
            token_resolutions=[],
            inserted=True,
        )
