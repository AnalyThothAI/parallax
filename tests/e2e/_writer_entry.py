"""Entrypoint for the e2e writer sidecar process.

Run as:
  python -m tests.e2e._writer_entry --event-id <id> --text <text>

Reads GMGN_POSTGRES_DSN (and optional GMGN_E2E_WS_TOKEN, defaults to
"e2e-token") from env. Builds a CliRuntime via the same _build_runtime path
the production app uses (start_collector=False, no upstream WS), then calls
runtime.ingest.ingest_event(event, is_watched=True) with a synthetic mention.

By writing through the production wiring chain we exercise the same
EvidenceRepository -> events table path the API will read from. The event is
flagged is_watched=True so it shows up under /api/recent's default
scope=matched filter.

Stdout: 'INGESTED <event_id>'. Exit 0 on success.
"""

from __future__ import annotations

import argparse
import os
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--text", required=True)
    parser.add_argument("--author", default="e2e_test")
    args = parser.parse_args()

    dsn = os.environ.get("GMGN_POSTGRES_DSN")
    if not dsn:
        print("FATAL: GMGN_POSTGRES_DSN not set", file=sys.stderr)
        return 1
    ws_token = os.environ.get("GMGN_E2E_WS_TOKEN", "e2e-token")

    from gmgn_twitter_intel.app.runtime.app import _build_runtime
    from gmgn_twitter_intel.domains.evidence.interfaces import (
        Author,
        Content,
        Source,
        TwitterEvent,
    )
    from gmgn_twitter_intel.platform.config.settings import Settings

    settings = Settings(
        ws_token=ws_token,
        handles=(args.author,),
        storage={"postgres": {"dsn": dsn, "password_file": None}},
    )
    runtime = _build_runtime(settings, start_collector=False)

    received_at_ms = int(time.time() * 1000)
    event = TwitterEvent(
        event_id=args.event_id,
        source=Source(
            provider="gmgn",
            transport="direct_ws",
            coverage="public_stream",
            channel="twitter_monitor_basic",
        ),
        action="tweet",
        original_action=None,
        tweet_id=args.event_id,
        internal_id=args.event_id,
        timestamp=received_at_ms // 1000,
        received_at_ms=received_at_ms,
        author=Author(handle=args.author, name=args.author, avatar=None, followers=100, tags=[]),
        content=Content(text=args.text, media=[]),
        reference=None,
        unfollow_target=None,
        avatar_change=None,
        bio_change=None,
        matched_handles=[args.author],
        raw={"id": args.event_id},
    )
    runtime.ingest.ingest_event(event, is_watched=True)
    print(f"INGESTED {args.event_id}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
