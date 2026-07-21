from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import pytest

from parallax.app.runtime import bootstrap as bootstrap_module
from parallax.app.runtime.bootstrap import _ingest_service_for_repos, _PooledIngestStore
from parallax.app.runtime.provider_wiring.types import AssetMarketProviders
from parallax.domains.asset_market.providers import DexTokenQuote
from parallax.domains.evidence.interfaces import materialize_event
from parallax.domains.evidence.services.ingest_service import IngestService, PreparedIngest
from parallax.domains.ingestion.interfaces import IngestedEvent
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
        event_anchor_active_window_ms=300_000,
        now_ms=lambda: event.received_at_ms + 100,
    )

    result = store.ingest_event(event, is_watched=True)

    assert result.inserted is True
    assert provider.calls == []
    assert db.session_names == ["collector"]


def test_pooled_ingest_duplicate_event_skips_inline_provider(monkeypatch) -> None:
    state = _FakeState()
    provider = _AssertingDexQuoteProvider(state)
    db = _FakeDB(state, event_exists=True)
    event = make_event("event-duplicate")

    monkeypatch.setattr(bootstrap_module, "IngestService", _FakeIngestService)

    store = _PooledIngestStore(
        db,
        providers=AssetMarketProviders(dex_quote_market=provider),
        event_anchor_active_window_ms=300_000,
        now_ms=lambda: event.received_at_ms + 100,
    )

    result = store.ingest_event(event, is_watched=True)

    assert result.inserted is False
    assert provider.calls == []
    assert db.session_names == ["collector"]


def test_direct_ingest_keeps_registry_resolution_and_event_commit_in_one_transaction(monkeypatch) -> None:
    evidence = _FakeEvidenceTransaction()
    dependency = object()
    ingest = IngestService(
        evidence=evidence,
        entities=dependency,
        signals=dependency,
        registry=dependency,
        identity_evidence=dependency,
        token_intent_lookup=dependency,
        token_evidence=dependency,
        token_intents=dependency,
        intent_resolutions=dependency,
        discovery=dependency,
        market_ticks=dependency,
        market_tick_current=dependency,
        enriched_events=dependency,
        event_anchor_jobs=dependency,
        token_radar_dirty_targets=dependency,
        transaction=evidence.transaction,
        event_anchor_active_window_ms=300_000,
    )
    event = make_event("event-direct-atomic")

    monkeypatch.setattr(ingest, "event_already_exists", lambda prepared: _assert_depth(evidence, False))
    monkeypatch.setattr(ingest, "prepare_registry_for_resolution", lambda prepared: _assert_depth(evidence))
    monkeypatch.setattr(ingest, "resolve_prepared", lambda prepared, persist=False: _assert_depth(evidence, []))
    monkeypatch.setattr(
        ingest,
        "commit_prepared_event",
        lambda prepared, resolutions, captures: _assert_depth(
            evidence,
            IngestedEvent(
                event=prepared.event_read,
                entities=[],
                alerts=[],
                token_intents=[],
                token_resolutions=[],
                inserted=True,
            ),
        ),
    )

    result = ingest.ingest_event(event, is_watched=True)

    assert result.inserted is True
    assert evidence.entries == 1
    assert evidence.depth == 0


@pytest.mark.parametrize(
    "repository_name",
    [
        "token_evidence",
        "token_intents",
        "intent_resolutions",
        "discovery",
        "market_ticks",
        "enriched_events",
        "event_anchor_jobs",
    ],
)
def test_ingest_service_wiring_requires_formal_repository_session_contract(repository_name: str, monkeypatch) -> None:
    repos = _FakeRepos(event_exists=False)
    delattr(repos, repository_name)
    monkeypatch.setattr(bootstrap_module, "IngestService", _FakeIngestService)

    with pytest.raises(AttributeError, match=repository_name):
        _ingest_service_for_repos(repos, event_anchor_active_window_ms=300_000)


