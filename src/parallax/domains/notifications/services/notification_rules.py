from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from parallax.domains.pulse_lab.interfaces import contains_trading_execution_instruction
from parallax.domains.token_intel.interfaces import is_token_factor_snapshot
from parallax.platform.config.settings import NotificationRuleConfig, Settings

from ..types import NotificationCandidate

SIGNAL_PULSE_RULE_ID = "signal_pulse_candidate"
NEWS_HIGH_SIGNAL_RULE_ID = "news_high_signal"
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

    def evaluate(self, *, now_ms: int) -> list[NotificationCandidate]:
        now = int(now_ms)
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
        since_ms = now_ms - int(self.settings.notifications.watched_activity_window_ms)
        events = self.evidence.recent_events(
            limit=self._limit(),
            since_ms=since_ms,
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
            now_ms=now_ms,
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
        if rule.window is None or rule.scopes is None or rule.statuses is None:
            raise RuntimeError("signal_pulse_notification_rule_config_required")
        window = rule.window
        scopes = rule.scopes
        statuses = set(rule.statuses)
        for row in self.pulse.list_signal_pulse_notification_candidates(
            window=window,
            scopes=scopes,
            statuses=tuple(sorted(statuses)),
            per_scope_status_limit=self._signal_pulse_per_scope_status_limit(),
        ):
            if not isinstance(row, dict):
                continue
            candidate_id = str(row.get("candidate_id") or "")
            if not candidate_id or candidate_id in seen:
                continue
            seen.add(candidate_id)
            rows.append(row)

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
            semantic_signature = _pulse_semantic_signature(row)
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
                semantic_signature=semantic_signature,
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
                    dedup_key=f"{SIGNAL_PULSE_RULE_ID}:{semantic_signature}:{external_identity}",
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
        rows = self.news.list_news_high_signal_notification_candidates(
            limit=self._news_high_signal_query_limit(),
        )
        candidates: list[NotificationCandidate] = []
        seen_semantic_signatures: set[str] = set()
        seen_external_push_signatures: set[str] = set()
        for row in rows:
            news_item_id = _required_news_text(row, "news_item_id")
            representative_news_item_id = _required_news_text(row, "representative_news_item_id")
            story_key = _required_news_text(row, "story_key")
            source_domain = _required_news_text(row, "source_domain")
            agent_admission_status = _required_news_text(row, "agent_admission_status")
            agent_admission_reason = _required_news_text(row, "agent_admission_reason")
            source_latest_at_ms = _required_news_positive_int(row, "latest_at_ms")
            if source_latest_at_ms < now_ms - int(self.settings.notifications.news_high_signal_recency_window_ms):
                continue
            signal = _required_news_mapping(row.get("signal"), "signal")
            eligibility = _required_news_mapping(signal.get("alert_eligibility"), "alert_eligibility")
            _required_news_signal_true(eligibility, "in_app_eligible", section="alert_eligibility")
            agent_brief = _required_news_mapping(row.get("agent_brief"), "agent_brief")
            story = _news_story_payload(row.get("story"))
            market_scope = _news_market_scope_payload(row.get("market_scope"))
            agent_admission = _news_agent_admission_payload(row.get("agent_admission"))
            token_impacts = _required_news_list(row.get("token_impacts"), "token_impacts")
            ready_agent_brief = _ready_news_agent_brief(agent_brief)
            external_push_ready, readiness_suppression_reason = _news_external_push_readiness(
                eligibility=eligibility,
                ready_agent_brief=ready_agent_brief,
            )
            decision_class, direction = _news_notification_signal_fields(
                row,
                ready_agent_brief=ready_agent_brief,
            )
            affected_entities = _news_public_affected_entities(agent_brief)
            occurrence_at_ms = source_latest_at_ms
            semantic_signature = _news_semantic_signature(row, agent_brief=ready_agent_brief)
            if semantic_signature in seen_semantic_signatures:
                continue
            seen_semantic_signatures.add(semantic_signature)
            external_push_signature = None
            external_push_eligible = False
            suppression_reason = None
            if not _has_external_channels(rule.channels):
                suppression_reason = "external_channel_unavailable"
            elif not external_push_ready:
                suppression_reason = readiness_suppression_reason
            else:
                external_push_signature = _news_external_push_signature(
                    row,
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
            source_id = _required_news_text(row, "row_id")
            summary = _news_agent_summary(ready_agent_brief)
            title = _news_display_title(row, agent_brief=ready_agent_brief)
            body = _news_body(row, summary=summary, source_domain=source_domain)
            candidates.append(
                NotificationCandidate(
                    dedup_key=f"{NEWS_HIGH_SIGNAL_RULE_ID}:{semantic_signature}",
                    rule_id=NEWS_HIGH_SIGNAL_RULE_ID,
                    severity="high",
                    title=title,
                    body=body,
                    entity_type="news_story",
                    entity_key=f"news_story:{story_key}",
                    symbol=_news_primary_symbol(row),
                    source_table="news_page_rows",
                    source_id=source_id,
                    occurrence_at_ms=occurrence_at_ms,
                    payload={
                        "news_item_id": news_item_id,
                        "representative_news_item_id": representative_news_item_id,
                        "story_key": story_key,
                        "story": story,
                        "market_scope": market_scope,
                        "agent_admission_status": agent_admission_status,
                        "agent_admission_reason": agent_admission_reason,
                        "agent_admission": agent_admission,
                        "decision_class": decision_class,
                        "direction": direction,
                        "affected_entities": affected_entities,
                        "semantic_signature": semantic_signature,
                        "display_title": title,
                        "external_push_signature": external_push_signature,
                        "external_push_eligible": external_push_eligible,
                        "external_push_suppression_reason": suppression_reason,
                        "agent_brief": _public_news_agent_brief(agent_brief),
                        "canonical_url": _optional_news_text(row, "canonical_url"),
                        "source_domain": source_domain,
                        "duplicate_count": _required_news_nonnegative_int(row, "duplicate_count"),
                        "token_impacts": _news_token_impacts_payload(token_impacts),
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

    def _signal_pulse_per_scope_status_limit(self) -> int:
        return self._limit() * int(self.settings.notifications.signal_pulse_max_pages)


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


def _pulse_semantic_signature(row: dict[str, Any]) -> str:
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
    semantic_signature: str,
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
        "semantic_signature": semantic_signature,
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
        "route": row.get("decision_route"),
        "recommendation": row.get("decision_recommendation"),
        "confidence": row.get("decision_confidence"),
        "abstain_reason": row.get("decision_abstain_reason"),
        "summary_zh": decision.get("summary_zh") or "",
        "invalidation_conditions": _string_list(decision.get("invalidation_conditions")),
        "residual_risks": _string_list(decision.get("residual_risks")),
        "evidence_event_ids": _string_list(decision.get("evidence_event_ids")),
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


def _news_token_impacts_payload(value: Any) -> list[dict[str, Any]]:
    impacts: list[dict[str, Any]] = []
    for item_value in _required_news_list(value, "token_impacts"):
        item = _required_news_list_mapping(item_value, "token_impacts")
        symbol_text = _news_token_impact_optional_text(item, "symbol")
        if symbol_text is None:
            symbol_text = _news_token_impact_optional_text(item, "target_symbol")
        symbol = _symbol(symbol_text)
        if not symbol:
            continue
        market_type = _news_token_impact_optional_text(item, "market_type")
        payload = {
            "symbol": symbol,
            "market_type": market_type,
        }
        impacts.append({key: value for key, value in payload.items() if value is not None})
    return impacts[:12]


def _news_token_impact_optional_text(item: dict[str, Any], field_name: str) -> str | None:
    if field_name not in item or item.get(field_name) is None:
        return None
    value = item.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"news_high_signal_token_impacts_{field_name}_required")
    return value.strip()


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
    if not agent_brief or "summary_zh" not in agent_brief:
        return ""
    value = agent_brief.get("summary_zh")
    if not isinstance(value, str):
        raise ValueError("news_high_signal_agent_brief_summary_zh_required")
    return _compact_text(value.strip(), limit=360)


def _ready_news_agent_brief(agent_brief: dict[str, Any]) -> dict[str, Any]:
    if _required_news_agent_status(agent_brief) != "ready":
        return {}
    return agent_brief


def _required_news_agent_status(agent_brief: dict[str, Any]) -> str:
    value = agent_brief.get("status")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("news_high_signal_agent_brief_status_required")
    return value.strip()


def _news_external_push_readiness(
    *,
    eligibility: dict[str, Any],
    ready_agent_brief: dict[str, Any],
) -> tuple[bool, str | None]:
    external_push_ready = _optional_news_signal_bool(
        eligibility,
        "external_push_ready",
        section="alert_eligibility",
    )
    block_reason = _optional_news_signal_text(
        eligibility,
        "external_push_block_reason",
        section="alert_eligibility",
    )
    if external_push_ready is not True:
        return False, block_reason or "external_push_state_missing"
    _required_news_external_push_basis(eligibility)
    if not ready_agent_brief:
        return False, "agent_brief_not_ready"
    if not _news_agent_summary(ready_agent_brief):
        return False, "agent_brief_missing_summary"
    if not _news_agent_required_text(ready_agent_brief, "direction"):
        return False, "agent_brief_missing_direction"
    if not _news_agent_required_text(ready_agent_brief, "decision_class"):
        return False, "agent_brief_missing_decision_class"
    return True, None


def _news_agent_required_text(agent_brief: dict[str, Any], field_name: str) -> str:
    value = agent_brief.get(field_name)
    return value.strip() if isinstance(value, str) else ""


def _required_news_agent_text(agent_brief: dict[str, Any], field_name: str) -> str:
    value = _news_agent_required_text(agent_brief, field_name)
    if not value:
        raise ValueError(f"news_high_signal_agent_brief_{field_name}_required")
    return value


def _required_news_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"news_high_signal_{field_name}_required")
    return value


def _optional_news_mapping(row: dict[str, Any], field_name: str) -> dict[str, Any]:
    if field_name not in row:
        return {}
    return _required_news_mapping(row.get(field_name), field_name)


def _required_news_list(value: Any, field_name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"news_high_signal_{field_name}_required")
    return value


def _required_news_list_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"news_high_signal_{field_name}_required")
    return value


def _required_news_positive_int(row: dict[str, Any], field_name: str) -> int:
    value = row.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"news_high_signal_{field_name}_required")
    return value


def _required_news_nonnegative_int(row: dict[str, Any], field_name: str) -> int:
    value = row.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"news_high_signal_{field_name}_required")
    return value


