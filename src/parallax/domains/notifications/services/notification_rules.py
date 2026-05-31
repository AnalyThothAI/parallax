from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

from parallax.domains.pulse_lab.interfaces import contains_trading_execution_instruction
from parallax.domains.token_intel.interfaces import is_token_factor_snapshot
from parallax.platform.config.settings import NotificationRuleConfig, Settings

from ..types import NotificationCandidate

WATCHED_ACTIVITY_WINDOW_MS = 60 * 60_000
DEFAULT_LIMIT = 50
MAX_SIGNAL_PULSE_NOTIFICATION_PAGES = 5
NEWS_HIGH_SIGNAL_QUERY_MIN_LIMIT = 500
NEWS_HIGH_SIGNAL_QUERY_MULTIPLIER = 20
NEWS_HIGH_SIGNAL_RECENCY_WINDOW_MS = 2 * 60 * 60_000
SIGNAL_PULSE_RULE_ID = "signal_pulse_candidate"
NEWS_HIGH_SIGNAL_RULE_ID = "news_high_signal"
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
        pulse: Any = None,
        news: Any = None,
    ) -> None:
        self.settings = settings
        self.evidence = evidence
        self.account_alerts = account_alerts
        self.pulse = pulse
        self.news = news

    def evaluate(self, *, now_ms: int | None = None) -> list[NotificationCandidate]:
        now = int(now_ms if now_ms is not None else _now_ms())
        if not self.settings.notifications.enabled:
            return []
        candidates: list[NotificationCandidate] = []
        candidates.extend(self._watched_account_activity(now_ms=now))
        candidates.extend(self._watched_account_token_alerts(now_ms=now))
        candidates.extend(self._signal_pulse_candidates(now_ms=now))
        candidates.extend(self._news_high_signal_candidates(now_ms=now))
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

    def _news_high_signal_candidates(self, *, now_ms: int) -> list[NotificationCandidate]:
        rule = self._rule(NEWS_HIGH_SIGNAL_RULE_ID)
        if not rule.enabled or self.news is None:
            return []
        min_score = int(rule.combined_score_min if rule.combined_score_min is not None else 85)
        external_min_score = int(rule.external_score_min if rule.external_score_min is not None else 85)
        rows = self.news.list_news_high_signal_notification_candidates(
            min_score=min_score,
            limit=self._news_high_signal_query_limit(),
        )
        candidates: list[NotificationCandidate] = []
        seen_semantic_signatures: set[str] = set()
        seen_external_push_signatures: set[str] = set()
        for row in rows:
            news_item_id = str(row.get("news_item_id") or "")
            if not news_item_id:
                continue
            source_latest_at_ms = _int(row.get("latest_at_ms"))
            if source_latest_at_ms and source_latest_at_ms < now_ms - NEWS_HIGH_SIGNAL_RECENCY_WINDOW_MS:
                continue
            signal = _dict(row.get("signal"))
            eligibility = _dict(signal.get("alert_eligibility"))
            provider_score = _int(eligibility.get("provider_score") or signal.get("score"))
            agent_brief = _dict(row.get("agent_brief"))
            ready_agent_brief = _ready_news_agent_brief(agent_brief)
            external_push_ready, readiness_suppression_reason = _news_external_push_readiness(
                eligibility=eligibility,
                ready_agent_brief=ready_agent_brief,
            )
            decision_class = str(eligibility.get("decision_class") or ready_agent_brief.get("decision_class") or "")
            occurrence_at_ms = _int(row.get("latest_at_ms") or row.get("agent_brief_computed_at_ms") or now_ms)
            semantic_signature = _news_semantic_signature(row, agent_brief=ready_agent_brief)
            if semantic_signature in seen_semantic_signatures:
                continue
            seen_semantic_signatures.add(semantic_signature)
            external_push_signature = None
            external_push_eligible = False
            suppression_reason = None
            if provider_score < external_min_score or not _has_external_channels(rule.channels):
                suppression_reason = "external_threshold_or_channel"
            elif not external_push_ready:
                suppression_reason = readiness_suppression_reason
            else:
                external_push_signature = _news_external_push_signature(
                    row,
                    provider_score=provider_score,
                    occurrence_at_ms=occurrence_at_ms,
                    cooldown_seconds=rule.cooldown_seconds,
                )
                external_push_eligible = True
                if external_push_signature in seen_external_push_signatures:
                    external_push_eligible = False
                    suppression_reason = "external_signature_duplicate"
            if external_push_eligible and external_push_signature:
                seen_external_push_signatures.add(external_push_signature)
            channels = rule.channels if external_push_eligible else tuple(c for c in rule.channels if c == "in_app")
            source_id = news_item_id
            summary = _news_agent_summary(ready_agent_brief)
            title = _news_display_title(row, agent_brief=ready_agent_brief)
            body = _news_body(row, provider_score=provider_score, summary=summary)
            candidates.append(
                NotificationCandidate(
                    dedup_key=f"{NEWS_HIGH_SIGNAL_RULE_ID}:{semantic_signature}",
                    rule_id=NEWS_HIGH_SIGNAL_RULE_ID,
                    severity="high" if provider_score < external_min_score else "critical",
                    title=title,
                    body=body,
                    entity_type="news_item",
                    entity_key=f"news_item:{news_item_id}",
                    symbol=_news_primary_symbol(row),
                    source_table="news_page_rows",
                    source_id=source_id,
                    occurrence_at_ms=occurrence_at_ms,
                    payload={
                        "news_item_id": news_item_id,
                        "provider_score": provider_score,
                        "decision_class": decision_class,
                        "direction": agent_brief.get("direction") or signal.get("direction"),
                        "semantic_signature": semantic_signature,
                        "display_title": title,
                        "external_push_signature": external_push_signature,
                        "external_push_eligible": external_push_eligible,
                        "external_push_suppression_reason": suppression_reason,
                        "agent_brief": agent_brief,
                        "canonical_url": row.get("canonical_url"),
                        "source_domain": row.get("source_domain"),
                        "duplicate_count": _int(row.get("duplicate_count")),
                        "token_impacts": _safe_signature_list(row.get("token_impacts")),
                    },
                    channels=channels,
                )
            )
        return candidates

    def _rule(self, rule_id: str) -> NotificationRuleConfig:
        return self.settings.notifications.rules[rule_id]

    def _limit(self) -> int:
        return max(DEFAULT_LIMIT, int(self.settings.notifications.candidate_limit))

    def _news_high_signal_query_limit(self) -> int:
        return max(
            NEWS_HIGH_SIGNAL_QUERY_MIN_LIMIT,
            self._limit() * NEWS_HIGH_SIGNAL_QUERY_MULTIPLIER,
        )


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


