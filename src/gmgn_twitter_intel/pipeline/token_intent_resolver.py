from __future__ import annotations

from typing import Any

from .deterministic_token_resolver import (
    DeterministicResolution,
    DeterministicTokenResolver,
    MentionKeys,
)
from .token_evidence_builder import TokenEvidenceInput
from .token_intent_builder import TokenIntentInput

TokenIntentResolutionDecision = DeterministicResolution


class TokenIntentResolver:
    def __init__(self, *, registry, resolutions):
        self.registry = registry
        self.resolutions = resolutions
        self.resolver = DeterministicTokenResolver(registry=registry)

    def resolve(
        self,
        intent: TokenIntentInput | dict[str, Any],
        evidence: list[TokenEvidenceInput] | list[dict[str, Any]],
        *,
        decision_time_ms: int | None = None,
        persist: bool = False,
        commit: bool = False,
    ) -> DeterministicResolution:
        now_ms = int(decision_time_ms or _intent_created_at(intent) or 0)
        decision = self.resolver.resolve(
            intent_id=str(_intent_value(intent, "intent_id")),
            event_id=str(_intent_value(intent, "event_id")),
            keys=_mention_keys(intent, evidence),
            decision_time_ms=now_ms,
        )
        if persist:
            self.resolutions.insert_resolution(decision, commit=False)
            if commit:
                self.resolutions.conn.commit()
        return decision


def _mention_keys(
    intent: TokenIntentInput | dict[str, Any],
    evidence: list[TokenEvidenceInput] | list[dict[str, Any]],
) -> MentionKeys:
    cex_pricefeed_id = _cex_pricefeed_id(evidence)
    return MentionKeys(
        symbol=_intent_value(intent, "display_symbol"),
        chain_id=_chain_id(_intent_value(intent, "chain_hint")),
        address=_address(_intent_value(intent, "address_hint")),
        cex_pricefeed_id=cex_pricefeed_id,
        exchange=_exchange_hint(evidence),
    )


def _cex_pricefeed_id(evidence: list[TokenEvidenceInput] | list[dict[str, Any]]) -> str | None:
    for item in evidence:
        evidence_type = _evidence_value(item, "evidence_type")
        if evidence_type == "cex_pricefeed":
            return _evidence_value(item, "provider_ref")
    return None


def _exchange_hint(evidence: list[TokenEvidenceInput] | list[dict[str, Any]]) -> str | None:
    for item in evidence:
        provider = _evidence_value(item, "provider")
        if provider:
            return str(provider).lower()
    return None


def _intent_value(intent: TokenIntentInput | dict[str, Any], key: str) -> Any:
    return intent.get(key) if isinstance(intent, dict) else getattr(intent, key)


def _evidence_value(evidence: TokenEvidenceInput | dict[str, Any], key: str) -> Any:
    return evidence.get(key) if isinstance(evidence, dict) else getattr(evidence, key)


def _intent_created_at(intent: TokenIntentInput | dict[str, Any]) -> int | None:
    value = _intent_value(intent, "created_at_ms")
    return int(value) if value is not None else None


def _chain_id(chain: Any) -> str | None:
    if chain is None:
        return None
    normalized = str(chain).strip().lower()
    if normalized in {"", "unknown", "evm_unknown"}:
        return None
    if normalized in {"eth", "ethereum"}:
        return "eip155:1"
    if normalized == "base":
        return "eip155:8453"
    if normalized in {"bsc", "bnb"}:
        return "eip155:56"
    if normalized in {"sol", "solana"}:
        return "solana"
    return normalized


def _address(address: Any) -> str | None:
    if address is None:
        return None
    value = str(address).strip()
    return value.lower() if value.startswith("0x") else value
