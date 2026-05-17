from __future__ import annotations

from types import SimpleNamespace

from gmgn_twitter_intel.app.runtime.bootstrap import _construct_workers
from gmgn_twitter_intel.domains.asset_market.runtime.event_anchor_backfill_worker import EventAnchorBackfillWorker
from gmgn_twitter_intel.domains.asset_market.runtime.live_price_gateway import LivePriceGateway
from gmgn_twitter_intel.domains.asset_market.runtime.market_tick_poll_worker import MarketTickPollWorker
from gmgn_twitter_intel.domains.asset_market.runtime.market_tick_stream_worker import MarketTickStreamWorker
from gmgn_twitter_intel.domains.asset_market.runtime.token_capture_tier_worker import TokenCaptureTierWorker
from gmgn_twitter_intel.domains.asset_market.runtime.token_profile_current_worker import TokenProfileCurrentWorker
from gmgn_twitter_intel.platform.config.settings import Settings

_UNSET = object()


def _legacy_anchor_worker_key() -> str:
    return "_".join(("anchor", "price"))


def test_bootstrap_wires_market_tick_runtime_and_hard_cuts_legacy_anchor_worker() -> None:
    db = FakeDB()
    providers = FakeProviders()

    workers = _construct_workers(
        settings=_settings(),
        db=db,
        telemetry=object(),
        providers=providers,
        hub=SimpleNamespace(publish=lambda payload: None),
        collector=SimpleNamespace(),
        collector_enabled=False,
        wake_bus=db.wake,
    )

    assert _legacy_anchor_worker_key() not in workers
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
    assert isinstance(workers["token_profile_current"], TokenProfileCurrentWorker)


def test_bootstrap_wires_live_price_gateway_as_db_only_worker_without_price_providers() -> None:
    db = FakeDB()
    providers = FakeProviders(
        message_cex_market=None,
        dex_quote_market=None,
        stream_dex_market=None,
    )

    workers = _construct_workers(
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


def _settings() -> Settings:
    return Settings(
        ws_token="secret",
        notifications={"enabled": False},
        workers={
            "collector": {"enabled": False},
            "market_tick_stream": {"enabled": True},
            "market_tick_poll": {"enabled": True},
            "event_anchor_backfill": {"enabled": True},
            "token_capture_tier": {"enabled": True},
            "live_price_gateway": {"enabled": True},
            "resolution_refresh": {"enabled": False},
            "asset_profile_refresh": {"enabled": False},
            "token_profile_current": {"enabled": True},
            "token_radar_projection": {"enabled": False},
            "pulse_candidate": {"enabled": False},
            "enrichment": {"enabled": False},
            "handle_summary": {"enabled": False},
            "harness_ops": {"enabled": False},
            "notification_rule": {"enabled": False},
            "notification_delivery": {"enabled": False},
        },
    )


class FakeProviders:
    def __init__(
        self,
        *,
        message_cex_market=_UNSET,
        dex_quote_market=_UNSET,
        stream_dex_market=_UNSET,
    ) -> None:
        self.asset_market = SimpleNamespace(
            message_cex_market=object() if message_cex_market is _UNSET else message_cex_market,
            dex_quote_market=object() if dex_quote_market is _UNSET else dex_quote_market,
            dex_profile_sources=(),
            dex_discovery_market=None,
            stream_dex_market=object() if stream_dex_market is _UNSET else stream_dex_market,
        )
        self.pulse_lab = SimpleNamespace(decision_provider=None)
        self.watchlist_intel = SimpleNamespace(summary_provider=None)
        self.social_enrichment = SimpleNamespace(event_enrichment=None)


class FakeDB:
    def __init__(self) -> None:
        self.wake = object()

    def wake_emitter(self):
        return self.wake

    def wake_listener(self, worker_name, channels):
        return SimpleNamespace(worker_name=worker_name, channels=channels)
