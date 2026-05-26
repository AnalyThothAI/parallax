from __future__ import annotations

from types import SimpleNamespace

import pytest

from gmgn_twitter_intel.app.runtime import worker_factories
from gmgn_twitter_intel.app.runtime.bootstrap import _assemble_runtime
from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_factories import WorkerFactorySpec, construct_workers
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.asset_market.runtime.event_anchor_backfill_worker import EventAnchorBackfillWorker
from gmgn_twitter_intel.domains.asset_market.runtime.live_price_gateway import LivePriceGateway
from gmgn_twitter_intel.domains.asset_market.runtime.market_tick_current_projection_worker import (
    MarketTickCurrentProjectionWorker,
)
from gmgn_twitter_intel.domains.asset_market.runtime.market_tick_poll_worker import MarketTickPollWorker
from gmgn_twitter_intel.domains.asset_market.runtime.market_tick_stream_worker import MarketTickStreamWorker
from gmgn_twitter_intel.domains.asset_market.runtime.token_capture_tier_worker import TokenCaptureTierWorker
from gmgn_twitter_intel.domains.asset_market.runtime.token_image_mirror_worker import TokenImageMirrorWorker
from gmgn_twitter_intel.domains.asset_market.runtime.token_profile_current_worker import TokenProfileCurrentWorker
from gmgn_twitter_intel.domains.equity_event_intel.runtime.equity_event_brief_worker import EquityEventBriefWorker
from gmgn_twitter_intel.domains.macro_intel.runtime.macro_view_projection_worker import MacroViewProjectionWorker
from gmgn_twitter_intel.domains.narrative_intel.runtime.mention_semantics_worker import MentionSemanticsWorker
from gmgn_twitter_intel.domains.narrative_intel.runtime.token_discussion_digest_worker import (
    TokenDiscussionDigestWorker,
)
from gmgn_twitter_intel.domains.news_intel.runtime.news_fetch_worker import NewsFetchWorker
from gmgn_twitter_intel.domains.news_intel.runtime.news_item_brief_worker import NewsItemBriefWorker
from gmgn_twitter_intel.domains.news_intel.runtime.news_item_process_worker import NewsItemProcessWorker
from gmgn_twitter_intel.domains.news_intel.runtime.news_page_projection_worker import NewsPageProjectionWorker
from gmgn_twitter_intel.domains.news_intel.runtime.news_source_quality_projection_worker import (
    NewsSourceQualityProjectionWorker,
)
from gmgn_twitter_intel.domains.news_intel.runtime.news_story_projection_worker import NewsStoryProjectionWorker
from gmgn_twitter_intel.domains.notifications.runtime.notification_delivery import NotificationDeliveryWorker
from gmgn_twitter_intel.domains.notifications.runtime.notification_worker import NotificationWorker
from gmgn_twitter_intel.platform.config.settings import Settings

_UNSET = object()


def _old_anchor_worker_key() -> str:
    return "_".join(("anchor", "price"))


