from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import parallax.app.runtime.bootstrap as bootstrap_module
from parallax.app.runtime import worker_factories
from parallax.app.runtime.bootstrap import _assemble_runtime
from parallax.app.runtime.provider_wiring.types import (
    AssetMarketProviders,
    CexMarketIntelProviders,
    IngestionProviders,
    NewsIntelProviders,
    WiredProviders,
)
from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_factories import (
    WorkerFactoryContext,
    WorkerFactorySpec,
    construct_workers,
    intentionally_not_started_worker,
)
from parallax.app.runtime.worker_manifest import all_worker_manifests
from parallax.app.runtime.worker_result import WorkerResult
from parallax.app.runtime.worker_scheduler import WorkerScheduler
from parallax.domains.asset_market.runtime.event_anchor_backfill_worker import EventAnchorBackfillWorker
from parallax.domains.asset_market.runtime.live_price_gateway import LivePriceGateway
from parallax.domains.asset_market.runtime.market_tick_current_projection_worker import (
    MarketTickCurrentProjectionWorker,
)
from parallax.domains.asset_market.runtime.market_tick_poll_worker import MarketTickPollWorker
from parallax.domains.asset_market.runtime.market_tick_stream_worker import MarketTickStreamWorker
from parallax.domains.asset_market.runtime.token_capture_tier_worker import TokenCaptureTierWorker
from parallax.domains.asset_market.runtime.token_image_mirror_worker import TokenImageMirrorWorker
from parallax.domains.asset_market.runtime.token_profile_current_worker import TokenProfileCurrentWorker
from parallax.domains.cex_market_intel.runtime.cex_oi_radar_board_worker import CexOiRadarBoardWorker
from parallax.domains.macro_intel.runtime.macro_daily_brief_projection_worker import MacroDailyBriefProjectionWorker
from parallax.domains.macro_intel.runtime.macro_sync_worker import MacroSyncWorker
from parallax.domains.macro_intel.runtime.macro_view_projection_worker import MacroViewProjectionWorker
from parallax.domains.narrative_intel.runtime.narrative_admission_worker import NarrativeAdmissionWorker
from parallax.domains.news_intel.runtime.news_fetch_worker import NewsFetchWorker
from parallax.domains.news_intel.runtime.news_item_brief_worker import NewsItemBriefWorker
from parallax.domains.news_intel.runtime.news_item_process_worker import NewsItemProcessWorker
from parallax.domains.news_intel.runtime.news_page_projection_worker import NewsPageProjectionWorker
from parallax.domains.news_intel.runtime.news_source_quality_projection_worker import (
    NewsSourceQualityProjectionWorker,
)
from parallax.domains.news_intel.runtime.news_story_brief_worker import NewsStoryBriefWorker
from parallax.domains.notifications.runtime.notification_delivery import NotificationDeliveryWorker
from parallax.domains.notifications.runtime.notification_worker import NotificationWorker
from parallax.domains.token_intel.runtime.token_radar_projection_worker import TokenRadarProjectionWorker
from parallax.platform.config.settings import Settings

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
    assert workers["live_price_gateway"].target_limit == 100
    assert workers["live_price_gateway"].target_ttl_seconds == 300
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
    assert workers["market_tick_stream"].status_payload()["effective_status"] == "unavailable"
    assert workers["market_tick_stream"].status_payload()["unavailable_reason"] == (
        "missing_asset_market_stream_provider"
    )
    assert workers["market_tick_poll"].status_payload()["effective_status"] == "unavailable"
    assert workers["market_tick_poll"].status_payload()["unavailable_reason"] == ("missing_asset_market_quote_provider")
    reasons = WorkerScheduler(workers=workers, db=db).unhealthy_reasons()
    assert "worker:market_tick_stream:unavailable:missing_asset_market_stream_provider" in reasons
    assert "worker:market_tick_poll:unavailable:missing_asset_market_quote_provider" in reasons
    assert isinstance(workers["event_anchor_backfill"], EventAnchorBackfillWorker)
    assert isinstance(workers["market_tick_current_projection"], MarketTickCurrentProjectionWorker)


