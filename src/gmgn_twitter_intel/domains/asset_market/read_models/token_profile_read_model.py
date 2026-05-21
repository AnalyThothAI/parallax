from __future__ import annotations

from typing import Any


class TokenProfileReadModel:
    def __init__(self, *, token_profiles: Any) -> None:
        self.token_profiles = token_profiles

    def profile_for_target(self, *, target_type: str | None, target_id: str | None) -> dict[str, Any] | None:
        key = _target_key({"target_type": target_type, "target_id": target_id})
        if key is None:
            return None
        return self.profiles_for_targets([{"target_type": key[0], "target_id": key[1]}]).get(key)

    def profiles_for_targets(self, targets: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any] | None]:
        keys = [_target_key(target) for target in targets]
        requested_keys = list(dict.fromkeys(key for key in keys if key is not None))
        rows = self.token_profiles.current_for_targets(requested_keys)
        profiles: dict[tuple[str, str], dict[str, Any] | None] = {}
        for target_type, target_id in requested_keys:
            key = (target_type, target_id)
            row = rows.get(key)
            if row is not None:
                profiles[key] = _block_from_row(row)
                continue
            if target_type == "Asset":
                profiles[key] = _pending_block()
            elif target_type == "CexToken":
                profiles[key] = _unsupported_block()
            else:
                profiles[key] = None
        return profiles


def _block_from_row(row: dict[str, Any]) -> dict[str, Any]:
    status = (_clean(row.get("status")) or "pending").lower()
    if status == "ready":
        return {
            "status": "ready",
            "provider": _provider(row),
            "observed_at_ms": _int_or_none(row.get("observed_at_ms")),
            "identity": {
                "symbol": _clean(row.get("symbol")),
                "name": _clean(row.get("name")),
                "logo_url": _local_logo_url(row.get("logo_url")),
                "banner_url": _clean(row.get("banner_url")),
                "description": _clean(row.get("description")),
            },
            "links": {
                "website_url": _clean(row.get("website_url")),
                "twitter_url": _twitter_url(_clean(row.get("twitter_url")) or _clean(row.get("twitter_username"))),
                "twitter_username": _clean(row.get("twitter_username")),
                "telegram_url": _clean(row.get("telegram_url")),
                "gmgn_url": _clean(row.get("gmgn_url")),
                "geckoterminal_url": _clean(row.get("geckoterminal_url")),
            },
            "source": _source(row),
        }

    return {
        "status": status,
        "provider": _provider(row),
        "observed_at_ms": _int_or_none(row.get("observed_at_ms")),
        "source": _source(row),
    }


def _pending_block() -> dict[str, Any]:
    return {
        "status": "pending",
        "provider": None,
        "observed_at_ms": None,
        "source": {
            "provider": None,
            "source_kind": "token_profile_current",
            "source_ref": None,
            "quality_flags": [],
            "raw_available": False,
            "last_error": None,
        },
    }


def _unsupported_block() -> dict[str, Any]:
    return {
        "status": "unsupported",
        "provider": None,
        "observed_at_ms": None,
        "source": {
            "provider": None,
            "source_kind": "token_profile_current",
            "source_ref": None,
            "quality_flags": ["cex_profile_unsupported"],
            "raw_available": False,
            "last_error": None,
        },
    }


def _source(row: dict[str, Any]) -> dict[str, Any]:
    payload = _payload(row)
    return {
        "provider": _provider(row),
        "source_kind": _clean(row.get("source_kind")),
        "source_ref": _clean(row.get("source_ref")),
        "quality_flags": _quality_flags(row.get("quality_flags_json")),
        "raw_available": bool(payload),
        "last_error": _clean(payload.get("last_error")),
    }


def _target_key(target: dict[str, Any]) -> tuple[str, str] | None:
    target_type = _clean(target.get("target_type"))
    target_id = _clean(target.get("target_id"))
    if not target_type or not target_id:
        return None
    return (target_type, target_id)


def _twitter_url(username_or_url: str | None) -> str | None:
    value = _clean(username_or_url)
    if not value:
        return None
    if value.startswith(("http://", "https://")):
        return value
    handle = value.lstrip("@").strip("/")
    return f"https://x.com/{handle}" if handle else None


def _local_logo_url(value: Any) -> str | None:
    url = _clean(value)
    if url and url.startswith("/api/token-images/"):
        return url
    return None


def _provider(row: dict[str, Any]) -> str | None:
    return _clean(row.get("profile_provider"))


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("source_payload_json")
    return dict(payload) if isinstance(payload, dict) else {}


def _quality_flags(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    result: list[str] = []
    for item in value:
        cleaned = _clean(item)
        if cleaned:
            result.append(cleaned)
    return result


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)
