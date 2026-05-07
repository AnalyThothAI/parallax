from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .token_evidence_builder import TokenEvidenceInput
from .token_intent_builder import TokenIntentInput

RESOLVER_POLICY_VERSION = "token_intent_resolver_v1"


@dataclass(frozen=True, slots=True)
class TokenIntentResolutionDecision:
    intent_id: str
    event_id: str
    asset_id: str | None
    primary_venue_id: str | None
    resolution_status: str
    identity_status: str
    confidence: float
    resolver_policy_version: str
    reasons: list[str]
    risks: list[str]
    decision_time_ms: int
    created_at_ms: int


class TokenIntentResolver:
    def __init__(self, *, assets, resolutions):
        self.assets = assets
        self.resolutions = resolutions

    def resolve(
        self,
        intent: TokenIntentInput | dict[str, Any],
        evidence: list[TokenEvidenceInput] | list[dict[str, Any]],
        *,
        decision_time_ms: int | None = None,
        persist: bool = False,
        commit: bool = False,
    ) -> TokenIntentResolutionDecision:
        now_ms = int(decision_time_ms or _intent_created_at(intent) or time.time() * 1000)
        decision = self._decision(intent, evidence, now_ms=now_ms)
        if persist:
            self.resolutions.insert_resolution(decision, commit=commit)
        return decision

    def _decision(
        self,
        intent: TokenIntentInput | dict[str, Any],
        evidence: list[TokenEvidenceInput] | list[dict[str, Any]],
        *,
        now_ms: int,
    ) -> TokenIntentResolutionDecision:
        chain = _intent_value(intent, "chain_hint")
        address = _intent_value(intent, "address_hint")
        if address:
            if chain:
                symbol = _intent_value(intent, "display_symbol") or address
                result = self.assets.upsert_dex_asset(
                    chain=chain,
                    address=address,
                    symbol=symbol,
                    event_id=str(_intent_value(intent, "event_id")),
                    observed_at_ms=now_ms,
                    provider="gmgn" if _has_gmgn_payload(evidence) else "deterministic",
                    commit=False,
                )
                venue = result.venue or {}
                return _decision(
                    intent,
                    asset_id=str(result.asset["asset_id"]),
                    primary_venue_id=str(venue.get("venue_id")) if venue.get("venue_id") else None,
                    resolution_status="direct",
                    identity_status="resolved",
                    confidence=1.0,
                    reasons=["gmgn_payload_direct"] if _has_gmgn_payload(evidence) else ["exact_ca_with_chain_hint"],
                    risks=[],
                    now_ms=now_ms,
                )
            candidates = self.assets.candidates_for_ca(chain=chain, address=address)
            real = [_real_candidate(row) for row in candidates if _is_real_candidate(row)]
            if len(real) == 1:
                candidate = real[0]
                return _decision(
                    intent,
                    asset_id=str(candidate["asset_id"]),
                    primary_venue_id=str(candidate["venue_id"]),
                    resolution_status="direct",
                    identity_status="resolved",
                    confidence=1.0 if chain else 0.95,
                    reasons=["exact_ca_with_chain_hint"] if chain else ["local_exact_ca_match"],
                    risks=[],
                    now_ms=now_ms,
                )
            if len(real) > 1:
                return _decision(
                    intent,
                    asset_id=None,
                    primary_venue_id=None,
                    resolution_status="ambiguous",
                    identity_status="ambiguous",
                    confidence=0.55,
                    reasons=["multiple_local_ca_matches"],
                    risks=["chain_required_for_exact_ca"],
                    now_ms=now_ms,
                )
            return _decision(
                intent,
                asset_id=None,
                primary_venue_id=None,
                resolution_status="unresolved",
                identity_status="unresolved",
                confidence=0.35,
                reasons=["ca_requires_provider_resolution"],
                risks=["provider_resolution_pending"],
                now_ms=now_ms,
            )

        symbol = _intent_value(intent, "display_symbol")
        if symbol:
            candidates = self.assets.candidates_for_symbol(symbol)
            real = [_real_candidate(row) for row in candidates if _is_real_candidate(row)]
            asset_ids = {str(row["asset_id"]) for row in real if row.get("asset_id")}
            if len(asset_ids) == 1 and real:
                candidate = real[0]
                return _decision(
                    intent,
                    asset_id=str(candidate["asset_id"]),
                    primary_venue_id=str(candidate["venue_id"]) if candidate.get("venue_id") else None,
                    resolution_status="selected",
                    identity_status="resolved",
                    confidence=float(candidate.get("asset_confidence") or candidate.get("alias_confidence") or 0.85),
                    reasons=["single_local_symbol_candidate"],
                    risks=[],
                    now_ms=now_ms,
                )
            if real:
                return _decision(
                    intent,
                    asset_id=None,
                    primary_venue_id=None,
                    resolution_status="ambiguous",
                    identity_status="ambiguous",
                    confidence=0.5,
                    reasons=["multiple_local_symbol_candidates"],
                    risks=["candidate_selection_requires_provider_resolution"],
                    now_ms=now_ms,
                )

        return _decision(
            intent,
            asset_id=None,
            primary_venue_id=None,
            resolution_status="unresolved",
            identity_status="unresolved",
            confidence=0.25,
            reasons=["no_local_identity_match"],
            risks=["provider_resolution_pending"],
            now_ms=now_ms,
        )


def _decision(
    intent: TokenIntentInput | dict[str, Any],
    *,
    asset_id: str | None,
    primary_venue_id: str | None,
    resolution_status: str,
    identity_status: str,
    confidence: float,
    reasons: list[str],
    risks: list[str],
    now_ms: int,
) -> TokenIntentResolutionDecision:
    return TokenIntentResolutionDecision(
        intent_id=str(_intent_value(intent, "intent_id")),
        event_id=str(_intent_value(intent, "event_id")),
        asset_id=asset_id,
        primary_venue_id=primary_venue_id,
        resolution_status=resolution_status,
        identity_status=identity_status,
        confidence=confidence,
        resolver_policy_version=RESOLVER_POLICY_VERSION,
        reasons=reasons,
        risks=risks,
        decision_time_ms=now_ms,
        created_at_ms=now_ms,
    )


def _real_candidate(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row)


def _is_real_candidate(row: dict[str, Any]) -> bool:
    asset_id = str(row.get("asset_id") or "")
    identity_status = str(row.get("identity_status") or "")
    asset_type = str(row.get("asset_type") or "")
    if not asset_id or not row.get("venue_id"):
        return False
    if identity_status in {"unresolved", "ambiguous"}:
        return False
    if asset_type.startswith(("unresolved", "ambiguous")):
        return False
    return not asset_id.startswith(("asset:unresolved", "asset:ambiguous"))


def _intent_value(intent: TokenIntentInput | dict[str, Any], key: str) -> Any:
    return intent.get(key) if isinstance(intent, dict) else getattr(intent, key)


def _intent_created_at(intent: TokenIntentInput | dict[str, Any]) -> int | None:
    value = _intent_value(intent, "created_at_ms")
    return int(value) if value is not None else None


def _has_gmgn_payload(evidence: list[TokenEvidenceInput] | list[dict[str, Any]]) -> bool:
    for item in evidence:
        value = item.get("evidence_type") if isinstance(item, dict) else item.evidence_type
        if value == "gmgn_token_payload":
            return True
    return False