def _required_news_text(row: dict[str, Any], field_name: str) -> str:
    value = row.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"news_high_signal_{field_name}_required")
    return value.strip()


def _optional_news_text(row: dict[str, Any], field_name: str) -> str | None:
    if field_name not in row or row.get(field_name) is None:
        return None
    value = row.get(field_name)
    if not isinstance(value, str):
        raise ValueError(f"news_high_signal_{field_name}_required")
    text = value.strip()
    return text or None


def _news_story_payload(value: Any) -> dict[str, Any]:
    payload = _required_news_mapping(value, "story")
    public = {
        "story_key": _required_news_nested_text(payload, "story", "story_key"),
        "member_count": _required_news_nested_positive_int(payload, "story", "member_count"),
    }
    representative_news_item_id = _optional_news_nested_text(payload, "story", "representative_news_item_id")
    if representative_news_item_id is not None:
        public["representative_news_item_id"] = representative_news_item_id
    for field_name in ("member_news_item_ids", "source_domains", "source_ids", "provider_article_keys"):
        values = _optional_news_nested_string_list(payload, "story", field_name)
        if values is not None:
            public[field_name] = values
    return public


def _news_market_scope_payload(value: Any) -> dict[str, Any]:
    payload = _required_news_mapping(value, "market_scope")
    return {
        "scope": _required_news_nested_string_list(payload, "market_scope", "scope"),
        "primary": _required_news_nested_text(payload, "market_scope", "primary"),
        "status": _required_news_nested_text(payload, "market_scope", "status"),
        "reason": _required_news_nested_text(payload, "market_scope", "reason"),
        "basis": _required_news_nested_mapping(payload, "market_scope", "basis"),
        "version": _required_news_nested_text(payload, "market_scope", "version"),
    }