def test_enabled_worker_without_required_provider_surfaces_unavailable() -> None:
    db = FakeDB()

    workers = construct_workers(
        settings=_settings(cex_oi_radar_board_enabled=True),
        db=db,
        telemetry=object(),
        providers=FakeProviders(cex_oi_market=None),
        hub=SimpleNamespace(publish=lambda payload: None),
        collector=SimpleNamespace(),
        collector_enabled=False,
        wake_bus=db.wake,
    )

    status = workers["cex_oi_radar_board"].status_payload()
    assert status["enabled"] is True
    assert status["effective_status"] == "unavailable"
    assert status["unavailable_reason"] == "missing_cex_oi_market_provider"
    assert "secret" not in status["unavailable_reason"]
    assert (
        "worker:cex_oi_radar_board:unavailable:missing_cex_oi_market_provider"
        in WorkerScheduler(workers=workers, db=db).unhealthy_reasons()
    )


def test_enabled_cex_oi_radar_worker_uses_formal_runtime_contract_with_provider() -> None:
    db = FakeDB()
    oi_market = object()
    coinglass = object()

    workers = construct_workers(
        settings=_settings(cex_oi_radar_board_enabled=True),
        db=db,
        telemetry=object(),
        providers=FakeProviders(cex_oi_market=oi_market, coinglass_derivatives=coinglass),
        hub=SimpleNamespace(publish=lambda payload: None),
        collector=SimpleNamespace(),
        collector_enabled=False,
        wake_bus=db.wake,
    )

    worker = workers["cex_oi_radar_board"]
    assert isinstance(worker, CexOiRadarBoardWorker)
    assert worker.oi_market is oi_market
    assert worker.coinglass_derivatives is coinglass
    assert worker.settings.batch_size == 500
    assert worker.settings.universe_limit == 500
    assert worker.settings.statement_timeout_seconds == 120
    assert not hasattr(worker, "wake_bus")


def test_enabled_asset_profile_refresh_without_profile_provider_surfaces_unavailable() -> None:
    db = FakeDB()

    workers = construct_workers(
        settings=_settings(asset_profile_refresh_enabled=True),
        db=db,
        telemetry=object(),
        providers=FakeProviders(dex_profile_sources=()),
        hub=SimpleNamespace(publish=lambda payload: None),
        collector=SimpleNamespace(),
        collector_enabled=False,
        wake_bus=db.wake,
    )

    status = workers["asset_profile_refresh"].status_payload()
    assert status["enabled"] is True
    assert status["effective_status"] == "unavailable"
    assert status["unavailable_reason"] == "missing_asset_profile_provider"
    assert (
        "worker:asset_profile_refresh:unavailable:missing_asset_profile_provider"
        in WorkerScheduler(workers=workers, db=db).unhealthy_reasons()
    )


def test_enabled_resolution_refresh_without_discovery_provider_surfaces_unavailable() -> None:
    db = FakeDB()

    workers = construct_workers(
        settings=_settings(resolution_refresh_enabled=True),
        db=db,
        telemetry=object(),
        providers=FakeProviders(dex_discovery_market=None),
        hub=SimpleNamespace(publish=lambda payload: None),
        collector=SimpleNamespace(),
        collector_enabled=False,
        wake_bus=db.wake,
    )

    status = workers["resolution_refresh"].status_payload()
    assert status["enabled"] is True
    assert status["effective_status"] == "unavailable"
    assert status["unavailable_reason"] == "missing_asset_discovery_provider"
    assert (
        "worker:resolution_refresh:unavailable:missing_asset_discovery_provider"
        in WorkerScheduler(workers=workers, db=db).unhealthy_reasons()
    )


def test_asset_market_worker_factory_requires_formal_provider_bundle_fields() -> None:
    providers = FakeProviders()
    providers.asset_market = SimpleNamespace(stream_dex_market=object())

    try:
        construct_workers(
            settings=_settings(),
            db=FakeDB(),
            telemetry=object(),
            providers=providers,
            hub=SimpleNamespace(publish=lambda payload: None),
            collector=SimpleNamespace(),
            collector_enabled=False,
            wake_bus=object(),
        )
    except AttributeError as exc:
        assert "cex_market" in str(exc)
    else:  # pragma: no cover - RED guard expectation
        raise AssertionError("Asset Market worker factory must not hide missing bundle fields as unavailable providers")