def test_bootstrap_wires_market_tick_runtime_and_hard_cuts_legacy_anchor_worker() -> None:
    db = FakeDB()
    providers = FakeProviders()

    workers = construct_workers(
        settings=_settings(),
        db=db,
        telemetry=object(),
        providers=providers,
        hub=SimpleNamespace(publish=lambda payload: None),
        collector=SimpleNamespace(),
        collector_enabled=False,
        wake_bus=db.wake,
    )

    assert _old_anchor_worker_key() not in workers
    assert isinstance(workers["token_capture_tier"], TokenCaptureTierWorker)
    assert workers["token_capture_tier"].batch_size == 500
    assert workers["token_capture_tier"].ws_limit == 100
    assert workers["token_capture_tier"].poll_limit == 500

    assert isinstance(workers["market_tick_stream"], MarketTickStreamWorker)
    assert workers["market_tick_stream"].stream_dex_market is providers.asset_market.stream_dex_market
    assert workers["market_tick_stream"].wake_emitter is db.wake
    assert workers["market_tick_stream"].subscription_limit == 100

    assert isinstance(workers["market_tick_poll"], MarketTickPollWorker)
    assert workers["market_tick_poll"].providers is providers.asset_market
    assert workers["market_tick_poll"].wake_emitter is db.wake
    assert workers["market_tick_poll"].batch_size == 100
    assert isinstance(workers["market_tick_current_projection"], MarketTickCurrentProjectionWorker)
    assert workers["market_tick_current_projection"].wake_emitter is db.wake
    assert workers["market_tick_current_projection"].wake_waiter.channels == ("market_tick_written",)
    assert workers["market_tick_current_projection"].settings.advisory_lock_key == 2026052401

    assert isinstance(workers["event_anchor_backfill"], EventAnchorBackfillWorker)
    assert workers["event_anchor_backfill"].wake_emitter is db.wake
    assert workers["event_anchor_backfill"].batch_size == 50
    assert workers["event_anchor_backfill"].concurrency == 8
    assert workers["event_anchor_backfill"].min_age_ms == 250

    assert isinstance(workers["live_price_gateway"], LivePriceGateway)
    # LivePriceGateway is now a DB-only fan-out: it must not retain references to upstream
    # stream or CEX REST providers. OKX DEX WS has exactly one runtime owner (market_tick_stream).
    assert not hasattr(workers["live_price_gateway"], "stream_provider")
    assert not hasattr(workers["live_price_gateway"], "cex_market")
    assert not hasattr(workers["live_price_gateway"], "wake_bus")
    assert isinstance(workers["token_image_mirror"], TokenImageMirrorWorker)
    assert workers["token_image_mirror"].settings.source_limit == 5000
    assert isinstance(workers["token_profile_current"], TokenProfileCurrentWorker)


def test_bootstrap_wires_live_price_gateway_as_db_only_worker_without_price_providers() -> None:
    db = FakeDB()
    providers = FakeProviders(
        cex_market=None,
        dex_quote_market=None,
        stream_dex_market=None,
    )

    workers = construct_workers(
        settings=_settings(),
        db=db,
        telemetry=object(),
        providers=providers,
        hub=SimpleNamespace(publish=lambda payload: None),
        collector=SimpleNamespace(),
        collector_enabled=False,
        wake_bus=db.wake,
    )

    assert isinstance(workers["live_price_gateway"], LivePriceGateway)
    assert not isinstance(workers["market_tick_stream"], MarketTickStreamWorker)
    assert not isinstance(workers["market_tick_poll"], MarketTickPollWorker)
    assert not isinstance(workers["event_anchor_backfill"], EventAnchorBackfillWorker)
    assert isinstance(workers["market_tick_current_projection"], MarketTickCurrentProjectionWorker)


def test_worker_factory_preserves_enabled_collector_injection() -> None:
    db = FakeDB()
    providers = FakeProviders()
    collector = FakeCollector(name="collector", settings=SimpleNamespace(enabled=True), db=db, telemetry=object())

    workers = construct_workers(
        settings=_settings(collector_enabled=True),
        db=db,
        telemetry=object(),
        providers=providers,
        hub=SimpleNamespace(publish=lambda payload: None),
        collector=collector,
        collector_enabled=True,
        wake_bus=db.wake,
    )

    assert workers["collector"] is collector


def test_bootstrap_runtime_preserves_enabled_collector_injection_and_attaches_upstream_client() -> None:
    db = FakeDB()
    created_clients: list[FakeUpstreamClient] = []

    def upstream_client_factory(on_frame):
        client = FakeUpstreamClient(on_frame=on_frame)
        created_clients.append(client)
        return client

    runtime = _assemble_runtime(
        settings=_settings(collector_enabled=True),
        db=db,
        telemetry=object(),
        providers=FakeProviders(upstream_client_factory=upstream_client_factory),
        start_collector=True,
        llm_gateway=None,
    )

    assert runtime.start_collector is True
    assert runtime.workers["collector"] is runtime.collector
    assert created_clients == [runtime.collector.upstream_client]
    assert runtime.collector.upstream_client is not None
    assert runtime.collector.upstream_client.on_frame.__self__ is runtime.collector
    assert runtime.collector.upstream_client.on_frame.__func__ is runtime.collector.handle_frame.__func__


