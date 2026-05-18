from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from gmgn_twitter_intel.domains.pulse_lab.interfaces import contains_trading_execution_instruction
from gmgn_twitter_intel.domains.token_intel.interfaces import is_token_factor_snapshot
from gmgn_twitter_intel.platform.config.settings import NotificationRuleConfig, Settings

from ..types import NotificationCandidate

WATCHED_ACTIVITY_WINDOW_MS = 60 * 60_000
DEFAULT_LIMIT = 50
MAX_SIGNAL_PULSE_NOTIFICATION_PAGES = 5
SIGNAL_PULSE_RULE_ID = "signal_pulse_candidate"
DEFAULT_SIGNAL_PULSE_WINDOW = "1h"
DEFAULT_SIGNAL_PULSE_SCOPES = ("all", "matched")
DEFAULT_SIGNAL_PULSE_STATUSES = ("trade_candidate", "token_watch", "risk_rejected_high_info")
SIGNAL_PULSE_SEVERITY = {
    "trade_candidate": "critical",
    "risk_rejected_high_info": "warning",
}


@dataclass(frozen=True, slots=True)
class _PulseExternalPushPolicy:
    eligible: bool
    external_push_signature: str | None
    suppression_reason: str | None


class NotificationRuleEngine:
    def __init__(
        self,
        *,
        settings: Settings,
        evidence: Any,
        account_alerts: Any,
        asset_flow: Any,
        pulse: Any = None,
    ) -> None:
        self.settings = settings
        self.evidence = evidence
        self.account_alerts = account_alerts
        self.asset_flow = asset_flow
        self.pulse = pulse

    def evaluate(self, *, now_ms: int | None = None) -> list[NotificationCandidate]:
        now = int(now_ms if now_ms is not None else _now_ms())
        if not self.settings.notifications.enabled:
            return []
        candidates: list[NotificationCandidate] = []
        candidates.extend(self._watched_account_activity(now_ms=now))
        candidates.extend(self._watched_account_token_alerts(now_ms=now))
        hot_entity_keys: set[str] = set()
        hot_candidates = self._hot_quality_tokens(now_ms=now)
        hot_entity_keys.update(key for item in hot_candidates if (key := item.entity_key))
        candidates.extend(hot_candidates)
        candidates.extend(self._quality_tokens(now_ms=now, skip_entity_keys=hot_entity_keys))
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
        items: list[dict[str, Any]] = []
        if isinstance(data, dict):
            items.extend(data.get("targets") or [])
            items.extend(data.get("attention") or [])
        candidates: list[NotificationCandidate] = []
        for item in items:
            factor_snapshot = _asset_flow_factor_snapshot(item)
            if factor_snapshot is None:
                continue
            decision = _asset_flow_decision(factor_snapshot)
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
            target = _dict(item.get("target"))
            attention = _dict(item.get("attention"))
            data_health = _dict(factor_snapshot.get("data_health"))
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
                "score_version": str(factor_snapshot.get("schema_version") or ""),
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

    def _signal_pulse_candidates(self, *, now_ms: int) -> list[NotificationCandidate]:
        rule = self._rule(SIGNAL_PULSE_RULE_ID)
        if not rule.enabled or self.pulse is None:
            return []
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        window = rule.window or DEFAULT_SIGNAL_PULSE_WINDOW
        scopes = rule.scopes or DEFAULT_SIGNAL_PULSE_SCOPES
        statuses = set(rule.statuses or DEFAULT_SIGNAL_PULSE_STATUSES) & set(DEFAULT_SIGNAL_PULSE_STATUSES)
        for scope in scopes:
            for status in sorted(statuses):
                cursor = None
                for _ in range(MAX_SIGNAL_PULSE_NOTIFICATION_PAGES):
                    page = self.pulse.list_candidates(
                        window=window,
                        scope=scope,
                        status=status,
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
        seen_external_push_signatures: set[str] = set()
        for row in rows:
            status = str(row.get("pulse_status") or "")
            if status not in statuses:
                continue
            factor_snapshot = _dict(row.get("factor_snapshot_json"))
            if not _valid_factor_snapshot(factor_snapshot):
                continue
            severity = _signal_pulse_severity(row, factor_snapshot=factor_snapshot)
            if severity is None:
                continue
            if severity in {"high", "critical"} and not _has_resolved_pulse_target(row, factor_snapshot):
                continue
            candidate_id = str(row.get("candidate_id") or "")
            occurrence_at_ms = _int(row.get("updated_at_ms") or now_ms)
            in_app_signature = _pulse_in_app_signature(row)
            push_policy = _pulse_external_push_policy(
                row,
                severity=severity,
                factor_snapshot=factor_snapshot,
                occurrence_at_ms=occurrence_at_ms,
                cooldown_seconds=rule.cooldown_seconds,
            )
            if push_policy.eligible and push_policy.external_push_signature in seen_external_push_signatures:
                push_policy = _PulseExternalPushPolicy(
                    eligible=False,
                    external_push_signature=push_policy.external_push_signature,
                    suppression_reason="external_signature_duplicate",
                )
            if push_policy.eligible and push_policy.external_push_signature:
                seen_external_push_signatures.add(push_policy.external_push_signature)
            external_identity = push_policy.external_push_signature or "in_app"
            payload = _pulse_payload(
                row,
                notification_signature=in_app_signature,
                in_app_signature=in_app_signature,
                external_push_signature=push_policy.external_push_signature,
                external_push_eligible=push_policy.eligible,
                external_push_suppression_reason=push_policy.suppression_reason,
            )
            channels = (
                rule.channels
                if push_policy.eligible
                else tuple(channel for channel in rule.channels if channel == "in_app")
            )
            symbol = _symbol(row.get("symbol"))
            subject = _compact_text(row.get("subject_key") or candidate_id, limit=80)
            title_subject = f"${symbol}" if symbol else subject
            candidates.append(
                NotificationCandidate(
                    dedup_key=f"{SIGNAL_PULSE_RULE_ID}:{in_app_signature}:{external_identity}",
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
                    channels=channels,
                )
            )
        return candidates

    def _rule(self, rule_id: str) -> NotificationRuleConfig:
        return self.settings.notifications.rules[rule_id]

    def _limit(self) -> int:
        return max(DEFAULT_LIMIT, int(self.settings.notifications.token_flow_limit))


def _score_value(item: dict[str, Any], key: str) -> int:
    factor_snapshot = _asset_flow_factor_snapshot(item)
    if factor_snapshot is None:
        return 0
    if key == "heat":
        return _int(_dict(_dict(factor_snapshot.get("families")).get("social_heat")).get("score"))
    if key == "quality":
        return _int(_dict(_dict(factor_snapshot.get("families")).get("semantic_catalyst")).get("score"))
    if key == "opportunity":
        return _int(_dict(factor_snapshot.get("composite")).get("rank_score"))
    return 0


def _asset_flow_factor_snapshot(item: dict[str, Any]) -> dict[str, Any] | None:
    value = item.get("factor_snapshot")
    if not is_token_factor_snapshot(value):
        return None
    return _dict(value)


def _asset_flow_decision(factor_snapshot: dict[str, Any]) -> str:
    value = str(_dict(factor_snapshot.get("composite")).get("recommended_decision") or "").strip().lower()
    if value in {"driver", "high_alert", "alert", "trade_candidate"}:
        return "driver"
    if value in {"watch", "token_watch"}:
        return "watch"
    if value in {"discard", "ignore"}:
        return "discard"
    return "investigate"


def _score_version(block: Any) -> str | None:
    return str(block.get("score_version")) if isinstance(block, dict) and block.get("score_version") else None


def _cooldown_bucket(occurrence_at_ms: int, cooldown_seconds: int) -> int:
    return occurrence_at_ms // (max(1, int(cooldown_seconds)) * 1000)


def _activity_dedup_key(
    rule_id: str,
    *,
    author_handle: str | None,
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
    author_handle: str | None,
    occurrence_at_ms: int,
    cooldown_seconds: int,
) -> str:
    identity = entity_key or "unknown"
    author = author_handle or "unknown"
    return f"{rule_id}:{identity}:author:{author}:{_cooldown_bucket(occurrence_at_ms, cooldown_seconds)}"


def _pulse_notification_signature(row: dict[str, Any]) -> str:
    """Hash only stable decision dimensions to avoid:
    - free-text micro-changes (thesis_zh / narrative_thesis_zh / summary_zh) triggering duplicate notifications
    - bull/bear strength changes failing to trigger refresh

    Drops: edge_events, evidence/source event ids, factor_snapshot fingerprint, free text.
    """
    decision = _pulse_decision(row)
    factor_snapshot = _dict(row.get("factor_snapshot_json"))
    bull_view = decision.get("bull_view") or {}
    bear_view = decision.get("bear_view") or {}
    playbook = decision.get("playbook") or {}
    payload = {
        "pulse_version": row.get("pulse_version"),
        "candidate_id": row.get("candidate_id"),
        "pulse_status": row.get("pulse_status"),
        "score_band": row.get("score_band"),
        "decision_route": decision.get("route"),
        "decision_recommendation": decision.get("recommendation"),
        "bull_strength": bull_view.get("strength") if isinstance(bull_view, dict) else None,
        "bear_strength": bear_view.get("strength") if isinstance(bear_view, dict) else None,
        "narrative_archetype": decision.get("narrative_archetype") or "",
        "playbook_has_playbook": bool(playbook.get("has_playbook")) if isinstance(playbook, dict) else False,
        "playbook_monitoring_horizon": playbook.get("monitoring_horizon") if isinstance(playbook, dict) else None,
        "playbook_watch_signal_count": len(_safe_signature_list(playbook.get("watch_signals")))
        if isinstance(playbook, dict)
        else 0,
        "playbook_exit_trigger_count": len(_safe_signature_list(playbook.get("exit_triggers")))
        if isinstance(playbook, dict)
        else 0,
        "gates": _dict(factor_snapshot.get("gates")),
    }
    return _stable_hash(payload)


def _pulse_in_app_signature(row: dict[str, Any]) -> str:
    return _pulse_notification_signature(row)


def _pulse_external_push_signature(
    row: dict[str, Any],
    *,
    cooldown_seconds: int,
    occurrence_at_ms: int,
    alert_class: str,
    status_level: int,
    recommendation_level: int,
    target_type: str,
    target_id: str,
) -> str:
    payload = {
        "target_type": target_type,
        "target_id": target_id,
        "alert_class": alert_class,
        "status_level": status_level,
        "recommendation_level": recommendation_level,
        "cooldown_bucket": _cooldown_bucket(occurrence_at_ms, cooldown_seconds),
        "pulse_version": row.get("pulse_version"),
        "gate_version": row.get("gate_version"),
    }
    return _stable_hash(payload)


def _pulse_external_push_policy(
    row: dict[str, Any],
    *,
    severity: str,
    factor_snapshot: dict[str, Any],
    occurrence_at_ms: int,
    cooldown_seconds: int,
) -> _PulseExternalPushPolicy:
    status = str(row.get("pulse_status") or "")
    if status == "risk_rejected_high_info":
        return _PulseExternalPushPolicy(False, None, "risk_rejected_in_app_only")
    if severity not in {"high", "critical"}:
        return _PulseExternalPushPolicy(False, None, "severity_below_high")
    target_type, target_id = _pulse_resolved_target(row, factor_snapshot)
    if not _is_resolved_target(target_type=target_type, target_id=target_id):
        return _PulseExternalPushPolicy(False, None, "unresolved_target")
    edge_events = set(_string_list(row.get("last_edge_events_json")))
    if not edge_events & {"pulse_status_changed", "recommended_decision_changed"}:
        return _PulseExternalPushPolicy(False, None, "not_escalation")
    signature = _pulse_external_push_signature(
        row,
        cooldown_seconds=cooldown_seconds,
        occurrence_at_ms=occurrence_at_ms,
        alert_class=status,
        status_level=_pulse_status_escalation_level(status),
        recommendation_level=_pulse_recommendation_escalation_level(_pulse_decision(row).get("recommendation")),
        target_type=target_type,
        target_id=target_id,
    )
    return _PulseExternalPushPolicy(True, signature, None)


def _pulse_status_escalation_level(status: str) -> int:
    return {"risk_rejected_high_info": 0, "token_watch": 1, "trade_candidate": 2}.get(status, 0)


def _pulse_recommendation_escalation_level(value: Any) -> int:
    recommendation = str(value or "")
    return {"ignore": 0, "abstain": 0, "watchlist": 1, "trade_candidate": 2, "high_conviction": 3}.get(
        recommendation,
        0,
    )


def _pulse_payload(
    row: dict[str, Any],
    *,
    notification_signature: str,
    in_app_signature: str,
    external_push_signature: str | None,
    external_push_eligible: bool,
    external_push_suppression_reason: str | None,
) -> dict[str, Any]:
    factor_snapshot = _dict(row.get("factor_snapshot_json"))
    return {
        "candidate_id": row.get("candidate_id"),
        "pulse_status": row.get("pulse_status"),
        "score_band": row.get("score_band"),
        "social_phase": row.get("social_phase"),
        "decision": _pulse_decision(row),
        "gate": _dict(factor_snapshot.get("gates")),
        "factor_snapshot": factor_snapshot,
        "evidence_event_ids": _list(row.get("evidence_event_ids_json")),
        "source_event_ids": _list(row.get("source_event_ids_json")),
        "edge_events": _list(row.get("last_edge_events_json")),
        "candidate_score": row.get("candidate_score"),
        "target_type": row.get("target_type"),
        "target_id": row.get("target_id"),
        "symbol": _symbol(row.get("symbol")),
        "notification_signature": notification_signature,
        "in_app_signature": in_app_signature,
        "external_push_signature": external_push_signature,
        "external_push_eligible": external_push_eligible,
        "external_push_suppression_reason": external_push_suppression_reason,
    }


def _pulse_body(row: dict[str, Any]) -> str:
    from gmgn_twitter_intel.domains.notifications.services.pulse_surface_card import render_pulse_surface_card

    decision = _pulse_decision(row)
    snapshot = _dict(row.get("factor_snapshot_json"))
    return render_pulse_surface_card(
        row=row,
        decision=decision,
        factor_snapshot=snapshot,
        asset_profile=None,  # phase 1 skips asset_profile lookup; surface card uses row-borne fields
    )


def _signal_pulse_severity(
    row: dict[str, Any],
    *,
    factor_snapshot: dict[str, Any],
) -> str | None:
    status = str(row.get("pulse_status") or "")
    gates = _dict(factor_snapshot.get("gates"))
    eligible_for_high_alert = bool(gates.get("eligible_for_high_alert"))
    blocked_reasons = _list(gates.get("blocked_reasons"))
    max_decision = str(gates.get("max_decision") or "").strip()
    gate_allows_high = (
        eligible_for_high_alert
        and not blocked_reasons
        and max_decision
        in {
            "watch",
            "trade_candidate",
            "alert",
            "high_alert",
        }
    )
    if status == "token_watch":
        return "high" if gate_allows_high else None
    if status == "trade_candidate":
        return "critical" if gate_allows_high else None
    return SIGNAL_PULSE_SEVERITY.get(status)


def _has_resolved_pulse_target(row: dict[str, Any], factor_snapshot: dict[str, Any]) -> bool:
    target_type, target_id = _pulse_resolved_target(row, factor_snapshot)
    return _is_resolved_target(target_type=target_type, target_id=target_id)


def _pulse_resolved_target(row: dict[str, Any], factor_snapshot: dict[str, Any]) -> tuple[str, str]:
    subject = _dict(factor_snapshot.get("subject"))
    target_type = str(row.get("target_type") or subject.get("target_type") or "").strip()
    target_id = str(row.get("target_id") or subject.get("target_id") or "").strip()
    return target_type, target_id


def _is_resolved_target(*, target_type: str, target_id: str) -> bool:
    return bool(target_type and target_id and target_type.lower() != "unresolved")


def _valid_factor_snapshot(value: Any) -> bool:
    return is_token_factor_snapshot(value)


def _pulse_decision(row: dict[str, Any]) -> dict[str, Any]:
    decision = _dict(row.get("decision_json"))
    return {
        # v1 retained fields
        "route": row.get("decision_route") or decision.get("route"),
        "recommendation": row.get("decision_recommendation") or decision.get("recommendation"),
        "confidence": row.get("decision_confidence"),
        "abstain_reason": row.get("decision_abstain_reason") or decision.get("abstain_reason"),
        "stage_count": int(row.get("decision_stage_count") or 0),
        "summary_zh": decision.get("summary_zh") or "",
        "invalidation_conditions": _string_list(decision.get("invalidation_conditions")),
        "residual_risks": _string_list(decision.get("residual_risks")),
        "evidence_event_ids": _string_list(decision.get("evidence_event_ids")),
        # v2 new fields (consumed by SurfaceCard renderer + signature)
        "narrative_archetype": decision.get("narrative_archetype") or "",
        "narrative_thesis_zh": decision.get("narrative_thesis_zh") or "",
        "bull_view": _bull_bear_view(decision.get("bull_view")),
        "bear_view": _bull_bear_view(decision.get("bear_view")),
        "playbook": _playbook(decision.get("playbook")),
        "evidence_event_urls": _string_string_map(decision.get("evidence_event_urls")),
    }


def _bull_bear_view(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    strength = value.get("strength")
    if strength not in ("absent", "weak", "moderate", "strong"):
        return None
    return {
        "strength": strength,
        "thesis_zh": str(value.get("thesis_zh") or ""),
        "supporting_event_ids": _string_list(value.get("supporting_event_ids")),
    }


def _playbook(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    horizon = value.get("monitoring_horizon")
    if horizon not in ("1h", "4h", "24h"):
        return None
    return {
        "has_playbook": bool(value.get("has_playbook")),
        "watch_signals": _string_list(value.get("watch_signals")),
        "exit_triggers": _string_list(value.get("exit_triggers")),
        "monitoring_horizon": horizon,
    }


def _string_string_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(k): str(v) for k, v in value.items() if isinstance(k, str) and isinstance(v, str)}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _safe_signature_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    safe: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text or contains_trading_execution_instruction(text):
            continue
        safe.append(text)
    return safe


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


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
