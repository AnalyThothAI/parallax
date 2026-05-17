from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.asset_market.providers import (
    DexProfileSource,
    DexProviderTemporarilyUnavailable,
    DexTokenProfile,
)
from gmgn_twitter_intel.domains.asset_market.queries.pending_asset_profile_query import PendingAssetProfileQuery
from gmgn_twitter_intel.domains.asset_market.repositories.asset_profile_repository import (
    ERROR_REFRESH_MS,
    MISSING_REFRESH_MS,
    READY_REFRESH_MS,
)


def refresh_asset_profiles_once(
    *,
    repos: Any,
    profile_source: DexProfileSource,
    now_ms: int,
    limit: int = 50,
) -> dict[str, Any]:
    result = _empty_result(provider=profile_source.provider, now_ms=now_ms)

    rows = PendingAssetProfileQuery(repos.conn).pending_rows(
        provider=profile_source.provider,
        now_ms=now_ms,
        limit=limit,
    )
    result["selected"] = len(rows)
    for row in rows:
        try:
            profile = fetch_asset_profile(profile_source=profile_source, row=row)
        except DexProviderTemporarilyUnavailable as exc:
            result["provider_blocked"] = 1
            result["last_error"] = str(exc)[:500]
            break
        except Exception as exc:
            _write_error_profile(repos=repos, provider=profile_source.provider, row=row, exc=exc, now_ms=now_ms)
            result["error"] += 1
            continue

        if isinstance(profile, DexTokenProfile):
            _write_ready_profile(repos=repos, provider=profile_source.provider, row=row, profile=profile, now_ms=now_ms)
            result["ready"] += 1
            continue

        _write_missing_profile(repos=repos, provider=profile_source.provider, row=row, now_ms=now_ms)
        result["missing"] += 1
    return result


def select_due_asset_profile_rows(*, repos: Any, provider: str, now_ms: int, limit: int = 50) -> list[dict[str, Any]]:
    return list(
        PendingAssetProfileQuery(repos.conn).pending_rows(
            provider=provider,
            now_ms=now_ms,
            limit=limit,
        )
    )


def fetch_asset_profile(*, profile_source: DexProfileSource, row: dict[str, Any]) -> DexTokenProfile | None:
    profile: object = profile_source.market.token_profile(
        chain_id=str(row["chain_id"]),
        address=str(row["address"]),
    )
    if isinstance(profile, DexTokenProfile):
        return profile
    return None


def write_ready_asset_profile(
    *, repos: Any, provider: str, row: dict[str, Any], profile: DexTokenProfile, now_ms: int
) -> None:
    _write_ready_profile(repos=repos, provider=provider, row=row, profile=profile, now_ms=now_ms)


def write_missing_asset_profile(*, repos: Any, provider: str, row: dict[str, Any], now_ms: int) -> None:
    _write_missing_profile(repos=repos, provider=provider, row=row, now_ms=now_ms)


def write_error_asset_profile(*, repos: Any, provider: str, row: dict[str, Any], exc: Exception, now_ms: int) -> None:
    _write_error_profile(repos=repos, provider=provider, row=row, exc=exc, now_ms=now_ms)


def _empty_result(*, provider: str, now_ms: int) -> dict[str, Any]:
    return {
        "provider": provider,
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
    provider: str,
    row: dict[str, Any],
    profile: DexTokenProfile,
    now_ms: int,
) -> None:
    repos.asset_profiles.upsert_ready_profile(
        asset_id=str(row["asset_id"]),
        provider=provider,
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


def _write_missing_profile(*, repos: Any, provider: str, row: dict[str, Any], now_ms: int) -> None:
    repos.asset_profiles.upsert_status(
        asset_id=str(row["asset_id"]),
        provider=provider,
        status="missing",
        observed_at_ms=int(now_ms),
        next_refresh_at_ms=int(now_ms) + MISSING_REFRESH_MS,
        last_error=None,
    )


def _write_error_profile(*, repos: Any, provider: str, row: dict[str, Any], exc: Exception, now_ms: int) -> None:
    repos.asset_profiles.upsert_status(
        asset_id=str(row["asset_id"]),
        provider=provider,
        status="error",
        observed_at_ms=int(now_ms),
        next_refresh_at_ms=int(now_ms) + ERROR_REFRESH_MS,
        last_error=str(exc)[:500],
    )
