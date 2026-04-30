import unittest

from gmgn_twitter_cli.collector.normalizer import normalize_gmgn_payload


class EventNormalizerTests(unittest.TestCase):
    def test_normalizes_gmgn_twitter_item_to_stable_event(self):
        events = normalize_gmgn_payload(
            {
                "channel": "twitter_monitor_basic",
                "data": [
                    {
                        "i": "msg-1",
                        "tw": "quote",
                        "ti": "2049501031357456529",
                        "cp": 1,
                        "ts": "1777474098420",
                        "u": {"s": "toly", "n": "Toly", "a": "avatar", "f": 1000},
                        "ut": ["kol"],
                        "c": {"t": "hello", "m": [{"t": "image", "u": "https://example.test/a.jpg"}]},
                        "si": "2049500000000000000",
                        "su": {"s": "source", "n": "Source"},
                        "sc": {"t": "reference"},
                    }
                ],
            },
            received_at_ms=1777474100123,
        )

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.event_id, "gmgn:twitter_monitor_basic:msg-1")
        self.assertEqual(event.source.coverage, "public_stream")
        self.assertEqual(event.source.channel, "twitter_monitor_basic")
        self.assertEqual(event.action, "quote")
        self.assertEqual(event.author.handle, "toly")
        self.assertEqual(event.content.text, "hello")
        self.assertEqual(event.reference.author_handle, "source")
        self.assertEqual(event.received_at_ms, 1777474100123)

    def test_skips_public_broadcast_when_it_has_no_tweet_identity(self):
        events = normalize_gmgn_payload(
            {
                "channel": "public_broadcast",
                "data": [
                    {
                        "et": "twitter_watched",
                        "ed": {
                            "id": "event-1",
                            "tp": "translation",
                            "ot": {"ti": "", "ak": ""},
                            "st": {"ti": "", "ak": ""},
                        },
                    }
                ],
            },
            received_at_ms=1,
        )

        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
