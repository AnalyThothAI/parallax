from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from parallax.domains.token_intel._constants import (
    TOKEN_FACTOR_SNAPSHOT_VERSION,
    TOKEN_RADAR_DEFAULT_VENUE,
    TOKEN_RADAR_FACTOR_FAMILIES,
    TOKEN_RADAR_PROJECTION_NAME,
    TOKEN_RADAR_PROJECTION_VERSION,
    TOKEN_RADAR_RESOLVER_POLICY_VERSION,
    TOKEN_RADAR_SOURCE_TABLE,
    TOKEN_RADAR_VENUES,
    WINDOW_MS,
)
from parallax.domains.token_intel.queries.event_token_projection_query import EventTokenProjectionQuery
from parallax.domains.token_intel.read_models.token_target_stage_builder import build_token_target_stages
from parallax.domains.token_intel.repositories.intent_resolution_repository import (
    IntentResolutionRepository,
    token_intent_resolution_id,
)
from parallax.domains.token_intel.repositories.signal_repository import SignalAlert, SignalRepository
from parallax.domains.token_intel.repositories.token_evidence_repository import TokenEvidenceRepository
from parallax.domains.token_intel.repositories.token_intent_lookup_repository import (
    TokenIntentLookupRepository,
)
from parallax.domains.token_intel.repositories.token_intent_repository import TokenIntentRepository
from parallax.domains.token_intel.scoring.factor_snapshot_contract import (
    is_token_factor_snapshot,
    require_token_factor_snapshot,
)
from parallax.domains.token_intel.scoring.scoring_common import clamp_score, safe_float, safe_int
from parallax.domains.token_intel.services.token_evidence_builder import build_token_evidence
from parallax.domains.token_intel.services.token_intent_builder import build_token_intents
from parallax.domains.token_intel.services.token_intent_resolver import (
    TokenIntentResolutionDecision,
    TokenIntentResolver,
)
from parallax.domains.token_intel.services.token_resolution_refresh import (
    DEFAULT_REPROCESS_LIMIT,
    DEFAULT_REPROCESS_WINDOW,
    deferred_token_radar_projection,
    refresh_recent_token_state,
    reprocess_recent_token_intents,
)


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


__all__ = [
    "DEFAULT_REPROCESS_LIMIT",
    "DEFAULT_REPROCESS_WINDOW",
    "TOKEN_FACTOR_SNAPSHOT_VERSION",
    "TOKEN_RADAR_DEFAULT_VENUE",
    "TOKEN_RADAR_FACTOR_FAMILIES",
    "TOKEN_RADAR_PROJECTION_NAME",
    "TOKEN_RADAR_PROJECTION_VERSION",
    "TOKEN_RADAR_RESOLVER_POLICY_VERSION",
    "TOKEN_RADAR_SOURCE_TABLE",
    "TOKEN_RADAR_VENUES",
    "WINDOW_MS",
    "EventTokenProjectionQuery",
    "IntentResolutionRepository",
    "SignalAlert",
    "SignalRepository",
    "TokenEvidenceRepository",
    "TokenIdentityLookup",
    "TokenIdentityLookupResult",
    "TokenIntentLookupRepository",
    "TokenIntentRepository",
    "TokenIntentResolutionDecision",
    "TokenIntentResolver",
    "build_token_evidence",
    "build_token_intents",
    "build_token_target_stages",
    "clamp_score",
    "deferred_token_radar_projection",
    "is_token_factor_snapshot",
    "refresh_recent_token_state",
    "reprocess_recent_token_intents",
    "require_token_factor_snapshot",
    "safe_float",
    "safe_int",
    "token_intent_resolution_id",
]
