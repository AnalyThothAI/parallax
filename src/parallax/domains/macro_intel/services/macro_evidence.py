from __future__ import annotations

import math
from calendar import monthrange
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, SupportsFloat, SupportsIndex

from parallax.domains.macro_intel.observation_identity import normalize_macro_date
from parallax.domains.macro_intel.services.macro_concept_manifest import (
    MACRO_CONCEPT_MANIFEST,
    MacroConceptSpec,
    MacroPageId,
)


def build_evidence_index(
    observations: Sequence[Mapping[str, Any]],
    *,
    computed_at_ms: int,
) -> dict[str, dict[str, Any]]:
    grouped = _group_manifest_observations(observations)
    computed_date = datetime.fromtimestamp(int(computed_at_ms) / 1000, tz=UTC).date()
    return {
        concept_key: _evidence_item(spec, grouped.get(concept_key, ()), computed_date=computed_date)
        for concept_key, spec in MACRO_CONCEPT_MANIFEST.items()
    }


def evidence_sections(
    page: MacroPageId,
    evidence: Mapping[str, Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    sections: dict[str, list[dict[str, Any]]] = {}
    for concept_key, spec in MACRO_CONCEPT_MANIFEST.items():
        if spec.page != page:
            continue
        item = evidence.get(concept_key)
        if item is not None:
            sections.setdefault(spec.section, []).append(dict(item))
    return sections


def page_freshness(
    page: MacroPageId,
    evidence: Mapping[str, Mapping[str, Any]],
    *,
    extra_critical_concepts: Sequence[str] = (),
) -> dict[str, Any]:
    page_specs = [spec for spec in MACRO_CONCEPT_MANIFEST.values() if spec.page == page]
    critical = {spec.concept_key for spec in page_specs if spec.criticality == "critical"}
    critical.update(extra_critical_concepts)
    optional = {spec.concept_key for spec in page_specs if spec.concept_key not in critical}
    critical_missing = sorted(key for key in critical if claim_gap_status(evidence.get(key)) == "missing")
    critical_stale = sorted(key for key in critical if str((evidence.get(key) or {}).get("status") or "") == "stale")
    optional_unavailable = sorted(
        key for key in optional if claim_gap_status(evidence.get(key)) in {"missing", "stale"}
    )
    if critical_missing or critical_stale:
        status = "insufficient_evidence"
    elif optional_unavailable:
        status = "degraded"
    else:
        status = "fresh"
    return {
        "status": status,
        "critical_missing": critical_missing,
        "critical_stale": critical_stale,
        "optional_unavailable": optional_unavailable,
    }


def numeric_series(
    observations: Sequence[Mapping[str, Any]],
    concept_key: str,
    *,
    cutoff: date | None = None,
) -> list[dict[str, Any]]:
    spec = MACRO_CONCEPT_MANIFEST.get(concept_key)
    if spec is None:
        return []
    points_by_date: dict[date, dict[str, Any]] = {}
    for observation in observations:
        if str(observation.get("concept_key") or "").strip() != concept_key:
            continue
        if _metadata_error(spec, observation) is not None:
            continue
        observed_at = _date_value(observation.get("observed_at"))
        value = _number(observation.get("value_numeric"))
        if observed_at is None or value is None or (cutoff is not None and observed_at > cutoff):
            continue
        points_by_date.setdefault(
            observed_at,
            {
                "observed_at": observed_at,
                "value": value,
                "source_name": _text(observation.get("source_name")),
                "series_key": _text(observation.get("series_key")),
                "unit": _text(observation.get("unit")),
                "frequency": _text(observation.get("frequency")),
                "data_quality": _text(observation.get("data_quality")),
            },
        )
    return [points_by_date[key] for key in sorted(points_by_date)]


def evidence_value(evidence: Mapping[str, Mapping[str, Any]], concept_key: str) -> float | None:
    item = evidence.get(concept_key)
    if item is None or str(item.get("status") or "") != "available":
        return None
    return _number(item.get("value"))


def evidence_change(evidence: Mapping[str, Mapping[str, Any]], concept_key: str) -> float | None:
    item = evidence.get(concept_key)
    if item is None or str(item.get("status") or "") != "available":
        return None
    return _number(item.get("change"))


def unavailable_capability(capability: str, reason: str) -> dict[str, str]:
    return {"capability": capability, "status": "not_assessed", "reason": reason}


def rule_hit(rule_id: str, outcome: str, evidence_refs: Sequence[str]) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "outcome": outcome,
        "evidence_refs": list(dict.fromkeys(str(ref) for ref in evidence_refs if str(ref))),
    }


def derived_evidence(
    *,
    concept_key: str,
    role: str,
    value: float | None,
    unit: str,
    change: float | None,
    change_window: str | None,
    observed_at: str | None,
    frequency: str,
    source_name: str,
    series_key: str,
    sample_start: str | None,
    sample_end: str | None,
    sample_count: int,
    criticality: str,
    claim_effect: str,
    formula: str,
    inputs: Sequence[Mapping[str, Any]],
    references: Sequence[str],
    status: str = "available",
    reason: str | None = None,
) -> dict[str, Any]:
    return {
        "concept_key": concept_key,
        "role": role,
        "status": status,
        "reason": reason,
        "value": None if value is None else _rounded(value),
        "unit": unit,
        "change": None if change is None else _rounded(change),
        "change_window": change_window,
        "observed_at": observed_at,
        "frequency": frequency,
        "source_name": source_name,
        "series_key": series_key,
        "data_quality": "derived",
        "freshness": {"status": "derived", "age_days": None, "stale_after_days": None},
        "sample": {"start": sample_start, "end": sample_end, "count": int(sample_count)},
        "criticality": criticality,
        "claim_effect": claim_effect,
        "derivation": {
            "formula": formula,
            "inputs": [dict(item) for item in inputs],
            "references": list(dict.fromkeys(references)),
        },
    }


def date_value(value: object) -> date | None:
    return _date_value(value)


def _group_manifest_observations(
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for observation in observations:
        concept_key = str(observation.get("concept_key") or "").strip()
        if concept_key in MACRO_CONCEPT_MANIFEST:
            grouped.setdefault(concept_key, []).append(observation)
    return grouped


def _evidence_item(
    spec: MacroConceptSpec,
    observations: Sequence[Mapping[str, Any]],
    *,
    computed_date: date,
) -> dict[str, Any]:
    if not observations:
        return _unavailable_evidence(spec, reason="missing_observation")
    ordered = _ordered_unique_observations(observations)
    if not ordered:
        return _unavailable_evidence(spec, reason="invalid_observed_at", status="invalid")
    latest = ordered[0]
    metadata_error = _metadata_error(spec, latest)
    numeric = _numeric_observations(spec, ordered)
    source_value = _number(latest.get("value_numeric"))
    if spec.frequency != "event" and source_value is None:
        metadata_error = metadata_error or "missing_numeric_value"
    latest_date = _date_value(latest.get("observed_at"))
    age_days = _freshness_days(latest_date, computed_date=computed_date, frequency=spec.frequency)
    freshness_status = "missing" if age_days is None else "stale" if age_days > spec.stale_after_days else "fresh"
    status = "invalid" if metadata_error else "stale" if freshness_status == "stale" else "available"
    reason = metadata_error or ("stale_observation" if status == "stale" else None)
    change, sample, derivation, change_reason = _change_payload(spec, numeric)
    latest_value, change, derivation = _normalize_evidence_unit(
        spec,
        source_value=source_value,
        change=change,
        latest=latest,
        derivation=derivation,
    )
    if change_reason is not None and reason is None:
        reason = change_reason
    return {
        "concept_key": spec.concept_key,
        "role": spec.evidence_role,
        "status": status,
        "reason": reason,
        "value": None if latest_value is None else _rounded(latest_value),
        "unit": spec.unit,
        "change": change,
        "change_window": spec.legal_change_window,
        "observed_at": latest_date.isoformat() if latest_date is not None else None,
        "frequency": _text(latest.get("frequency")) or spec.frequency,
        "source_name": _text(latest.get("source_name")),
        "series_key": _text(latest.get("series_key")),
        "data_quality": _text(latest.get("data_quality")) or "missing",
        "freshness": {
            "status": freshness_status,
            "age_days": age_days,
            "stale_after_days": spec.stale_after_days,
        },
        "sample": sample,
        "criticality": spec.criticality,
        "claim_effect": spec.claim_effect,
        "derivation": derivation,
    }


def _unavailable_evidence(
    spec: MacroConceptSpec,
    *,
    reason: str,
    status: str = "unavailable",
) -> dict[str, Any]:
    return {
        "concept_key": spec.concept_key,
        "role": spec.evidence_role,
        "status": status,
        "reason": reason,
        "value": None,
        "unit": spec.unit,
        "change": None,
        "change_window": spec.legal_change_window,
        "observed_at": None,
        "frequency": spec.frequency,
        "source_name": None,
        "series_key": None,
        "data_quality": "missing",
        "freshness": {"status": "missing", "age_days": None, "stale_after_days": spec.stale_after_days},
        "sample": {"start": None, "end": None, "count": 0},
        "criticality": spec.criticality,
        "claim_effect": spec.claim_effect,
        "derivation": None,
    }


def _metadata_error(spec: MacroConceptSpec, observation: Mapping[str, Any]) -> str | None:
    source_name = _text(observation.get("source_name"))
    series_key = _text(observation.get("series_key"))
    unit = _text(observation.get("unit"))
    frequency = _text(observation.get("frequency"))
    data_quality = _text(observation.get("data_quality"))
    if source_name is None:
        return "missing_source_name"
    if series_key is None:
        return "missing_series_key"
    if unit is None:
        return "missing_unit"
    if unit != spec.source_unit:
        return f"unit_mismatch:{spec.source_unit}"
    if frequency is None:
        return "missing_frequency"
    if frequency != spec.frequency:
        return f"frequency_mismatch:{spec.frequency}"
    if data_quality is None:
        return "missing_data_quality"
    if data_quality.lower() not in {"ok", "ready"}:
        return f"data_quality:{data_quality.lower()}"
    return None


def claim_gap_status(item: Mapping[str, Any] | None) -> str:
    if item is None:
        return "missing"
    status = str(item.get("status") or "")
    if status == "stale":
        return "stale"
    if status in {"unavailable", "invalid"}:
        return "missing"
    reason = str(item.get("reason") or "")
    if reason.startswith("insufficient_history:") or reason in {
        "missing_numeric_history",
        "zero_prior_value",
    }:
        return "missing"
    return "ready"


def _ordered_unique_observations(
    observations: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    ordered = sorted(
        observations,
        key=lambda observation: _date_value(observation.get("observed_at")) or date.min,
        reverse=True,
    )
    result: list[Mapping[str, Any]] = []
    seen: set[date] = set()
    for observation in ordered:
        observed_at = _date_value(observation.get("observed_at"))
        if observed_at is None or observed_at in seen:
            continue
        seen.add(observed_at)
        result.append(observation)
    return result


def _numeric_observations(
    spec: MacroConceptSpec,
    observations: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for observation in observations:
        if _metadata_error(spec, observation) is not None:
            continue
        observed_at = _date_value(observation.get("observed_at"))
        value = _number(observation.get("value_numeric"))
        if observed_at is None or value is None:
            continue
        result.append(
            {
                "observed_at": observed_at,
                "value": value,
                "series_key": _text(observation.get("series_key")),
            }
        )
    return result


def _change_payload(
    spec: MacroConceptSpec,
    observations: Sequence[Mapping[str, Any]],
) -> tuple[float | None, dict[str, Any], dict[str, Any] | None, str | None]:
    if not observations:
        return None, {"start": None, "end": None, "count": 0}, None, "missing_numeric_history"
    latest = observations[0]
    if spec.change_kind == "none" or spec.change_periods == 0:
        observed_at = latest["observed_at"].isoformat()
        return None, {"start": observed_at, "end": observed_at, "count": 1}, None, None
    if len(observations) <= spec.change_periods:
        return (
            None,
            {
                "start": observations[-1]["observed_at"].isoformat(),
                "end": latest["observed_at"].isoformat(),
                "count": len(observations),
            },
            None,
            f"insufficient_history:{spec.legal_change_window}",
        )
    prior = observations[spec.change_periods]
    if spec.change_kind == "return_pct":
        if prior["value"] == 0:
            change = None
            reason = "zero_prior_value"
        else:
            change = (latest["value"] / prior["value"] - 1.0) * 100.0
            reason = None
        formula = "(latest / prior - 1) * 100"
    else:
        change = latest["value"] - prior["value"]
        reason = None
        formula = "latest - prior"
    inputs = [
        {"observed_at": prior["observed_at"].isoformat(), "value": _rounded(prior["value"])},
        {"observed_at": latest["observed_at"].isoformat(), "value": _rounded(latest["value"])},
    ]
    references = [str(item["series_key"]) for item in (prior, latest) if item.get("series_key")]
    return (
        None if change is None else _rounded(change),
        {
            "start": prior["observed_at"].isoformat(),
            "end": latest["observed_at"].isoformat(),
            "count": spec.change_periods + 1,
        },
        {"formula": formula, "inputs": inputs, "references": list(dict.fromkeys(references))},
        reason,
    )


def _normalize_evidence_unit(
    spec: MacroConceptSpec,
    *,
    source_value: float | None,
    change: float | None,
    latest: Mapping[str, Any],
    derivation: Mapping[str, Any] | None,
) -> tuple[float | None, float | None, dict[str, Any] | None]:
    if spec.source_unit == spec.unit:
        return source_value, change, dict(derivation) if derivation is not None else None
    if spec.source_unit != "percent" or spec.unit != "basis_points":
        raise RuntimeError(f"unsupported_macro_evidence_unit_conversion:{spec.source_unit}:{spec.unit}")
    if derivation is not None:
        inputs = [dict(item) for item in derivation.get("inputs", []) if isinstance(item, Mapping)]
        references = [str(item) for item in derivation.get("references", []) if str(item)]
    else:
        observed_at = _date_value(latest.get("observed_at"))
        inputs = [
            {
                "observed_at": observed_at.isoformat() if observed_at is not None else None,
                "value": None if source_value is None else _rounded(source_value),
            }
        ]
        series_key = _text(latest.get("series_key"))
        references = [series_key] if series_key is not None else []
    return (
        None if source_value is None else _rounded(source_value * 100.0),
        None if change is None else _rounded(change * 100.0),
        {
            "formula": "source_percent * 100",
            "inputs": inputs,
            "references": list(dict.fromkeys(references)),
        },
    )


def _freshness_days(latest_date: date | None, *, computed_date: date, frequency: str) -> int | None:
    if latest_date is None:
        return None
    reference = latest_date
    if frequency == "monthly":
        reference = date(latest_date.year, latest_date.month, monthrange(latest_date.year, latest_date.month)[1])
    elif frequency == "quarterly":
        quarter_end_month = ((latest_date.month - 1) // 3 + 1) * 3
        reference = date(latest_date.year, quarter_end_month, monthrange(latest_date.year, quarter_end_month)[1])
    return max(0, (computed_date - reference).days)


def _date_value(value: object) -> date | None:
    try:
        return normalize_macro_date(value)
    except ValueError:
        return None


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, str | bytes | bytearray | Decimal | SupportsFloat | SupportsIndex):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return numeric if math.isfinite(numeric) else None


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    result = value.strip()
    return result or None


def _rounded(value: float) -> float:
    return round(float(value), 10)


__all__ = [
    "build_evidence_index",
    "claim_gap_status",
    "date_value",
    "derived_evidence",
    "evidence_change",
    "evidence_sections",
    "evidence_value",
    "numeric_series",
    "page_freshness",
    "rule_hit",
    "unavailable_capability",
]
