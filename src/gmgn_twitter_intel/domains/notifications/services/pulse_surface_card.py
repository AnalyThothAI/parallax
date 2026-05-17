"""Pulse SurfaceCard renderer.

Renders signal_pulse_candidate notification body from FinalDecision v2.
Replaces the legacy _pulse_body markdown that dropped 80% of payload information.

Body sections (in order):
1. Header: $SYMBOL · {route} · {recommendation} · conf {pct}
2. Narrative: archetype label + narrative_thesis_zh
3. Bull (if strength != absent): label + thesis_zh + evidence deep-links
4. Bear (if strength != absent): label + thesis_zh + evidence deep-links
5. Playbook (if has_playbook): watch_signals + exit_triggers + monitoring_horizon
6. Links: GMGN / X Search / Pulse Detail

Degradation order under length cap (~2500 chars):
- Always keep: Header / Playbook / Links
- First drop: Bear section
- Second drop: Bull section
- Third drop: Narrative section
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from gmgn_twitter_intel.domains.pulse_lab.interfaces import contains_trading_execution_instruction

# 字符上限
_MAX_BODY_CHARS = 2500

# 强度标签
_STRENGTH_LABELS_ZH = {
    "weak": "弱",
    "moderate": "中",
    "strong": "强",
}

# Route 中文
_ROUTE_LABELS_ZH = {
    "cex": "CEX",
    "meme": "Meme",
    "research_only": "Research",
}

_RECOMMENDATION_LABELS_ZH = {
    "high_conviction": "高确信",
    "trade_candidate": "交易候选",
    "watchlist": "观察",
    "ignore": "忽略",
    "abstain": "弃权",
}


def render_pulse_surface_card(
    *,
    row: dict[str, Any],
    decision: dict[str, Any],
    factor_snapshot: dict[str, Any] | None = None,
    asset_profile: dict[str, Any] | None = None,
) -> str:
    """Render full surface card markdown body. Length-capped via section degradation."""
    factor_snapshot = factor_snapshot or {}
    asset_profile = asset_profile or {}

    header = _render_header(row=row, decision=decision)
    playbook = _render_playbook(decision)
    links = _render_links(row=row, decision=decision, factor_snapshot=factor_snapshot, asset_profile=asset_profile)
    narrative = _render_narrative(decision)
    bull = _render_view("看多", decision.get("bull_view"), decision=decision)
    bear = _render_view("看空", decision.get("bear_view"), decision=decision)

    # Always-keep sections first; optional sections at degradation tiers.
    # Links go LAST in the rendered body so they remain visible at the bottom.
    always_head = [header, playbook]
    always_tail = [links]
    optional_full = [narrative, bull, bear]  # narrative first to keep, bear first to drop

    # Try full body
    body = _join_sections([*always_head, *optional_full, *always_tail])
    if len(body) <= _MAX_BODY_CHARS:
        return body

    # Tier 1: drop bear
    body = _join_sections([*always_head, narrative, bull, *always_tail])
    if len(body) <= _MAX_BODY_CHARS:
        return body

    # Tier 2: drop bull
    body = _join_sections([*always_head, narrative, *always_tail])
    if len(body) <= _MAX_BODY_CHARS:
        return body

    # Tier 3: drop narrative
    body = _join_sections([*always_head, *always_tail])
    return _cap_body(body)


def _render_header(*, row: dict[str, Any], decision: dict[str, Any]) -> str:
    symbol = _symbol(row.get("symbol"))
    display = f"${symbol}" if symbol else (str(row.get("subject_key") or "")[:80] or "Pulse")
    route_raw = str(decision.get("route") or "")
    route = _ROUTE_LABELS_ZH.get(route_raw, route_raw)
    rec_raw = str(decision.get("recommendation") or "")
    rec = _RECOMMENDATION_LABELS_ZH.get(rec_raw, rec_raw)
    conf = _confidence_pct(decision.get("confidence"))
    parts = [display]
    if route:
        parts.append(route)
    if rec:
        parts.append(rec)
    if conf:
        parts.append(f"conf {conf}")
    head_line = " · ".join(parts)
    return f"## {head_line} Signal Pulse"


def _render_narrative(decision: dict[str, Any]) -> str:
    archetype = str(decision.get("narrative_archetype") or "").strip()
    thesis = _safe_text(decision.get("narrative_thesis_zh"))
    if not (archetype or thesis):
        return ""
    lines = ["### 📖 叙事"]
    if archetype:
        lines.append(f"**类型**: `{archetype}`")
    if thesis:
        lines.append(thesis)
    return "\n".join(lines)


def _render_view(zh_label: str, view: Any, *, decision: dict[str, Any]) -> str:
    if not isinstance(view, dict):
        return ""
    strength = str(view.get("strength") or "")
    if strength == "absent" or not strength:
        return ""
    label_zh = _STRENGTH_LABELS_ZH.get(strength, strength)
    thesis = _safe_text(view.get("thesis_zh"))
    if not thesis:
        return ""
    icon = "🟢" if zh_label == "看多" else "🔴"
    lines = [f"### {icon} {zh_label}（{label_zh}）", thesis]
    # Deep-link evidence ids via decision.evidence_event_urls map
    urls_map = decision.get("evidence_event_urls") or {}
    ids = view.get("supporting_event_ids") or []
    if isinstance(ids, list) and ids:
        link_parts: list[str] = []
        for eid in ids[:5]:  # 限 5 个避免过长
            eid_s = str(eid)
            url = urls_map.get(eid_s) if isinstance(urls_map, dict) else None
            if url:
                link_parts.append(f"[原推]({url})")
            else:
                link_parts.append(f"`{eid_s[:24]}…`")
        if link_parts:
            lines.append("证据: " + " · ".join(link_parts))
    return "\n".join(lines)


def _render_playbook(decision: dict[str, Any]) -> str:
    playbook = decision.get("playbook")
    if not isinstance(playbook, dict):
        return ""
    if not playbook.get("has_playbook"):
        return ""
    horizon = playbook.get("monitoring_horizon") or "—"
    lines = [f"### 🎯 Playbook （监控窗口 {horizon}）"]
    watch = _safe_list(playbook.get("watch_signals"))
    if watch:
        lines.append("**关注信号**:")
        lines.extend(f"- {s}" for s in watch)
    exits = _safe_list(playbook.get("exit_triggers"))
    if exits:
        lines.append("**退场触发**:")
        lines.extend(f"- {s}" for s in exits)
    return "\n".join(lines)


def _render_links(
    *,
    row: dict[str, Any],
    decision: dict[str, Any],
    factor_snapshot: dict[str, Any],
    asset_profile: dict[str, Any],
) -> str:
    symbol = _symbol(row.get("symbol"))
    snapshot_subject = _dict(factor_snapshot.get("subject"))
    profile_identity = _dict(asset_profile.get("identity"))
    chain = _chain(row.get("chain") or snapshot_subject.get("chain") or profile_identity.get("chain"))
    address = row.get("address") or snapshot_subject.get("address") or profile_identity.get("address") or ""
    candidate_id = row.get("candidate_id") or ""
    parts = ["### 🔗 链接"]
    if chain and address:
        parts.append(f"- [GMGN](https://gmgn.ai/{quote(str(chain))}/token/{quote(str(address))})")
    if symbol:
        parts.append(f"- [X 搜索](https://x.com/search?q={quote('$' + symbol)}&f=live)")
    if candidate_id:
        parts.append(f"- Pulse: `{candidate_id}`")
    if len(parts) == 1:
        return ""
    return "\n".join(parts)


def _confidence_pct(conf: Any) -> str:
    try:
        return f"{round(float(conf) * 100)}%"
    except (TypeError, ValueError):
        return ""


def _symbol(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lstrip("$").upper()
    return text or None


def _chain(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text or contains_trading_execution_instruction(text):
        return ""
    return text


def _safe_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    safe: list[str] = []
    for value in values:
        text = _safe_text(value)
        if text:
            safe.append(text)
    return safe


def _join_sections(sections: list[str]) -> str:
    return "\n\n".join(s for s in sections if s)


def _cap_body(body: str) -> str:
    if len(body) <= _MAX_BODY_CHARS:
        return body
    return body[: _MAX_BODY_CHARS - 3].rstrip() + "..."


__all__ = ["render_pulse_surface_card"]
