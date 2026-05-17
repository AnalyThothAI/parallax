from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.asset_market.providers import DexProviderTemporarilyUnavailable, DexTokenProfile
from gmgn_twitter_intel.domains.asset_market.queries.pending_asset_profile_query import PendingAssetProfileQuery
from gmgn_twitter_intel.domains.asset_market.repositories.asset_profile_repository import (
    ERROR_REFRESH_MS,
    GMGN_DEX_PROFILE_PROVIDER,
    MISSING_REFRESH_MS,
    READY_REFRESH_MS,
)


def refresh_asset_profiles_once(
    *,
    repos: Any,
    dex_profile_market: Any,
    now_ms: int,
    limit: int = 50,
) -> dict[str, Any]:
    result = _empty_result(now_ms=now_ms)
    if dex_profile_market is None:
        result["skipped"] = 1
        return result

    rows = PendingAssetProfileQuery(repos.conn).pending_rows(
        provider=GMGN_DEX_PROFILE_PROVIDER,
        now_ms=now_ms,
        limit=limit,
    )
    result["selected"] = len(rows)
    for row in rows:
        try:
            profile = dex_profile_market.token_profile(
                chain_id=str(row["chain_id"]),
                address=str(row["address"]),
            )
        except DexProviderTemporarilyUnavailable as exc:
            result["provider_blocked"] = 1
            result["last_error"] = str(exc)[:500]
            break
        except Exception as exc:
            _write_error_profile(repos=repos, row=row, exc=exc, now_ms=now_ms)
            result["error"] += 1
            continue

        if isinstance(profile, DexTokenProfile):
            _write_ready_profile(repos=repos, row=row, profile=profile, now_ms=now_ms)
            result["ready"] += 1
            continue

        _write_missing_profile(repos=repos, row=row, now_ms=now_ms)
        result["missing"] += 1
    return result


def select_due_asset_profile_rows(*, repos: Any, now_ms: int, limit: int = 50) -> list[dict[str, Any]]:
    return list(
        PendingAssetProfileQuery(repos.conn).pending_rows(
            provider=GMGN_DEX_PROFILE_PROVIDER,
            now_ms=now_ms,
            limit=limit,
        )
    )


def fetch_asset_profile(*, dex_profile_market: Any, row: dict[str, Any]) -> DexTokenProfile | None:
    if dex_profile_market is None:
        return None
    profile: object = dex_profile_market.token_profile(
        chain_id=str(row["chain_id"]),
        address=str(row["address"]),
    )
    if isinstance(profile, DexTokenProfile):
        return profile
    return None


def write_ready_asset_profile(*, repos: Any, row: dict[str, Any], profile: DexTokenProfile, now_ms: int) -> None:
    _write_ready_profile(repos=repos, row=row, profile=profile, now_ms=now_ms)


def write_missing_asset_profile(*, repos: Any, row: dict[str, Any], now_ms: int) -> None:
    _write_missing_profile(repos=repos, row=row, now_ms=now_ms)


def write_error_asset_profile(*, repos: Any, row: dict[str, Any], exc: Exception, now_ms: int) -> None:
    _write_error_profile(repos=repos, row=row, exc=exc, now_ms=now_ms)


def _empty_result(*, now_ms: int) -> dict[str, Any]:
    return {
        "provider": GMGN_DEX_PROFILE_PROVIDER,
        "selected": 0,
        "ready": 0,
        "missing": 0,
        "error": 0,
        "skipped": 0,
        "started_at_ms": int(now_ms),
        "finished_at_ms": int(now_ms),
    }


def _write_ready_profile(
    *,
    repos: Any,
    row: dict[str, Any],
    profile: DexTokenProfile,
    now_ms: int,
) -> None:
    repos.asset_profiles.upsert_ready_profile(
        asset_id=str(row["asset_id"]),
        provider=GMGN_DEX_PROFILE_PROVIDER,
        symbol=profile.symbol,
        name=profile.name,
        logo_url=profile.logo_url,
        banner_url=profile.banner_url,
        website_url=profile.website,
        twitter_username=profile.twitter_username,
        twitter_url=None,
        telegram_url=profile.telegram,
        gmgn_url=profile.gmgn_url,
        geckoterminal_url=profile.geckoterminal_url,
        description=profile.description,
        raw_payload=profile.raw,
        observed_at_ms=int(now_ms),
        next_refresh_at_ms=int(now_ms) + READY_REFRESH_MS,
    )


def _write_missing_profile(*, repos: Any, row: dict[str, Any], now_ms: int) -> None:
    repos.asset_profiles.upsert_status(
        asset_id=str(row["asset_id"]),
        provider=GMGN_DEX_PROFILE_PROVIDER,
        status="missing",
        observed_at_ms=int(now_ms),
        next_refresh_at_ms=int(now_ms) + MISSING_REFRESH_MS,
        last_error=None,
    )


def _write_error_profile(*, repos: Any, row: dict[str, Any], exc: Exception, now_ms: int) -> None:
    repos.asset_profiles.upsert_status(
        asset_id=str(row["asset_id"]),
        provider=GMGN_DEX_PROFILE_PROVIDER,
        status="error",
        observed_at_ms=int(now_ms),
        next_refresh_at_ms=int(now_ms) + ERROR_REFRESH_MS,
        last_error=str(exc)[:500],
    )
