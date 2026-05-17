from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.asset_market.repositories.cex_token_profile_repository import (
    BINANCE_CEX_PROFILE_PROVIDER,
)


def sync_cex_token_profiles(*, cex_token_profiles: Any, profile_source: Any, observed_at_ms: int) -> dict[str, Any]:
    profiles_seen = 0
    profiles_updated = 0
    missing_cex_tokens = 0
    affected_lookup_keys: set[str] = set()
    provider_name = None

    for profile in profile_source.token_profiles():
        base_symbol = _field(profile, "base_symbol")
        logo_url = _field(profile, "logo_url")
        provider = _field(profile, "provider") or BINANCE_CEX_PROFILE_PROVIDER
        if not base_symbol or not logo_url:
            continue
        profiles_seen += 1
        provider_name = provider_name or provider
        row = cex_token_profiles.upsert_ready_profile_if_token_exists(
            base_symbol=base_symbol,
            provider=provider,
            symbol=_field(profile, "symbol") or base_symbol,
            name=_field(profile, "name"),
            logo_url=logo_url,
            source_ref=_field(profile, "source_ref"),
            raw_payload=_raw_payload(profile),
            observed_at_ms=int(observed_at_ms),
            commit=False,
        )
        if row is None:
            missing_cex_tokens += 1
            continue
        profiles_updated += 1
        affected_lookup_keys.update(_symbol_lookup_keys(base_symbol))

    cex_token_profiles.conn.commit()
    return {
        "profiles_seen": profiles_seen,
        "profiles_updated": profiles_updated,
        "missing_cex_tokens": missing_cex_tokens,
        "affected_lookup_keys": sorted(affected_lookup_keys),
        "provider": provider_name or BINANCE_CEX_PROFILE_PROVIDER,
    }


def _field(profile: Any, key: str) -> str | None:
    value = profile.get(key) if isinstance(profile, dict) else getattr(profile, key, None)
    text = str(value or "").strip()
    return text or None


def _raw_payload(profile: Any) -> dict[str, Any]:
    raw = profile.get("raw_payload") if isinstance(profile, dict) else getattr(profile, "raw_payload", None)
    return dict(raw) if isinstance(raw, dict) else {}


def _symbol_lookup_keys(symbol: Any) -> set[str]:
    normalized = str(symbol or "").strip().lstrip("$").upper()
    if not normalized:
        return set()
    return {f"symbol:{normalized}", f"project_symbol:{normalized}", f"cex_token:{normalized}"}
