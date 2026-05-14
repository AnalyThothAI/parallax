import json
import unittest
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

from gmgn_twitter_intel.integrations.gmgn.direct_ws import (
    DirectGmgnWebSocketClient,
    UpstreamIdleTimeoutError,
    build_gmgn_ws_url,
    build_heartbeat_message,
    build_subscribe_message,
)


class DirectWebSocketProtocolTests(unittest.TestCase):
    def test_build_ws_url_matches_gmgn_web_client_shape(self):
        url = build_gmgn_ws_url(
            app_version="20260429-12894-ccec416",
            device_id="device-1",
            fp_did="fp-1",
            client_uuid="uuid-1",
        )

        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        self.assertEqual(parsed.scheme, "wss")
        self.assertEqual(parsed.netloc, "gmgn.ai")
        self.assertEqual(parsed.path, "/ws")
        self.assertEqual(query["device_id"], ["device-1"])
        self.assertEqual(query["fp_did"], ["fp-1"])
        self.assertEqual(query["uuid"], ["uuid-1"])
        self.assertEqual(query["client_id"], ["gmgn_web_20260429-12894-ccec416"])
        self.assertEqual(query["from_app"], ["gmgn"])
        self.assertEqual(query["app_ver"], ["20260429-12894-ccec416"])
        self.assertEqual(query["app_lang"], ["zh-CN"])
        self.assertEqual(query["os"], ["web"])

    def test_build_subscribe_message_uses_frontend_wire_shape(self):
        message = build_subscribe_message(
            "twitter_monitor_basic",
            [{"chain": "bsc"}],
            subscription_id="sub-1",
        )

        self.assertEqual(
            message,
            {
                "action": "subscribe",
                "channel": "twitter_monitor_basic",
                "f": "w",
                "id": "sub-1",
                "data": [{"chain": "bsc"}],
            },
        )
        json.dumps(message)

    def test_build_heartbeat_message_uses_client_timestamp(self):
        self.assertEqual(
            build_heartbeat_message(client_ts=123456),
            {"action": "heartbeat", "client_ts": 123456},
        )

    def test_direct_client_subscribes_all_configured_chains_in_one_frame(self):
        class WebSocket:
            def __init__(self):
                self.send = AsyncMock()

        websocket = WebSocket()
        client = DirectGmgnWebSocketClient(
            app_version="20260429-12894-ccec416",
            channels=["twitter_monitor_basic"],
            chains=["sol", "eth", "base", "bsc"],
            on_frame=lambda _: None,
        )

        import asyncio

        asyncio.run(client._subscribe_all(websocket))

        websocket.send.assert_awaited_once()
        sent = json.loads(websocket.send.await_args.args[0])
        self.assertEqual(sent["channel"], "twitter_monitor_basic")
        self.assertEqual(
            sent["data"],
            [{"chain": "sol"}, {"chain": "eth"}, {"chain": "base"}, {"chain": "bsc"}],
        )

    def test_direct_client_times_out_silent_upstream_connections(self):
        class SilentWebSocket:
            async def recv(self):
                import asyncio

                await asyncio.sleep(60)

        client = DirectGmgnWebSocketClient(
            app_version="20260429-12894-ccec416",
            channels=["twitter_monitor_basic"],
            chains=["sol"],
            on_frame=lambda _: None,
            idle_timeout=0.01,
        )

        import asyncio

        with self.assertRaises(UpstreamIdleTimeoutError):
            asyncio.run(client._receive_frames(SilentWebSocket()))

    def test_direct_client_yields_between_hot_upstream_frames(self):
        import asyncio

        class StopAfterYield(RuntimeError):
            pass

        class HotWebSocket:
            async def recv(self):
                return "{}"

        async def run_probe():
            yielded = asyncio.Event()
            processed = 0
            marker_tasks = []

            async def mark_yielded():
                yielded.set()

            def on_frame(_):
                nonlocal processed
                processed += 1
                if processed == 1:
                    marker_tasks.append(asyncio.create_task(mark_yielded()))
                if yielded.is_set() and processed >= 2:
                    raise StopAfterYield
                if processed > 1_000:
                    raise AssertionError("hot upstream frames starved the event loop")

            client = DirectGmgnWebSocketClient(
                app_version="20260429-12894-ccec416",
                channels=["twitter_monitor_basic"],
                chains=["sol"],
                on_frame=on_frame,
            )
            await client._receive_frames(HotWebSocket())

        with self.assertRaises(StopAfterYield):
            asyncio.run(run_probe())


if __name__ == "__main__":
    unittest.main()
