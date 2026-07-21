from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from parallax.domains.news_intel.interfaces import NewsNotificationCandidate
from parallax.platform.config.settings import NotificationRuleConfig, Settings
from parallax.platform.validation import require_nonnegative_int

from ..types import NotificationCandidate

NEWS_HIGH_SIGNAL_RULE_ID = "news_high_signal"


class NotificationRuleEngine:
    def __init__(
        self,
        *,
        settings: Settings,
        evidence: Any,
        account_alerts: Any,
        news: Any = None,
    ) -> None:
        self.settings = settings
        self.evidence = evidence
        self.account_alerts = account_alerts
        self.news = news

    def evaluate(self, *, now_ms: int) -> list[NotificationCandidate]:
        if not self.settings.notifications.enabled:
            return []
        return [
            *self._watched_account_activity(now_ms=now_ms),
            *self._watched_account_token_alerts(now_ms=now_ms),
            *self._news_high_signal_candidates(now_ms=now_ms),
        ]

    def _watched_account_activity(self, *, now_ms: int) -> list[NotificationCandidate]:
        rule_id = "watched_account_activity"
        rule = self._rule(rule_id)
        if not rule.enabled:
            return []
        since_ms = now_ms - int(self.settings.notifications.watched_activity_window_ms)
        events = self.evidence.recent_events(
            limit=self._limit(),
            since_ms=since_ms,
            watched_only=True,
        )
        candidates: list[NotificationCandidate] = []
        for event in events:
            received_at_ms = _required_source_timestamp_ms(event, "received_at_ms", rule_id=rule_id)
            if received_at_ms < since_ms:
                continue
            event_id = _required_source_text(event, "event_id", rule_id=rule_id)
            author_handle = _handle(event.get("author_handle"))
            action = str(event.get("action") or "activity")
            title = f"@{author_handle} new {action}" if author_handle else f"Watched account {action}"
            candidates.append(
                NotificationCandidate(
                    dedup_key=_activity_dedup_key(
                        rule_id,
                        author_handle=author_handle,
                        action=action,
                        occurrence_at_ms=received_at_ms,
                        cooldown_seconds=rule.cooldown_seconds,
                    ),
                    rule_id=rule_id,
                    severity="info",
                    title=title,
                    body=_compact_text(event.get("text_clean") or event.get("text") or action),
                    entity_type="account",
                    entity_key=f"account:{author_handle}" if author_handle else None,
                    author_handle=author_handle,
                    event_id=event_id,
                    source_table="events",
                    source_id=event_id,
                    occurrence_at_ms=received_at_ms,
                    payload={
                        "event_id": event_id,
                        "author_handle": author_handle,
                        "action": action,
                        "received_at_ms": received_at_ms,
                    },
                    channels=rule.channels,
                )
            )
        return candidates

    def _watched_account_token_alerts(self, *, now_ms: int) -> list[NotificationCandidate]:
        rule_id = "watched_account_token_alert"
        rule = self._rule(rule_id)
        if not rule.enabled:
            return []
        alerts = self.account_alerts.account_alerts(window="1h", limit=self._limit(), now_ms=now_ms)
        candidates: list[NotificationCandidate] = []
        for alert in alerts:
            alert_id = _required_source_text(alert, "alert_id", rule_id=rule_id)
            received_at_ms = _required_source_timestamp_ms(alert, "received_at_ms", rule_id=rule_id)
            author_handle = _handle(alert.get("author_handle"))
            symbol = _symbol(alert.get("normalized_value"))
            first_global = bool(alert.get("is_first_seen_global"))
            first_author = bool(alert.get("is_first_seen_by_author"))
            severity = "warning" if first_global or first_author else "info"
            entity_key = str(alert.get("entity_key") or (f"symbol:{symbol}" if symbol else ""))
            candidates.append(
                NotificationCandidate(
                    dedup_key=_alert_dedup_key(
                        rule_id,
                        entity_key=entity_key,
                        author_handle=author_handle,
                        occurrence_at_ms=received_at_ms,
                        cooldown_seconds=rule.cooldown_seconds,
                    ),
                    rule_id=rule_id,
                    severity=severity,
                    title=(
                        f"@{author_handle} mentioned ${symbol}" if author_handle and symbol else "Watched token alert"
                    ),
                    body=(
                        "First-seen watched-account token mention" if first_global else "Watched-account token mention"
                    ),
                    entity_type="token",
                    entity_key=entity_key,
                    author_handle=author_handle,
                    symbol=symbol,
                    chain=_chain(alert.get("chain")),
                    event_id=str(alert.get("event_id") or "") or None,
                    source_table="account_token_alerts",
                    source_id=alert_id,
                    occurrence_at_ms=received_at_ms,
                    payload={
                        "alert_id": alert_id,
                        "event_id": alert.get("event_id"),
                        "author_handle": author_handle,
                        "symbol": symbol,
                        "is_first_seen_global": first_global,
                        "is_first_seen_by_author": first_author,
                        "received_at_ms": received_at_ms,
                    },
                    channels=rule.channels,
                )
            )
        return candidates

    def _news_high_signal_candidates(self, *, now_ms: int) -> list[NotificationCandidate]:
        rule = self._rule(NEWS_HIGH_SIGNAL_RULE_ID)
        if not rule.enabled or self.news is None:
            return []
        since_ms = now_ms - int(self.settings.notifications.news_high_signal_recency_window_ms)
        rows: list[NewsNotificationCandidate] = self.news.list_news_high_signal_notification_candidates(
            limit=self._news_high_signal_query_limit(),
            since_ms=since_ms,
        )
        candidates: list[NotificationCandidate] = []
        seen_semantic_signatures: set[str] = set()
        seen_external_push_signatures: set[str] = set()
        for row in rows:
            if row.latest_at_ms < since_ms:
                continue
            semantic_signature = _news_semantic_signature(row)
            if semantic_signature in seen_semantic_signatures:
                continue
            seen_semantic_signatures.add(semantic_signature)

            external_push_eligible, suppression_reason = _news_external_push_readiness(row)
            if not _has_external_channels(rule.channels):
                external_push_eligible = False
                suppression_reason = "external_channel_unavailable"
            external_push_signature = None
            if external_push_eligible:
                external_push_signature = _news_external_push_signature(
                    row,
                    cooldown_seconds=rule.cooldown_seconds,
                )
                if external_push_signature in seen_external_push_signatures:
                    external_push_eligible = False
                    suppression_reason = "external_signature_duplicate"
                else:
                    seen_external_push_signatures.add(external_push_signature)

            title = _news_display_title(row)
            summary = _compact_text(row.summary_zh, limit=360) if row.summary_zh else ""
            symbols = _news_symbols(row)
            channels = (
                rule.channels
                if external_push_eligible
                else tuple(channel for channel in rule.channels if channel == "in_app")
            )
            candidates.append(
                NotificationCandidate(
                    dedup_key=f"{NEWS_HIGH_SIGNAL_RULE_ID}:{semantic_signature}",
                    rule_id=NEWS_HIGH_SIGNAL_RULE_ID,
                    severity="high",
                    title=title,
                    body=_news_body(row, summary=summary),
                    entity_type="news_story",
                    entity_key=f"news_story:{row.story_key}",
                    symbol=symbols[0] if symbols else None,
                    source_table="news_page_rows",
                    source_id=row.row_id,
                    occurrence_at_ms=row.latest_at_ms,
                    payload={
                        "news_item_id": row.news_item_id,
                        "representative_news_item_id": row.representative_news_item_id,
                        "story_key": row.story_key,
                        "decision_class": row.decision_class,
                        "direction": row.direction,
                        "symbols": list(symbols),
                        "semantic_signature": semantic_signature,
                        "display_title": title,
                        "summary": summary or None,
                        "canonical_url": row.canonical_url,
                        "source_domain": row.source_domain,
                        "external_push_signature": external_push_signature,
                        "external_push_eligible": external_push_eligible,
                        "external_push_suppression_reason": suppression_reason,
                    },
                    channels=channels,
                )
            )
        return candidates

    def _rule(self, rule_id: str) -> NotificationRuleConfig:
        return self.settings.notifications.rules[rule_id]

    def _limit(self) -> int:
        return int(self.settings.notifications.candidate_limit)

    def _news_high_signal_query_limit(self) -> int:
        return max(
            int(self.settings.notifications.news_high_signal_query_min_limit),
            self._limit() * int(self.settings.notifications.news_high_signal_query_multiplier),
        )


