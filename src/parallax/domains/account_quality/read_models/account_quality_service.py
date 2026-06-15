from __future__ import annotations

from typing import Any

from ..repositories.account_quality_repository import AccountQualityRepository


class AccountQualityService:
    def __init__(self, *, repository: AccountQualityRepository) -> None:
        self.repository = repository

    @classmethod
    def from_conn(cls, conn: Any) -> AccountQualityService:
        return cls(repository=AccountQualityRepository(conn))

    def account_quality(self, handle: str) -> dict[str, Any]:
        data = self.repository.account_quality(handle)
        return _account_quality_payload(data)

    def watched_handles(self, handles: list[str]) -> set[str]:
        profiles = self.repository.profiles_by_handles(handles)
        return {
            handle
            for handle, profile in profiles.items()
            if (profile or {}).get("watched_status") in {"active", "watched"}
        }

    def account_quality_for_handles(self, handles: list[str]) -> dict[str, Any]:
        unique_handles = _unique_handles(handles)
        accounts = [_account_quality_payload(data) for data in self.repository.accounts_quality(unique_handles)]
        return {
            "query": {"handles": unique_handles},
            "accounts": accounts,
        }


def _account_quality_payload(data: dict[str, Any]) -> dict[str, Any]:
    profile = data.get("profile")
    snapshots = data.get("quality_snapshots") or []
    latest = snapshots[0] if snapshots else None
    sample_size = int(latest.get("sample_size") or 0) if latest else 0
    return {
        "profile": profile,
        "summary": {
            "status": "ready" if sample_size >= 5 else "insufficient_sample",
            "sample_size": sample_size,
            "precision_score": latest.get("precision_score") if latest else None,
            "early_call_score": latest.get("early_call_score") if latest else None,
            "spam_risk_score": latest.get("spam_risk_score") if latest else None,
            "avg_realized_return": latest.get("avg_realized_return") if latest else None,
        },
        "token_call_stats": data.get("token_call_stats") or [],
        "quality_snapshots": snapshots,
    }


def _handle(handle: str) -> str:
    return handle.strip().lstrip("@").lower()


def _unique_handles(handles: list[str]) -> list[str]:
    normalized = [_handle(handle) for handle in handles if _handle(handle)]
    seen: set[str] = set()
    unique_handles: list[str] = []
    for handle in normalized:
        if handle in seen:
            continue
        seen.add(handle)
        unique_handles.append(handle)
    return unique_handles