def _news_agent_admission_payload(value: Any) -> dict[str, Any]:
    payload = _required_news_mapping(value, "agent_admission")
    public: dict[str, Any] = {
        "status": _required_news_nested_text(payload, "agent_admission", "status"),
        "reason": _required_news_nested_text(payload, "agent_admission", "reason"),
        "representative_news_item_id": _required_news_nested_text(
            payload,
            "agent_admission",
            "representative_news_item_id",
        ),
    }
    basis = _optional_news_nested_mapping(payload, "agent_admission", "basis")
    if basis is not None:
        public["basis"] = basis
    version = _optional_news_nested_text(payload, "agent_admission", "version")
    if version is not None:
        public["version"] = version
    eligible = _optional_news_nested_bool(payload, "agent_admission", "eligible")
    if eligible is not None:
        public["eligible"] = eligible
    return public


def _required_news_nested_text(payload: dict[str, Any], section: str, field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"news_high_signal_{section}_{field_name}_required")
    return value.strip()


def _optional_news_nested_text(payload: dict[str, Any], section: str, field_name: str) -> str | None:
    if field_name not in payload or payload.get(field_name) is None:
        return None
    return _required_news_nested_text(payload, section, field_name)


def _required_news_nested_string_list(payload: dict[str, Any], section: str, field_name: str) -> list[str]:
    values = payload.get(field_name)
    if not isinstance(values, list):
        raise ValueError(f"news_high_signal_{section}_{field_name}_required")
    strings: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"news_high_signal_{section}_{field_name}_required")
        strings.append(value.strip())
    if not strings:
        raise ValueError(f"news_high_signal_{section}_{field_name}_required")
    return strings


