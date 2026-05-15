import asyncio
import time
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.notifications.runtime.notification_worker import NotificationWorker


class SlowRuleEngine:
    def evaluate(self, *, now_ms: int | None = None) -> list[Any]:
        time.sleep(0.08)
        return []


class FakeRepos:
    notifications = None


@contextmanager
def fake_repository_session():
    yield FakeRepos()


def test_process_once_does_not_block_event_loop():
    worker = NotificationWorker(
        name="notification_rule",
        settings=SimpleNamespace(enabled=True, interval_seconds=0.2, batch_size=10),
        db=SimpleNamespace(worker_session=lambda *_args, **_kwargs: fake_repository_session()),
        telemetry=SimpleNamespace(),
        rule_engine=SlowRuleEngine(),
    )

    async def run_probe() -> None:
        task = asyncio.create_task(worker.process_once(now_ms=1_700_000_000_000))
        await asyncio.sleep(0.01)
        assert not task.done()
        assert await task == []

    asyncio.run(run_probe())


def test_notification_worker_is_worker_base_and_run_once_returns_result():
    worker = NotificationWorker(
        name="notification_rule",
        settings=SimpleNamespace(enabled=True, interval_seconds=0.2, batch_size=10),
        db=SimpleNamespace(worker_session=lambda *_args, **_kwargs: fake_repository_session()),
        telemetry=SimpleNamespace(),
        rule_engine=SlowRuleEngine(),
    )

    result = asyncio.run(worker.run_once(now_ms=1_700_000_000_000))

    assert isinstance(worker, WorkerBase)
    assert isinstance(result, WorkerResult)
    assert result.skipped == 1
    assert result.notes["created"] == 0
