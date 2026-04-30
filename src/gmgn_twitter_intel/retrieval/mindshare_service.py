from __future__ import annotations

import json
import math
import time
from collections import Counter
from typing import Any

from ..pipeline.social_windows import previous_window, window_bounds
from ..pipeline.token_extractor import normalize_ca


class MindshareService:
    def __init__(self, repo, social_repo, *, sentiment_backend: str = "none"):
        self.repo = repo
        self.social_repo = social_repo
        self.sentiment_backend = sentiment_backend

    def mindshare(
        self,
        *,
        ca: str | None = None,
        chain: str | None = None,
        symbol: str | None = None,
        window: str = "1h",
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        now = now_ms or int(time.time() * 1000)
        bounds = window_bounds(window, now_ms=now)
        resolved = self._resolve_filter(ca=ca, chain=chain, symbol=symbol, bounds=bounds)
        if not resolved["ok"]:
            return resolved

        token_chain = resolved["chain"]
        token_ca = resolved["ca"]
        current_events = self._events_for_ca(token_ca, token_chain, bounds.start_ms, bounds.end_ms)
        previous = previous_window(bounds)
        previous_events = self._events_for_ca(token_ca, token_chain, previous.start_ms, previous.end_ms)
        denominator = max(1, self._resolved_token_event_count(bounds.start_ms, bounds.end_ms))

        data = self._metrics(
            events=current_events,
            previous_count=len(previous_events),
            denominator=denominator,
            ca=token_ca,
            chain=token_chain,
            symbol=resolved.get("symbol") or symbol,
            window=window,
            start_ms=bounds.start_ms,
            end_ms=bounds.end_ms,
        )
        self.social_repo.upsert_window(_window_row(data))
        return {"ok": True, "data": data}

    def _resolve_filter(self, *, ca, chain, symbol, bounds) -> dict[str, Any]:
        if ca:
            normalized_chain, normalized_ca = normalize_ca(ca, chain=chain)
            return {"ok": True, "chain": normalized_chain, "ca": normalized_ca}
        if not symbol:
            return {"ok": False, "error": "token_filter_required", "candidates": []}

        normalized_symbol = symbol.strip().lstrip("$").upper()
        symbol_rows = self.repo.client.query_where(
            "tweet_entities",
            where=f"entity_type = 'symbol' AND normalized_value = '{_sql_literal(normalized_symbol)}'",
        )
        event_ids = {row["event_id"] for row in symbol_rows}
        ca_rows = [
            row
            for row in self.repo.client.query_in("tweet_entities", column="event_id", values=sorted(event_ids))
            if row.get("entity_type") == "ca" and row.get("token_resolution_status") == "resolved"
        ]
        ca_candidates = {}
        for row in ca_rows:
            event = self.repo.client.get_one("twitter_events", event_id=row["event_id"])
            if not event or not _within(event, bounds.start_ms, bounds.end_ms):
                continue
            key = (row.get("chain"), row.get("normalized_value"))
            ca_candidates[key] = {
                "chain": row.get("chain"),
                "ca": row.get("normalized_value"),
                "symbol": normalized_symbol,
            }
        candidates = sorted(ca_candidates.values(), key=lambda item: (item["chain"] or "", item["ca"] or ""))
        if len(candidates) != 1:
            return {"ok": False, "error": "ambiguous_symbol", "candidates": candidates}
        candidate = candidates[0]
        return {"ok": True, **candidate}

    def _events_for_ca(self, ca: str, chain: str, start_ms: int, end_ms: int) -> list[dict[str, Any]]:
        entity_rows = self.repo.client.query_where(
            "tweet_entities",
            where=(
                "entity_type = 'ca' "
                f"AND normalized_value = '{_sql_literal(ca)}' "
                f"AND chain = '{_sql_literal(chain)}'"
            ),
        )
        events = []
        for row in entity_rows:
            event_row = self.repo.client.get_one("twitter_events", event_id=row["event_id"])
            if event_row and _within(event_row, start_ms, end_ms):
                events.append(self.repo.decode_event_row(event_row))
        events.sort(key=lambda item: item.get("received_at_ms") or 0, reverse=True)
        return events

    def _resolved_token_event_count(self, start_ms: int, end_ms: int) -> int:
        entity_rows = self.repo.client.query_where(
            "tweet_entities",
            where="entity_type = 'ca' AND token_resolution_status = 'resolved'",
        )
        event_ids = set()
        for row in entity_rows:
            event_row = self.repo.client.get_one("twitter_events", event_id=row["event_id"])
            if event_row and _within(event_row, start_ms, end_ms):
                event_ids.add(row["event_id"])
        return len(event_ids)

    def _metrics(
        self,
        *,
        events: list[dict[str, Any]],
        previous_count: int,
        denominator: int,
        ca: str,
        chain: str,
        symbol: str | None,
        window: str,
        start_ms: int,
        end_ms: int,
    ) -> dict[str, Any]:
        author_counts = Counter((event.get("author") or {}).get("handle") for event in events)
        author_counts.pop(None, None)
        weighted_reach = sum(math.log10(((event.get("author") or {}).get("followers") or 0) + 1) for event in events)
        mention_count = len(events)
        velocity = None if previous_count == 0 else round((mention_count - previous_count) / previous_count, 6)
        quality_flags = ["public_stream_coverage"]
        if mention_count < 3:
            quality_flags.append("low_sample")
        return {
            "window_id": f"{chain}:{ca}:{window}:{start_ms}:{end_ms}",
            "chain": chain,
            "ca": ca,
            "symbol": symbol,
            "window": window,
            "window_start_ms": start_ms,
            "window_end_ms": end_ms,
            "mention_count": mention_count,
            "unique_authors": len(author_counts),
            "weighted_reach": round(weighted_reach, 6),
            "share_of_voice": round(mention_count / denominator, 6),
            "velocity": velocity,
            "top_authors": [
                {"handle": handle, "count": count}
                for handle, count in sorted(author_counts.items(), key=lambda item: (-item[1], item[0]))[:10]
            ],
            "top_tweets": [
                {
                    "event_id": event["event_id"],
                    "author_handle": (event.get("author") or {}).get("handle"),
                    "text": (event.get("content") or {}).get("text"),
                    "received_at_ms": event.get("received_at_ms"),
                }
                for event in events[:10]
            ],
            "narratives": _narratives(events),
            "sentiment": {"backend": self.sentiment_backend, "status": "disabled"},
            "quality_flags": quality_flags,
        }


def _window_row(data: dict[str, Any]) -> dict[str, Any]:
    now_ms = int(time.time() * 1000)
    return {
        "window_id": data["window_id"],
        "chain": data["chain"],
        "ca": data["ca"],
        "symbol": data.get("symbol"),
        "window": data["window"],
        "window_start_ms": data["window_start_ms"],
        "window_end_ms": data["window_end_ms"],
        "mention_count": data["mention_count"],
        "unique_authors": data["unique_authors"],
        "weighted_reach": data["weighted_reach"],
        "share_of_voice": data["share_of_voice"],
        "velocity": data["velocity"],
        "top_authors_json": _json(data["top_authors"]),
        "top_tweets_json": _json(data["top_tweets"]),
        "narratives_json": _json(data["narratives"]),
        "sentiment_json": _json(data["sentiment"]),
        "quality_flags_json": _json(data["quality_flags"]),
        "created_at_ms": now_ms,
        "updated_at_ms": now_ms,
    }


def _within(row: dict[str, Any], start_ms: int, end_ms: int) -> bool:
    received_at_ms = int(row.get("received_at_ms") or 0)
    return start_ms < received_at_ms <= end_ms and int(row.get("matched_at_ms") or 0) > 0


def _narratives(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter()
    for event in events:
        for key in ("cashtags", "hashtags"):
            for value in event.get(key) or []:
                counts[str(value).upper()] += 1
    return [{"term": term, "count": count} for term, count in counts.most_common(10)]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _sql_literal(value: str) -> str:
    return value.replace("'", "''")