def _optional_news_nested_string_list(payload: dict[str, Any], section: str, field_name: str) -> list[str] | None:
    if field_name not in payload or payload.get(field_name) is None:
        return None
    return _required_news_nested_string_list(payload, section, field_name)


def _required_news_nested_mapping(payload: dict[str, Any], section: str, field_name: str) -> dict[str, Any]:
    value = payload.get(field_name)
    if not isinstance(value, dict):
        raise ValueError(f"news_high_signal_{section}_{field_name}_required")
    return value


def _optional_news_nested_mapping(payload: dict[str, Any], section: str, field_name: str) -> dict[str, Any] | None:
    if field_name not in payload or payload.get(field_name) is None:
        return None
    return _required_news_nested_mapping(payload, section, field_name)


def _required_news_nested_positive_int(payload: dict[str, Any], section: str, field_name: str) -> int:
    value = payload.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"news_high_signal_{section}_{field_name}_required")
    return value


def _optional_news_nested_bool(payload: dict[str, Any], section: str, field_name: str) -> bool | None:
    if field_name not in payload or payload.get(field_name) is None:
        return None
    value = payload.get(field_name)
    if not isinstance(value, bool):
        raise ValueError(f"news_high_signal_{section}_{field_name}_required")
    return value


def _news_display_title(row: dict[str, Any], *, agent_brief: dict[str, Any]) -> str:
    display_signal = _news_display_signal(row)
    title = _news_agent_optional_text(agent_brief, "title_zh")
    if title is None:
        title = _optional_news_signal_text(display_signal, "title_zh", section="display_signal")
    if title is None:
        title = _optional_news_text(row, "headline")
    if title is None:
        title = "News high signal"
    return _compact_text(title, limit=96)


def _news_display_signal(row: dict[str, Any]) -> dict[str, Any]:
    signal = _required_news_mapping(row.get("signal"), "signal")
    return _optional_news_mapping(signal, "display_signal")


def _news_notification_signal_fields(
    row: dict[str, Any],
    *,
    ready_agent_brief: dict[str, Any],
) -> tuple[str, str]:
    if ready_agent_brief:
        return (
            _news_agent_required_text(ready_agent_brief, "decision_class"),
            _news_agent_required_text(ready_agent_brief, "direction"),
        )

    signal = _required_news_mapping(row.get("signal"), "signal")
    display_signal = _news_display_signal(row)
    eligibility = _required_news_mapping(signal.get("alert_eligibility"), "alert_eligibility")
    return (
        _required_news_signal_text(eligibility, "decision_class", section="alert_eligibility"),
        _required_news_signal_direction(signal=signal, display_signal=display_signal),
    )