def _cooldown_bucket(occurrence_at_ms: int, cooldown_seconds: int) -> int:
    seconds = require_nonnegative_int(
        cooldown_seconds,
        error_code="notification_cooldown_seconds_required",
    )
    return occurrence_at_ms // (max(1, seconds) * 1000)


def _activity_dedup_key(
    rule_id: str,
    *,
    author_handle: str | None,
    action: str,
    occurrence_at_ms: int,
    cooldown_seconds: int,
) -> str:
    return (
        f"{rule_id}:account:{author_handle or 'unknown'}:{action or 'activity'}:"
        f"{_cooldown_bucket(occurrence_at_ms, cooldown_seconds)}"
    )


def _alert_dedup_key(
    rule_id: str,
    *,
    entity_key: str,
    author_handle: str | None,
    occurrence_at_ms: int,
    cooldown_seconds: int,
) -> str:
    return (
        f"{rule_id}:{entity_key or 'unknown'}:author:{author_handle or 'unknown'}:"
        f"{_cooldown_bucket(occurrence_at_ms, cooldown_seconds)}"
    )


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _news_semantic_signature(row: NewsNotificationCandidate) -> str:
    return _stable_hash(
        {
            "story_key": row.story_key,
            "decision_class": row.decision_class,
            "direction": row.direction,
            "symbols": list(row.affected_symbols),
        }
    )


