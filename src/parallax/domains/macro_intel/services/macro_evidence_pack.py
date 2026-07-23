from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from parallax.domains.macro_intel._constants import MACRO_EVIDENCE_PROJECTION_VERSION
from parallax.domains.macro_intel.services.daily_macro_judgment import (
    EvidenceAvailability,
    EvidenceExclusion,
    EvidencePackHealth,
    EvidencePackHealthStatus,
    MacroEvidenceItem,
    MacroEvidencePack,
    MacroTextEvidence,
    canonical_json_hash,
)
from parallax.domains.macro_intel.services.macro_concept_manifest import (
    MACRO_CONCEPT_MANIFEST,
)
from parallax.domains.macro_intel.services.macro_evidence_snapshot import (
    build_macro_evidence_snapshot,
)

MACRO_EVIDENCE_COMPILER_VERSION = "macro_evidence_compiler_v1"
MACRO_NEWS_SELECTION_VERSION = "macro_news_selection_v1"
_NEW_YORK = ZoneInfo("America/New_York")
_MARKET_CLOSE_PREFIXES = ("asset:", "vol:", "fx:", "commodity:", "crypto:")
_MAX_AGENT_FACTS_PER_CONCEPT = 2
_MAX_NEWS_TEXTS = 12
_MAX_TEXT_SUMMARY_CHARS = 1_200
_MAX_TEXT_BODY_CHARS = 4_000


def compile_macro_evidence_pack(
    *,
    session_date: date,
    market_cutoff_ms: int,
    sealed_at_ms: int,
    observation_rows: Sequence[Mapping[str, Any]],
    news_rows: Sequence[Mapping[str, Any]] = (),
) -> MacroEvidencePack:
    if sealed_at_ms < market_cutoff_ms:
        raise ValueError("macro_evidence_pack_sealed_before_cutoff")
    eligible_rows: list[dict[str, Any]] = []
    exclusions: list[EvidenceExclusion] = []
    for raw_row in observation_rows:
        row = dict(raw_row)
        eligibility = _observation_eligibility(
            row,
            session_date=session_date,
            market_cutoff_ms=market_cutoff_ms,
            sealed_at_ms=sealed_at_ms,
        )
        if eligibility is None:
            exclusions.append(_observation_exclusion(row, reason=_observation_exclusion_reason(row, sealed_at_ms)))
            continue
        available_at_ms, availability = eligibility
        row["_available_at_ms"] = available_at_ms
        row["_availability"] = availability
        eligible_rows.append(row)

    snapshot_rows = [_snapshot_row(row) for row in eligible_rows]
    snapshot = build_macro_evidence_snapshot(snapshot_rows, computed_at_ms=market_cutoff_ms)
    pages = {page_id: dict(snapshot[page_id]) for page_id in _page_ids()}
    _require_page_identity(pages, session_date=session_date)

    selected_rows = _bounded_agent_rows(eligible_rows)
    evidence = tuple(_evidence_item(row) for row in selected_rows)
    texts, text_exclusions = _select_news_texts(
        news_rows,
        market_cutoff_ms=market_cutoff_ms,
        sealed_at_ms=sealed_at_ms,
    )
    exclusions.extend(text_exclusions)
    health = _pack_health(pages=pages, evidence=evidence, exclusions=exclusions)
    return MacroEvidencePack(
        session_date=session_date,
        market_cutoff_ms=market_cutoff_ms,
        sealed_at_ms=sealed_at_ms,
        projection_version=MACRO_EVIDENCE_PROJECTION_VERSION,
        pages=pages,
        evidence=evidence,
        texts=texts,
        exclusions=tuple(exclusions),
        health=health,
    )


