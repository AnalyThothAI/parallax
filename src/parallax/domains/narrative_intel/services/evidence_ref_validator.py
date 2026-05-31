from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from parallax.domains.narrative_intel.types.discussion_digest import TokenDiscussionDigest
from parallax.domains.narrative_intel.types.evidence_refs import EvidenceRef


@dataclass(frozen=True, slots=True)
class ValidationResult:
    ok: bool
    unknown_refs: list[str]
    missing_claim_refs: list[str]


class EvidenceRefValidator:
    def validate_digest_refs(
        self,
        result: TokenDiscussionDigest | dict[str, Any],
        allowed_refs: Iterable[EvidenceRef | dict[str, Any] | str],
    ) -> ValidationResult:
        allowed = {_ref_id(ref) for ref in allowed_refs if _ref_id(ref)}
        digest = result if isinstance(result, TokenDiscussionDigest) else TokenDiscussionDigest.model_validate(result)
        referenced = _digest_ref_ids(digest)
        unknown = sorted(ref_id for ref_id in referenced if ref_id not in allowed)
        missing_claims: list[str] = []
        if digest.status == "ready":
            missing_claims.extend(
                f"cluster:{cluster.cluster_key}" for cluster in digest.dominant_narratives if not cluster.evidence_refs
            )
            if not (digest.bull_view.evidence_refs or digest.bear_view.evidence_refs):
                missing_claims.append("arguments")
        return ValidationResult(
            ok=not unknown and not missing_claims,
            unknown_refs=unknown,
            missing_claim_refs=missing_claims,
        )


def _digest_ref_ids(digest: TokenDiscussionDigest) -> set[str]:
    refs = {_ref_id(ref) for ref in digest.evidence_refs}
    refs.update(_ref_id(ref) for ref in digest.bull_view.evidence_refs)
    refs.update(_ref_id(ref) for ref in digest.bear_view.evidence_refs)
    for cluster in digest.dominant_narratives:
        refs.update(_ref_id(ref) for ref in cluster.evidence_refs)
    reflexivity = digest.reflexivity_read
    if isinstance(reflexivity, dict):
        refs.update(_ref_id(ref) for ref in reflexivity.get("evidence_refs") or [])
    else:
        refs.update(_ref_id(ref) for ref in reflexivity.evidence_refs)
    return {ref for ref in refs if ref}


def _ref_id(ref: EvidenceRef | dict[str, Any] | str | None) -> str | None:
    if ref is None:
        return None
    if isinstance(ref, str):
        return ref
    if isinstance(ref, EvidenceRef):
        return ref.ref_id
    return str(ref.get("ref_id") or "").strip() or None
