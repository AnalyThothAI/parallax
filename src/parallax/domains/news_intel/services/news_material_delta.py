from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from parallax.domains.news_intel.types.news_source_role_rank import source_role_rank


@dataclass(frozen=True, slots=True)
class NewsMaterialDelta:
    has_delta: bool
    reasons: list[str]
    evidence: dict[str, Any]


def decide_news_material_delta(
    *,
    item: Mapping[str, Any],
    representative_item: Mapping[str, Any] | None,
    entities: Sequence[Mapping[str, Any]],
    representative_entities: Sequence[Mapping[str, Any]],
    fact_candidates: Sequence[Mapping[str, Any]],
    representative_fact_candidates: Sequence[Mapping[str, Any]],
) -> NewsMaterialDelta:
    if representative_item is None:
        return NewsMaterialDelta(has_delta=True, reasons=["no_representative"], evidence={})

    reasons: list[str] = []
    evidence: dict[str, Any] = {}
    _source_role_delta(item, representative_item, reasons=reasons, evidence=evidence)
    _entity_delta(entities, representative_entities, reasons=reasons, evidence=evidence)
    _fact_delta(fact_candidates, representative_fact_candidates, reasons=reasons, evidence=evidence)
    _content_delta(item, representative_item, reasons=reasons, evidence=evidence)

    return NewsMaterialDelta(has_delta=bool(reasons), reasons=list(dict.fromkeys(reasons)), evidence=evidence)


def _source_role_delta(
    item: Mapping[str, Any],
    representative_item: Mapping[str, Any],
    *,
    reasons: list[str],
    evidence: dict[str, Any],
) -> None:
    current = str(item.get("source_role") or "").strip().lower()
    previous = str(representative_item.get("source_role") or "").strip().lower()
    if source_role_rank(current) > source_role_rank(previous):
        reasons.append("source_role_upgrade")
        evidence["source_role"] = {"current": current, "representative": previous}


def _entity_delta(
    entities: Sequence[Mapping[str, Any]],
    representative_entities: Sequence[Mapping[str, Any]],
    *,
    reasons: list[str],
    evidence: dict[str, Any],
) -> None:
    current = _entity_keys(entities)
    previous = _entity_keys(representative_entities)
    new_entities = sorted(current - previous)
    if new_entities:
        reasons.append("new_market_entity")
        evidence["new_entities"] = new_entities[:20]


def _fact_delta(
    fact_candidates: Sequence[Mapping[str, Any]],
    representative_fact_candidates: Sequence[Mapping[str, Any]],
    *,
    reasons: list[str],
    evidence: dict[str, Any],
) -> None:
    current = _accepted_fact_keys(fact_candidates)
    previous = _accepted_fact_keys(representative_fact_candidates)
    new_facts = sorted(current - previous)
    if new_facts:
        reasons.append("new_accepted_fact")
        evidence["new_facts"] = new_facts[:20]


def _content_delta(
    item: Mapping[str, Any],
    representative_item: Mapping[str, Any],
    *,
    reasons: list[str],
    evidence: dict[str, Any],
) -> None:
    current_hash = str(item.get("content_hash") or "").strip()
    previous_hash = str(representative_item.get("content_hash") or "").strip()
    if current_hash and previous_hash and current_hash != previous_hash:
        title_current = str(item.get("title_fingerprint") or item.get("title") or "").strip()
        title_previous = str(representative_item.get("title_fingerprint") or representative_item.get("title") or "")
        if title_current and title_previous and title_current != title_previous:
            reasons.append("new_material_content")
            evidence["content_hash"] = {"current": current_hash, "representative": previous_hash}


def _entity_keys(rows: Sequence[Mapping[str, Any]]) -> set[str]:
    result: set[str] = set()
    for row in rows:
        key = (
            str(
                row.get("target_id")
                or row.get("normalized_value")
                or row.get("display_symbol")
                or row.get("raw_value")
                or row.get("entity_id")
                or ""
            )
            .strip()
            .lower()
        )
        entity_type = str(row.get("entity_type") or "").strip().lower()
        if key:
            result.add(f"{entity_type}:{key}")
    return result


def _accepted_fact_keys(rows: Sequence[Mapping[str, Any]]) -> set[str]:
    result: set[str] = set()
    for row in rows:
        if str(row.get("validation_status") or "").strip() not in {"", "accepted"}:
            continue
        event_type = str(row.get("event_type") or "").strip().lower()
        claim = str(row.get("claim") or row.get("fact_candidate_id") or "").strip().lower()
        if event_type or claim:
            result.add(f"{event_type}:{claim[:120]}")
    return result


__all__ = ["NewsMaterialDelta", "decide_news_material_delta"]
