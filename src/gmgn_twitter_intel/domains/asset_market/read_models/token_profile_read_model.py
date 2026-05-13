from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.asset_market.repositories.asset_profile_repository import GMGN_DEX_PROFILE_PROVIDER


class TokenProfileReadModel:
    def __init__(self, *, asset_profiles: Any) -> None:
        self.asset_profiles = asset_profiles

    def profile_for_target(self, *, target_type: str | None, target_id: str | None) -> dict[str, Any] | None:
        key = _target_key({"target_type": target_type, "target_id": target_id})
        if key is None:
            return None
        return self.profiles_for_targets([{"target_type": key[0], "target_id": key[1]}]).get(key)

    def profiles_for_targets(self, targets: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any] | None]:
        keys = [_target_key(target) for target in targets]
        requested_keys = [key for key in keys if key is not None]
        asset_ids = [
            target_id
            for target_type, target_id in dict.fromkeys(requested_keys)
            if target_type == "Asset" and target_id
        ]
        rows = self.asset_profiles.profiles_for_asset_ids(asset_ids, provider=GMGN_DEX_PROFILE_PROVIDER)
        profiles: dict[tuple[str, str], dict[str, Any] | None] = {}
        for target_type, target_id in dict.fromkeys(requested_keys):
            key = (target_type, target_id)
            if target_type != "Asset":
                profiles[key] = None
                continue
            profiles[key] = _block_from_row(rows.get(target_id))
        return profiles


def _block_from_row(row: dict[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return {
            "status": "pending",
            "provider": GMGN_DEX_PROFILE_PROVIDER,
            "observed_at_ms": None,
            "source": _source(None),
        }

    status = (_clean(row.get("status")) or "pending").lower()
    if status == "ready":
        return {
            "status": "ready",
            "provider": _provider(row),
            "observed_at_ms": _int_or_none(row.get("observed_at_ms")),
            "identity": {
                "symbol": _clean(row.get("symbol")),
                "name": _clean(row.get("name")),
                "logo_url": _clean(row.get("logo_url")),
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


def _source(row: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "provider": _provider(row),
        "raw_available": _raw_available(row),
        "last_error": _clean((row or {}).get("last_error")),
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


def _provider(row: dict[str, Any] | None) -> str:
    return _clean((row or {}).get("provider")) or GMGN_DEX_PROFILE_PROVIDER


def _raw_available(row: dict[str, Any] | None) -> bool:
    if not row:
        return False
    raw = row.get("raw_payload_json")
    return bool(raw)


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)
