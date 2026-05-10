from __future__ import annotations

import json

from gmgn_twitter_intel.domains.pulse_lab.services.pulse_timeline_context import build_pulse_timeline_context

TARGET = {
    "target_type": "CexToken",
    "target_id": "cex_token:PEPE",
    "symbol": "PEPE",
}
NOW_MS = 1_700_000_000_000


def test_build_context_has_all_windows_and_budget_limits():
    rows = [
        row(
            f"event-{index:02d}",
            f"author-{index:02d}",
            NOW_MS - (29 - index) * 60_000,
            text=f"$PEPE post {index} " + ("x" * 400),
        )
        for index in range(30)
    ]

    context = build_pulse_timeline_context(
        target=TARGET,
        rows=rows,
        window="1h",
        now_ms=NOW_MS,
        max_selected_posts=24,
        max_post_clusters=16,
        max_raw_text_chars_per_post=80,
    )

    assert set(context) == {
        "target",
        "windows",
        "stage_segments",
        "post_clusters",
        "selected_posts",
        "market_overlay",
        "radar_score",
        "timeline_signature",
    }
    assert set(context["windows"]) == {"5m", "1h", "4h", "24h"}
    assert len(context["selected_posts"]) <= 24
    assert len(context["post_clusters"]) <= 16
    assert all(len(post["text"]) <= 80 for post in context["selected_posts"])


def test_deduplicates_same_author_text_and_clusters_multi_author_duplicates():
    rows = [
        row("event-1", "alice", NOW_MS - 10_000, text="PEPE ripping https://x.test/a 🚀!!!"),
        row("event-2", "alice", NOW_MS - 9_000, text="pepe ripping https://x.test/b !!!"),
        row("event-3", "bob", NOW_MS - 8_000, text="PEPE ripping https://x.test/c 🚀"),
        row("event-4", "alice", NOW_MS - 7_000, text="PEPE ripping https://x.test/d"),
        row("event-5", "carol", NOW_MS - 6_000, text="Different $PEPE confirmation"),
    ]

    context = build_pulse_timeline_context(target=TARGET, rows=rows, now_ms=NOW_MS)

    assert context["windows"]["1h"]["duplicate_text_share"] > 0
    duplicate_cluster = next(cluster for cluster in context["post_clusters"] if len(cluster["authors"]) > 1)
    assert duplicate_cluster["authors"] == ["alice", "bob"]
    assert duplicate_cluster["event_ids"] == ["event-1", "event-3", "event-4"]
    assert duplicate_cluster["duplicate_text_share"] > 0
    assert "event-2" not in {post["event_id"] for post in context["selected_posts"]}


def test_window_duplicate_metrics_are_computed_per_window():
    rows = [
        row("event-1", "alice", NOW_MS - 10 * 60_000, text="Older duplicate PEPE phrase"),
        row("event-2", "bob", NOW_MS - 9 * 60_000, text="Older duplicate PEPE phrase"),
        row("event-3", "carol", NOW_MS - 60_000, text="Fresh unique PEPE post"),
    ]

    context = build_pulse_timeline_context(target=TARGET, rows=rows, window="5m", now_ms=NOW_MS)

    assert context["windows"]["5m"]["duplicate_text_share"] == 0
    assert context["windows"]["1h"]["duplicate_text_share"] > 0
    assert context["windows"]["5m"]["duplicate_text_share"] != context["windows"]["1h"]["duplicate_text_share"]


def test_selected_posts_include_required_roles():
    rows = [
        row("event-1", "seed", NOW_MS - 50_000, text="Early PEPE flow"),
        row("event-2", "ticker", NOW_MS - 40_000, text="$PEPE ticker evidence"),
        row("event-3", "watcher", NOW_MS - 30_000, text="Watched account sees PEPE", watched=True),
        row("event-4", "newbie", NOW_MS - 20_000, text="New independent PEPE author"),
        row(
            "event-5",
            "price",
            NOW_MS - 10_000,
            text="PEPE price inflection",
            price_change_since_social_pct=0.42,
        ),
        row("event-6", "latest", NOW_MS - 1_000, text="Latest PEPE update"),
        row("event-7", "dupe-a", NOW_MS - 900, text="Copied PEPE phrase"),
        row("event-8", "dupe-b", NOW_MS - 800, text="Copied PEPE phrase"),
    ]

    context = build_pulse_timeline_context(target=TARGET, rows=rows, now_ms=NOW_MS)

    roles = {role for post in context["selected_posts"] for role in post["roles"]}
    assert {
        "first_seed",
        "latest",
        "watched_author",
        "stage_representative",
        "direct_ca_or_ticker_evidence",
        "price_inflection",
        "new_independent_author",
        "duplicate_or_concentration_risk",
    }.issubset(roles)
    selected_ids = [post["event_id"] for post in context["selected_posts"]]
    assert selected_ids == sorted(selected_ids, key=lambda event_id: int(event_id.removeprefix("event-")))


def test_selected_posts_preserve_overlapping_roles_for_same_event():
    rows = [
        row("event-1", "watcher", NOW_MS - 1_000, text="$PEPE watched seed", watched=True),
    ]

    context = build_pulse_timeline_context(target=TARGET, rows=rows, now_ms=NOW_MS)

    assert len(context["selected_posts"]) == 1
    post = context["selected_posts"][0]
    assert post["role"] == "first_seed"
    assert {
        "first_seed",
        "latest",
        "watched_author",
        "stage_representative",
        "direct_ca_or_ticker_evidence",
    }.issubset(set(post["roles"]))


