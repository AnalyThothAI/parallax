from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from parallax.domains.notifications.types import NotificationCandidate
from parallax.platform.config.settings import NotificationRuleConfig, Settings
from parallax.platform.validation import require_nonnegative_int


class NotificationRuleEngine:
    def __init__(
        self,
        *,
        settings: Settings,
        evidence: Any,
        account_alerts: Any,
    ) -> None:
        self.settings = settings
        self.evidence = evidence
        self.account_alerts = account_alerts

    def evaluate(self, *, now_ms: int) -> list[NotificationCandidate]:
        if not self.settings.notifications.enabled:
            return []
        return [
            *self._watched_account_activity(now_ms=now_ms),
            *self._watched_account_token_alerts(now_ms=now_ms),
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

    def _rule(self, rule_id: str) -> NotificationRuleConfig:
        return self.settings.notifications.rules[rule_id]

    def _limit(self) -> int:
        return int(self.settings.notifications.candidate_limit)


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


def _required_source_timestamp_ms(row: Mapping[str, Any], field_name: str, *, rule_id: str) -> int:
    try:
        value: object = row[field_name]
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
