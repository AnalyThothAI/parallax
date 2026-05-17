from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.asset_market.identity_evidence_policy import (
    EVIDENCE_GMGN_PAYLOAD_EXACT,
    EVIDENCE_OKX_DEX_EXACT_ADDRESS,
)


def select_gmgn_stream_source(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [
        row
        for row in rows
        if _clean(row.get("provider")) == "gmgn"
        and _clean(row.get("evidence_kind")) == EVIDENCE_GMGN_PAYLOAD_EXACT
        and _valid_logo_url(_raw(row).get("i"))
    ]
    return _latest(candidates)


def select_okx_dex_source(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [
        row
        for row in rows
        if _clean(row.get("provider")) == "okx"
        and _clean(row.get("evidence_kind")) == EVIDENCE_OKX_DEX_EXACT_ADDRESS
        and _clean(_raw(row).get("tokenLogoUrl"))
    ]
    return _latest(candidates)


def _valid_logo_url(value: Any) -> bool:
    return not _logo_quality_flags(_clean(value))


def _logo_quality_flags(value: str | None) -> list[str]:
    if not value:
        return ["invalid_logo_url"]
    if not value.startswith(("http://", "https://")):
        return ["invalid_logo_url"]
    if "/default-logo/" in value:
        return ["placeholder_logo"]
    return []


def _raw(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("raw_payload_json")
    return dict(raw) if isinstance(raw, dict) else {}


def _latest(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    return max(rows, key=lambda row: (_int_or_none(row.get("observed_at_ms")) or 0, str(row.get("evidence_id") or "")))


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None
