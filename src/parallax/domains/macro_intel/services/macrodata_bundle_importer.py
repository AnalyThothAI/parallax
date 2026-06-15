from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from parallax.domains.macro_intel._constants import (
    MACRO_PROVIDER_SERIES_SOURCE_PRIORITY,
    MACRO_PROVIDER_SERIES_TO_CONCEPT,
    MACRO_VIEW_PROJECTION_VERSION,
)
from parallax.domains.macro_intel.observation_identity import normalize_macro_date
from parallax.domains.macro_intel.services.macro_sync_types import MacrodataBundleImport

if TYPE_CHECKING:
    from parallax.app.runtime.repository_session import RepositorySession


def parse_macrodata_bundle(envelope: Mapping[str, Any], *, now_ms: int) -> MacrodataBundleImport:
    snapshot = _snapshot(envelope)
    bundle_name = str(snapshot.get("bundle") or "unknown")
    asof = snapshot.get("asof")
    observations = _sequence(snapshot.get("observations"))
    coverage = _mapping(snapshot.get("coverage"))
    missing_series = list(_sequence(snapshot.get("missing_series")))
    series_errors = list(_sequence(snapshot.get("series_errors")))
    reason_codes = list(_sequence(snapshot.get("reason_codes")))
    data_quality = str(snapshot.get("data_quality") or "ok")
    normalized_observations = _observations(observations, now_ms=now_ms)
    max_observed_at = _max_observed_at(normalized_observations)

    run_id = _run_id(
        bundle_name=bundle_name,
        asof=asof,
        now_ms=now_ms,
        observations_count=len(normalized_observations),
    )
    import_run = {
        "run_id": run_id,
        "source_name": "macrodata-cli",
        "bundle_name": bundle_name,
        "asof_date": asof,
        "status": data_quality,
        "observations_count": len(normalized_observations),
        "coverage_json": coverage,
        "missing_series_json": missing_series,
        "series_errors_json": series_errors,
        "reason_codes_json": reason_codes,
        "started_at_ms": int(now_ms),
        "completed_at_ms": int(now_ms),
    }

    return MacrodataBundleImport(
        import_run=import_run,
        observations=normalized_observations,
        bundle_name=bundle_name,
        asof=asof,
        status=data_quality,
        coverage=coverage,
        missing_series=missing_series,
        series_errors=series_errors,
        reason_codes=reason_codes,
        max_observed_at=max_observed_at,
    )


def write_macrodata_bundle_import(
    parsed: MacrodataBundleImport,
    *,
    repos: RepositorySession,
) -> dict[str, Any]:
    repos.require_transaction(operation="macrodata_bundle_import")
    observation_outcomes = [
        dict(repos.macro_intel.upsert_observation(observation)) for observation in parsed.observations
    ]
    changed_observations = [
        outcome for outcome in observation_outcomes if str(outcome.get("status")) in {"inserted", "changed"}
    ]
    inserted_observation_count = _count_outcomes(observation_outcomes, "inserted")
    changed_observation_count = _count_outcomes(observation_outcomes, "changed")
    noop_observation_count = _count_outcomes(observation_outcomes, "noop")
    imported_observation_count = inserted_observation_count + changed_observation_count
    changed_concept_keys = sorted({str(outcome["concept_key"]) for outcome in changed_observations})
    max_seen_observed_at = _max_observed_at(observation_outcomes)
    min_changed_observed_at = _min_observed_at(changed_observations)
    max_changed_observed_at = _max_observed_at(changed_observations)
    import_run = dict(parsed.import_run)
    import_run.update(
        {
            "seen_observation_count": len(observation_outcomes),
            "inserted_observation_count": inserted_observation_count,
            "changed_observation_count": changed_observation_count,
            "noop_observation_count": noop_observation_count,
            "imported_observation_count": imported_observation_count,
        }
    )
    repos.macro_intel.record_import_run(import_run)
    dirty_targets_enqueued = 0
    if imported_observation_count > 0:
        dirty_targets_enqueued = int(
            repos.macro_intel.enqueue_macro_projection_dirty_targets_for_changes(
                changed_observations=changed_observations,
                projection_name="macro_view",
                projection_version=MACRO_VIEW_PROJECTION_VERSION,
                now_ms=int(import_run["completed_at_ms"]),
                due_at_ms=int(import_run["completed_at_ms"]),
                reason="macro_observations_changed",
                commit=False,
            )
        )

    return {
        "bundle_name": parsed.bundle_name,
        "asof": parsed.asof,
        "max_observed_at": parsed.max_observed_at,
        "observations_count": len(observation_outcomes),
        "seen_observation_count": len(observation_outcomes),
        "inserted_observation_count": inserted_observation_count,
        "changed_observation_count": changed_observation_count,
        "noop_observation_count": noop_observation_count,
        "imported_observation_count": imported_observation_count,
        "imported_observation_ids": [str(outcome["observation_id"]) for outcome in changed_observations],
        "max_seen_observed_at": max_seen_observed_at,
        "min_changed_observed_at": min_changed_observed_at,
        "max_changed_observed_at": max_changed_observed_at,
        "observation_outcomes": observation_outcomes,
        "changed_observations": changed_observations,
        "changed_concept_keys": changed_concept_keys,
        "dirty_targets_enqueued": dirty_targets_enqueued,
        "run_id": import_run["run_id"],
        "import_run_id": import_run["run_id"],
        "status": parsed.status,
        "data_quality": parsed.status,
        "coverage": dict(parsed.coverage),
        "missing_series": list(parsed.missing_series),
        "series_errors": list(parsed.series_errors),
        "reason_codes": list(parsed.reason_codes),
    }