def test_pooled_ingest_store_requires_event_anchor_window_contract() -> None:
    with pytest.raises(TypeError, match="event_anchor_active_window_ms"):
        _PooledIngestStore(
            _FakeDB(_FakeState(), event_exists=False),
            providers=AssetMarketProviders(),
        )


def test_ingest_service_for_repos_requires_event_anchor_window_contract() -> None:
    with pytest.raises(TypeError, match="event_anchor_active_window_ms"):
        _ingest_service_for_repos(_FakeRepos(event_exists=False))


@pytest.mark.parametrize("value", [0, -1, True, "300000"])
def test_pooled_ingest_store_rejects_malformed_event_anchor_window_without_runtime_repair(value: Any) -> None:
    with pytest.raises(ValueError, match="event_anchor_active_window_ms_required"):
        _PooledIngestStore(
            _FakeDB(_FakeState(), event_exists=False),
            providers=AssetMarketProviders(),
            event_anchor_active_window_ms=value,
        )


@pytest.mark.parametrize("value", [0, -1, True, "300000"])
def test_ingest_service_rejects_malformed_event_anchor_window_without_runtime_repair(value: Any) -> None:
    with pytest.raises(ValueError, match="event_anchor_active_window_ms_required"):
        _ingest_service_for_repos(_FakeRepos(event_exists=False), event_anchor_active_window_ms=value)


@dataclass
class _FakeState:
    in_session: bool = False


class _FakeEvidenceTransaction:
    def __init__(self) -> None:
        self.conn = object()
        self.depth = 0
        self.entries = 0

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.entries += 1
        self.depth += 1
        try:
            yield
        finally:
            self.depth -= 1


def _assert_depth(evidence: _FakeEvidenceTransaction, result: Any = None) -> Any:
    assert evidence.depth == 1
    return result


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
        self.conn = object()
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
        self.discovery = self
        self.enriched_events = self
        self.event_exists = event_exists
        self.market_ticks = _FakeMarketTicks()
        self.market_tick_current = self
        self.event_anchor_jobs = self
        self.token_radar_dirty_targets = self
        self.transaction_depth = 0

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.transaction_depth += 1
        try:
            yield
        finally:
            self.transaction_depth -= 1


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
        _row, event_read = materialize_event(event, is_watched=is_watched, now_ms=event.received_at_ms)
        return PreparedIngest(
            raw_event=event,
            event_read=event_read,
            event_id=event.event_id,
            event_ms=event.received_at_ms,
            event_row={},
            entities=[],
            evidence_inputs=[],
            intents=[],
            is_watched=is_watched,
        )

    def event_already_exists(self, prepared) -> bool:
        assert self.repos.transaction_depth == 1
        return bool(self.repos.event_exists)

    def prepare_registry_for_resolution(self, prepared) -> None:
        assert self.repos.transaction_depth == 1

    def resolve_prepared(self, prepared, *, persist: bool = False):
        return [
            {
                "event_id": prepared.event_id,
                "intent_id": "intent-1",
                "target_type": "Asset",
                "target_id": "asset:eip155:1:erc20:0xabc",
                "pricefeed_id": None,
                "decision_time_ms": prepared.event_ms,
            }
        ]

    def market_resolution_for_decision(self, decision):
        return {
            "event_id": decision["event_id"],
            "intent_id": decision["intent_id"],
            "resolution_id": "resolution-1",
            "target_type": "chain_token",
            "target_id": "eip155:1:0xabc",
        }

    def duplicate_result(self, prepared):
        return IngestedEvent(
            event=prepared.event_read,
            entities=[],
            alerts=[],
            token_intents=[],
            token_resolutions=[],
            inserted=False,
        )

    def commit_prepared_event(self, prepared, *, resolutions, captures):
        assert self.repos.transaction_depth == 1
        return IngestedEvent(
            event=prepared.event_read,
            entities=[],
            alerts=[],
            token_intents=[],
            token_resolutions=[],
            inserted=True,
        )