def test_worker_disabled_by_config_surfaces_disabled_and_is_readiness_ignored() -> None:
    db = FakeDB()

    workers = construct_workers(
        settings=_settings(cex_oi_radar_board_enabled=False),
        db=db,
        telemetry=object(),
        providers=FakeProviders(cex_market=None),
        hub=SimpleNamespace(publish=lambda payload: None),
        collector=SimpleNamespace(),
        collector_enabled=False,
        wake_bus=db.wake,
    )

    status = workers["cex_oi_radar_board"].status_payload()
    assert status["enabled"] is False
    assert status["effective_status"] == "disabled"
    assert status["unavailable_reason"] is None
    assert not any(
        "cex_oi_radar_board" in reason for reason in WorkerScheduler(workers=workers, db=db).unhealthy_reasons()
    )


def test_start_collector_false_surfaces_intentional_not_started_status() -> None:
    db = FakeDB()

    runtime = _assemble_runtime(
        settings=_settings(collector_enabled=True, event_anchor_active_window_ms=123_456),
        db=db,
        telemetry=object(),
        providers=FakeProviders(upstream_client_factory=lambda on_frame: FakeUpstreamClient(on_frame=on_frame)),
        start_collector=False,
        llm_gateway=None,
    )

    status = runtime.workers["collector"].status_payload()
    assert runtime.start_collector is False
    assert runtime.collector.upstream_client is None
    assert runtime.ingest.event_anchor_active_window_ms == 123_456
    assert status["enabled"] is False
    assert status["effective_status"] == "intentionally_not_started"
    assert status["unavailable_reason"] is None
    assert not any("collector:unavailable" in reason for reason in runtime.scheduler.unhealthy_reasons())


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
    assert workers["notification_delivery"].wake_waiter.close() is None
    assert workers["notification_rule"].settings.batch_size == 50
    assert workers["notification_rule"].settings.statement_timeout_seconds == 30
    assert workers["notification_delivery"].settings.batch_size == 1
    assert workers["notification_delivery"].settings.statement_timeout_seconds == 30


@pytest.mark.parametrize("timeout", [-1, True, "0.01"])
def test_notification_local_wake_waiter_rejects_malformed_timeout_without_runtime_repair(timeout: object) -> None:
    db = FakeDB()
    workers = construct_workers(
        settings=_settings(notifications_enabled=True),
        db=db,
        telemetry=object(),
        providers=FakeProviders(),
        hub=SimpleNamespace(publish=lambda payload: None),
        collector=FakeCollector(name="collector", settings=SimpleNamespace(enabled=False), db=db, telemetry=object()),
        collector_enabled=False,
        wake_bus=db.wake,
    )

    with pytest.raises(ValueError, match="wake_waiter_timeout_seconds_required"):
        asyncio.run(workers["notification_delivery"].wake_waiter.async_wait(timeout))