def _pulse_stable_decision_signature(row: dict[str, Any]) -> str:
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
    return _pulse_stable_decision_signature(row)


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
        "in_app_signature": in_app_signature,
        "external_push_signature": external_push_signature,
        "external_push_eligible": external_push_eligible,
        "external_push_suppression_reason": external_push_suppression_reason,
    }


def _pulse_body(row: dict[str, Any]) -> str:
    from parallax.domains.notifications.services.pulse_surface_card import render_pulse_surface_card

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


def _has_external_channels(channels: tuple[str, ...]) -> bool:
    return any(channel != "in_app" for channel in channels)


def _news_agent_summary(agent_brief: dict[str, Any]) -> str:
    brief_json = _dict(agent_brief.get("brief_json"))
    return _compact_text(
        agent_brief.get("summary_zh")
        or brief_json.get("summary_zh")
        or agent_brief.get("market_read_zh")
        or brief_json.get("market_read_zh")
        or "",
        limit=360,
    )


def _ready_news_agent_brief(agent_brief: dict[str, Any]) -> dict[str, Any]:
    if str(agent_brief.get("status") or "") != "ready":
        return {}
    return agent_brief


def _news_external_push_readiness(
    *,
    eligibility: dict[str, Any],
    ready_agent_brief: dict[str, Any],
) -> tuple[bool, str | None]:
    if eligibility.get("external_push_ready") is not True:
        return False, str(eligibility.get("external_push_block_reason") or "external_push_state_missing")
    if not ready_agent_brief:
        return False, "agent_brief_not_ready"
    if not _news_agent_summary(ready_agent_brief):
        return False, "agent_brief_missing_summary"
    return True, None


