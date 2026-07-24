from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class TokenIdentityLookupResult:
    resolution_status: str
    target_type: str | None
    target_id: str | None
    display_symbol: str | None
    display_name: str | None
    reason_codes: list[str]
    candidate_targets: list[dict[str, object]]


class TokenIdentityLookup(Protocol):
    def resolve_address(self, *, chain_id: str | None, address: str) -> TokenIdentityLookupResult: ...

    def resolve_symbol(self, *, symbol: str) -> TokenIdentityLookupResult: ...


__all__ = ["TokenIdentityLookup", "TokenIdentityLookupResult"]
