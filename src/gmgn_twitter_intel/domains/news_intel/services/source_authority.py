from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

ROLE_EVENT_TYPES: dict[str, frozenset[str]] = {
    "official_exchange": frozenset(
        {"exchange_listing", "exchange_delisting", "maintenance", "exchange_incident"}
    ),
    "official_regulator": frozenset({"regulatory_action", "macro_policy"}),
    "official_protocol": frozenset(
        {"protocol_upgrade", "security_incident", "governance_tokenomics", "developer_release"}
    ),
    "official_issuer": frozenset({"etf_fund_flow", "equity_company_event"}),
    "developer_signal": frozenset({"developer_release", "protocol_upgrade"}),
}
ACCEPTANCE_GRADE_REALIS = frozenset({"actual", "scheduled", "official_proposed"})


@dataclass(frozen=True, slots=True)
class SourceAuthorityDecision:
    acceptance_allowed: bool
    rejection_reasons: list[str]


def validate_source_authority(
    *,
    source_role: str,
    authority_scope: Mapping[str, Any] | None,
    event_type: str,
    source_domain: str,
    affected_targets: list[dict[str, object]],
    realis: str,
) -> SourceAuthorityDecision:
    reasons: list[str] = []
    normalized_role = _normalized_text(source_role)
    normalized_event_type = _normalized_text(event_type)
    normalized_source_domain = _normalized_domain(source_domain)
    scope = dict(authority_scope or {})

    if _normalized_text(realis) not in ACCEPTANCE_GRADE_REALIS:
        reasons.append("realis_not_acceptance_grade")

    role_event_types = ROLE_EVENT_TYPES.get(normalized_role, frozenset())
    if normalized_event_type not in role_event_types:
        reasons.append("source_not_authoritative_for_event_type")
    elif not _has_explicit_scope(scope):
        reasons.append("authority_scope_missing")

    scoped_event_types = _normalized_set(scope.get("event_types"))
    if scoped_event_types and normalized_event_type not in scoped_event_types:
        reasons.append("event_type_out_of_authority_scope")

    scoped_domains = {_normalized_domain(value) for value in _iter_values(scope.get("domains"))}
    scoped_domains.discard("")
    if scoped_domains and not _domain_in_scope(normalized_source_domain, scoped_domains):
        reasons.append("source_domain_out_of_authority_scope")

    scoped_target_ids = _normalized_set(scope.get("target_ids"))
    scoped_targets = _normalized_target_scope(scope.get("targets"))
    scoped_symbols = _normalized_set(scope.get("symbols") or scope.get("asset_symbols"))
    if scoped_target_ids and not _has_scoped_target_id(affected_targets, scoped_target_ids):
        _append_reason(reasons, "target_out_of_authority_scope")
    if scoped_targets and not _has_scoped_target(affected_targets, scoped_targets):
        _append_reason(reasons, "target_out_of_authority_scope")
    if scoped_symbols and not _has_scoped_symbol(affected_targets, scoped_symbols):
        _append_reason(reasons, "target_out_of_authority_scope")

    if not any(bool(target.get("production_eligible")) for target in affected_targets):
        reasons.append("target_identity_not_production_eligible")

    return SourceAuthorityDecision(acceptance_allowed=not reasons, rejection_reasons=reasons)


def _normalized_set(value: object) -> set[str]:
    return {_normalized_text(item) for item in _iter_values(value) if _normalized_text(item)}


def _has_explicit_scope(scope: Mapping[str, Any]) -> bool:
    for key in ("event_types", "domains", "targets", "target_ids", "symbols", "asset_symbols"):
        if list(_iter_values(scope.get(key))):
            return True
    return False


def _normalized_target_scope(value: object) -> list[dict[str, str]]:
    targets: list[dict[str, str]] = []
    for item in _iter_values(value):
        if isinstance(item, Mapping):
            target = {
                "target_type": _normalized_text(item.get("target_type")),
                "target_id": _normalized_text(item.get("target_id")),
            }
            if target["target_type"] or target["target_id"]:
                targets.append(target)
        else:
            target_id = _normalized_text(item)
            if target_id:
                targets.append({"target_type": "", "target_id": target_id})
    return targets


def _append_reason(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def _iter_values(value: object) -> Iterable[object]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(","))
    if isinstance(value, bytes | bytearray):
        try:
            return _iter_values(bytes(value).decode("utf-8"))
        except UnicodeDecodeError:
            return (str(value),)
    if isinstance(value, Mapping):
        return ()
    if isinstance(value, Iterable):
        return value
    return (value,)


def _normalized_text(value: object) -> str:
    return str(value or "").strip().lower()


def _normalized_domain(value: object) -> str:
    normalized = _normalized_text(value)
    if normalized.startswith("www."):
        return normalized[4:]
    return normalized


def _domain_in_scope(source_domain: str, scoped_domains: set[str]) -> bool:
    if not source_domain:
        return False
    return any(source_domain == domain or source_domain.endswith(f".{domain}") for domain in scoped_domains)


def _has_scoped_target_id(targets: list[dict[str, object]], scoped_target_ids: set[str]) -> bool:
    return any(_normalized_text(target.get("target_id")) in scoped_target_ids for target in targets)


def _has_scoped_target(targets: list[dict[str, object]], scoped_targets: list[dict[str, str]]) -> bool:
    for target in targets:
        target_type = _normalized_text(target.get("target_type"))
        target_id = _normalized_text(target.get("target_id"))
        for scoped in scoped_targets:
            if scoped["target_id"] and target_id != scoped["target_id"]:
                continue
            if scoped["target_type"] and target_type != _normalized_text(scoped["target_type"]):
                continue
            return True
    return False


def _has_scoped_symbol(targets: list[dict[str, object]], scoped_symbols: set[str]) -> bool:
    for target in targets:
        symbols = (
            target.get("display_symbol"),
            target.get("observed_symbol"),
            str(target.get("target_id") or "").split(":")[-1],
        )
        if any(_normalized_text(symbol) in scoped_symbols for symbol in symbols):
            return True
    return False


__all__ = ["ROLE_EVENT_TYPES", "SourceAuthorityDecision", "validate_source_authority"]
