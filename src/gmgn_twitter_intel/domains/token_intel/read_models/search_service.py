from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any

from gmgn_twitter_intel.domains.token_intel.services.query_parser import SearchIntent, parse_search_query
from gmgn_twitter_intel.domains.token_intel.services.search_aliases import (
    canonical_symbol_for_query,
    expanded_lexical_query,
)

RRF_K = 60.0
ROUTE_WEIGHTS = {
    "target": 1.0,
    "handle": 0.85,
    "lexical": 0.65,
    "trigram": 0.35,
}
_ROUTE_LIMIT_MIN = 100
_ROUTE_LIMIT_MULTIPLIER = 4


@dataclass(frozen=True, slots=True)
class SearchPage:
    ok: bool
    query: dict[str, Any]
    items: list[dict[str, Any]] = field(default_factory=list)
    target_candidates: list[dict[str, Any]] = field(default_factory=list)
    page: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class SearchCursorError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class _CursorState:
    sort_tuple: tuple[float, int, str]
    offset: int


class SearchService:
    def __init__(self, *, search_query: Any) -> None:
        self.search_query = search_query

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        scope: str = "all",
        cursor: str | None = None,
    ) -> SearchPage:
        requested_limit = max(0, int(limit))
        intent = parse_search_query(query, scope=scope)
        query_payload = _query_payload(intent)
        if intent.kind == "empty":
            return SearchPage(
                ok=False,
                query=query_payload,
                page=_page([], requested_limit, offset=0, has_more=False),
                error="empty_query",
            )
        cursor_state = _decode_cursor(cursor) if cursor else None
        cursor_offset = cursor_state.offset if cursor_state else 0
        target_intent = _target_intent(intent)
        target_candidates = self.search_query.resolve_targets(target_intent)
        lexical_query = expanded_lexical_query(intent, target_candidates)
        route_intent = replace(target_intent, lexical_query=lexical_query)
        route_limit = _route_limit(requested_limit=requested_limit, cursor_offset=cursor_offset)
        route_hits = self.search_query.route_hits(
            intent=route_intent,
            target_candidates=target_candidates,
            watched_only=scope == "matched",
            route_limit=route_limit,
        )
        items = _items_from_hits(route_hits)
        if cursor_state is not None:
            items = [item for item in items if _sort_tuple(item) > cursor_state.sort_tuple]
        page_items = items[: requested_limit + 1]
        has_more = len(page_items) > requested_limit
        returned = page_items[:requested_limit]
        return SearchPage(
            ok=True,
            query=query_payload | {"lexical_query": lexical_query},
            items=[_public_item(item) for item in returned],
            target_candidates=target_candidates,
            page=_page(returned, requested_limit, offset=cursor_offset, has_more=has_more),
        )


def _target_intent(intent: SearchIntent) -> SearchIntent:
    alias_symbol = canonical_symbol_for_query(intent.normalized_text)
    if alias_symbol and intent.kind in {"symbol", "text"}:
        return replace(intent, kind="symbol", symbol=alias_symbol)
    return intent


def _items_from_hits(route_hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_event: dict[str, list[dict[str, Any]]] = {}
    for hit in route_hits:
        by_event.setdefault(str(hit["event_id"]), []).append(hit)
    items = [_item_from_event_hits(hits) for hits in by_event.values()]
    return sorted(items, key=_sort_tuple)


def _item_from_event_hits(hits: list[dict[str, Any]]) -> dict[str, Any]:
    first = hits[0]
    route_scores: dict[str, float] = {}
    reasons: list[str] = []
    target = None
    for hit in hits:
        route = str(hit["route"])
        route_scores[route] = max(route_scores.get(route, 0.0), float(hit.get("route_score") or 0.0))
        reasons.extend(str(reason) for reason in hit.get("match_reasons") or [])
        if target is None and route == "target":
            target = hit.get("target")
    score = _fused_score(hits)
    return {
        "event": first["event"],
        "match_type": _match_type(hits),
        "score": score,
        "match_reasons": list(dict.fromkeys(reasons)),
        "target": target,
        "route_scores": route_scores,
        "_sort": {
            "rank_score": score,
            "received_at_ms": int(first.get("received_at_ms") or 0),
            "event_id": str(first["event_id"]),
        },
    }


def _fused_score(route_hits: list[dict[str, Any]]) -> float:
    return sum(ROUTE_WEIGHTS[str(hit["route"])] / (RRF_K + max(1, int(hit["route_rank"]))) for hit in route_hits)


def _match_type(hits: list[dict[str, Any]]) -> str:
    routes = {str(hit["route"]) for hit in hits}
    if "target" in routes:
        return "target"
    if "handle" in routes:
        return "handle"
    if "lexical" in routes:
        return "lexical"
    return "trigram"


def _sort_tuple(item: dict[str, Any]) -> tuple[float, int, str]:
    sort = item["_sort"]
    return (-float(sort["rank_score"]), -int(sort["received_at_ms"]), str(sort["event_id"]))


def _route_limit(*, requested_limit: int, cursor_offset: int) -> int:
    window = max(0, int(cursor_offset)) + max(0, int(requested_limit)) + 1
    return max(window * _ROUTE_LIMIT_MULTIPLIER, _ROUTE_LIMIT_MIN)


def _page(items: list[dict[str, Any]], limit: int, *, offset: int, has_more: bool) -> dict[str, Any]:
    next_cursor = _encode_cursor(items[-1], offset=offset + len(items)) if has_more and items else None
    return {
        "returned_count": min(len(items), max(0, int(limit))),
        "has_more": has_more,
        "next_cursor": next_cursor,
    }


def _public_item(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if key != "_sort"}


def _encode_cursor(item: dict[str, Any], *, offset: int) -> str:
    sort = item["_sort"]
    return f"v2:{max(0, int(offset))}:{float(sort['rank_score']):.17g}:{int(sort['received_at_ms'])}:{sort['event_id']}"


def _decode_cursor(cursor: str | None) -> _CursorState:
    if not cursor:
        raise SearchCursorError("invalid_cursor")
    try:
        version, offset_raw, score_raw, received_raw, event_id = cursor.split(":", 4)
        if version != "v2":
            raise ValueError("unsupported cursor version")
        return _CursorState(
            sort_tuple=(-float(score_raw), -int(received_raw), event_id),
            offset=max(0, int(offset_raw)),
        )
    except (TypeError, ValueError) as exc:
        raise SearchCursorError("invalid_cursor") from exc


def _query_payload(intent: SearchIntent) -> dict[str, Any]:
    return {key: value for key, value in asdict(intent).items() if value not in {None, ""}}
