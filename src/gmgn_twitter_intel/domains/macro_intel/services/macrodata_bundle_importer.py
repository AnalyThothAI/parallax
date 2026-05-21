from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gmgn_twitter_intel.app.runtime.repository_session import RepositorySession


def import_macrodata_bundle(envelope: Mapping[str, Any], *, repos: RepositorySession, now_ms: int) -> dict[str, Any]:
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

    imported_observation_ids: list[str] = []
    with _unit_of_work(repos):
        imported_observation_ids.extend(
            repos.macro_intel.upsert_observation(observation) for observation in normalized_observations
        )
        repos.macro_intel.record_import_run(import_run)

    return {
        "bundle_name": bundle_name,
        "asof": asof,
        "observations_count": len(imported_observation_ids),
        "imported_observation_ids": imported_observation_ids,
        "run_id": run_id,
        "status": data_quality,
        "data_quality": data_quality,
        "coverage": coverage,
        "missing_series": missing_series,
        "series_errors": series_errors,
        "reason_codes": reason_codes,
    }


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
    return {
        "source_name": str(raw_observation.get("provider") or _provider_prefix(series_key)),
        "series_key": series_key,
        "observed_at": raw_observation.get("observed_at"),
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


def _unit_of_work(repos: RepositorySession) -> AbstractContextManager[Any]:
    unit_of_work = getattr(repos, "unit_of_work", None)
    if callable(unit_of_work):
        return unit_of_work()
    transaction = getattr(getattr(repos, "conn", None), "transaction", None)
    if callable(transaction):
        return transaction()
    raise RuntimeError("repository session does not expose a transaction")


__all__ = ["import_macrodata_bundle"]