def import_macrodata_bundle(envelope: Mapping[str, Any], *, repos: RepositorySession, now_ms: int) -> dict[str, Any]:
    parsed = parse_macrodata_bundle(envelope, now_ms=now_ms)
    with repos.unit_of_work():
        return write_macrodata_bundle_import(parsed, repos=repos)


def _snapshot(envelope: Mapping[str, Any]) -> Mapping[str, Any]:
    if envelope.get("ok") is not True:
        raise ValueError("macrodata envelope must have ok: true")
    data = envelope.get("data")
    if not isinstance(data, Mapping):
        raise ValueError("macrodata envelope must contain data.snapshot")
    snapshot = data.get("snapshot")
    if not isinstance(snapshot, Mapping):
        raise ValueError("macrodata envelope must contain data.snapshot")
    return snapshot


def _observations(raw_observations: Sequence[Any], *, now_ms: int) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for raw_observation in raw_observations:
        if not isinstance(raw_observation, Mapping):
            raise ValueError("macrodata observation must be a JSON object")
        observations.append(_observation(raw_observation, now_ms=now_ms))
    return observations


def _observation(raw_observation: Mapping[str, Any], *, now_ms: int) -> dict[str, Any]:
    series_key = str(raw_observation.get("series_key") or "").strip()
    if not series_key:
        raise ValueError("macrodata observation missing series_key")
    concept_key = MACRO_PROVIDER_SERIES_TO_CONCEPT.get(series_key)
    if concept_key is None:
        raise ValueError(f"unknown macro-core series_key: {series_key}")
    return {
        "source_name": str(raw_observation.get("provider") or _provider_prefix(series_key)),
        "concept_key": concept_key,
        "series_key": series_key,
        "source_priority": MACRO_PROVIDER_SERIES_SOURCE_PRIORITY[series_key],
        "observed_at": normalize_macro_date(raw_observation.get("observed_at")),
        "value_numeric": _numeric_value(raw_observation.get("value")),
        "unit": raw_observation.get("unit"),
        "frequency": raw_observation.get("frequency"),
        "data_quality": str(raw_observation.get("data_quality") or "ok"),
        "source_ts": raw_observation.get("source_ts"),
        "raw_payload": dict(raw_observation),
        "ingested_at_ms": int(now_ms),
    }


def _numeric_value(value: Any) -> int | float | Decimal | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float | Decimal):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            parsed = float(stripped)
        except ValueError:
            return None
        return parsed if math.isfinite(parsed) else None
    return None


def _provider_prefix(series_key: str) -> str:
    provider, _, _rest = series_key.partition(":")
    return provider or "unknown"


def _run_id(*, bundle_name: str, asof: object, now_ms: int, observations_count: int) -> str:
    identity = "|".join(["macrodata-cli", bundle_name, str(asof or ""), str(int(now_ms)), str(observations_count)])
    digest = hashlib.sha256(identity.encode()).hexdigest()[:32]
    return f"macro-import:{digest}"


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: object) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray) else []


def _max_observed_at(observations: Sequence[Mapping[str, Any]]) -> date | str | None:
    observed_dates = [observation["observed_at"] for observation in observations if observation.get("observed_at")]
    return cast("date | str | None", max(observed_dates) if observed_dates else None)


def _min_observed_at(observations: Sequence[Mapping[str, Any]]) -> object | None:
    observed_dates = [observation["observed_at"] for observation in observations if observation.get("observed_at")]
    return min(observed_dates) if observed_dates else None


def _count_outcomes(outcomes: Sequence[Mapping[str, Any]], status: str) -> int:
    return sum(1 for outcome in outcomes if outcome.get("status") == status)


__all__ = ["import_macrodata_bundle", "parse_macrodata_bundle", "write_macrodata_bundle_import"]