def _observation_eligibility(
    row: Mapping[str, Any],
    *,
    session_date: date,
    market_cutoff_ms: int,
    sealed_at_ms: int,
) -> tuple[int, EvidenceAvailability] | None:
    try:
        ingested_at_ms = _required_int(row.get("ingested_at_ms"))
    except (TypeError, ValueError):
        return None
    if ingested_at_ms < 0 or ingested_at_ms > sealed_at_ms:
        return None
    source_timestamp = str(row.get("source_ts") or "").strip()
    if not source_timestamp:
        return None
    exact = _parse_exact_timestamp_ms(source_timestamp)
    if exact is not None:
        if exact > market_cutoff_ms:
            return None
        return exact, EvidenceAvailability.EXACT_TIMESTAMP
    source_date = _parse_date_only(source_timestamp)
    if source_date is None or source_date > session_date:
        return None
    concept_key = str(row.get("concept_key") or "")
    if source_date == session_date:
        if not concept_key.startswith(_MARKET_CLOSE_PREFIXES):
            return None
        return market_cutoff_ms, EvidenceAvailability.SESSION_CLOSE
    prior_date_end = datetime.combine(source_date, time(23, 59, 59, 999999), tzinfo=_NEW_YORK)
    return int(prior_date_end.astimezone(UTC).timestamp() * 1000), EvidenceAvailability.PRIOR_DATE


def _observation_exclusion_reason(row: Mapping[str, Any], sealed_at_ms: int) -> str:
    source_timestamp = str(row.get("source_ts") or "").strip()
    if not source_timestamp:
        return "source_availability_missing"
    try:
        ingested_at_ms = _required_int(row.get("ingested_at_ms"))
    except (TypeError, ValueError):
        return "ingestion_lineage_invalid"
    if ingested_at_ms > sealed_at_ms:
        return "not_persisted_at_seal"
    if _parse_exact_timestamp_ms(source_timestamp) is None and _parse_date_only(source_timestamp) is None:
        return "source_availability_unparseable"
    return "source_availability_after_or_unproven_at_cutoff"


def _snapshot_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "concept_key": str(row["concept_key"]),
        "observed_at": _as_date(row["observed_at"]),
        "value_numeric": row.get("value_numeric"),
        "source_name": str(row["source_name"]),
        "series_key": str(row["series_key"]),
        "unit": row.get("unit"),
        "frequency": row.get("frequency"),
        "data_quality": str(row.get("data_quality") or ""),
        "event_metadata_json": _event_metadata(row),
    }


def _bounded_agent_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for raw_row in rows:
        row = dict(raw_row)
        concept_key = str(row.get("concept_key") or "")
        if concept_key not in MACRO_CONCEPT_MANIFEST:
            continue
        grouped.setdefault(concept_key, []).append(row)
    selected: list[dict[str, Any]] = []
    for concept_key in sorted(grouped):
        candidates = sorted(
            grouped[concept_key],
            key=lambda row: (
                _as_date(row["observed_at"]),
                int(row["_available_at_ms"]),
                str(row.get("source_name") or ""),
                str(row.get("series_key") or ""),
            ),
            reverse=True,
        )
        selected.extend(candidates[:_MAX_AGENT_FACTS_PER_CONCEPT])
    return selected


def _evidence_item(row: Mapping[str, Any]) -> MacroEvidenceItem:
    concept_key = str(row["concept_key"])
    spec = MACRO_CONCEPT_MANIFEST[concept_key]
    observed_at = _as_date(row["observed_at"])
    content = {
        "value_numeric": _json_value(row.get("value_numeric")),
        "unit": row.get("unit"),
        "frequency": row.get("frequency"),
        "event_metadata": _event_metadata(row),
        "source_fact_payload_hash": str(row.get("fact_payload_hash") or ""),
    }
    content_hash = canonical_json_hash(content)
    evidence_ref = f"macro:{concept_key}:{observed_at.isoformat()}:{row.get('source_name') or ''!s}:{content_hash[:12]}"
    return MacroEvidenceItem(
        evidence_ref=evidence_ref,
        page_id=spec.page,
        source_name=str(row["source_name"]),
        concept_key=concept_key,
        series_key=str(row["series_key"]),
        observed_at=observed_at,
        available_at_ms=int(row["_available_at_ms"]),
        availability=row["_availability"],
        source_timestamp=str(row["source_ts"]),
        ingested_at_ms=int(row["ingested_at_ms"]),
        data_quality=str(row.get("data_quality") or ""),
        selection_rule=f"{MACRO_EVIDENCE_COMPILER_VERSION}:{row['_availability']}",
        content_hash=content_hash,
        content=content,
    )


