import asyncio
import json
import unittest

from gmgn_twitter_cli.collector.service import CollectorService


class MemoryStore:
    def __init__(self):
        self.observed_events = []
        self.matched_events = []

    def insert_observed_event(self, event):
        self.observed_events.append(event)
        return True

    def insert_matched_event(self, event):
        self.matched_events.append(event)
        return True


class MemoryPublisher:
    def __init__(self):
        self.events = []

    async def publish(self, event):
        self.events.append(event)


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

            self.assertEqual([event.author.handle for event in store.observed_events], ["random", "toly"])
            self.assertEqual([event.author.handle for event in store.matched_events], ["toly"])
            self.assertEqual([event.event_id for event in publisher.events], ["gmgn:twitter_monitor_basic:keep"])

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

            self.assertEqual(len(store.observed_events), 1)
            self.assertEqual(len(store.matched_events), 1)
            self.assertEqual(store.observed_events[0].content.text, "complete")
            self.assertEqual(store.matched_events[0].content.text, "complete")

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
