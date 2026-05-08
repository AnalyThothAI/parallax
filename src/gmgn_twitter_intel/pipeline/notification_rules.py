from __future__ import annotations

import hashlib
import json
import time
from typing import Any
from urllib.parse import quote

from ..settings import NotificationRuleConfig, Settings
from .notification_models import NotificationCandidate

WATCHED_ACTIVITY_WINDOW_MS = 60 * 60_000
DEFAULT_LIMIT = 50
MAX_SIGNAL_PULSE_NOTIFICATION_PAGES = 5
SIGNAL_PULSE_RULE_ID = "signal_pulse_candidate"
DEFAULT_SIGNAL_PULSE_WINDOW = "1h"
DEFAULT_SIGNAL_PULSE_SCOPES = ("all", "matched")
DEFAULT_SIGNAL_PULSE_STATUSES = ("trade_candidate", "token_watch", "theme_watch", "risk_rejected_high_info")
SIGNAL_PULSE_SEVERITY = {
    "trade_candidate": "critical",
    "token_watch": "high",
    "theme_watch": "warning",
    "risk_rejected_high_info": "high",
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
            heat_score = _pulse_heat_score(row)
            if (
                rule.social_heat_min is not None
                and _pulse_candidate_has_token_target(row)
                and (heat_score is None or heat_score < rule.social_heat_min)
            ):
                continue
            if rule.candidate_score_min is not None and _float(row.get("candidate_score")) < rule.candidate_score_min:
                continue
            severity = SIGNAL_PULSE_SEVERITY.get(status)
            if severity is None:
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
                    dedup_key=f"{SIGNAL_PULSE_RULE_ID}:{candidate_id}:{signature}:{bucket}",
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


def _pulse_heat_score(row: dict[str, Any]) -> int | None:
    radar = _dict(row.get("radar_score_json"))
    heat = radar.get("heat")
    if isinstance(heat, dict):
        if "score" not in heat:
            return None
        return _int(heat.get("score"))
    if heat is None:
        return None
    return _int(heat)


def _pulse_candidate_has_token_target(row: dict[str, Any]) -> bool:
    return bool(row.get("symbol") or row.get("target_id") or row.get("candidate_type") == "token_target")


def _score_version(block: Any) -> str | None:
    return str(block.get("score_version")) if isinstance(block, dict) and block.get("score_version") else None


def _pulse_notification_signature(row: dict[str, Any]) -> str:
    thesis = _dict(row.get("thesis_json"))
    evidence_ids = _list(row.get("evidence_event_ids_json"))
    source_ids = _list(row.get("source_event_ids_json"))
    payload = {
        "pulse_version": row.get("pulse_version"),
        "candidate_id": row.get("candidate_id"),
        "pulse_status": row.get("pulse_status"),
        "score_band": row.get("score_band"),
        "social_phase": row.get("social_phase"),
        "top_risk_keys": _risk_keys(row),
        "confirmation_trigger_keys": _fingerprints(_list(thesis.get("confirmation_triggers_zh"))),
        "latest_evidence_event_id_bucket": _event_id_bucket([*evidence_ids, *source_ids]),
        "source_event_fingerprint": _short_hash(_stable_list(source_ids)),
    }
    return _stable_hash(payload)


def _pulse_payload(row: dict[str, Any], *, notification_signature: str) -> dict[str, Any]:
    thesis = _dict(row.get("thesis_json"))
    return {
        "candidate_id": row.get("candidate_id"),
        "pulse_status": row.get("pulse_status"),
        "score_band": row.get("score_band"),
        "social_phase": row.get("social_phase"),
        "narrative_type": row.get("narrative_type"),
        "top_risks": _list(thesis.get("top_risks")),
        "confirmation_triggers_zh": _list(thesis.get("confirmation_triggers_zh")),
        "invalidation_triggers_zh": _list(thesis.get("invalidation_triggers_zh")),
        "evidence_event_ids": _list(row.get("evidence_event_ids_json")),
        "source_event_ids": _list(row.get("source_event_ids_json")),
        "candidate_score": row.get("candidate_score"),
        "target_type": row.get("target_type"),
        "target_id": row.get("target_id"),
        "symbol": _symbol(row.get("symbol")),
        "notification_signature": notification_signature,
    }


def _pulse_body(row: dict[str, Any]) -> str:
    thesis = _dict(row.get("thesis_json"))
    symbol = _symbol(row.get("symbol"))
    display = f"${symbol}" if symbol else str(row.get("subject_key") or row.get("candidate_id") or "Signal Pulse")
    lines = [
        f"## {display} Signal Pulse",
        "",
        f"- **Status:** {str(row.get('pulse_status') or '').replace('_', ' ')}",
        f"- **Score band:** {row.get('score_band') or 'unknown'}",
        f"- **Social phase:** {row.get('social_phase') or 'unknown'}",
        f"- **Candidate score:** {row.get('candidate_score')}",
    ]
    why_now = _compact_text(thesis.get("why_now_zh") or thesis.get("summary_zh"), limit=240)
    if why_now:
        lines.extend(["", why_now])
    risks = _list(thesis.get("top_risks")) or _list(row.get("risk_reasons_json"))
    if risks:
        lines.extend(["", "**Risks**"])
        lines.extend(f"- {risk}" for risk in risks[:4])
    confirmations = _list(thesis.get("confirmation_triggers_zh"))
    if confirmations:
        lines.extend(["", "**Confirmation**"])
        lines.extend(f"- {item}" for item in confirmations[:3])
    return "\n".join(lines)


def _risk_keys(row: dict[str, Any]) -> list[str]:
    thesis = _dict(row.get("thesis_json"))
    values = [
        *_list(thesis.get("top_risks")),
        *_list(row.get("risk_reasons_json")),
    ]
    return sorted({str(value).strip() for value in values if str(value).strip()})[:8]


def _fingerprints(values: list[Any]) -> list[str]:
    return [_short_hash(str(value).strip().lower()) for value in values if str(value).strip()][:8]


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


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


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
