from __future__ import annotations

import hashlib
import json
import time
from typing import Any
from urllib.parse import quote

from gmgn_twitter_intel.domains.token_intel.scoring.factor_snapshot import TOKEN_FACTOR_SNAPSHOT_VERSION
from gmgn_twitter_intel.platform.config.settings import NotificationRuleConfig, Settings

from ..types import NotificationCandidate

WATCHED_ACTIVITY_WINDOW_MS = 60 * 60_000
DEFAULT_LIMIT = 50
MAX_SIGNAL_PULSE_NOTIFICATION_PAGES = 5
SIGNAL_PULSE_RULE_ID = "signal_pulse_candidate"
DEFAULT_SIGNAL_PULSE_WINDOW = "1h"
DEFAULT_SIGNAL_PULSE_SCOPES = ("all", "matched")
DEFAULT_SIGNAL_PULSE_STATUSES = ("trade_candidate", "token_watch", "theme_watch", "risk_rejected_high_info")
SIGNAL_PULSE_SEVERITY = {
    "trade_candidate": "critical",
    "theme_watch": "warning",
    "risk_rejected_high_info": "warning",
}
SIGNAL_PULSE_COOLDOWN_MS = {
    "trade_candidate": 15 * 60_000,
    "token_watch": 30 * 60_000,
    "theme_watch": 2 * 60 * 60_000,
    "risk_rejected_high_info": 60 * 60_000,
}


