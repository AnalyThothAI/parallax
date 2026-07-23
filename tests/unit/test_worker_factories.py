from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import parallax.app.runtime.worker_factories as composition
from parallax.app.runtime.provider_wiring.types import (
    AssetMarketProviders,
    IngestionProviders,
    NewsIntelProviders,
    WiredProviders,
)
from parallax.app.runtime.worker_factories import InactiveWorker, construct_worker, construct_workers
from parallax.app.runtime.worker_manifest import worker_names
from parallax.platform.config.settings import Settings
from parallax.platform.runtime.worker_base import WorkerBase
from parallax.platform.runtime.worker_result import WorkerResult


class _ProbeWorker(WorkerBase):
    def __init__(self, name: str) -> None:
        super().__init__(
            name=name,
            settings=SimpleNamespace(enabled=True),
            db=None,
            telemetry=None,
        )

    async def run_once(self) -> WorkerResult:
        return WorkerResult()


class _FakeDB(SimpleNamespace):
    pass


def _construct(settings: Any) -> dict[str, WorkerBase]:
    return construct_workers(
        settings=settings,
        db=_FakeDB(),
        telemetry=SimpleNamespace(),
        providers=WiredProviders(
            ingestion=IngestionProviders(),
            asset_market=AssetMarketProviders(),
            news_intel=NewsIntelProviders(),
        ),
        hub=SimpleNamespace(publish=lambda _event: None),
        collector=_ProbeWorker("collector"),
        collector_enabled=False,
    )


def test_default_runtime_constructs_the_complete_canonical_inventory() -> None:
    workers = _construct(Settings(ws_token="test-token"))

    assert tuple(workers) == worker_names()
    assert all(isinstance(worker, WorkerBase) for worker in workers.values())


def test_all_domain_factories_construct_every_configured_worker() -> None:
    settings = Settings(
        ws_token="test-token",
        workers={name: {"enabled": False} for name in worker_names()},
    )

    workers = _construct(settings)

    assert tuple(workers) == worker_names()
    assert all(isinstance(worker, InactiveWorker) for worker in workers.values())
    assert {worker.effective_status for worker in workers.values()} == {"disabled"}


def test_one_worker_composition_does_not_require_fake_provider_bundles() -> None:
    settings = Settings(
        ws_token="test-token",
        workers={name: {"enabled": name == "token_profile_current"} for name in worker_names()},
    )

    worker = construct_worker(
        worker_name="token_profile_current",
        settings=settings,
        db=_FakeDB(),
        telemetry=SimpleNamespace(),
        asset_market=None,
        news_intel=None,
        hub=None,
        collector=None,
        collector_enabled=False,
    )

    assert worker.name == "token_profile_current"
    assert worker.effective_status == "stopped"


def test_enabled_notification_rule_without_publisher_is_unavailable() -> None:
    settings = Settings(
        ws_token="test-token",
        workers={name: {"enabled": name == "notification_rule"} for name in worker_names()},
    )

    worker = construct_worker(
        worker_name="notification_rule",
        settings=settings,
        db=_FakeDB(),
        telemetry=SimpleNamespace(),
        asset_market=None,
        news_intel=None,
        hub=None,
        collector=None,
        collector_enabled=False,
    )

    assert worker.effective_status == "unavailable"
    assert worker.unavailable_reason == "missing_notification_publisher"


def test_enabled_notification_delivery_without_channel_is_unavailable() -> None:
    settings = Settings(
        ws_token="test-token",
        workers={name: {"enabled": name == "notification_delivery"} for name in worker_names()},
    )

    worker = construct_worker(
        worker_name="notification_delivery",
        settings=settings,
        db=_FakeDB(),
        telemetry=SimpleNamespace(),
        asset_market=None,
        news_intel=None,
        hub=None,
        collector=None,
        collector_enabled=False,
    )

    assert worker.effective_status == "unavailable"
    assert worker.unavailable_reason == "missing_notification_delivery_channel"


def test_daily_macro_judgment_requires_llm_config_and_wires_distinct_role_models() -> None:
    worker_settings = {
        name: (
            {
                "enabled": True,
                "analyst_model": "openai/gpt-5.5",
                "reviewer_model": "openai/gpt-5.6-terra",
            }
            if name == "daily_macro_judgment"
            else {"enabled": False}
        )
        for name in worker_names()
    }
    unavailable = construct_worker(
        worker_name="daily_macro_judgment",
        settings=Settings(ws_token="test-token", workers=worker_settings),
        db=_FakeDB(),
        telemetry=SimpleNamespace(),
        asset_market=None,
        news_intel=None,
        hub=None,
        collector=None,
        collector_enabled=False,
    )
    configured = construct_worker(
        worker_name="daily_macro_judgment",
        settings=Settings(
            ws_token="test-token",
            llm={"api_key": "test-key", "base_url": "https://llm.example.test/v1"},
            workers=worker_settings,
        ),
        db=_FakeDB(),
        telemetry=SimpleNamespace(),
        asset_market=None,
        news_intel=None,
        hub=None,
        collector=None,
        collector_enabled=False,
    )

    assert unavailable.effective_status == "unavailable"
    assert unavailable.unavailable_reason == "llm_not_configured"
    assert configured.name == "daily_macro_judgment"
    assert configured.effective_status == "stopped"
    assert configured._agent._model_name == "openai/gpt-5.5"
    assert configured._agent._reviewer_model_name == "openai/gpt-5.6-terra"


def test_composition_fails_when_a_factory_omits_a_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(composition, "worker_names", lambda: ("expected",))
    monkeypatch.setattr(composition, "worker_factories", lambda: (lambda _ctx: {},))

    with pytest.raises(
        RuntimeError,
        match=r"worker_composition_mismatch:missing=\['expected'\]:unknown=\[\]",
    ):
        _construct(SimpleNamespace())


def test_composition_fails_when_a_factory_returns_an_unknown_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(composition, "worker_names", lambda: ("expected",))
    monkeypatch.setattr(
        composition,
        "worker_factories",
        lambda: (lambda _ctx: {"unexpected": _ProbeWorker("unexpected")},),
    )

    with pytest.raises(
        RuntimeError,
        match=r"worker_composition_mismatch:missing=\['expected'\]:unknown=\['unexpected'\]",
    ):
        _construct(SimpleNamespace())


def test_composition_fails_when_two_factories_construct_the_same_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(composition, "worker_names", lambda: ("worker",))
    monkeypatch.setattr(
        composition,
        "worker_factories",
        lambda: (
            lambda _ctx: {"worker": _ProbeWorker("worker")},
            lambda _ctx: {"worker": _ProbeWorker("worker")},
        ),
    )

    with pytest.raises(ValueError, match="worker_composition_duplicate:worker"):
        _construct(SimpleNamespace())