def test_worker_factory_wires_notification_workers_with_shared_local_wake_waiter() -> None:
    db = FakeDB()
    providers = FakeProviders()

    workers = construct_workers(
        settings=_settings(notifications_enabled=True),
        db=db,
        telemetry=object(),
        providers=providers,
        hub=SimpleNamespace(publish=lambda payload: None),
        collector=FakeCollector(name="collector", settings=SimpleNamespace(enabled=False), db=db, telemetry=object()),
        collector_enabled=False,
        wake_bus=db.wake,
    )

    assert isinstance(workers["notification_rule"], NotificationWorker)
    assert isinstance(workers["notification_delivery"], NotificationDeliveryWorker)
    assert workers["notification_rule"].delivery_wake is workers["notification_delivery"].wake_waiter


def test_worker_factory_wires_news_fetch_by_default() -> None:
    db = FakeDB()
    providers = FakeProviders()

    workers = construct_workers(
        settings=_settings(),
        db=db,
        telemetry=object(),
        providers=providers,
        hub=SimpleNamespace(publish=lambda payload: None),
        collector=FakeCollector(name="collector", settings=SimpleNamespace(enabled=False), db=db, telemetry=object()),
        collector_enabled=False,
        wake_bus=db.wake,
    )

    assert isinstance(workers["news_fetch"], NewsFetchWorker)
    assert workers["news_fetch"].wake_bus is db.wake
    assert workers["news_fetch"].feed_client is providers.news_intel.feed_client
    assert isinstance(workers["news_item_process"], NewsItemProcessWorker)
    assert workers["news_item_process"].wake_bus is db.wake
    assert workers["news_item_process"].identity_lookup is not None
    assert workers["news_item_process"].wake_waiter.channels == ("news_item_written",)
    assert workers["news_item_process"].settings.advisory_lock_key == 2026051902
    assert isinstance(workers["news_story_projection"], NewsStoryProjectionWorker)
    assert workers["news_story_projection"].wake_bus is db.wake
    assert workers["news_story_projection"].wake_waiter.channels == ("news_item_processed",)
    assert workers["news_story_projection"].settings.advisory_lock_key == 2026051903
    assert not isinstance(workers["news_item_brief"], NewsItemBriefWorker)
    assert isinstance(workers["news_page_projection"], NewsPageProjectionWorker)
    assert workers["news_page_projection"].wake_bus is db.wake
    assert workers["news_page_projection"].wake_waiter.channels == (
        "news_item_written",
        "news_item_processed",
        "news_story_updated",
        "news_item_brief_updated",
        "news_page_dirty",
    )
    assert workers["news_page_projection"].settings.advisory_lock_key == 2026051904
    assert isinstance(workers["news_source_quality_projection"], NewsSourceQualityProjectionWorker)
    assert workers["news_source_quality_projection"].wake_bus is db.wake
    assert workers["news_source_quality_projection"].wake_waiter.channels == (
        "news_item_written",
        "news_item_processed",
        "news_story_updated",
        "news_item_brief_updated",
    )
    assert workers["news_source_quality_projection"].settings.advisory_lock_key == 2026052201
    assert isinstance(workers["macro_view_projection"], MacroViewProjectionWorker)
    assert workers["macro_view_projection"].settings.advisory_lock_key == 2026052109
    assert workers["macro_view_projection"].settings.batch_size == 250


