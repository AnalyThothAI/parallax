import asyncio
import json
import unittest
from types import SimpleNamespace

from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.ingestion.interfaces import IngestedEvent
from gmgn_twitter_intel.domains.ingestion.runtime.collector_service import CollectorService


class MemoryStore:
    def __init__(self):
        self.twitter_events = []
        self.raw_frames = []
        self.watched_flags = []

    def insert_raw_frame(self, **kwargs):
        self.raw_frames.append(kwargs)
        return True

    def ingest_event(self, event, *, is_watched):
        self.twitter_events.append(event)
        self.watched_flags.append(is_watched)
        return IngestedEvent(event=event, entities=[], alerts=[], token_intents=[], token_resolutions=[], inserted=True)


class MemoryPublisher:
    def __init__(self):
        self.payloads = []

    async def publish(self, payload):
        self.payloads.append(payload)


class CollectorServiceTests(unittest.TestCase):
    def test_handle_frame_stores_all_observed_events_and_publishes_only_matches(self):
        async def scenario():
            store = MemoryStore()
            publisher = MemoryPublisher()
            service = CollectorService(
                name="collector",
                settings=worker_settings(),
                db=object(),
                telemetry=object(),
                handles=("toly",),
                store=store,
                publisher=publisher,
                upstream_client=None,
            )
            frame = json.dumps(
                {
                    "channel": "twitter_monitor_basic",
                    "data": [
                        {
                            "i": "skip",
                            "tw": "tweet",
                            "ti": "1",
                            "cp": 1,
                            "u": {"s": "random"},
                            "c": {"t": "skip"},
                        },
                        {
                            "i": "keep",
                            "tw": "tweet",
                            "ti": "2",
                            "cp": 1,
                            "u": {"s": "toly"},
                            "c": {"t": "keep"},
                        },
                    ],
                }
            )

            await service.handle_frame(frame, received_at_ms=1234)

            self.assertEqual([event.author.handle for event in store.twitter_events], ["random", "toly"])
            self.assertEqual(store.watched_flags, [False, True])
            self.assertEqual(
                [payload["event"]["event_id"] for payload in publisher.payloads],
                ["gmgn:twitter_monitor_basic:keep"],
            )
            self.assertEqual(store.raw_frames[0]["channel"], "twitter_monitor_basic")

        asyncio.run(scenario())

    def test_cp_zero_waits_for_cp_one_before_publishing(self):
        async def scenario():
            store = MemoryStore()
            publisher = MemoryPublisher()
            service = CollectorService(
                name="collector",
                settings=worker_settings(snapshot_timeout_seconds=0.05),
                db=object(),
                telemetry=object(),
                handles=("toly",),
                store=store,
                publisher=publisher,
                upstream_client=None,
            )
            snapshot = json.dumps(
                {
                    "channel": "twitter_monitor_basic",
                    "data": [
                        {
                            "i": "same-id",
                            "tw": "tweet",
                            "ti": "1",
                            "cp": 0,
                            "u": {"s": "toly"},
                            "c": {"t": "snapshot"},
                        }
                    ],
                }
            )
            complete = json.dumps(
                {
                    "channel": "twitter_monitor_basic",
                    "data": [
                        {
                            "i": "same-id",
                            "tw": "tweet",
                            "ti": "1",
                            "cp": 1,
                            "u": {"s": "toly"},
                            "c": {"t": "complete"},
                        }
                    ],
                }
            )

            await service.handle_frame(snapshot, received_at_ms=1000)
            await service.handle_frame(complete, received_at_ms=1010)
            await asyncio.sleep(0.06)

            self.assertEqual(len(store.twitter_events), 1)
            self.assertEqual(store.twitter_events[0].content.text, "complete")
            self.assertEqual(store.watched_flags, [True])
            self.assertEqual(service.status.snapshot_gate_outcomes["debounced_complete"], 1)

        asyncio.run(scenario())

    def test_snapshot_gate_records_timeout_and_non_tw_outcomes(self):
        async def scenario():
            store = MemoryStore()
            publisher = MemoryPublisher()
            service = CollectorService(
                name="collector",
                settings=worker_settings(snapshot_timeout_seconds=0.01),
                db=object(),
                telemetry=object(),
                handles=("toly",),
                store=store,
                publisher=publisher,
                upstream_client=None,
            )
            non_tw = json.dumps({"channel": "public_broadcast", "data": [{"hello": "world"}]})
            snapshot = json.dumps(
                {
                    "channel": "twitter_monitor_basic",
                    "data": [
                        {
                            "i": "timeout-id",
                            "tw": "tweet",
                            "ti": "1",
                            "cp": 0,
                            "u": {"s": "toly"},
                            "c": {"t": "snapshot"},
                        }
                    ],
                }
            )

            await service.handle_frame(non_tw, received_at_ms=900)
            await service.handle_frame(snapshot, received_at_ms=1000)
            await asyncio.sleep(0.03)

            self.assertEqual(service.status.snapshot_gate_outcomes["non_tw_channel"], 1)
            self.assertEqual(service.status.snapshot_gate_outcomes["debounced_timeout"], 1)

        asyncio.run(scenario())

    def test_run_once_delegates_to_upstream_client(self):
        async def scenario():
            upstream = FakeUpstreamClient()
            service = CollectorService(
                name="collector",
                settings=worker_settings(),
                db=object(),
                telemetry=object(),
                handles=("toly",),
                store=MemoryStore(),
                publisher=MemoryPublisher(),
                upstream_client=upstream,
            )

            result = await service.run_once()

            self.assertIsInstance(result, WorkerResult)
            self.assertEqual(result.processed, 1)
            self.assertEqual(upstream.run_calls, 1)

        asyncio.run(scenario())

    def test_stop_cancels_running_upstream_client_without_scheduler_timeout(self):
        async def scenario():
            upstream = BlockingUpstreamClient()
            service = CollectorService(
                name="collector",
                settings=worker_settings(),
                db=object(),
                telemetry=object(),
                handles=("toly",),
                store=MemoryStore(),
                publisher=MemoryPublisher(),
                upstream_client=upstream,
            )

            task = asyncio.create_task(service.run_once())
            await upstream.started.wait()
            await service.stop()
            result = await asyncio.wait_for(task, timeout=0.2)

            self.assertIsInstance(result, WorkerResult)
            self.assertEqual(result.notes["upstream_cancelled"], True)
            self.assertEqual(upstream.cancelled, True)

        asyncio.run(scenario())

    def test_collector_close_closes_owned_upstream_client(self):
        async def scenario():
            upstream = ClosingUpstreamClient()
            service = CollectorService(
                name="collector",
                settings=worker_settings(),
                db=object(),
                telemetry=object(),
                handles=("toly",),
                store=MemoryStore(),
                publisher=MemoryPublisher(),
                upstream_client=upstream,
            )

            await service.on_close()

            self.assertEqual(upstream.closed, True)

        asyncio.run(scenario())


def worker_settings(**overrides):
    values = {
        "enabled": True,
        "interval_seconds": 3.0,
        "timeout_seconds": 0.0,
        "snapshot_timeout_seconds": 0.5,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeUpstreamClient:
    def __init__(self):
        self.run_calls = 0

    async def run(self):
        self.run_calls += 1


class BlockingUpstreamClient:
    def __init__(self):
        self.started = asyncio.Event()
        self.cancelled = False

    async def run(self):
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


class ClosingUpstreamClient:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


if __name__ == "__main__":
    unittest.main()