def test_notification_delivery_without_enabled_channel_is_disabled_not_unavailable() -> None:
    db = FakeDB()

    workers = construct_workers(
        settings=_settings(notifications_enabled=True, notification_log_channel_enabled=False),
        db=db,
        telemetry=object(),
        providers=FakeProviders(),
        hub=SimpleNamespace(publish=lambda payload: None),
        collector=FakeCollector(name="collector", settings=SimpleNamespace(enabled=False), db=db, telemetry=object()),
        collector_enabled=False,
        wake_bus=db.wake,
    )

    assert isinstance(workers["notification_rule"], NotificationWorker)
    assert not isinstance(workers["notification_delivery"], NotificationDeliveryWorker)
    status = workers["notification_delivery"].status_payload()
    assert status["effective_status"] == "disabled"
    assert status["unavailable_reason"] is None
    assert not any(
        "notification_delivery" in reason for reason in WorkerScheduler(workers=workers, db=db).unhealthy_reasons()
    )


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
    assert workers["news_fetch"].wake_emitter is db.wake
    assert not hasattr(workers["news_fetch"], "wake_bus")
    assert workers["news_fetch"].feed_client is providers.news_intel.feed_client
    assert workers["news_fetch"].settings.batch_size == 5
    assert workers["news_fetch"].settings.statement_timeout_seconds == 30
    assert isinstance(workers["news_item_process"], NewsItemProcessWorker)
    assert workers["news_item_process"].wake_emitter is db.wake
    assert not hasattr(workers["news_item_process"], "wake_bus")
    assert workers["news_item_process"].identity_lookup is not None
    assert workers["news_item_process"].wake_waiter.channels == ("news_item_written",)
    assert workers["news_item_process"].settings.advisory_lock_key == 2026051902
    assert workers["news_item_process"].settings.batch_size == 10
    assert workers["news_item_process"].settings.lease_ms == 120_000
    assert workers["news_item_process"].settings.max_attempts == 3
    assert workers["news_item_process"].settings.retry_delay_ms == 60_000
    assert workers["news_item_process"].settings.statement_timeout_seconds == 30
    assert "news_story_projection" not in workers
    assert not isinstance(workers["news_item_brief"], NewsItemBriefWorker)
    assert not isinstance(workers["news_story_brief"], NewsStoryBriefWorker)
    assert workers["news_story_brief"].status_payload()["effective_status"] == "disabled"
    assert isinstance(workers["news_page_projection"], NewsPageProjectionWorker)
    assert not hasattr(workers["news_page_projection"], "wake_bus")
    assert workers["news_page_projection"].wake_waiter.channels == (
        "news_item_written",
        "news_item_processed",
        "news_story_brief_updated",
        "news_page_dirty",
    )
    assert workers["news_page_projection"].settings.advisory_lock_key == 2026051904
    assert workers["news_page_projection"].settings.batch_size == 100
    assert workers["news_page_projection"].settings.lease_ms == 120_000
    assert workers["news_page_projection"].settings.retry_ms == 30_000
    assert workers["news_page_projection"].settings.statement_timeout_seconds == 30
    assert isinstance(workers["news_source_quality_projection"], NewsSourceQualityProjectionWorker)
    assert workers["news_source_quality_projection"].wake_emitter is db.wake
    assert not hasattr(workers["news_source_quality_projection"], "wake_bus")
    assert workers["news_source_quality_projection"].wake_waiter.channels == ("news_item_written",)
    assert workers["news_source_quality_projection"].settings.advisory_lock_key == 2026052201
    assert workers["news_source_quality_projection"].settings.lease_ms == 120_000
    assert workers["news_source_quality_projection"].settings.retry_ms == 30_000
    assert isinstance(workers["macro_view_projection"], MacroViewProjectionWorker)
    assert isinstance(workers["macro_sync"], MacroSyncWorker)
    assert workers["macro_sync"].wake_emitter is db.wake
    assert not hasattr(workers["macro_sync"], "wake_bus")
    assert workers["macro_sync"].settings.batch_size == 3
    assert workers["macro_view_projection"].wake_emitter is db.wake
    assert not hasattr(workers["macro_view_projection"], "wake_bus")
    assert workers["macro_view_projection"].settings.advisory_lock_key == 2026052109
    assert workers["macro_view_projection"].settings.batch_size == 250
    assert workers["macro_view_projection"].settings.lease_ms == 300_000
    assert workers["macro_view_projection"].settings.retry_ms == 300_000
    assert workers["macro_view_projection"].wake_waiter.channels == ("macro_observations_imported",)
    assert isinstance(workers["macro_daily_brief_projection"], MacroDailyBriefProjectionWorker)
    assert workers["macro_daily_brief_projection"].wake_waiter.channels == ("macro_view_snapshot_updated",)
    assert workers["macro_daily_brief_projection"].settings.statement_timeout_seconds == 30


def test_worker_factory_requires_news_intel_provider_bundle_root() -> None:
    db = FakeDB()
    providers = FakeProviders()
    del providers.news_intel

    with pytest.raises(AttributeError, match="news_intel"):
        construct_workers(
            settings=_settings(),
            db=db,
            telemetry=object(),
            providers=providers,
            hub=SimpleNamespace(publish=lambda payload: None),
            collector=FakeCollector(
                name="collector",
                settings=SimpleNamespace(enabled=False),
                db=db,
                telemetry=object(),
            ),
            collector_enabled=False,
            wake_bus=db.wake,
        )


def test_worker_factory_requires_news_intel_provider_bundle_fields() -> None:
    db = FakeDB()
    providers = FakeProviders()
    providers.news_intel = SimpleNamespace(brief_provider=None)

    with pytest.raises(AttributeError, match="feed_client"):
        construct_workers(
            settings=_settings(),
            db=db,
            telemetry=object(),
            providers=providers,
            hub=SimpleNamespace(publish=lambda payload: None),
            collector=FakeCollector(
                name="collector",
                settings=SimpleNamespace(enabled=False),
                db=db,
                telemetry=object(),
            ),
            collector_enabled=False,
            wake_bus=db.wake,
        )


