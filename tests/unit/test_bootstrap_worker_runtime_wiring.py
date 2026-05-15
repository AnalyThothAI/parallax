from __future__ import annotations

from types import SimpleNamespace

from gmgn_twitter_intel.app.runtime.bootstrap import _construct_workers
from gmgn_twitter_intel.domains.asset_market.runtime.live_price_gateway import LivePriceGateway
from gmgn_twitter_intel.domains.asset_market.runtime.market_tick_poll_worker import MarketTickPollWorker
from gmgn_twitter_intel.domains.asset_market.runtime.market_tick_stream_worker import MarketTickStreamWorker
from gmgn_twitter_intel.domains.asset_market.runtime.token_capture_tier_worker import TokenCaptureTierWorker
from gmgn_twitter_intel.platform.config.settings import Settings


def test_bootstrap_wires_market_tick_runtime_and_hard_cuts_anchor_worker() -> None:
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

    assert "anchor_price" not in workers
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

    assert isinstance(workers["live_price_gateway"], LivePriceGateway)
    assert workers["live_price_gateway"].stream_provider is providers.asset_market.stream_dex_market
    assert workers["live_price_gateway"].cex_market is providers.asset_market.message_cex_market
    assert not hasattr(workers["live_price_gateway"], "wake_bus")


def _settings() -> Settings:
    return Settings(
        ws_token="secret",
        notifications={"enabled": False},
        workers={
            "collector": {"enabled": False},
            "market_tick_stream": {"enabled": True},
            "market_tick_poll": {"enabled": True},
            "token_capture_tier": {"enabled": True},
            "live_price_gateway": {"enabled": True},
            "resolution_refresh": {"enabled": False},
            "asset_profile_refresh": {"enabled": False},
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
    def __init__(self) -> None:
        self.asset_market = SimpleNamespace(
            message_cex_market=object(),
            dex_quote_market=object(),
            dex_profile_market=None,
            dex_discovery_market=None,
            stream_dex_market=object(),
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
