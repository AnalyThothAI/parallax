from __future__ import annotations

import time
from typing import Any

from .asset_flow_service import WINDOW_MS
from .token_target_cursor import TokenTargetCursorError, decode_target_cursor, encode_target_cursor
from .token_target_post_serializer import token_target_post_payload
from .token_target_stage_builder import build_token_target_stages


class TokenTargetPostsCursorError(Exception):
    pass


class TokenTargetPostsRangeError(Exception):
    pass


class TokenTargetPostsSortError(Exception):
    pass


class TokenTargetPostsService:
    def __init__(self, *, targets: Any) -> None:
        self.targets = targets

    def target_posts(
        self,
        *,
        target_type: str,
        target_id: str,
        window: str,
        scope: str,
        post_range: str,
        sort: str,
        limit: int,
        cursor: str | None = None,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        if post_range not in {"current_window", "since_ignition", "all_history"}:
            raise TokenTargetPostsRangeError(post_range)
        if sort not in {"recent", "catalyst"}:
            raise TokenTargetPostsSortError(sort)
        try:
            timeline_cursor = decode_target_cursor(cursor)
        except TokenTargetCursorError as exc:
            raise TokenTargetPostsCursorError(cursor) from exc
        resolved_now_ms = int(now_ms or time.time() * 1000)
        since_ms = (
            0
            if post_range in {"since_ignition", "all_history"}
            else resolved_now_ms - WINDOW_MS.get(window, WINDOW_MS["1h"])
        )
        rows = self.targets.timeline_rows(
            target_type=target_type,
            target_id=target_id,
            since_ms=since_ms,
            watched_only=scope == "matched",
            limit=max(0, int(limit)) + 1,
            cursor=timeline_cursor,
        )
        page_rows = rows[: max(0, int(limit))]
        has_more = len(rows) > len(page_rows)
        next_cursor = encode_target_cursor(page_rows[-1]) if has_more and page_rows else None
        stage_build = build_token_target_stages(page_rows)
        return {
            "query": {
                "target_type": target_type,
                "target_id": target_id,
                "window": window,
                "scope": scope,
                "range": post_range,
                "sort": sort,
            },
            "score_window": {"window": window},
            "total_count": len(page_rows) + (1 if has_more else 0),
            "returned_count": len(page_rows),
            "has_more": has_more,
            "next_cursor": next_cursor,
            "items": [
                token_target_post_payload(
                    row,
                    stage=stage_build.annotations.get(str(row.get("event_id") or "")),
                )
                for row in page_rows
            ],
        }
