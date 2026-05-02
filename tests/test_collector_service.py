import asyncio
import json
import unittest

from gmgn_twitter_intel.collector.service import CollectorService
from gmgn_twitter_intel.pipeline.ingest_service import IngestedEvent


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
        return IngestedEvent(event=event, entities=[], alerts=[], inserted=True)


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
                handles=("toly",),
                store=store,
                publisher=publisher,
                upstream_client=None,
                snapshot_timeout=0.05,
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

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