def test_news_provider_wiring_constructs_opennews_rest_client_without_websocket_kwargs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import parallax.app.runtime.provider_wiring.news as news_wiring

    constructor_calls: list[dict[str, object]] = []

    class RecordingOpenNewsFeedClient:
        def __init__(self, **kwargs: object) -> None:
            constructor_calls.append(dict(kwargs))

        def fetch(self, *_args: object, **_kwargs: object) -> object:
            raise AssertionError("fetch should not run during provider wiring")

        def close(self) -> None:
            return None

    monkeypatch.setattr(news_wiring, "OpenNewsFeedClient", RecordingOpenNewsFeedClient)

    news_wiring.news_feed_client(
        Settings(
            ws_token="secret",
            news_intel={"opennews": {"api_token": "opennews-token", "api_base_url": "https://example.com/"}},
        )
    )

    assert constructor_calls == [{"token": "opennews-token", "api_base_url": "https://example.com"}]


def test_macro_projection_disabled_does_not_suppress_macro_sync() -> None:
    db = FakeDB()

    workers = construct_workers(
        settings=_settings(macro_view_projection_enabled=False),
        db=db,
        telemetry=object(),
        providers=FakeProviders(),
        hub=SimpleNamespace(publish=lambda payload: None),
        collector=FakeCollector(name="collector", settings=SimpleNamespace(enabled=False), db=db, telemetry=object()),
        collector_enabled=False,
        wake_bus=db.wake,
    )

    assert isinstance(workers["macro_sync"], MacroSyncWorker)
    assert not isinstance(workers["macro_view_projection"], MacroViewProjectionWorker)


def test_macro_sync_skips_when_macrodata_provider_disabled() -> None:
    db = FakeDB()

    workers = construct_workers(
        settings=_settings(macrodata_enabled=False),
        db=db,
        telemetry=object(),
        providers=FakeProviders(),
        hub=SimpleNamespace(publish=lambda payload: None),
        collector=FakeCollector(name="collector", settings=SimpleNamespace(enabled=False), db=db, telemetry=object()),
        collector_enabled=False,
        wake_bus=db.wake,
    )

    assert not isinstance(workers["macro_sync"], MacroSyncWorker)
    assert isinstance(workers["macro_view_projection"], MacroViewProjectionWorker)


def test_worker_factory_wires_narrative_admission_without_llm_siblings() -> None:
    db = FakeDB()
    providers = FakeProviders()

    workers = construct_workers(
        settings=_settings(narrative_admission_enabled=True),
        db=db,
        telemetry=object(),
        providers=providers,
        hub=SimpleNamespace(publish=lambda payload: None),
        collector=FakeCollector(name="collector", settings=SimpleNamespace(enabled=False), db=db, telemetry=object()),
        collector_enabled=False,
        wake_bus=db.wake,
    )

    assert isinstance(workers["narrative_admission"], NarrativeAdmissionWorker)
    assert workers["narrative_admission"].wake_waiter.worker_name == "narrative_admission"
    assert workers["narrative_admission"].wake_waiter.channels == ("token_radar_updated", "resolution_updated")
    assert workers["narrative_admission"].settings.lease_ms == 60_000
    assert workers["narrative_admission"].settings.retry_ms == 60_000
    assert workers["narrative_admission"].settings.statement_timeout_seconds == 30
    assert not hasattr(workers["narrative_admission"], "wake_bus")
    assert not hasattr(workers["narrative_admission"], "wake_emitter")
    assert "mention_semantics" not in workers
    assert "token_discussion_digest" not in workers


