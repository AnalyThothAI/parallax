from __future__ import annotations

import re
import time
from collections import Counter, defaultdict
from typing import Any

from ..storage.evidence_repository import decode_event_row

WINDOW_MS = {
    "5m": 300_000,
    "1h": 3_600_000,
    "4h": 4 * 3_600_000,
    "24h": 24 * 3_600_000,
}
KINDS = {"direct_token", "topic_heat", "ecosystem_signal", "market_structure", "risk_alert", "low_signal"}
PRIORITY_RANK = {"hot": 4, "watch": 3, "context": 2, "muted": 1}
KIND_LABELS = {
    "direct_token": "Direct token",
    "topic_heat": "Topic heat",
    "ecosystem_signal": "Ecosystem",
    "market_structure": "Structure",
    "risk_alert": "Risk",
    "low_signal": "Low signal",
}


class TradingAttentionService:
    def __init__(self, *, evidence, signals, assets):
        self.evidence = evidence
        self.signals = signals
        self.assets = assets

    def pulse(
        self,
        *,
        window: str,
        scope: str,
        limit: int,
        kind: str | None = None,
        handle: str | None = None,
        q: str | None = None,
        cursor: str | None = None,
        handles: set[str] | None = None,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        reference_ms = now_ms if now_ms is not None else _now_ms()
        window_ms = WINDOW_MS.get(window, WINDOW_MS["1h"])
        requested_limit = max(0, int(limit))
        offset = _cursor_offset(cursor)
        events = self._events(
            since_ms=reference_ms - window_ms,
            limit=max(200, requested_limit + offset + 100),
            scope=scope,
            handles=handles,
            handle=handle,
        )
        event_ids = [str(event["event_id"]) for event in events]
        social_by_event = self._social_by_event(event_ids)
        token_links_by_event = self._asset_links_by_event(event_ids)
        alerts_by_event = self._alerts_by_event(event_ids)
        raw_items = [
            self._item(
                event=event,
                social=social_by_event.get(str(event["event_id"])),
                token_links=token_links_by_event.get(str(event["event_id"]), []),
                alerts=alerts_by_event.get(str(event["event_id"]), []),
            )
            for event in events
        ]
        items = self._attach_window_metrics(raw_items)
        items = _filter_items(items, kind=kind, q=q)
        if kind is None and not q:
            items = [item for item in items if item["kind"] != "low_signal" and item["priority"] != "muted"]
        summary = _summary(items)
        items.sort(
            key=lambda item: (
                PRIORITY_RANK[item["priority"]],
                float(item["heat_score"]),
                int(item["received_at_ms"]),
            ),
            reverse=True,
        )
        limited = items[offset : offset + requested_limit]
        next_offset = offset + requested_limit
        has_more = next_offset < len(items)
        return {
            "query": {
                "window": window,
                "scope": scope,
                "kind": kind if kind in KINDS else None,
                "handle": handle or None,
                "q": q or None,
            },
            "summary": summary,
            "items": limited,
            "returned_count": len(limited),
            "has_more": has_more,
            "next_cursor": str(next_offset) if has_more else None,
        }

    def _events(
        self,
        *,
        since_ms: int,
        limit: int,
        scope: str,
        handles: set[str] | None,
        handle: str | None,
    ) -> list[dict[str, Any]]:
        clauses = ["e.received_at_ms >= %s"]
        params: list[Any] = [since_ms]
        if scope == "matched":
            clauses.append("e.is_watched = true")
        allowed_handles = _handle_filter(handles=handles, handle=handle)
        if allowed_handles is not None:
            if not allowed_handles:
                return []
            placeholders = ",".join("%s" for _ in allowed_handles)
            clauses.append(f"lower(e.author_handle) IN ({placeholders})")
            params.extend(sorted(allowed_handles))
        rows = self.evidence.conn.execute(
            f"""
            SELECT e.*
            FROM events e
            WHERE {" AND ".join(clauses)}
            ORDER BY e.received_at_ms DESC
            LIMIT %s
            """,
            (*params, max(0, int(limit))),
        ).fetchall()
        return [decode_event_row(row) for row in rows]

    def _social_by_event(self, event_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not event_ids:
            return {}
        placeholders = ",".join("%s" for _ in event_ids)
        rows = self.evidence.conn.execute(
            f"""
            SELECT *
            FROM social_event_extractions
            WHERE event_id IN ({placeholders})
            """,
            event_ids,
        ).fetchall()
        return {str(row["event_id"]): _social_row(row) for row in rows}

    def _asset_links_by_event(self, event_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        if not event_ids:
            return {}
        placeholders = ",".join("%s" for _ in event_ids)
        rows = self.assets.conn.execute(
            f"""
            SELECT
              tir.event_id,
              tir.target_type,
              tir.target_id,
              tir.pricefeed_id,
              tir.resolution_status,
              CASE
                WHEN tir.resolution_status = 'EXACT' THEN 1.0
                WHEN tir.resolution_status = 'UNIQUE_BY_CONTEXT' THEN 0.9
                ELSE 0.0
              END AS confidence,
              registry_assets.chain_id,
              registry_assets.token_standard,
              registry_assets.address,
              registry_assets.symbol AS asset_symbol,
              cex_tokens.base_symbol AS cex_base_symbol,
              price_feeds.provider,
              price_feeds.native_market_id,
              price_feeds.quote_symbol,
              price_feeds.feed_type
            FROM token_intent_resolutions tir
            LEFT JOIN registry_assets
              ON tir.target_type = 'Asset'
             AND registry_assets.asset_id = tir.target_id
            LEFT JOIN cex_tokens
              ON tir.target_type = 'CexToken'
             AND cex_tokens.cex_token_id = tir.target_id
            LEFT JOIN price_feeds
              ON price_feeds.pricefeed_id = tir.pricefeed_id
            WHERE tir.event_id IN ({placeholders})
              AND tir.is_current = true
              AND tir.target_type IN ('Asset', 'CexToken')
              AND tir.target_id IS NOT NULL
              AND tir.resolution_status IN ('EXACT', 'UNIQUE_BY_CONTEXT')
            ORDER BY confidence DESC, tir.created_at_ms ASC
            """,
            event_ids,
        ).fetchall()
        by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
        seen: set[tuple[str, str]] = set()
        for row in rows:
            event_id = str(row["event_id"])
            identity_key = str(row["target_id"])
            if (event_id, identity_key) in seen:
                continue
            seen.add((event_id, identity_key))
            relation = "direct" if str(row.get("resolution_status")) == "EXACT" else "selected"
            by_event[event_id].append(_asset_link(row, relation=relation))
        return dict(by_event)

    def _alerts_by_event(self, event_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        if not event_ids:
            return {}
        placeholders = ",".join("%s" for _ in event_ids)
        rows = self.signals.conn.execute(
            f"""
            SELECT *
            FROM account_token_alerts
            WHERE event_id IN ({placeholders})
            ORDER BY normalized_value
            """,
            event_ids,
        ).fetchall()
        by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            by_event[str(row["event_id"])].append(dict(row))
        return dict(by_event)

    def _item(
        self,
        *,
        event: dict[str, Any],
        social: dict[str, Any] | None,
        token_links: list[dict[str, Any]],
        alerts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        grounded_social = social if _social_is_grounded(event=event, social=social) else None
        topics = _topics(event=event, social=grounded_social)
        kind = _kind(social=grounded_social, token_links=token_links, topics=topics)
        score = _heat_score(social=grounded_social, token_links=token_links, topics=topics, alerts=alerts, kind=kind)
        priority = _priority(score=score, kind=kind)
        title = _title(kind=kind, social=grounded_social, token_links=token_links, topics=topics, event=event)
        return {
            "item_id": f"attention:{event['event_id']}",
            "kind": kind,
            "kind_label": KIND_LABELS[kind],
            "priority": priority,
            "heat_score": score,
            "received_at_ms": int(event.get("received_at_ms") or 0),
            "updated_at_ms": int(
                grounded_social.get("updated_at_ms") if grounded_social else event.get("received_at_ms") or 0
            ),
            "source": {
                "handle": event.get("author_handle") or (event.get("author") or {}).get("handle"),
                "followers": (event.get("author") or {}).get("followers"),
            },
            "event": _event_summary(event),
            "event_type": grounded_social.get("event_type") if grounded_social else None,
            "direction_hint": grounded_social.get("direction_hint") if grounded_social else "unknown",
            "attention_mechanism": grounded_social.get("attention_mechanism") if grounded_social else None,
            "title": title,
            "summary": (grounded_social.get("summary_zh") if grounded_social else None) or _event_text(event)[:180],
            "why_it_matters": _why_it_matters(
                kind=kind,
                social=grounded_social,
                token_links=token_links,
                topics=topics,
            ),
            "linked_tokens": token_links[:5],
            "linked_topics": topics[:6],
            "metrics": {
                "impact": _float(grounded_social.get("impact_hint")) if grounded_social else 0.0,
                "novelty": _float(grounded_social.get("semantic_novelty_hint")) if grounded_social else 0.0,
                "confidence": _float(grounded_social.get("confidence")) if grounded_social else 0.0,
                "direct_token_count": len(token_links),
                "topic_count": len(topics),
                "account_alert_count": len(alerts),
                "window_mentions": 1,
                "watched_author_count": 1,
            },
            "risks": _item_risks(social=grounded_social, alerts=alerts),
            "next_action": _next_action(kind=kind, priority=priority, token_links=token_links),
        }

    def _attach_window_metrics(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        mention_counts: Counter[str] = Counter()
        author_sets: dict[str, set[str]] = defaultdict(set)
        for item in items:
            keys = _attention_keys(item)
            handle = str((item.get("source") or {}).get("handle") or "")
            for key in keys:
                mention_counts[key] += 1
                if handle:
                    author_sets[key].add(handle)
        for item in items:
            keys = _attention_keys(item)
            if not keys:
                continue
            item["metrics"]["window_mentions"] = max(mention_counts[key] for key in keys)
            item["metrics"]["watched_author_count"] = max(len(author_sets[key]) for key in keys)
            mention_bonus = min(15, (item["metrics"]["window_mentions"] - 1) * 3)
            item["heat_score"] = min(100.0, round(float(item["heat_score"]) + mention_bonus, 2))
            item["priority"] = _priority(score=float(item["heat_score"]), kind=str(item["kind"]))
        return items


def _social_row(row: Any) -> dict[str, Any]:
    data = dict(row)
    return {
        **data,
        "anchor_terms": _json_value(data.get("anchor_terms_json"), []),
        "token_candidates": _json_value(data.get("token_candidates_json"), []),
        "semantic_risks": _json_value(data.get("semantic_risks_json"), []),
        "raw_response": _json_value(data.get("raw_response_json"), {}),
    }


def _asset_link(row: Any, *, relation: str) -> dict[str, Any]:
    data = dict(row)
    status = str(data.get("resolution_status") or "resolved")
    target_type = data.get("target_type")
    target_id = data.get("target_id")
    symbol = data.get("asset_symbol") or data.get("cex_base_symbol")
    return {
        "target_type": target_type,
        "target_id": target_id,
        "asset_id": target_id if target_type == "Asset" else None,
        "identity_key": target_id,
        "symbol": symbol,
        "asset_type": target_type,
        "venue_type": "cex" if target_type == "CexToken" else "dex" if target_type == "Asset" else None,
        "exchange": data.get("provider") if target_type == "CexToken" else None,
        "chain": data.get("chain_id"),
        "address": data.get("address"),
        "inst_id": data.get("native_market_id"),
        "base_symbol": symbol,
        "quote_symbol": data.get("quote_symbol"),
        "inst_type": data.get("feed_type"),
        "relation": relation,
        "confidence": _float(data.get("confidence"), default=1.0),
        "status": status,
        "source": "token_intents",
    }


def _social_is_grounded(*, event: dict[str, Any], social: dict[str, Any] | None) -> bool:
    if not social:
        return False
    event_text = _normalized_text(_event_text(event))
    if not event_text:
        return False
    evidence_terms: list[str] = []
    for anchor in social.get("anchor_terms") or []:
        evidence_terms.extend([str(anchor.get("term") or ""), str(anchor.get("evidence") or "")])
    for candidate in social.get("token_candidates") or []:
        evidence_terms.extend(
            [
                str(candidate.get("symbol") or ""),
                str(candidate.get("project_name") or ""),
                str(candidate.get("address") or ""),
                str(candidate.get("evidence") or ""),
            ]
        )
    evidence_terms.append(str(social.get("subject") or ""))
    return any(_term_is_grounded(term, event_text) for term in evidence_terms)


def _term_is_grounded(term: str, normalized_event_text: str) -> bool:
    normalized_term = _normalized_text(term.lstrip("$@"))
    if len(normalized_term) < 3:
        return False
    return normalized_term in normalized_event_text


def _kind(
    *,
    social: dict[str, Any] | None,
    token_links: list[dict[str, Any]],
    topics: list[dict[str, Any]],
) -> str:
    if any(
        link.get("target_id") and link.get("status") in {"EXACT", "UNIQUE_BY_CONTEXT", "resolved"}
        for link in token_links
    ):
        return "direct_token"
    event_type = str(social.get("event_type") if social else "")
    direction = str(social.get("direction_hint") if social else "")
    if event_type == "market_structure_comment":
        return "market_structure"
    if event_type in {"exchange_risk", "regulation_comment"} or direction == "risk_negative":
        return "risk_alert"
    if event_type in {"ecosystem_boost", "product_mention", "listing_hint"}:
        return "ecosystem_signal"
    if topics:
        return "topic_heat"
    return "low_signal"


def _topics(*, event: dict[str, Any], social: dict[str, Any] | None) -> list[dict[str, Any]]:
    values: list[tuple[str, str, str]] = []
    for anchor in social.get("anchor_terms", []) if social else []:
        term = str(anchor.get("term") or "").strip()
        if term:
            values.append((_topic_key(term), term, str(anchor.get("role") or "keyword")))
    subject = str(social.get("subject") or "").strip() if social else ""
    if subject:
        values.append((_topic_key(subject), subject, "subject"))
    for hashtag in event.get("hashtags") or []:
        values.append((_topic_key(str(hashtag)), str(hashtag), "hashtag"))
    for cashtag in event.get("cashtags") or []:
        values.append((_topic_key(str(cashtag)), f"${str(cashtag).lstrip('$')}", "cashtag"))
    topics = []
    seen: set[str] = set()
    for key, label, role in values:
        if not key or key in seen:
            continue
        seen.add(key)
        topics.append({"key": key, "label": label, "role": role})
    return topics


def _heat_score(
    *,
    social: dict[str, Any] | None,
    token_links: list[dict[str, Any]],
    topics: list[dict[str, Any]],
    alerts: list[dict[str, Any]],
    kind: str,
) -> float:
    base = 20.0
    if kind == "direct_token":
        base += 32
    elif kind in {"risk_alert", "market_structure"}:
        base += 20
    elif kind == "ecosystem_signal":
        base += 18
    elif kind == "topic_heat":
        base += 12
    if social:
        base += _float(social.get("impact_hint")) * 18
        base += _float(social.get("semantic_novelty_hint")) * 12
        base += _float(social.get("confidence")) * 12
    if token_links:
        base += min(10, len(token_links) * 4)
    if topics:
        base += min(8, len(topics) * 2)
    if alerts:
        base += min(8, len(alerts) * 3)
    return round(max(0.0, min(100.0, base)), 2)


def _priority(*, score: float, kind: str) -> str:
    if kind == "low_signal" or score < 35:
        return "muted"
    if score >= 75:
        return "hot"
    if score >= 50:
        return "watch"
    return "context"


def _title(
    *,
    kind: str,
    social: dict[str, Any] | None,
    token_links: list[dict[str, Any]],
    topics: list[dict[str, Any]],
    event: dict[str, Any],
) -> str:
    if token_links:
        symbols = [str(link.get("symbol") or link.get("identity_key")) for link in token_links[:2]]
        return " / ".join(symbols)
    if topics:
        return str(topics[0]["label"])
    if social and social.get("subject"):
        return str(social["subject"])
    return _event_text(event)[:64] or KIND_LABELS[kind]


def _why_it_matters(
    *,
    kind: str,
    social: dict[str, Any] | None,
    token_links: list[dict[str, Any]],
    topics: list[dict[str, Any]],
) -> str:
    if kind == "direct_token":
        return "watched account mentioned a concrete token or CA; check token flow and market reaction."
    if kind == "risk_alert":
        return "watched account flagged a risk regime or negative catalyst; check exposure and related assets."
    if kind == "market_structure":
        return "market structure commentary can change positioning even without a single token target."
    if kind == "ecosystem_signal":
        return "ecosystem-level attention can spill into multiple tokens before a direct ticker appears."
    if kind == "topic_heat":
        label = topics[0]["label"] if topics else (social or {}).get("subject")
        return f"keyword/topic attention detected around {label}; keep it as a topic until a token link is proven."
    return "low trading relevance; keep as context, not a signal."


def _next_action(*, kind: str, priority: str, token_links: list[dict[str, Any]]) -> str:
    if kind == "direct_token" and token_links:
        return "open_token_flow"
    if kind in {"topic_heat", "ecosystem_signal"} and priority in {"hot", "watch"}:
        return "watch_topic_followups"
    if kind in {"risk_alert", "market_structure"}:
        return "review_market_context"
    return "keep_context"


def _event_summary(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": event.get("event_id"),
        "tweet_id": event.get("tweet_id"),
        "canonical_url": event.get("canonical_url"),
        "author_handle": event.get("author_handle") or (event.get("author") or {}).get("handle"),
        "text": _event_text(event),
        "received_at_ms": event.get("received_at_ms"),
    }


def _event_text(event: dict[str, Any]) -> str:
    return str(event.get("text_clean") or event.get("search_text") or (event.get("content") or {}).get("text") or "")


def _attention_keys(item: dict[str, Any]) -> list[str]:
    keys = [
        f"target:{link.get('target_type') or 'target'}:{link.get('target_id') or link.get('identity_key')}"
        for link in item.get("linked_tokens") or []
        if link.get("target_id") or link.get("identity_key")
    ]
    keys.extend(f"topic:{topic['key']}" for topic in item.get("linked_topics") or [] if topic.get("key"))
    return keys or [str(item["item_id"])]


def _summary(items: list[dict[str, Any]]) -> dict[str, int]:
    summary = {kind: 0 for kind in KINDS}
    summary.update({priority: 0 for priority in PRIORITY_RANK})
    for item in items:
        summary[str(item["kind"])] += 1
        summary[str(item["priority"])] += 1
    return summary


def _filter_items(
    items: list[dict[str, Any]],
    *,
    kind: str | None,
    q: str | None,
) -> list[dict[str, Any]]:
    filtered = items
    if kind in KINDS:
        filtered = [item for item in filtered if item["kind"] == kind]
    if q and q.strip():
        terms = _query_terms(q)
        if terms:
            filtered = [item for item in filtered if any(term in _search_text(item) for term in terms)]
    return filtered


def _query_terms(q: str) -> list[str]:
    return [term.strip().lower().lstrip("@") for term in re.split(r"[,\n]+", q) if term.strip()]


def _search_text(item: dict[str, Any]) -> str:
    values = [
        item.get("title"),
        item.get("summary"),
        item.get("why_it_matters"),
        (item.get("source") or {}).get("handle"),
        (item.get("event") or {}).get("text"),
        item.get("event_type"),
        *(topic.get("label") for topic in item.get("linked_topics") or []),
        *(link.get("symbol") for link in item.get("linked_tokens") or []),
    ]
    return " ".join(str(value).lower() for value in values if value)


def _handle_filter(*, handles: set[str] | None, handle: str | None) -> set[str] | None:
    base = {item.strip().lstrip("@").lower() for item in handles or set() if item.strip()}
    requested = {item.strip().lstrip("@").lower() for item in (handle or "").split(",") if item.strip()}
    if handles is None:
        return requested or None
    if not requested:
        return base
    return base & requested


def _cursor_offset(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        return max(0, int(cursor))
    except ValueError:
        return 0


def _topic_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


def _normalized_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _alert_risks(alerts: list[dict[str, Any]]) -> list[str]:
    risks = []
    for alert in alerts:
        if alert.get("token_resolution_status") not in {None, "resolved_ca"}:
            risks.append(str(alert["token_resolution_status"]))
    return risks


def _item_risks(*, social: dict[str, Any] | None, alerts: list[dict[str, Any]]) -> list[str]:
    social_risks = social.get("semantic_risks") if social else []
    return list(dict.fromkeys([*social_risks, *_alert_risks(alerts)]))


def _json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    return value


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _now_ms() -> int:
    return int(time.time() * 1000)
