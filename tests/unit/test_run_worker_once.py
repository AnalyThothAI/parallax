from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from parallax.platform.config.settings import Settings
from parallax.platform.runtime.worker_base import WorkerBase
from parallax.platform.runtime.worker_result import WorkerResult


class _DB:
    def __init__(self, events: list[tuple[Any, ...]]) -> None:
        self.events = events

    async def aclose(self) -> None:
        self.events.append(("db_close",))


class _Worker(WorkerBase):
    def __init__(self, *, events: list[tuple[Any, ...]], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.events = events

    async def on_start(self) -> None:
        self.events.append(("worker_start",))

    async def run_once(self) -> WorkerResult:
        self.events.append(("worker_run_once",))
        return WorkerResult(processed=2, notes={"rows_written": 1})

    async def on_stop(self) -> None:
        self.events.append(("worker_stop",))

    async def on_close(self) -> None:
        self.events.append(("worker_close",))


class _Transaction:
    def __init__(self, events: list[tuple[Any, ...]]) -> None:
        self.events = events

    def __enter__(self) -> None:
        self.events.append(("transaction_enter",))

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        self.events.append(("transaction_exit",))
        return False


class _PreparationDB(_DB):
    def __init__(self, events: list[tuple[Any, ...]], repos: object) -> None:
        super().__init__(events)
        self.repos = repos

    @contextmanager
    def worker_session(self, worker_name: str, **kwargs: object):
        self.events.append(("worker_session", worker_name, kwargs))
        yield self.repos


def test_run_worker_once_uses_factory_and_public_worker_lifecycle(monkeypatch) -> None:
    from parallax.app.operations import run_worker_once as operation

    events: list[tuple[Any, ...]] = []
    db = _DB(events)

    def factory(context: Any) -> dict[str, WorkerBase]:
        enabled = [name for name, value in context.settings.workers if name != "agent_runtime" and value.enabled]
        events.append(("factory", tuple(enabled), context.settings.workers.token_profile_current.batch_size))
        return {
            "token_profile_current": _Worker(
                events=events,
                name="token_profile_current",
                settings=context.settings.workers.token_profile_current,
                db=context.db,
                telemetry=context.telemetry,
            )
        }

    monkeypatch.setattr(operation.DBPoolBundle, "create", staticmethod(lambda _settings, *, telemetry: db))
    monkeypatch.setattr(
        operation,
        "construct_worker",
        lambda **kwargs: factory(SimpleNamespace(**kwargs))[str(kwargs["worker_name"])],
    )

    execution = operation.run_worker_once(
        Settings(),
        "token_profile_current",
        {"batch_size": 7},
    )

    assert execution.payload() == {
        "worker_name": "token_profile_current",
        "processed": 2,
        "failed": 0,
        "dead": 0,
        "skipped": 0,
        "notes": {"rows_written": 1},
    }
    assert ("factory", ("token_profile_current",), 7) in events
    assert events.index(("worker_run_once",)) < events.index(("worker_stop",))
    assert events.index(("worker_stop",)) < events.index(("worker_close",))
    assert events[-1] == ("db_close",)


def test_run_worker_once_validates_overrides_before_opening_database(monkeypatch) -> None:
    from parallax.app.operations import run_worker_once as operation

    monkeypatch.setattr(
        operation.DBPoolBundle,
        "create",
        staticmethod(lambda *_args, **_kwargs: pytest.fail("database must not open")),
    )

    with pytest.raises(ValidationError):
        operation.run_worker_once(Settings(), "token_profile_current", {"batch_size": 0})


def test_run_worker_once_rejects_unknown_worker_before_opening_database(monkeypatch) -> None:
    from parallax.app.operations import run_worker_once as operation

    monkeypatch.setattr(
        operation.DBPoolBundle,
        "create",
        staticmethod(lambda *_args, **_kwargs: pytest.fail("database must not open")),
    )

    with pytest.raises(ValueError, match="unknown worker manifest: missing-worker"):
        operation.run_worker_once(Settings(), "missing-worker")


def test_run_worker_once_rejects_unsupported_runtime_worker_before_opening_database(monkeypatch) -> None:
    from parallax.app.operations import run_worker_once as operation

    monkeypatch.setattr(
        operation.DBPoolBundle,
        "create",
        staticmethod(lambda *_args, **_kwargs: pytest.fail("database must not open")),
    )

    with pytest.raises(ValueError, match="worker_once_unsupported:macro_sync"):
        operation.run_worker_once(Settings(), "macro_sync")


def test_repair_token_profile_images_prepares_targets_before_public_worker_run(monkeypatch) -> None:
    from parallax.app.operations import run_worker_once as operation

    events: list[tuple[Any, ...]] = []

    class DirtyTargets:
        def enqueue_targets(self, targets: list[dict[str, object]], **kwargs: object) -> dict[str, int]:
            events.append(("enqueue", tuple(target["target_id"] for target in targets), kwargs))
            return {"targets": len(targets)}

    repos = SimpleNamespace(
        conn=object(),
        transaction=lambda: _Transaction(events),
        token_profile_current_dirty_targets=DirtyTargets(),
    )
    db = _PreparationDB(events, repos)

    def factory(context: Any) -> dict[str, WorkerBase]:
        return {
            "token_profile_current": _Worker(
                events=events,
                name="token_profile_current",
                settings=context.settings.workers.token_profile_current,
                db=context.db,
                telemetry=context.telemetry,
            )
        }

    monkeypatch.setattr(operation.DBPoolBundle, "create", staticmethod(lambda _settings, *, telemetry: db))
    monkeypatch.setattr(
        operation,
        "construct_worker",
        lambda **kwargs: factory(SimpleNamespace(**kwargs))[str(kwargs["worker_name"])],
    )
    monkeypatch.setattr(
        operation,
        "token_profile_image_repair_targets",
        lambda _conn, *, limit: [{"target_type": "Asset", "target_id": "asset:one", "source_watermark_ms": limit}],
    )

    execution = operation.repair_token_profile_images_once(Settings(), limit=19)

    assert execution.preparation == {"selected_targets": 1, "profile_targets_enqueued": 1}
    assert events.index(("transaction_exit",)) < events.index(("worker_run_once",))
    enqueue = next(event for event in events if event[0] == "enqueue")
    assert enqueue[1] == ("asset:one",)
    assert enqueue[2] == {"reason": "token_profile_image_repair", "now_ms": enqueue[2]["now_ms"]}


def test_refresh_asset_profiles_prepares_each_provider_inside_transaction(monkeypatch) -> None:
    from parallax.app.operations import run_worker_once as operation
    from parallax.app.runtime.provider_wiring.types import AssetMarketProviders
    from parallax.domains.asset_market.providers import DexProfileSource

    events: list[tuple[Any, ...]] = []

    class ProfileMarket:
        def token_profile(self, **_kwargs: object) -> None:
            return None

        def close(self) -> None:
            events.append(("provider_close",))

    class Targets:
        def enqueue_missing_token_radar_current_targets_for_ops(self, **kwargs: object) -> dict[str, int]:
            events.append(("discover", kwargs))
            return {"source_rows_scanned": 4, "targets": 3}

    repos = SimpleNamespace(
        transaction=lambda: _Transaction(events),
        asset_profile_refresh_targets=Targets(),
    )
    db = _PreparationDB(events, repos)
    providers = AssetMarketProviders(
        dex_profile_sources=(DexProfileSource(provider="profile-source", market=ProfileMarket()),)
    )

    def factory(context: Any) -> dict[str, WorkerBase]:
        return {
            "asset_profile_refresh": _Worker(
                events=events,
                name="asset_profile_refresh",
                settings=context.settings.workers.asset_profile_refresh,
                db=context.db,
                telemetry=context.telemetry,
            )
        }

    monkeypatch.setattr(operation.DBPoolBundle, "create", staticmethod(lambda _settings, *, telemetry: db))
    monkeypatch.setattr(operation, "wire_asset_market", lambda _settings: providers)
    monkeypatch.setattr(
        operation,
        "construct_worker",
        lambda **kwargs: factory(SimpleNamespace(**kwargs))[str(kwargs["worker_name"])],
    )

    execution = operation.refresh_asset_profiles_once(Settings(), limit=11)

    assert execution.preparation == {
        "source_rows_scanned": 4,
        "targets_enqueued": 3,
        "sources": {"profile-source": {"source_rows_scanned": 4, "targets": 3}},
    }
    discover = next(event for event in events if event[0] == "discover")
    assert discover[1]["provider"] == "profile-source"
    assert discover[1]["limit"] == 11
    assert events.index(("transaction_exit",)) < events.index(("worker_run_once",))
    assert events.index(("worker_close",)) < events.index(("provider_close",))


def test_cli_worker_command_is_a_parse_and_serialize_adapter(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops

    captured: dict[str, Any] = {}
    execution = SimpleNamespace(payload=lambda: {"worker_name": "token_profile_current", "processed": 1})

    monkeypatch.setattr(ops, "load_settings", lambda require_ws_token=False: Settings())

    def fake_run_worker_once(settings: Settings, worker_name: str, overrides: dict[str, object]) -> object:
        captured.update(settings=settings, worker_name=worker_name, overrides=overrides)
        return execution

    monkeypatch.setattr(ops, "run_worker_once", fake_run_worker_once)

    code, payload = ops.handle_ops(
        SimpleNamespace(ops_command="rebuild-token-profiles", limit=23),
        SimpleNamespace(),
    )

    assert code == 0
    assert payload == {
        "ok": True,
        "data": {"worker_name": "token_profile_current", "processed": 1},
    }
    assert captured["worker_name"] == "token_profile_current"
    assert captured["overrides"] == {"batch_size": 23}