class NotificationRuleEngine:
    def __init__(
        self,
        *,
        settings: Settings,
        evidence,
        account_alerts,
        asset_flow,
        harness,
        pulse=None,
    ):
        self.settings = settings
        self.evidence = evidence
        self.account_alerts = account_alerts
        self.asset_flow = asset_flow
        self.harness = harness
        self.pulse = pulse

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
        candidates.extend(self._signal_pulse_candidates(now_ms=now))
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
            dedup_key = _activity_dedup_key(
                rule_id,
                author_handle=author_handle,
                action=action,
                occurrence_at_ms=received_at_ms,
                cooldown_seconds=rule.cooldown_seconds,
            )
            candidates.append(
                NotificationCandidate(
                    dedup_key=dedup_key,
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
            entity_key = str(alert.get("entity_key") or (f"symbol:{symbol}" if symbol else ""))
            dedup_key = _alert_dedup_key(
                rule_id,
                entity_key=entity_key,
                author_handle=author_handle,
                occurrence_at_ms=received_at_ms,
                cooldown_seconds=rule.cooldown_seconds,
            )
            candidates.append(
                NotificationCandidate(
                    dedup_key=dedup_key,
                    rule_id=rule_id,
                    severity=severity,
                    title=title,
                    body=body,
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
        data = self.asset_flow.asset_flow(
            window="5m",
            limit=self._limit(),
            scope="all",
            now_ms=now_ms,
        )
        items = []
        if isinstance(data, dict):
            items.extend(data.get("targets") or [])
            items.extend(data.get("attention") or [])
        candidates: list[NotificationCandidate] = []
        for item in items:
            decision = str(item.get("decision") or "").strip().lower()
            if decision not in {"driver", "watch"}:
                continue
            social_heat_score = _score_value(item, "heat")
            discussion_quality_score = _score_value(item, "quality")
            opportunity_score = _score_value(item, "opportunity")
            if rule.social_heat_min is not None and social_heat_score < rule.social_heat_min:
                continue
            if rule.discussion_quality_min is not None and discussion_quality_score < rule.discussion_quality_min:
                continue
            if rule.opportunity_min is not None and opportunity_score < rule.opportunity_min:
                continue
            target = item.get("target") if isinstance(item.get("target"), dict) else {}
            attention = item.get("attention") if isinstance(item.get("attention"), dict) else {}
            data_health = item.get("data_health") if isinstance(item.get("data_health"), dict) else {}
            score = item.get("score") if isinstance(item.get("score"), dict) else {}
            identity_key = str(target.get("target_id") or "").strip()
            if not identity_key:
                continue
            symbol = _symbol(target.get("symbol"))
            occurrence_at_ms = _int(attention.get("latest_seen_ms") or now_ms)
            bucket = occurrence_at_ms // max(1, int(rule.cooldown_seconds or 300) * 1000)
            target_type = str(target.get("target_type") or "")
            venue_type = "cex" if target_type == "CexToken" else "dex" if target_type == "Asset" else None
            chain = _chain(target.get("chain_id")) if target_type == "Asset" else None
            address = str(target.get("address") or "") or None if target_type == "Asset" else None
            timing = {"chase_risk": False}
            payload = {
                "identity_key": identity_key,
                "target_id": identity_key,
                "target_type": target_type or None,
                "venue_type": venue_type,
                "exchange": target.get("provider") if target_type == "CexToken" else None,
                "inst_id": target.get("native_market_id"),
                "symbol": symbol,
                "chain": chain,
                "address": address,
                "social_heat_score": social_heat_score,
                "discussion_quality_score": discussion_quality_score,
                "opportunity_score": opportunity_score,
                "score_version": _score_version(score.get("opportunity")),
                "decision": decision,
                "data_health": data_health,
                "mentions": _int(attention.get("mentions_window")),
                "unique_authors": _int(attention.get("unique_authors")),
                "watched_mentions": _int(attention.get("watched_mentions")),
                "timing": timing,
            }
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
                        mentions=_int(attention.get("mentions_window")),
                        chase_risk=bool(timing.get("chase_risk")),
                    ),
                    entity_type="token",
                    entity_key=identity_key,
                    symbol=symbol,
                    chain=chain,
                    address=address,
                    source_table="token_radar_rows",
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

    def _signal_pulse_candidates(self, *, now_ms: int) -> list[NotificationCandidate]:
        rule = self._rule(SIGNAL_PULSE_RULE_ID)
        if not rule.enabled or self.pulse is None:
            return []
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        window = rule.window or DEFAULT_SIGNAL_PULSE_WINDOW
        scopes = rule.scopes or DEFAULT_SIGNAL_PULSE_SCOPES
        statuses = set(rule.statuses or DEFAULT_SIGNAL_PULSE_STATUSES)
        for scope in scopes:
            cursor = None
            for _ in range(MAX_SIGNAL_PULSE_NOTIFICATION_PAGES):
                page = self.pulse.list_candidates(
                    window=window,
                    scope=scope,
                    status=None,
                    limit=self._limit(),
                    cursor=cursor,
                    displayable_only=True,
                )
                for row in page.get("items", []) if isinstance(page, dict) else []:
                    if not isinstance(row, dict):
                        continue
                    candidate_id = str(row.get("candidate_id") or "")
                    if not candidate_id or candidate_id in seen:
                        continue
                    seen.add(candidate_id)
                    rows.append(row)
                cursor = page.get("next_cursor") if isinstance(page, dict) else None
                if not cursor:
                    break

        candidates: list[NotificationCandidate] = []
        for row in rows:
            status = str(row.get("pulse_status") or "")
            if status not in statuses:
                continue
            factor_snapshot = _dict(row.get("factor_snapshot_json"))
            if not _valid_factor_snapshot(factor_snapshot):
                continue
            gate = _dict(row.get("gate_json"))
            severity = _signal_pulse_severity(row, factor_snapshot=factor_snapshot, gate=gate)
            if severity is None:
                continue
            if severity in {"high", "critical"} and not _has_resolved_pulse_target(row, factor_snapshot):
                continue
            candidate_id = str(row.get("candidate_id") or "")
            occurrence_at_ms = _int(row.get("updated_at_ms") or now_ms)
            cooldown_ms = max(0, int(rule.cooldown_seconds)) * 1000 or SIGNAL_PULSE_COOLDOWN_MS[status]
            bucket = occurrence_at_ms // cooldown_ms
            signature = _pulse_notification_signature(row)
            payload = _pulse_payload(row, notification_signature=signature)
            symbol = _symbol(row.get("symbol"))
            subject = _compact_text(row.get("subject_key") or candidate_id, limit=80)
            title_subject = f"${symbol}" if symbol else subject
            candidates.append(
                NotificationCandidate(
                    dedup_key=f"{SIGNAL_PULSE_RULE_ID}:{candidate_id}:{status}:{bucket}",
                    rule_id=SIGNAL_PULSE_RULE_ID,
                    severity=severity,
                    title=f"{title_subject} {status.replace('_', ' ')}",
                    body=_pulse_body(row),
                    entity_type="pulse_candidate",
                    entity_key=f"pulse_candidate:{candidate_id}",
                    symbol=symbol,
                    source_table="pulse_candidates",
                    source_id=candidate_id,
                    occurrence_at_ms=occurrence_at_ms,
                    payload=payload,
                    channels=rule.channels,
                )
            )
        return candidates

    def _rule(self, rule_id: str) -> NotificationRuleConfig:
        return self.settings.notifications.rules[rule_id]

    def _limit(self) -> int:
        return max(DEFAULT_LIMIT, int(self.settings.notifications.token_flow_limit))


def _score_value(item: dict[str, Any], key: str) -> int:
    score = item.get("score") if isinstance(item.get("score"), dict) else {}
    block = score.get(key) if isinstance(score.get(key), dict) else {}
    return _int(block.get("score"))


def _score_version(block: Any) -> str | None:
    return str(block.get("score_version")) if isinstance(block, dict) and block.get("score_version") else None


def _cooldown_bucket(occurrence_at_ms: int, cooldown_seconds: int) -> int:
    return occurrence_at_ms // (max(1, int(cooldown_seconds)) * 1000)


def _activity_dedup_key(
    rule_id: str,
    *,
    author_handle: str,
    action: str,
    occurrence_at_ms: int,
    cooldown_seconds: int,
) -> str:
    author = author_handle or "unknown"
    normalized_action = action or "activity"
    return f"{rule_id}:account:{author}:{normalized_action}:{_cooldown_bucket(occurrence_at_ms, cooldown_seconds)}"


def _alert_dedup_key(
    rule_id: str,
    *,
    entity_key: str,
    author_handle: str,
    occurrence_at_ms: int,
    cooldown_seconds: int,
) -> str:
    identity = entity_key or "unknown"
    author = author_handle or "unknown"
    return f"{rule_id}:{identity}:author:{author}:{_cooldown_bucket(occurrence_at_ms, cooldown_seconds)}"


def _pulse_notification_signature(row: dict[str, Any]) -> str:
    evidence_ids = _list(row.get("evidence_event_ids_json"))
    source_ids = _list(row.get("source_event_ids_json"))
    payload = {
        "pulse_version": row.get("pulse_version"),
        "candidate_id": row.get("candidate_id"),
        "pulse_status": row.get("pulse_status"),
        "score_band": row.get("score_band"),
        "gate": _dict(row.get("gate_json")),
        "agent_recommendation": _dict(row.get("agent_recommendation_json")),
        "factor_snapshot_fingerprint": _short_hash(_dict(row.get("factor_snapshot_json"))),
        "latest_evidence_event_id_bucket": _event_id_bucket([*evidence_ids, *source_ids]),
        "source_event_fingerprint": _short_hash(_stable_list(source_ids)),
    }
    return _stable_hash(payload)


def _pulse_payload(row: dict[str, Any], *, notification_signature: str) -> dict[str, Any]:
    return {
        "candidate_id": row.get("candidate_id"),
        "pulse_status": row.get("pulse_status"),
        "score_band": row.get("score_band"),
        "social_phase": row.get("social_phase"),
        "narrative_type": row.get("narrative_type"),
        "agent_recommendation": _dict(row.get("agent_recommendation_json")),
        "gate": _dict(row.get("gate_json")),
        "factor_snapshot": _dict(row.get("factor_snapshot_json")),
        "evidence_event_ids": _list(row.get("evidence_event_ids_json")),
        "source_event_ids": _list(row.get("source_event_ids_json")),
        "candidate_score": row.get("candidate_score"),
        "target_type": row.get("target_type"),
        "target_id": row.get("target_id"),
        "symbol": _symbol(row.get("symbol")),
        "notification_signature": notification_signature,
    }


def _pulse_body(row: dict[str, Any]) -> str:
    snapshot = _dict(row.get("factor_snapshot_json"))
    gate = _dict(row.get("gate_json"))
    recommendation = _dict(row.get("agent_recommendation_json"))
    subject = _dict(snapshot.get("subject"))
    symbol = _symbol(row.get("symbol") or subject.get("symbol"))
    display = f"${symbol}" if symbol else str(row.get("subject_key") or row.get("candidate_id") or "Signal Pulse")
    market = _market_fact_line(snapshot)
    social = _social_fact_line(snapshot)
    blocked_reasons = _list(gate.get("blocked_reasons"))
    summary = _compact_text(
        recommendation.get("summary_zh")
        or recommendation.get("summary")
        or recommendation.get("rationale_zh")
        or recommendation.get("rationale"),
        limit=240,
    )
    lines = [
        f"## {display} Signal Pulse",
        "",
        f"- **Status:** {str(row.get('pulse_status') or '').replace('_', ' ')}",
        f"- **Gate:** {_human_reasons(blocked_reasons) if blocked_reasons else 'clear'}",
        f"- **Market:** {market}",
        f"- **Social:** {social}",
    ]
    if summary:
        lines.extend(["", summary])
    return "\n".join(lines)


def _signal_pulse_severity(
    row: dict[str, Any],
    *,
    factor_snapshot: dict[str, Any],
    gate: dict[str, Any],
) -> str | None:
    status = str(row.get("pulse_status") or "")
    eligible_for_high_alert = bool(_nested(factor_snapshot, "hard_gates", "eligible_for_high_alert")) and bool(
        gate.get("eligible_for_high_alert")
    )
    blocked_reasons = _list(gate.get("blocked_reasons")) or _list(
        _nested(factor_snapshot, "hard_gates", "blocked_reasons")
    )
    max_recommendation = str(gate.get("max_recommendation") or "").strip()
    gate_allows_high = eligible_for_high_alert and not blocked_reasons and max_recommendation in {
        "watch",
        "trade_candidate",
        "alert",
        "high_alert",
    }
    if status == "token_watch":
        return "high" if gate_allows_high else None
    if status == "trade_candidate":
        return "critical" if gate_allows_high and max_recommendation == "trade_candidate" else None
    return SIGNAL_PULSE_SEVERITY.get(status)


def _has_resolved_pulse_target(row: dict[str, Any], factor_snapshot: dict[str, Any]) -> bool:
    subject = _dict(factor_snapshot.get("subject"))
    target_type = str(row.get("target_type") or subject.get("target_type") or "").strip()
    target_id = str(row.get("target_id") or subject.get("target_id") or "").strip()
    return bool(target_type and target_id and target_type not in {"source_seed", "SourceSeed", "unresolved"})


def _market_fact_line(snapshot: dict[str, Any]) -> str:
    facts = _family_facts(snapshot, "market_quality")
    parts = [
        f"mcap {_money(facts.get('market_cap_usd'))}",
        f"liq {_money(facts.get('liquidity_usd'))}",
        f"holders {_int(facts.get('holders'))}",
    ]
    volume = facts.get("volume_24h_usd")
    if volume is not None:
        parts.append(f"vol24h {_money(volume)}")
    status = str(facts.get("market_status") or "").strip()
    if status:
        parts.append(status)
    return " · ".join(parts)


def _social_fact_line(snapshot: dict[str, Any]) -> str:
    attention = _family_facts(snapshot, "social_attention")
    quality = _family_facts(snapshot, "social_quality")
    mentions = _int(attention.get("mentions_1h"))
    authors = _int(quality.get("independent_authors") or attention.get("unique_authors"))
    watched = _int(attention.get("watched_mentions"))
    return f"{mentions} mentions · {authors} authors · watched {watched}"


def _family_facts(snapshot: dict[str, Any], family: str) -> dict[str, Any]:
    families = _dict(snapshot.get("families"))
    payload = _dict(families.get(family))
    return _dict(payload.get("facts"))


def _valid_factor_snapshot(value: Any) -> bool:
    snapshot = _dict(value)
    return (
        bool(snapshot)
        and snapshot.get("schema_version") == TOKEN_FACTOR_SNAPSHOT_VERSION
        and isinstance(snapshot.get("subject"), dict)
        and isinstance(snapshot.get("families"), dict)
        and isinstance(snapshot.get("hard_gates"), dict)
        and isinstance(snapshot.get("composite"), dict)
    )


def _human_reasons(reasons: list[Any]) -> str:
    values = [str(reason).strip().replace("_", " ") for reason in reasons if str(reason).strip()]
    return ", ".join(values) if values else "clear"


def _money(value: Any) -> str:
    amount = float(_int(value))
    if amount >= 1_000_000_000:
        return f"${amount / 1_000_000_000:.1f}b"
    if amount >= 1_000_000:
        return f"${amount / 1_000_000:.1f}m"
    if amount >= 1_000:
        return f"${amount / 1_000:.1f}k"
    return f"${amount:.0f}"


def _nested(data: dict[str, Any], outer: str, inner: str) -> Any:
    value = data.get(outer)
    return value.get(inner) if isinstance(value, dict) else None


def _event_id_bucket(values: list[Any]) -> str:
    stable = _stable_list(values)
    if not stable:
        return ""
    return _short_hash(stable[-1])


def _stable_list(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _short_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


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