def test_selected_posts_include_multiple_watched_posts_under_budget():
    rows = [
        row("event-1", "seed", NOW_MS - 50_000, text="PEPE seed"),
        row("event-2", "watcher-a", NOW_MS - 40_000, text="Watched PEPE one", watched=True),
        row("event-3", "watcher-b", NOW_MS - 30_000, text="Watched PEPE two", watched=True),
        row("event-4", "latest", NOW_MS - 20_000, text="PEPE latest"),
    ]

    context = build_pulse_timeline_context(
        target=TARGET,
        rows=rows,
        now_ms=NOW_MS,
        max_selected_posts=4,
    )

    watched_posts = [post for post in context["selected_posts"] if "watched_author" in post["roles"]]
    assert [post["event_id"] for post in watched_posts] == ["event-2", "event-3"]


def test_selected_posts_include_multiple_direct_ticker_evidence_posts_under_budget():
    rows = [
        row("event-1", "seed", NOW_MS - 50_000, text="General seed"),
        row("event-2", "ticker-a", NOW_MS - 40_000, text="$PEPE first ticker"),
        row_without_symbol("event-3", "ticker-b", NOW_MS - 30_000, text="$PEPE fallback ticker"),
        row("event-4", "latest", NOW_MS - 20_000, text="General latest"),
    ]

    context = build_pulse_timeline_context(
        target=TARGET,
        rows=rows,
        now_ms=NOW_MS,
        max_selected_posts=4,
    )

    direct_posts = [post for post in context["selected_posts"] if "direct_ca_or_ticker_evidence" in post["roles"]]
    assert [post["event_id"] for post in direct_posts] == ["event-2", "event-3"]


def test_timeline_signature_changes_when_cluster_membership_changes_same_cluster_id():
    rows = [
        row("event-1", "alice", NOW_MS - 30_000, text="Same PEPE cluster"),
        row("event-2", "alice", NOW_MS - 20_000, text="Same PEPE cluster"),
    ]
    changed_rows = [
        row("event-1", "alice", NOW_MS - 30_000, text="Same PEPE cluster"),
        row("event-3", "alice", NOW_MS - 10_000, text="Same PEPE cluster"),
    ]

    first = build_pulse_timeline_context(
        target=TARGET,
        rows=rows,
        now_ms=NOW_MS,
        max_selected_posts=0,
    )
    changed = build_pulse_timeline_context(
        target=TARGET,
        rows=changed_rows,
        now_ms=NOW_MS,
        max_selected_posts=0,
    )

    assert first["post_clusters"][0]["cluster_id"] == changed["post_clusters"][0]["cluster_id"]
    assert first["timeline_signature"] != changed["timeline_signature"]


def test_timeline_signature_is_stable_and_materially_changes():
    rows = [
        row("event-1", "alice", NOW_MS - 30_000, text="PEPE seed"),
        row("event-2", "bob", NOW_MS - 20_000, text="$PEPE confirmation"),
        row("event-3", "carol", NOW_MS - 10_000, text="PEPE latest"),
    ]

    first = build_pulse_timeline_context(target=TARGET, rows=rows, now_ms=NOW_MS)
    reordered = build_pulse_timeline_context(target=TARGET, rows=list(reversed(rows)), now_ms=NOW_MS)
    changed = build_pulse_timeline_context(
        target=TARGET,
        rows=[*rows, row("event-4", "dave", NOW_MS - 5_000, text="New independent PEPE evidence")],
        now_ms=NOW_MS,
    )

    assert first["timeline_signature"] == reordered["timeline_signature"]
    assert first["timeline_signature"] != changed["timeline_signature"]


def test_context_is_stable_json_serializable():
    rows = [
        row("event-1", "alice", NOW_MS - 30_000, text="PEPE seed"),
        row("event-2", "bob", NOW_MS - 20_000, text="$PEPE confirmation"),
    ]

    first = build_pulse_timeline_context(target=TARGET, rows=rows, now_ms=NOW_MS)
    second = build_pulse_timeline_context(target=TARGET, rows=rows, now_ms=NOW_MS)

    assert json.dumps(first, sort_keys=True)
    assert first == second


def row(
    event_id: str,
    author_handle: str,
    received_at_ms: int,
    *,
    text: str,
    watched: bool = False,
    price_change_since_social_pct: float | None = None,
) -> dict:
    return {
        "event_id": event_id,
        "author_handle": author_handle,
        "received_at_ms": received_at_ms,
        "text": text,
        "is_watched": watched,
        "target_id": TARGET["target_id"],
        "target_type": TARGET["target_type"],
        "symbol": TARGET["symbol"],
        "cashtags": ["PEPE"] if "$PEPE" in text or "PEPE" in text else [],
        "entities": {
            "cashtags": ["PEPE"] if "$PEPE" in text or "PEPE" in text else [],
            "contract_addresses": ["0x1234567890abcdef1234567890abcdef12345678"] if "CA" in text else [],
        },
        "price_change_since_social_pct": price_change_since_social_pct,
    }


def row_without_symbol(
    event_id: str,
    author_handle: str,
    received_at_ms: int,
    *,
    text: str,
) -> dict:
    result = row(event_id, author_handle, received_at_ms, text=text)
    result.pop("symbol")
    return result