def _select_news_texts(
    rows: Sequence[Mapping[str, Any]],
    *,
    market_cutoff_ms: int,
    sealed_at_ms: int,
) -> tuple[tuple[MacroTextEvidence, ...], list[EvidenceExclusion]]:
    selected: list[MacroTextEvidence] = []
    exclusions: list[EvidenceExclusion] = []
    sorted_rows = sorted(
        (dict(row) for row in rows),
        key=lambda row: (
            int(row.get("published_at_ms") or -1),
            str(row.get("source_id") or ""),
            str(row.get("news_item_id") or ""),
        ),
        reverse=True,
    )
    seen_content: set[str] = set()
    for row in sorted_rows:
        source_name = str(row.get("source_name") or row.get("source_id") or "")
        if str(row.get("trust_tier") or "") not in {"official", "high"}:
            exclusions.append(EvidenceExclusion(source_name=source_name, reason="news_trust_tier_ineligible"))
            continue
        if str(row.get("source_quality_status") or "") not in {"healthy", "degraded"}:
            exclusions.append(EvidenceExclusion(source_name=source_name, reason="news_source_quality_ineligible"))
            continue
        try:
            published_at_ms = _required_int(row.get("published_at_ms"))
            fetched_at_ms = _required_int(row.get("fetched_at_ms"))
        except (TypeError, ValueError):
            exclusions.append(EvidenceExclusion(source_name=source_name, reason="news_lineage_invalid"))
            continue
        if published_at_ms > market_cutoff_ms or fetched_at_ms > sealed_at_ms:
            exclusions.append(EvidenceExclusion(source_name=source_name, reason="news_after_cutoff_or_seal"))
            continue
        visible = {
            "title": str(row.get("title") or "").strip(),
            "summary": str(row.get("summary") or "").strip()[:_MAX_TEXT_SUMMARY_CHARS],
            "body_text": str(row.get("body_text") or "").strip()[:_MAX_TEXT_BODY_CHARS],
            "canonical_url": str(row.get("canonical_url") or "").strip(),
        }
        visible_hash = canonical_json_hash(visible)
        if visible_hash in seen_content:
            continue
        seen_content.add(visible_hash)
        item_id = str(row.get("news_item_id") or visible_hash[:16])
        selected.append(
            MacroTextEvidence(
                evidence_ref=f"news:{item_id}:{visible_hash[:12]}",
                source_id=str(row.get("source_id") or ""),
                source_name=source_name,
                trust_tier=str(row["trust_tier"]),
                source_quality=str(row["source_quality_status"]),
                published_at_ms=published_at_ms,
                fetched_at_ms=fetched_at_ms,
                title=visible["title"],
                summary=visible["summary"],
                body_text=visible["body_text"],
                canonical_url=visible["canonical_url"],
                source_content_hash=str(row.get("content_hash") or ""),
                content_hash=visible_hash,
                selection_rule=MACRO_NEWS_SELECTION_VERSION,
            )
        )
        if len(selected) >= _MAX_NEWS_TEXTS:
            break
    return tuple(selected), exclusions


def _required_int(value: Any) -> int:
    if value is None or isinstance(value, bool):
        raise ValueError("integer_required")
    return int(value)