def test_worker_factory_wires_narrative_mention_and_digest_wake_waiters() -> None:
    db = FakeDB()
    providers = FakeProviders()

    workers = construct_workers(
        settings=_settings(narrative_intel_configured=True),
        db=db,
        telemetry=object(),
        providers=providers,
        hub=SimpleNamespace(publish=lambda payload: None),
        collector=FakeCollector(name="collector", settings=SimpleNamespace(enabled=False), db=db, telemetry=object()),
        collector_enabled=False,
        wake_bus=db.wake,
    )

    assert isinstance(workers["mention_semantics"], MentionSemanticsWorker)
    assert workers["mention_semantics"].wake_waiter.worker_name == "mention_semantics"
    assert workers["mention_semantics"].wake_waiter.channels == ("token_radar_updated", "resolution_updated")
    assert isinstance(workers["token_discussion_digest"], TokenDiscussionDigestWorker)
    assert workers["token_discussion_digest"].wake_waiter.worker_name == "token_discussion_digest"
    assert workers["token_discussion_digest"].wake_waiter.channels == (
        "token_radar_updated",
        "narrative_semantics_updated",
        "market_tick_written",
    )


def test_worker_factory_wires_news_item_brief_when_configured() -> None:
    db = FakeDB()
    providers = FakeProviders(brief_provider=object())

    workers = construct_workers(
        settings=_settings(news_item_brief_configured=True),
        db=db,
        telemetry=object(),
        providers=providers,
        hub=SimpleNamespace(publish=lambda payload: None),
        collector=FakeCollector(name="collector", settings=SimpleNamespace(enabled=False), db=db, telemetry=object()),
        collector_enabled=False,
        wake_bus=db.wake,
    )

    assert isinstance(workers["news_item_brief"], NewsItemBriefWorker)
    assert workers["news_item_brief"].provider is providers.news_intel.brief_provider
    assert workers["news_item_brief"].wake_bus is db.wake
    assert workers["news_item_brief"].wake_waiter.channels == ("news_item_processed", "news_story_updated")
    assert workers["news_item_brief"].settings.advisory_lock_key == 2026052001


def test_worker_factory_wires_equity_event_brief_when_configured() -> None:
    db = FakeDB()
    providers = FakeProviders(equity_brief_provider=object())

    workers = construct_workers(
        settings=_settings(equity_event_brief_configured=True),
        db=db,
        telemetry=object(),
        providers=providers,
        hub=SimpleNamespace(publish=lambda payload: None),
        collector=FakeCollector(name="collector", settings=SimpleNamespace(enabled=False), db=db, telemetry=object()),
        collector_enabled=False,
        wake_bus=db.wake,
    )

    assert isinstance(workers["equity_event_brief"], EquityEventBriefWorker)
    assert workers["equity_event_brief"].provider is providers.equity_event_intel.brief_provider
    assert workers["equity_event_brief"].wake_bus is db.wake
    assert workers["equity_event_brief"].wake_waiter.channels == ("equity_event_story_updated",)


def test_worker_factory_rejects_returned_key_outside_owned_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    def rogue_factory(ctx):
        return {"token_radar_projection": ctx.collector}

    specs = tuple(
        WorkerFactorySpec(spec.name, spec.keys, rogue_factory if spec.name == "ingestion.py" else spec.factory)
        for spec in worker_factories.worker_factory_specs()
    )
    monkeypatch.setattr(
        worker_factories,
        "worker_factory_specs",
        lambda: specs,
    )
    db = FakeDB()
    collector = FakeCollector(name="collector", settings=SimpleNamespace(enabled=True), db=db, telemetry=object())

    with pytest.raises(KeyError, match="returned unowned workers"):
        construct_workers(
            settings=_settings(collector_enabled=True),
            db=db,
            telemetry=object(),
            providers=FakeProviders(),
            hub=SimpleNamespace(publish=lambda payload: None),
            collector=collector,
            collector_enabled=True,
            wake_bus=object(),
        )


