from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.asset_market.identity_evidence_policy import (
    EVIDENCE_GMGN_PAYLOAD_EXACT,
    EVIDENCE_OKX_DEX_EXACT_ADDRESS,
)

GMGN_DEX_PROFILE_PROVIDER = "gmgn_dex_profile"
GMGN_STREAM_PROFILE_PROVIDER = "gmgn_stream_snapshot"
OKX_DEX_PROFILE_PROVIDER = "okx_dex_evidence"

STATUS_READY = "ready"
STATUS_MISSING = "missing"
STATUS_UNSUPPORTED = "unsupported"
STATUS_ERROR = "error"


def project_token_profile_current(
    *,
    target: dict[str, Any],
    gmgn_openapi: dict[str, Any] | None,
    gmgn_stream: dict[str, Any] | None,
    okx_dex: dict[str, Any] | None,
    computed_at_ms: int,
) -> dict[str, Any]:
    target_type = _clean(target.get("target_type"))
    target_id = _clean(target.get("target_id"))
    if target_type == "CexToken":
        return _status_row(
            target_type=target_type,
            target_id=target_id,
            status=STATUS_UNSUPPORTED,
            source_kind="projection",
            computed_at_ms=computed_at_ms,
            quality_flags=["cex_profile_unsupported"],
        )

    if _openapi_ready(gmgn_openapi):
        return _gmgn_openapi_row(
            target_type=target_type,
            target_id=target_id,
            source=gmgn_openapi,
            computed_at_ms=computed_at_ms,
        )

    if _gmgn_stream_ready(gmgn_stream):
        return _gmgn_stream_row(
            target_type=target_type,
            target_id=target_id,
            source=gmgn_stream,
            computed_at_ms=computed_at_ms,
        )

    if okx_dex is not None:
        return _okx_dex_row(target_type=target_type, target_id=target_id, source=okx_dex, computed_at_ms=computed_at_ms)

    return _status_row(
        target_type=target_type,
        target_id=target_id,
        status=STATUS_MISSING,
        source_kind="projection",
        computed_at_ms=computed_at_ms,
        quality_flags=["source_without_logo"],
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


def _gmgn_openapi_row(
    *,
    target_type: str | None,
    target_id: str | None,
    source: dict[str, Any],
    computed_at_ms: int,
) -> dict[str, Any]:
    raw = _raw(source)
    return _ready_row(
        target_type=target_type,
        target_id=target_id,
        profile_provider=GMGN_DEX_PROFILE_PROVIDER,
        source_kind="asset_profiles",
        source_ref=f"{GMGN_DEX_PROFILE_PROVIDER}:{target_id}",
        symbol=source.get("symbol"),
        name=source.get("name"),
        logo_url=source.get("logo_url"),
        banner_url=source.get("banner_url"),
        website_url=source.get("website_url"),
        twitter_username=source.get("twitter_username"),
        twitter_url=source.get("twitter_url"),
        telegram_url=source.get("telegram_url"),
        gmgn_url=source.get("gmgn_url"),
        geckoterminal_url=source.get("geckoterminal_url"),
        description=source.get("description"),
        source_payload=raw,
        observed_at_ms=_int_or_none(source.get("observed_at_ms")),
        computed_at_ms=computed_at_ms,
    )


def _gmgn_stream_row(
    *,
    target_type: str | None,
    target_id: str | None,
    source: dict[str, Any],
    computed_at_ms: int,
) -> dict[str, Any]:
    raw = _raw(source)
    return _ready_row(
        target_type=target_type,
        target_id=target_id,
        profile_provider=GMGN_STREAM_PROFILE_PROVIDER,
        source_kind="asset_identity_evidence",
        source_ref=_clean(source.get("evidence_id")) or _clean(source.get("source_event_id")),
        symbol=raw.get("s") or source.get("symbol"),
        name=source.get("name"),
        logo_url=raw.get("i"),
        source_payload=raw,
        observed_at_ms=_int_or_none(source.get("observed_at_ms")),
        computed_at_ms=computed_at_ms,
    )


def _okx_dex_row(
    *,
    target_type: str | None,
    target_id: str | None,
    source: dict[str, Any],
    computed_at_ms: int,
) -> dict[str, Any]:
    raw = _raw(source)
    logo_url = _clean(raw.get("tokenLogoUrl"))
    flags = _logo_quality_flags(logo_url, placeholder_flag="okx_placeholder_logo")
    if flags:
        flags.append("source_without_logo")
        row = _status_row(
            target_type=target_type,
            target_id=target_id,
            status=STATUS_MISSING,
            profile_provider=OKX_DEX_PROFILE_PROVIDER,
            source_kind="asset_identity_evidence",
            source_ref=_clean(source.get("evidence_id")),
            source_payload=raw,
            observed_at_ms=_int_or_none(source.get("observed_at_ms")),
            computed_at_ms=computed_at_ms,
            quality_flags=flags,
        )
        row["symbol"] = _clean(raw.get("tokenSymbol") or source.get("symbol"))
        row["name"] = _clean(raw.get("tokenName") or source.get("name"))
        return row

    return _ready_row(
        target_type=target_type,
        target_id=target_id,
        profile_provider=OKX_DEX_PROFILE_PROVIDER,
        source_kind="asset_identity_evidence",
        source_ref=_clean(source.get("evidence_id")),
        symbol=raw.get("tokenSymbol") or source.get("symbol"),
        name=raw.get("tokenName") or source.get("name"),
        logo_url=logo_url,
        source_payload=raw,
        observed_at_ms=_int_or_none(source.get("observed_at_ms")),
        computed_at_ms=computed_at_ms,
    )


def _ready_row(
    *,
    target_type: str | None,
    target_id: str | None,
    profile_provider: str,
    source_kind: str,
    source_ref: str | None,
    source_payload: dict[str, Any],
    computed_at_ms: int,
    symbol: Any = None,
    name: Any = None,
    logo_url: Any = None,
    banner_url: Any = None,
    website_url: Any = None,
    twitter_username: Any = None,
    twitter_url: Any = None,
    telegram_url: Any = None,
    gmgn_url: Any = None,
    geckoterminal_url: Any = None,
    description: Any = None,
    observed_at_ms: int | None = None,
) -> dict[str, Any]:
    return {
        "target_type": _clean(target_type),
        "target_id": _clean(target_id),
        "status": STATUS_READY,
        "profile_provider": profile_provider,
        "source_kind": source_kind,
        "source_ref": _clean(source_ref),
        "symbol": _clean(symbol),
        "name": _clean(name),
        "logo_url": _clean(logo_url),
        "banner_url": _clean(banner_url),
        "website_url": _clean(website_url),
        "twitter_username": _clean(twitter_username),
        "twitter_url": _clean(twitter_url),
        "telegram_url": _clean(telegram_url),
        "gmgn_url": _clean(gmgn_url),
        "geckoterminal_url": _clean(geckoterminal_url),
        "description": _clean(description),
        "quality_flags": [],
        "source_payload": dict(source_payload),
        "observed_at_ms": observed_at_ms,
        "computed_at_ms": int(computed_at_ms),
        "updated_at_ms": int(computed_at_ms),
    }


def _status_row(
    *,
    target_type: str | None,
    target_id: str | None,
    status: str,
    source_kind: str,
    computed_at_ms: int,
    profile_provider: str | None = None,
    source_ref: str | None = None,
    source_payload: dict[str, Any] | None = None,
    observed_at_ms: int | None = None,
    quality_flags: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "target_type": _clean(target_type),
        "target_id": _clean(target_id),
        "status": status,
        "profile_provider": profile_provider,
        "source_kind": source_kind,
        "source_ref": _clean(source_ref),
        "symbol": None,
        "name": None,
        "logo_url": None,
        "banner_url": None,
        "website_url": None,
        "twitter_username": None,
        "twitter_url": None,
        "telegram_url": None,
        "gmgn_url": None,
        "geckoterminal_url": None,
        "description": None,
        "quality_flags": list(quality_flags or []),
        "source_payload": dict(source_payload or {}),
        "observed_at_ms": observed_at_ms,
        "computed_at_ms": int(computed_at_ms),
        "updated_at_ms": int(computed_at_ms),
    }


def _openapi_ready(row: dict[str, Any] | None) -> bool:
    if not row or _clean(row.get("status")) != STATUS_READY:
        return False
    return _valid_logo_url(row.get("logo_url"))


def _gmgn_stream_ready(row: dict[str, Any] | None) -> bool:
    return bool(row and _valid_logo_url(_raw(row).get("i")))


def _valid_logo_url(value: Any) -> bool:
    return not _logo_quality_flags(_clean(value))


def _logo_quality_flags(value: str | None, *, placeholder_flag: str = "placeholder_logo") -> list[str]:
    if not value:
        return ["invalid_logo_url"]
    if not value.startswith(("http://", "https://")):
        return ["invalid_logo_url"]
    if "/default-logo/" in value:
        return [placeholder_flag]
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