def _pack_health(
    *,
    pages: Mapping[str, Mapping[str, Any]],
    evidence: Sequence[MacroEvidenceItem],
    exclusions: Sequence[EvidenceExclusion],
) -> EvidencePackHealth:
    if not evidence:
        return EvidencePackHealth(
            status=EvidencePackHealthStatus.BLOCKED,
            global_reasons=("no_eligible_macro_evidence",),
        )
    local_reasons: list[str] = []
    no_call: set[int] = set()
    for page_id, page in pages.items():
        conclusion = page.get("conclusion")
        status = str(conclusion.get("status") or "") if isinstance(conclusion, Mapping) else ""
        if status == "supported":
            continue
        local_reasons.append(f"{page_id}:{status or 'invalid'}")
        if page_id in {"overview", "cross_asset"}:
            no_call.add(5)
        else:
            no_call.add(20)
        if status == "insufficient_evidence" and page_id == "overview":
            no_call.update((5, 20))
    if exclusions:
        local_reasons.append(f"excluded_items:{len(exclusions)}")
    if local_reasons:
        return EvidencePackHealth(
            status=EvidencePackHealthStatus.DEGRADED,
            local_reasons=tuple(local_reasons),
            no_call_horizons=tuple(sorted(no_call)),
        )
    return EvidencePackHealth(status=EvidencePackHealthStatus.READY)


def _require_page_identity(pages: Mapping[str, Mapping[str, Any]], *, session_date: date) -> None:
    if set(pages) != set(_page_ids()):
        raise ValueError("macro_evidence_pack_exact_six_pages_required")
    for page_id, page in pages.items():
        if str(page.get("page_id") or "") != page_id:
            raise ValueError(f"macro_evidence_pack_page_identity_mismatch:{page_id}")
        snapshot = page.get("snapshot")
        if not isinstance(snapshot, Mapping):
            raise ValueError(f"macro_evidence_pack_page_snapshot_missing:{page_id}")
        if str(snapshot.get("projection_version") or "") != MACRO_EVIDENCE_PROJECTION_VERSION:
            raise ValueError(f"macro_evidence_pack_projection_version_mismatch:{page_id}")
        if str(snapshot.get("market_cutoff") or "") != session_date.isoformat():
            raise ValueError(f"macro_evidence_pack_cutoff_mismatch:{page_id}")


def _event_metadata(row: Mapping[str, Any]) -> dict[str, Any]:
    existing = row.get("event_metadata_json")
    if isinstance(existing, Mapping):
        return dict(existing)
    raw = row.get("raw_payload_json")
    if not isinstance(raw, Mapping):
        return {}
    provenance = raw.get("provenance")
    first = (
        provenance[0]
        if isinstance(provenance, Sequence)
        and not isinstance(provenance, str | bytes | bytearray)
        and provenance
        and isinstance(provenance[0], Mapping)
        else {}
    )
    metadata: dict[str, Any] = {}
    for key in (
        "document_title",
        "document_type",
        "speaker",
        "source_url",
        "event_time",
        "event_time_et",
        "reference_period",
        "cusip",
        "announcement_date",
        "settlement_date",
    ):
        value = first.get(key) or raw.get(key)
        if value not in (None, ""):
            target = "text_value" if key == "document_title" else key
            metadata[target] = _json_value(value)
    source_url = first.get("source_url") or raw.get("source_url") or raw.get("url")
    if source_url:
        metadata["source_url"] = str(source_url)
    raw_value = raw.get("value")
    if isinstance(raw_value, str) and raw_value.strip():
        metadata["text_value"] = raw_value.strip()
    return metadata


def _observation_exclusion(row: Mapping[str, Any], *, reason: str) -> EvidenceExclusion:
    return EvidenceExclusion(
        source_name=str(row.get("source_name") or ""),
        concept_key=str(row.get("concept_key") or "") or None,
        series_key=str(row.get("series_key") or "") or None,
        reason=reason,
    )


def _parse_exact_timestamp_ms(value: str) -> int | None:
    normalized = value.strip()
    if not normalized or len(normalized) <= 10:
        return None
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return int(parsed.astimezone(UTC).timestamp() * 1000)


def _parse_date_only(value: str) -> date | None:
    if len(value.strip()) != 10:
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return str(value)
    return value


def _page_ids() -> tuple[str, ...]:
    return (
        "overview",
        "cross_asset",
        "rates_inflation",
        "growth_labor",
        "liquidity_funding",
        "credit",
    )


__all__ = [
    "MACRO_EVIDENCE_COMPILER_VERSION",
    "MACRO_NEWS_SELECTION_VERSION",
    "compile_macro_evidence_pack",
]
