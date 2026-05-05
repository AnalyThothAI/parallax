from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote

from ..settings import NotificationRuleConfig, Settings
from .notification_models import NotificationCandidate

WATCHED_ACTIVITY_WINDOW_MS = 60 * 60_000
DEFAULT_LIMIT = 50


class NotificationRuleEngine:
    def __init__(
        self,
        *,
        settings: Settings,
        evidence,
        account_alerts,
        token_flow,
        harness,
    ):
        self.settings = settings
        self.evidence = evidence
        self.account_alerts = account_alerts
        self.token_flow = token_flow
        self.harness = harness

    def evaluate(self, *, now_ms: int | None = None) -> list[NotificationCandidate]:
        now = int(now_ms if now_ms is not None else _now_ms())
        if not self.settings.notifications.enabled:
            return []
        candidates: list[NotificationCandidate] = []
        candidates.extend(self._watched_account_activity(now_ms=now))
        candidates.extend(self._watched_account_token_alerts(now_ms=now))
        hot_entity_keys = set()
        hot_candidates = self._hot_quality_tokens(now_ms=now)
        hot_entity_keys.update(item.entity_key for item in hot_candidates if item.entity_key)
        candidates.extend(hot_candidates)
        candidates.extend(self._quality_tokens(now_ms=now, skip_entity_keys=hot_entity_keys))
        candidates.extend(self._harness_snapshots(now_ms=now))
        return candidates

    def _watched_account_activity(self, *, now_ms: int) -> list[NotificationCandidate]:
        rule_id = "watched_account_activity"
        rule = self._rule(rule_id)
        if not rule.enabled:
            return []
        since_ms = now_ms - WATCHED_ACTIVITY_WINDOW_MS
        events = self.evidence.recent_events(
            limit=self._limit(),
            watched_only=True,
        )
        candidates: list[NotificationCandidate] = []
        for event in events:
            received_at_ms = _int(event.get("received_at_ms"))
            if received_at_ms < since_ms:
                continue
            event_id = str(event.get("event_id") or "")
            if not event_id:
                continue
            author_handle = _handle(event.get("author_handle"))
            action = str(event.get("action") or "activity")
            title = f"@{author_handle} new {action}" if author_handle else f"Watched account {action}"
            body = _compact_text(event.get("text_clean") or event.get("text") or action)
            candidates.append(
                NotificationCandidate(
                    dedup_key=f"{rule_id}:event:{event_id}",
                    rule_id=rule_id,
                    severity="info",
                    title=title,
                    body=body,
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
        alerts = self.account_alerts.account_alerts(
            window="1h",
            limit=self._limit(),
        )
        candidates: list[NotificationCandidate] = []
        for alert in alerts:
            alert_id = str(alert.get("alert_id") or "")
            if not alert_id:
                continue
            received_at_ms = _int(alert.get("received_at_ms") or now_ms)
            author_handle = _handle(alert.get("author_handle"))
            symbol = _symbol(alert.get("normalized_value"))
            first_global = bool(alert.get("is_first_seen_global"))
            first_author = bool(alert.get("is_first_seen_by_author"))
            severity = "warning" if first_global or first_author else "info"
            title = f"@{author_handle} mentioned ${symbol}" if author_handle and symbol else "Watched token alert"
            body = "First-seen watched-account token mention" if first_global else "Watched-account token mention"
            candidates.append(
                NotificationCandidate(
                    dedup_key=f"{rule_id}:alert:{alert_id}",
                    rule_id=rule_id,
                    severity=severity,
                    title=title,
                    body=body,
                    entity_type="token",
                    entity_key=str(alert.get("entity_key") or f"symbol:{symbol}" if symbol else ""),
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

    def _hot_quality_tokens(self, *, now_ms: int) -> list[NotificationCandidate]:
        rule_id = "hot_quality_token_5m"
        rule = self._rule(rule_id)
        if not rule.enabled:
            return []
        return self._token_candidates(
            rule_id=rule_id,
            rule=rule,
            now_ms=now_ms,
            severity="high",
            title_suffix="hot social quality",
        )

    def _quality_tokens(self, *, now_ms: int, skip_entity_keys: set[str]) -> list[NotificationCandidate]:
        rule_id = "quality_token_5m"
        rule = self._rule(rule_id)
        if not rule.enabled:
            return []
        return [
            candidate
            for candidate in self._token_candidates(
                rule_id=rule_id,
                rule=rule,
                now_ms=now_ms,
                severity="warning",
                title_suffix="quality discussion",
            )
            if candidate.entity_key not in skip_entity_keys
        ]

    def _token_candidates(
        self,
        *,
        rule_id: str,
        rule: NotificationRuleConfig,
        now_ms: int,
        severity: str,
        title_suffix: str,
    ) -> list[NotificationCandidate]:
        items = self.token_flow.token_flow(
            window="5m",
            limit=self._limit(),
            scope="all",
            now_ms=now_ms,
        )
        candidates: list[NotificationCandidate] = []
        for item in items:
            social_heat_score = _score(item.get("social_heat"))
            discussion_quality_score = _score(item.get("discussion_quality"))
            opportunity_score = _score(item.get("opportunity"))
            if rule.social_heat_min is not None and social_heat_score < rule.social_heat_min:
                continue
            if rule.discussion_quality_min is not None and discussion_quality_score < rule.discussion_quality_min:
                continue
            if rule.opportunity_min is not None and opportunity_score < rule.opportunity_min:
                continue
            timing = item.get("timing") if isinstance(item.get("timing"), dict) else {}
            if rule.suppress_chase_risk and bool(timing.get("chase_risk")):
                continue
            identity = item.get("identity") if isinstance(item.get("identity"), dict) else {}
            identity_key = str(identity.get("identity_key") or identity.get("token_id") or "").strip()
            if not identity_key:
                continue
            symbol = _symbol(identity.get("symbol"))
            flow = item.get("flow") if isinstance(item.get("flow"), dict) else {}
            occurrence_at_ms = _int(flow.get("window_end_ms") or now_ms)
            bucket = occurrence_at_ms // max(1, int(rule.cooldown_seconds or 300) * 1000)
            payload = {
                "identity_key": identity_key,
                "token_id": identity.get("token_id"),
                "symbol": symbol,
                "chain": _chain(identity.get("chain")),
                "address": identity.get("address"),
                "social_heat_score": social_heat_score,
                "discussion_quality_score": discussion_quality_score,
                "opportunity_score": opportunity_score,
                "mentions": _int(flow.get("mentions")),
                "timing": timing,
            }
            chain = _chain(identity.get("chain"))
            address = str(identity.get("address") or "") or None
            candidates.append(
                NotificationCandidate(
                    dedup_key=f"{rule_id}:{identity_key}:{bucket}",
                    rule_id=rule_id,
                    severity=severity,
                    title=f"${symbol} {title_suffix}" if symbol else title_suffix,
                    body=_token_markdown_body(
                        heading="5m heat alert" if rule_id == "hot_quality_token_5m" else "5m quality alert",
                        symbol=symbol,
                        chain=chain,
                        address=address,
                        identity_key=identity_key,
                        social_heat_score=social_heat_score,
                        discussion_quality_score=discussion_quality_score,
                        opportunity_score=opportunity_score,
                        mentions=_int(flow.get("mentions")),
                        chase_risk=bool(timing.get("chase_risk")),
                    ),
                    entity_type="token",
                    entity_key=identity_key,
                    symbol=symbol,
                    chain=chain,
                    address=address,
                    source_table="token_flow",
                    source_id=identity_key,
                    occurrence_at_ms=occurrence_at_ms,
                    payload=payload,
                    channels=rule.channels,
                )
            )
        return candidates

    def _harness_snapshots(self, *, now_ms: int) -> list[NotificationCandidate]:
        rule_id = "harness_snapshot_high_score"
        rule = self._rule(rule_id)
        if not rule.enabled:
            return []
        data = self.harness.snapshots(
            window="1h",
            horizon="6h",
            limit=self._limit(),
        )
        rows = data.get("items", []) if isinstance(data, dict) else []
        candidates: list[NotificationCandidate] = []
        threshold = float(rule.combined_score_min if rule.combined_score_min is not None else 0.8)
        for row in rows:
            score = float(row.get("combined_score") or 0)
            if score < threshold:
                continue
            snapshot_id = str(row.get("snapshot_id") or "")
            if not snapshot_id:
                continue
            asset = _symbol(row.get("asset"))
            candidates.append(
                NotificationCandidate(
                    dedup_key=f"{rule_id}:snapshot:{snapshot_id}",
                    rule_id=rule_id,
                    severity="high",
                    title=f"{asset} high harness score" if asset else "High harness score",
                    body=f"Combined score {score:.2f}",
                    entity_type="harness_snapshot",
                    entity_key=f"harness_snapshot:{snapshot_id}",
                    symbol=asset,
                    event_id=str(row.get("source_event_id") or "") or None,
                    source_table="harness_snapshots",
                    source_id=snapshot_id,
                    occurrence_at_ms=_int(row.get("decision_time_ms") or now_ms),
                    payload={
                        "snapshot_id": snapshot_id,
                        "asset": asset,
                        "horizon": row.get("horizon"),
                        "combined_score": score,
                        "policy_signal": row.get("policy_signal"),
                        "source_event_id": row.get("source_event_id"),
                    },
                    channels=rule.channels,
                )
            )
        return candidates

    def _rule(self, rule_id: str) -> NotificationRuleConfig:
        return self.settings.notifications.rules[rule_id]

    def _limit(self) -> int:
        return max(DEFAULT_LIMIT, int(self.settings.notifications.token_flow_limit))


def _score(block: Any) -> int:
    if not isinstance(block, dict):
        return 0
    return int(block.get("score") or 0)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _handle(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lstrip("@").lower()
    return normalized or None


def _symbol(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lstrip("$").upper()
    return normalized or None


def _chain(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    return normalized or None


def _compact_text(value: Any, *, limit: int = 180) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def _token_markdown_body(
    *,
    heading: str,
    symbol: str | None,
    chain: str | None,
    address: str | None,
    identity_key: str,
    social_heat_score: int,
    discussion_quality_score: int,
    opportunity_score: int,
    mentions: int,
    chase_risk: bool,
) -> str:
    display = f"${symbol}" if symbol else identity_key
    lines = [
        f"## {display} {heading}",
        "",
        f"- **Heat:** {social_heat_score}",
        f"- **Discussion quality:** {discussion_quality_score}",
        f"- **Opportunity:** {opportunity_score}",
        f"- **5m mentions:** {mentions}",
        f"- **Chase risk:** {'yes' if chase_risk else 'no'}",
    ]
    if chain:
        lines.append(f"- **Chain:** `{chain}`")
    if address:
        lines.append(f"- **Address:** `{address}`")
    lines.append(f"- **Identity:** `{identity_key}`")
    links = _token_links(symbol=symbol, chain=chain, address=address)
    if links:
        lines.extend(["", "**Links**"])
        lines.extend(f"- [{label}]({url})" for label, url in links)
    return "\n".join(lines)


def _token_links(*, symbol: str | None, chain: str | None, address: str | None) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    if chain and address:
        links.append(("GMGN", f"https://gmgn.ai/{quote(chain)}/token/{quote(address)}"))
    if symbol:
        links.append(("X Search", f"https://x.com/search?q={quote('$' + symbol)}&f=live"))
    return links


def _now_ms() -> int:
    return int(time.time() * 1000)