def _news_external_push_signature(row: NewsNotificationCandidate, *, cooldown_seconds: int) -> str:
    return _stable_hash(
        {
            "asset_bucket": _news_asset_bucket(row),
            "direction": row.direction,
            "cooldown_bucket": _cooldown_bucket(row.latest_at_ms, cooldown_seconds),
            "story_key": row.story_key,
        }
    )


def _news_external_push_readiness(row: NewsNotificationCandidate) -> tuple[bool, str | None]:
    if row.external_push_ready is not True:
        return False, row.external_push_block_reason or "external_push_state_missing"
    if row.external_push_basis != "agent_brief":
        return False, "external_push_basis_invalid"
    if not row.summary_zh:
        return False, "agent_brief_missing_summary"
    return True, None


def _news_symbols(row: NewsNotificationCandidate) -> tuple[str, ...]:
    symbols: list[str] = []
    for symbol in (*row.token_symbols, *row.affected_symbols):
        normalized = _external_asset_symbol(symbol)
        if normalized and normalized not in symbols:
            symbols.append(normalized)
    return tuple(symbols[:12])


def _news_asset_bucket(row: NewsNotificationCandidate) -> str:
    symbols = list(_news_symbols(row))
    if "CL" in symbols:
        return "CL"
    return "|".join(symbols[:3]) if symbols else row.news_item_id


def _external_asset_symbol(value: str) -> str | None:
    symbol = _symbol(value)
    if symbol and symbol.startswith("XYZ-"):
        symbol = symbol[4:]
    return symbol


def _news_display_title(row: NewsNotificationCandidate) -> str:
    return _compact_text(row.title_zh or row.projected_title_zh or row.headline or "News high signal", limit=96)


def _news_body(row: NewsNotificationCandidate, *, summary: str) -> str:
    lines = [f"Source: {_compact_text(row.source_domain, limit=80)}"]
    if summary:
        lines.append(summary)
    if row.canonical_url:
        lines.append(row.canonical_url)
    return "\n".join(lines)


def _required_source_timestamp_ms(row: Mapping[str, Any], field_name: str, *, rule_id: str) -> int:
    try:
        value = row[field_name]
    except KeyError as exc:
        raise ValueError(f"notification_source_timestamp_required:{rule_id}:{field_name}") from exc
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"notification_source_timestamp_required:{rule_id}:{field_name}")
    return value


def _required_source_text(row: Mapping[str, Any], field_name: str, *, rule_id: str) -> str:
    value = row.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"notification_source_identity_required:{rule_id}:{field_name}")
    return value.strip()


def _handle(value: Any) -> str | None:
    normalized = str(value or "").strip().lstrip("@").lower()
    return normalized or None


def _symbol(value: Any) -> str | None:
    normalized = str(value or "").strip().lstrip("$").upper()
    return normalized or None


def _chain(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    return normalized or None


def _compact_text(value: Any, *, limit: int = 180) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "..."


def _has_external_channels(channels: tuple[str, ...]) -> bool:
    return any(channel != "in_app" for channel in channels)