def test_token_radar_enqueues_narrative_admission_when_admission_worker_enabled() -> None:
    db = FakeDB()
    providers = FakeProviders()

    workers = construct_workers(
        settings=_settings(
            token_radar_projection_enabled=True,
            narrative_admission_enabled=True,
        ),
        db=db,
        telemetry=object(),
        providers=providers,
        hub=SimpleNamespace(publish=lambda payload: None),
        collector=FakeCollector(name="collector", settings=SimpleNamespace(enabled=False), db=db, telemetry=object()),
        collector_enabled=False,
        wake_bus=db.wake,
    )

    assert isinstance(workers["token_radar_projection"], TokenRadarProjectionWorker)
    assert workers["token_radar_projection"].enqueue_narrative_admission is True
    assert workers["token_radar_projection"].wake_emitter is db.wake
    assert not hasattr(workers["token_radar_projection"], "wake_bus")
    assert isinstance(workers["narrative_admission"], NarrativeAdmissionWorker)


def test_narrative_admission_disabled_is_not_provider_unavailable() -> None:
    db = FakeDB()

    workers = construct_workers(
        settings=_settings(
            narrative_admission_enabled=False,
        ),
        db=db,
        telemetry=object(),
        providers=FakeProviders(),
        hub=SimpleNamespace(publish=lambda payload: None),
        collector=FakeCollector(name="collector", settings=SimpleNamespace(enabled=False), db=db, telemetry=object()),
        collector_enabled=False,
        wake_bus=db.wake,
    )

    assert workers["narrative_admission"].status_payload()["effective_status"] == "disabled"
    assert workers["narrative_admission"].status_payload()["unavailable_reason"] is None
    assert "mention_semantics" not in workers
    assert "token_discussion_digest" not in workers
    assert not any(
        "missing_narrative_intel_provider" in reason
        for reason in WorkerScheduler(workers=workers, db=db).unhealthy_reasons()
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
    assert not hasattr(workers["news_item_brief"], "wake_emitter")
    assert not hasattr(workers["news_item_brief"], "wake_bus")
    assert workers["news_item_brief"].wake_waiter is None
    assert not any(worker_name == "news_item_brief" for worker_name, _channels in db.wake_listener_calls)
    assert workers["news_item_brief"].settings.advisory_lock_key == 2026052001
    assert workers["news_item_brief"].settings.batch_size == 5
    assert workers["news_item_brief"].settings.lease_ms == 120_000
    assert workers["news_item_brief"].settings.retry_ms == 60_000
    assert workers["news_item_brief"].settings.statement_timeout_seconds == 30
    assert workers["news_item_brief"].settings.backpressure_cooldown_ms == 60_000


def test_worker_factory_wires_news_story_brief_when_configured() -> None:
    db = FakeDB()
    providers = FakeProviders(brief_provider=object())

    workers = construct_workers(
        settings=_settings(news_story_brief_configured=True),
        db=db,
        telemetry=object(),
        providers=providers,
        hub=SimpleNamespace(publish=lambda payload: None),
        collector=FakeCollector(name="collector", settings=SimpleNamespace(enabled=False), db=db, telemetry=object()),
        collector_enabled=False,
        wake_bus=db.wake,
    )

    assert not isinstance(workers["news_item_brief"], NewsItemBriefWorker)
    assert isinstance(workers["news_story_brief"], NewsStoryBriefWorker)
    assert workers["news_story_brief"].provider is providers.news_intel.brief_provider
    assert workers["news_story_brief"].wake_emitter is db.wake
    assert not hasattr(workers["news_story_brief"], "wake_bus")
    assert workers["news_story_brief"].wake_waiter.channels == ("news_item_processed",)
    assert workers["news_story_brief"].settings.advisory_lock_key == 2026061801
    assert workers["news_story_brief"].settings.batch_size == 5
    assert workers["news_story_brief"].settings.lease_ms == 120_000
    assert workers["news_story_brief"].settings.retry_ms == 60_000
    assert workers["news_story_brief"].settings.statement_timeout_seconds == 30
    assert workers["news_story_brief"].settings.backpressure_cooldown_ms == 60_000


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


def test_missing_worker_sentinel_requires_worker_settings_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    def empty_factory(_ctx):
        return {}

    specs = tuple(
        WorkerFactorySpec(spec.name, spec.keys, empty_factory) for spec in worker_factories.worker_factory_specs()
    )
    monkeypatch.setattr(worker_factories, "worker_factory_specs", lambda: specs)
    worker_settings = {manifest.name: SimpleNamespace(enabled=False) for manifest in all_worker_manifests()}
    del worker_settings["token_radar_projection"]
    settings = SimpleNamespace(workers=SimpleNamespace(**worker_settings))
    db = FakeDB()
    collector = FakeCollector(name="collector", settings=SimpleNamespace(enabled=False), db=db, telemetry=object())

    with pytest.raises(AttributeError, match="token_radar_projection"):
        construct_workers(
            settings=settings,
            db=db,
            telemetry=object(),
            providers=FakeProviders(),
            hub=SimpleNamespace(publish=lambda payload: None),
            collector=collector,
            collector_enabled=False,
            wake_bus=db.wake,
        )


def test_worker_factory_sentinel_requires_model_copy_for_enabled_state_changes() -> None:
    db = FakeDB()
    settings = SimpleNamespace(
        workers=SimpleNamespace(
            collector=SimpleNamespace(
                enabled=True,
                interval_seconds=3.0,
                soft_timeout_seconds=0.0,
                hard_timeout_seconds=0.0,
            )
        )
    )
    collector = FakeCollector(name="collector", settings=SimpleNamespace(enabled=True), db=db, telemetry=object())
    ctx = WorkerFactoryContext(
        settings=settings,
        db=db,
        telemetry=object(),
        providers=FakeProviders(),
        hub=SimpleNamespace(publish=lambda payload: None),
        collector=collector,
        collector_enabled=False,
        collector_start_requested=False,
        wake_bus=db.wake,
    )

    with pytest.raises(RuntimeError, match="worker_settings_model_copy_required:collector"):
        intentionally_not_started_worker(ctx, "collector")


def test_bootstrap_failure_closes_db_bundle_contract_without_pool_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    class BootstrapConnectionContext:
        def __enter__(self) -> object:
            return object()

        def __exit__(self, *_exc: object) -> None:
            return None

    class BootstrapPool:
        def __init__(self) -> None:
            self.close_calls = 0

        def connection(self) -> BootstrapConnectionContext:
            return BootstrapConnectionContext()

        def close(self) -> None:
            self.close_calls += 1

    class BootstrapDB:
        def __init__(self) -> None:
            self.api_pool = BootstrapPool()
            self.worker_pool = BootstrapPool()
            self.lock_pool = BootstrapPool()
            self.tool_pool = BootstrapPool()
            self.wake_pool = BootstrapPool()
            self.aclose_calls = 0

        async def aclose(self) -> None:
            self.aclose_calls += 1

    db = BootstrapDB()

    monkeypatch.setattr(
        bootstrap_module.DBPoolBundle,
        "create",
        staticmethod(lambda _settings, *, telemetry: db),
    )
    monkeypatch.setattr(
        bootstrap_module,
        "postgres_health_check",
        lambda _conn, *, expected_migration_version: {"ok": True},
    )
    monkeypatch.setattr(bootstrap_module, "latest_migration_version", lambda: "test")

    def fail_wire_providers(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("wire failed")

    monkeypatch.setattr(bootstrap_module, "wire_providers", fail_wire_providers)

    with pytest.raises(RuntimeError, match="wire failed"):
        bootstrap_module.bootstrap(_settings())

    assert db.aclose_calls == 1
    assert db.api_pool.close_calls == 0
    assert db.worker_pool.close_calls == 0
    assert db.lock_pool.close_calls == 0
    assert db.tool_pool.close_calls == 0
    assert db.wake_pool.close_calls == 0


def test_provider_cleanup_uses_formal_roots_without_provider_graph_fallback() -> None:
    alias = CloseOnlyProviderAlias()
    providers = WiredProviders(
        ingestion=IngestionProviders(),
        asset_market=AssetMarketProviders(),
        cex_market_intel=CexMarketIntelProviders(),
        news_intel=NewsIntelProviders(),
        agent_execution_gateway=alias,
    )

    errors = bootstrap_module._cleanup_provider_roots_sync(providers, None, None)

    assert errors == []
    assert alias.close_calls == 0


def _settings(
    *,
    collector_enabled: bool = False,
    notifications_enabled: bool = False,
    notification_log_channel_enabled: bool = True,
    news_item_brief_configured: bool = False,
    news_story_brief_configured: bool = False,
    macro_view_projection_enabled: bool = True,
    macrodata_enabled: bool = True,
    token_radar_projection_enabled: bool = False,
    narrative_admission_enabled: bool = True,
    cex_oi_radar_board_enabled: bool = False,
    market_tick_stream_enabled: bool = True,
    market_tick_poll_enabled: bool = True,
    asset_profile_refresh_enabled: bool = False,
    resolution_refresh_enabled: bool = False,
    event_anchor_active_window_ms: int = 300_000,
) -> Settings:
    llm = {}
    agent_lanes = {}
    if news_item_brief_configured:
        llm = {**llm, "api_key": "secret"}
        agent_lanes["news.item_brief"] = {"model": "gpt-5-mini"}
    if news_story_brief_configured:
        llm = {**llm, "api_key": "secret"}
        agent_lanes["news.story_brief"] = {"model": "gpt-5-mini"}
    return Settings(
        ws_token="secret",
        llm=llm,
        providers={"macrodata": {"enabled": macrodata_enabled}},
        notifications={
            "enabled": notifications_enabled,
            "channels": {
                "log": {
                    "enabled": notification_log_channel_enabled,
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
            "market_tick_stream": {"enabled": market_tick_stream_enabled},
            "market_tick_poll": {"enabled": market_tick_poll_enabled},
            "market_tick_current_projection": {"enabled": True},
            "event_anchor_backfill": {"enabled": True, "active_window_ms": event_anchor_active_window_ms},
            "token_capture_tier": {"enabled": True},
            "live_price_gateway": {"enabled": True},
            "resolution_refresh": {"enabled": resolution_refresh_enabled},
            "asset_profile_refresh": {"enabled": asset_profile_refresh_enabled},
            "token_image_mirror": {"enabled": True},
            "token_profile_current": {"enabled": True},
            "token_radar_projection": {"enabled": token_radar_projection_enabled},
            "cex_oi_radar_board": {"enabled": cex_oi_radar_board_enabled},
            "macro_view_projection": {"enabled": macro_view_projection_enabled},
            "narrative_admission": {"enabled": narrative_admission_enabled},
            "notification_rule": {"enabled": notifications_enabled},
            "notification_delivery": {"enabled": notifications_enabled},
            "news_item_brief": {"enabled": news_item_brief_configured},
        },
    )


class FakeProviders:
    def __init__(
        self,
        *,
        cex_market=_UNSET,
        dex_quote_market=_UNSET,
        dex_profile_sources=(),
        dex_discovery_market=None,
        stream_dex_market=_UNSET,
        cex_oi_market=_UNSET,
        coinglass_derivatives=None,
        upstream_client_factory=None,
        brief_provider=None,
    ) -> None:
        self.asset_market = SimpleNamespace(
            cex_market=object() if cex_market is _UNSET else cex_market,
            dex_quote_market=object() if dex_quote_market is _UNSET else dex_quote_market,
            dex_profile_sources=dex_profile_sources,
            dex_discovery_market=dex_discovery_market,
            stream_dex_market=object() if stream_dex_market is _UNSET else stream_dex_market,
        )
        self.cex_market_intel = SimpleNamespace(
            oi_market=object() if cex_oi_market is _UNSET else cex_oi_market,
            coinglass_derivatives=coinglass_derivatives,
        )
        self.ingestion = SimpleNamespace(upstream_client_factory=upstream_client_factory)
        self.news_intel = SimpleNamespace(feed_client=object(), brief_provider=brief_provider)


class FakeDB:
    def __init__(self) -> None:
        self.api_pool = object()
        self.wake = object()
        self.wake_listener_calls: list[tuple[str, tuple[str, ...]]] = []
        self.notification_delivery_running_timeout_ms = 300_000
        self.notification_delivery_stale_running_terminalization_batch_size = 50

    def api_session(self):
        raise AssertionError("api_session should not be opened by runtime assembly")

    def wake_emitter(self):
        return self.wake

    def wake_listener(self, worker_name, channels):
        self.wake_listener_calls.append((worker_name, tuple(channels)))
        return SimpleNamespace(worker_name=worker_name, channels=channels)


class FakeCollector(WorkerBase):
    async def run_once(self) -> WorkerResult:
        return WorkerResult(skipped=1)


class FakeUpstreamClient:
    def __init__(self, *, on_frame) -> None:
        self.on_frame = on_frame

    async def run(self) -> None:
        return None


class CloseOnlyProviderAlias:
    def __init__(self) -> None:
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1