def _settings(
    *,
    collector_enabled: bool = False,
    notifications_enabled: bool = False,
    narrative_intel_configured: bool = False,
    news_item_brief_configured: bool = False,
    equity_event_brief_configured: bool = False,
) -> Settings:
    llm = {"api_key": "secret"} if narrative_intel_configured else {}
    agent_lanes = {}
    if news_item_brief_configured:
        llm = {**llm, "api_key": "secret"}
        agent_lanes["news.item_brief"] = {"model": "gpt-5-mini"}
    equity_event_intel = {"enabled": False}
    if equity_event_brief_configured:
        llm = {**llm, "api_key": "secret"}
        agent_lanes["equity_event.brief"] = {"model": "gpt-5-mini"}
        equity_event_intel = {"enabled": True, "agent": {"enabled": True}}
    return Settings(
        ws_token="secret",
        llm=llm,
        equity_event_intel=equity_event_intel,
        notifications={
            "enabled": notifications_enabled,
            "channels": {
                "log": {
                    "enabled": True,
                    "provider": "log",
                    "min_severity": "info",
                }
            },
        },
        workers={
            "agent_runtime": {
                "defaults": {"model": "gpt-test"},
                "lanes": agent_lanes,
            },
            "collector": {"enabled": collector_enabled},
            "market_tick_stream": {"enabled": True},
            "market_tick_poll": {"enabled": True},
            "market_tick_current_projection": {"enabled": True},
            "event_anchor_backfill": {"enabled": True},
            "token_capture_tier": {"enabled": True},
            "live_price_gateway": {"enabled": True},
            "resolution_refresh": {"enabled": False},
            "asset_profile_refresh": {"enabled": False},
            "token_image_mirror": {"enabled": True},
            "token_profile_current": {"enabled": True},
            "token_radar_projection": {"enabled": False},
            "pulse_candidate": {"enabled": False},
            "enrichment": {"enabled": False},
            "handle_summary": {"enabled": False},
            "notification_rule": {"enabled": notifications_enabled},
            "notification_delivery": {"enabled": notifications_enabled},
            "equity_event_brief": {"enabled": equity_event_brief_configured},
        },
    )


class FakeProviders:
    def __init__(
        self,
        *,
        cex_market=_UNSET,
        dex_quote_market=_UNSET,
        stream_dex_market=_UNSET,
        upstream_client_factory=None,
        brief_provider=None,
        equity_brief_provider=None,
    ) -> None:
        self.asset_market = SimpleNamespace(
            cex_market=object() if cex_market is _UNSET else cex_market,
            dex_quote_market=object() if dex_quote_market is _UNSET else dex_quote_market,
            dex_profile_sources=(),
            dex_discovery_market=None,
            stream_dex_market=object() if stream_dex_market is _UNSET else stream_dex_market,
        )
        self.pulse_lab = SimpleNamespace(decision_provider=None)
        self.watchlist_intel = SimpleNamespace(summary_provider=None)
        self.social_enrichment = SimpleNamespace(event_enrichment=None)
        self.ingestion = SimpleNamespace(upstream_client_factory=upstream_client_factory)
        self.macrodata = SimpleNamespace(stock_quote_provider=None)
        self.news_intel = SimpleNamespace(feed_client=object(), brief_provider=brief_provider)
        self.narrative_intel = SimpleNamespace(narrative_provider=object())
        self.equity_event_intel = SimpleNamespace(document_provider=object(), brief_provider=equity_brief_provider)


class FakeDB:
    def __init__(self) -> None:
        self.api_pool = object()
        self.wake = object()

    def api_session(self):
        raise AssertionError("api_session should not be opened by runtime assembly")

    def wake_emitter(self):
        return self.wake

    def wake_listener(self, worker_name, channels):
        return SimpleNamespace(worker_name=worker_name, channels=channels)


class FakeCollector(WorkerBase):
    async def run_once(self) -> WorkerResult:
        return WorkerResult(skipped=1)


class FakeUpstreamClient:
    def __init__(self, *, on_frame) -> None:
        self.on_frame = on_frame

    async def run(self) -> None:
        return None