def _required_news_signal_direction(*, signal: dict[str, Any], display_signal: dict[str, Any]) -> str:
    if "direction" in display_signal:
        return _required_news_signal_text(display_signal, "direction", section="display_signal")
    return _required_news_signal_text(signal, "direction", section="signal")


def _required_news_signal_text(section_payload: dict[str, Any], field_name: str, *, section: str) -> str:
    value = section_payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"news_high_signal_{section}_{field_name}_required")
    return value.strip()


def _required_news_external_push_basis(eligibility: dict[str, Any]) -> None:
    basis = _required_news_signal_text(
        eligibility,
        "external_push_basis",
        section="alert_eligibility",
    )
    if basis != "agent_brief":
        raise ValueError("news_high_signal_alert_eligibility_external_push_basis_required")


def _optional_news_signal_text(section_payload: dict[str, Any], field_name: str, *, section: str) -> str | None:
    if field_name not in section_payload or section_payload.get(field_name) is None:
        return None
    return _required_news_signal_text(section_payload, field_name, section=section)


def _required_news_signal_true(section_payload: dict[str, Any], field_name: str, *, section: str) -> None:
    value = _required_news_signal_bool(section_payload, field_name, section=section)
    if value is not True:
        raise ValueError(f"news_high_signal_{section}_{field_name}_required")


def _required_news_signal_bool(section_payload: dict[str, Any], field_name: str, *, section: str) -> bool:
    value = section_payload.get(field_name)
    if not isinstance(value, bool):
        raise ValueError(f"news_high_signal_{section}_{field_name}_required")
    return value


def _optional_news_signal_bool(section_payload: dict[str, Any], field_name: str, *, section: str) -> bool | None:
    if field_name not in section_payload or section_payload.get(field_name) is None:
        return None
    return _required_news_signal_bool(section_payload, field_name, section=section)


def _news_semantic_signature(row: dict[str, Any], *, agent_brief: dict[str, Any]) -> str:
    decision_class, direction = _news_notification_signal_fields(row, ready_agent_brief=agent_brief)
    story_key = _required_news_text(row, "story_key")
    signature: dict[str, Any] = {
        "story_key": story_key,
        "decision_class": decision_class,
        "direction": direction,
        "affected_entities": _news_affected_entity_symbols(_news_agent_affected_entities(agent_brief)),
    }
    return _stable_hash(signature)


def _news_external_push_signature(
    row: dict[str, Any],
    *,
    occurrence_at_ms: int,
    cooldown_seconds: int,
) -> str:
    agent_brief = _ready_news_agent_brief(_required_news_mapping(row.get("agent_brief"), "agent_brief"))
    direction = _required_news_agent_text(agent_brief, "direction")
    signature = {
        "asset_bucket": _news_external_asset_bucket(row),
        "direction": direction,
        "cooldown_bucket": _cooldown_bucket(occurrence_at_ms, cooldown_seconds),
        "story_key": _required_news_text(row, "story_key"),
    }
    return _stable_hash(signature)


def _news_external_asset_bucket(row: dict[str, Any]) -> str:
    symbols: list[str] = []
    agent_brief = _required_news_mapping(row.get("agent_brief"), "agent_brief")
    for symbol in _news_affected_entity_symbols(_news_agent_affected_entities(agent_brief)):
        normalized = _news_external_asset_symbol(symbol)
        if normalized and normalized not in symbols:
            symbols.append(normalized)
    for impact_value in _required_news_list(row.get("token_impacts"), "token_impacts"):
        impact = _required_news_list_mapping(impact_value, "token_impacts")
        symbol_text = _news_token_impact_optional_text(impact, "symbol")
        if symbol_text is None:
            symbol_text = _news_token_impact_optional_text(impact, "target_symbol")
        normalized = _news_external_asset_symbol(symbol_text)
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
    return _required_news_text(row, "news_item_id")


def _news_external_asset_symbol(value: Any) -> str | None:
    symbol = _symbol(value)
    if not symbol:
        return None
    if symbol.startswith("XYZ-"):
        symbol = symbol[4:]
    return symbol or None


