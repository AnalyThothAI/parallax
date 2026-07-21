from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from parallax.integrations.binance.usdm_futures_client import BinanceUsdmRoute


def test_binance_universe_operation_owns_transport_lifecycle(monkeypatch) -> None:
    from parallax.app.operations import reference_data_sync as operation

    events: list[str] = []
    settings = _settings()

    class Client:
        def usdt_perpetual_routes(self):
            events.append("fetch")
            return [
                BinanceUsdmRoute(
                    provider="binance",
                    feed_type="cex_swap",
                    quote_symbol="USDT",
                    native_market_id="BTCUSDT",
                    base_symbol="BTC",
                    multiplier=None,
                    raw={},
                )
            ]

        def close(self) -> None:
            events.append("close")

    @contextmanager
    def fake_repositories(_settings):
        events.append("repos_enter")
        yield object()
        events.append("repos_exit")

    def fake_sync(**kwargs):
        events.append("sync")
        assert kwargs["routes"][0].native_market_id == "BTCUSDT"
        assert kwargs["observed_at_ms"] == 123
        return {"mode": "dry_run"}

    monkeypatch.setattr(operation, "BinanceUsdmFuturesClient", lambda **_kwargs: Client())
    monkeypatch.setattr(operation, "repositories", fake_repositories)
    monkeypatch.setattr(operation, "sync_binance_usdt_perp_routes", fake_sync)
    monkeypatch.setattr(operation, "_now_ms", lambda: 123)

    assert operation.sync_binance_usdt_perp_universe(settings, dry_run=True, execute=False) == {"mode": "dry_run"}
    assert events == ["fetch", "close", "repos_enter", "sync", "repos_exit"]


def test_cex_profile_operation_fetches_before_opening_repositories(monkeypatch) -> None:
    from parallax.app.operations import reference_data_sync as operation

    events: list[str] = []

    class Client:
        def token_profiles(self):
            events.append("fetch")
            return [{"base_symbol": "BTC"}]

        def close(self) -> None:
            events.append("close")

    @contextmanager
    def fake_repositories(_settings):
        events.append("repos_enter")
        yield object()
        events.append("repos_exit")

    def fake_sync(**kwargs):
        events.append("sync")
        assert kwargs["profiles"] == [{"base_symbol": "BTC"}]
        return {"profiles_seen": 1}

    monkeypatch.setattr(operation, "BinanceCexProfileClient", lambda **_kwargs: Client())
    monkeypatch.setattr(operation, "repositories", fake_repositories)
    monkeypatch.setattr(operation, "sync_cex_token_profiles", fake_sync)
    monkeypatch.setattr(operation, "_now_ms", lambda: 123)

    assert operation.sync_binance_cex_profiles_once(_settings()) == {"profiles_seen": 1}
    assert events == ["fetch", "close", "repos_enter", "sync", "repos_exit"]


def test_us_equity_operation_fetches_before_opening_repositories(monkeypatch) -> None:
    from parallax.app.operations import reference_data_sync as operation

    events: list[str] = []

    class Client:
        def symbols(self):
            events.append("fetch")
            return ["AAOI"]

        def close(self) -> None:
            events.append("close")

    @contextmanager
    def fake_repositories(_settings):
        events.append("repos_enter")
        yield object()
        events.append("repos_exit")

    def fake_sync(**kwargs):
        events.append("sync")
        assert kwargs["symbols"] == ["AAOI"]
        return {"symbols_seen": 1}

    monkeypatch.setattr(operation, "NasdaqTraderSymbolClient", lambda **_kwargs: Client())
    monkeypatch.setattr(operation, "repositories", fake_repositories)
    monkeypatch.setattr(operation, "sync_us_equity_symbols", fake_sync)
    monkeypatch.setattr(operation, "_now_ms", lambda: 123)

    assert operation.sync_us_equity_symbols_once(_settings()) == {"symbols_seen": 1}
    assert events == ["fetch", "close", "repos_enter", "sync", "repos_exit"]


def test_reference_sync_cli_is_only_an_operation_adapter(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops

    settings = _settings()
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(ops, "load_settings", lambda require_ws_token=False: settings)
    monkeypatch.setattr(
        ops,
        "sync_binance_usdt_perp_universe",
        lambda current, **kwargs: calls.append(("universe", (current, kwargs))) or {"command": "universe"},
    )
    monkeypatch.setattr(
        ops,
        "sync_binance_cex_profiles_once",
        lambda current: calls.append(("profiles", current)) or {"command": "profiles"},
    )
    monkeypatch.setattr(
        ops,
        "sync_us_equity_symbols_once",
        lambda current: calls.append(("equities", current)) or {"command": "equities"},
    )

    universe = ops.handle_ops(
        SimpleNamespace(ops_command="sync-binance-usdt-perp-universe", dry_run=True, execute=False),
        object(),
    )
    profiles = ops.handle_ops(SimpleNamespace(ops_command="sync-binance-cex-profiles"), object())
    equities = ops.handle_ops(SimpleNamespace(ops_command="sync-us-equity-symbols"), object())

    assert universe == (0, {"ok": True, "data": {"command": "universe"}})
    assert profiles == (0, {"ok": True, "data": {"command": "profiles"}})
    assert equities == (0, {"ok": True, "data": {"command": "equities"}})
    assert calls == [
        ("universe", (settings, {"dry_run": True, "execute": False})),
        ("profiles", settings),
        ("equities", settings),
    ]


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        binance_usdm_futures_base_url="https://binance.invalid",
        binance_cex_profile_base_url="https://binance.invalid",
        binance_timeout_seconds=1.0,
        okx_timeout_seconds=1.0,
    )
