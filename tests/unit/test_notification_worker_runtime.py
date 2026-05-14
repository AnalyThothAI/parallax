import asyncio
import time
from contextlib import contextmanager
from typing import Any

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
        rule_engine=SlowRuleEngine(),
        repository_session=fake_repository_session,
        poll_interval=0.2,
    )

    async def run_probe() -> None:
        task = asyncio.create_task(worker.process_once(now_ms=1_700_000_000_000))
        await asyncio.sleep(0.01)
        assert not task.done()
        assert await task == []

    asyncio.run(run_probe())