def _news_primary_symbol(row: dict[str, Any]) -> str | None:
    for impact_value in _required_news_list(row.get("token_impacts"), "token_impacts"):
        impact = _required_news_list_mapping(impact_value, "token_impacts")
        symbol_text = _news_token_impact_optional_text(impact, "symbol")
        if symbol_text is None:
            symbol_text = _news_token_impact_optional_text(impact, "target_symbol")
        symbol = _symbol(symbol_text)
        if symbol:
            return symbol
    agent_brief = _required_news_mapping(row.get("agent_brief"), "agent_brief")
    symbols = _news_affected_entity_symbols(_news_agent_affected_entities(agent_brief))
    return symbols[0] if symbols else None


def _news_agent_affected_entities(agent_brief: dict[str, Any]) -> list[dict[str, Any]]:
    if "affected_entities" not in agent_brief:
        return []
    return [
        _required_news_list_mapping(entity, "agent_brief_affected_entities")
        for entity in _required_news_list(agent_brief.get("affected_entities"), "agent_brief_affected_entities")
    ]


def _public_news_agent_brief(agent_brief: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": _required_news_agent_status(agent_brief)}
    for key in (
        "direction",
        "decision_class",
        "title_zh",
        "summary_zh",
        "market_read_zh",
    ):
        value = _news_agent_optional_text(agent_brief, key)
        if value is not None:
            payload[key] = value
    affected_entities = _news_public_affected_entities(agent_brief)
    if affected_entities:
        payload["affected_entities"] = affected_entities
    return payload


def _news_public_affected_entities(agent_brief: dict[str, Any]) -> list[dict[str, Any]]:
    affected_entities = [_public_news_affected_entity(entity) for entity in _news_agent_affected_entities(agent_brief)]
    return [entity for entity in affected_entities if entity]


def _news_agent_optional_text(agent_brief: dict[str, Any], field_name: str) -> str | None:
    if field_name not in agent_brief or agent_brief.get(field_name) is None:
        return None
    value = agent_brief.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"news_high_signal_agent_brief_{field_name}_required")
    return value.strip()


def _public_news_affected_entity(entity: Any) -> dict[str, Any]:
    entity = _required_news_list_mapping(entity, "agent_brief_affected_entities")
    payload: dict[str, Any] = {}
    for key in (
        "label",
        "symbol",
        "name",
        "entity_type",
        "market_domain",
        "resolution_status",
        "target_type",
        "target_id",
        "impact_direction",
        "reason_zh",
    ):
        value = _news_affected_entity_optional_text(entity, key)
        if value is not None:
            payload[key] = value
    evidence_refs = _news_affected_entity_optional_string_list(entity, "evidence_refs")
    if evidence_refs is not None:
        payload["evidence_refs"] = evidence_refs
    return payload


def _news_affected_entity_optional_text(entity: dict[str, Any], field_name: str) -> str | None:
    if field_name not in entity or entity.get(field_name) is None:
        return None
    value = entity.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"news_high_signal_agent_brief_affected_entities_{field_name}_required")
    return value.strip()


def _news_affected_entity_optional_string_list(entity: dict[str, Any], field_name: str) -> list[str] | None:
    if field_name not in entity or entity.get(field_name) is None:
        return None
    values = _required_news_list(entity.get(field_name), f"agent_brief_affected_entities_{field_name}")
    refs: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"news_high_signal_agent_brief_affected_entities_{field_name}_required")
        refs.append(value.strip())
    return refs


def _news_affected_entity_symbols(value: Any) -> list[str]:
    symbols: list[str] = []
    for item in _required_news_list(value, "agent_brief_affected_entities"):
        entity = _required_news_list_mapping(item, "agent_brief_affected_entities")
        symbol = _symbol(_news_affected_entity_optional_text(entity, "symbol"))
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    return symbols[:12]


def _news_body(row: dict[str, Any], *, summary: str, source_domain: str) -> str:
    lines = [
        f"Source: {_compact_text(source_domain, limit=80)}",
    ]
    if summary:
        lines.append(summary)
    url = _optional_news_text(row, "canonical_url")
    if url:
        lines.append(url)
    return "\n".join(lines)