def _news_display_title(row: dict[str, Any], *, agent_brief: dict[str, Any]) -> str:
    brief_json = _dict(agent_brief.get("brief_json"))
    signal = _dict(row.get("signal"))
    return _compact_text(
        agent_brief.get("title_zh")
        or brief_json.get("title_zh")
        or signal.get("title_zh")
        or row.get("headline")
        or "News high signal",
        limit=96,
    )


def _news_semantic_signature(row: dict[str, Any], *, agent_brief: dict[str, Any]) -> str:
    brief_json = _dict(agent_brief.get("brief_json"))
    signal = _dict(row.get("signal"))
    eligibility = _dict(signal.get("alert_eligibility"))
    return _stable_hash(
        {
            "asset_bucket": _news_external_asset_bucket(row),
            "decision_class": agent_brief.get("decision_class") or eligibility.get("decision_class"),
            "direction": agent_brief.get("direction") or signal.get("direction"),
            "content_class": row.get("content_class"),
            "content_tags": _safe_signature_list(row.get("content_tags") or row.get("content_tags_json")),
            "affected_assets": _news_affected_asset_symbols(brief_json.get("affected_assets")),
        }
    )


def _news_external_push_signature(
    row: dict[str, Any],
    *,
    provider_score: int,
    occurrence_at_ms: int,
    cooldown_seconds: int,
) -> str:
    signal = _dict(row.get("signal"))
    agent_brief = _ready_news_agent_brief(_dict(row.get("agent_brief")))
    return _stable_hash(
        {
            "asset_bucket": _news_external_asset_bucket(row),
            "direction": agent_brief.get("direction") or signal.get("direction"),
            "provider_score_band": provider_score // 5,
            "cooldown_bucket": _cooldown_bucket(occurrence_at_ms, cooldown_seconds),
        }
    )


def _news_external_asset_bucket(row: dict[str, Any]) -> str:
    symbols: list[str] = []
    brief_json = _dict(_dict(row.get("agent_brief")).get("brief_json"))
    for symbol in _news_affected_asset_symbols(brief_json.get("affected_assets")):
        normalized = _news_external_asset_symbol(symbol)
        if normalized and normalized not in symbols:
            symbols.append(normalized)
    for impact in _list(row.get("token_impacts")):
        if not isinstance(impact, dict):
            continue
        score = _int(impact.get("score") or impact.get("provider_score"))
        if score and score < 70:
            continue
        normalized = _news_external_asset_symbol(impact.get("symbol") or impact.get("target_symbol"))
        if normalized and normalized not in symbols:
            symbols.append(normalized)
    if not symbols:
        primary = _news_external_asset_symbol(_news_primary_symbol(row))
        if primary:
            symbols.append(primary)
    if "CL" in symbols:
        return "CL"
    if symbols:
        return "|".join(symbols[:3])
    return str(row.get("news_item_id") or "unknown")


def _news_external_asset_symbol(value: Any) -> str | None:
    symbol = _symbol(value)
    if not symbol:
        return None
    if symbol.startswith("XYZ-"):
        symbol = symbol[4:]
    return symbol or None


def _news_primary_symbol(row: dict[str, Any]) -> str | None:
    for impact in _list(row.get("token_impacts")):
        if isinstance(impact, dict):
            symbol = _symbol(impact.get("symbol") or impact.get("target_symbol"))
            if symbol:
                return symbol
    brief_json = _dict(_dict(row.get("agent_brief")).get("brief_json"))
    symbols = _news_affected_asset_symbols(brief_json.get("affected_assets"))
    return symbols[0] if symbols else None


def _news_affected_asset_symbols(value: Any) -> list[str]:
    symbols: list[str] = []
    for item in _list(value):
        if isinstance(item, dict):
            symbol = _symbol(item.get("symbol") or item.get("asset"))
            if symbol and symbol not in symbols:
                symbols.append(symbol)
    return symbols[:12]


def _news_body(row: dict[str, Any], *, provider_score: int, summary: str) -> str:
    lines = [
        f"Score: {provider_score}",
        f"Source: {_compact_text(row.get('source_domain') or 'unknown', limit=80)}",
    ]
    if summary:
        lines.append(summary)
    url = str(row.get("canonical_url") or "").strip()
    if url:
        lines.append(url)
    return "\n".join(lines)


def _now_ms() -> int:
    return int(time.time() * 1000)
