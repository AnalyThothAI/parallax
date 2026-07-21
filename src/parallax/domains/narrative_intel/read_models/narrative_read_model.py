from __future__ import annotations

from typing import Any

from parallax.domains.narrative_intel._constants import NARRATIVE_SCHEMA_VERSION

MISSING_ADMISSION_REASON = "no_current_admission"


class NarrativeReadModel:
    """Expose admission-derived narrative coverage."""

    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def hydrate_token_radar(self, data: dict[str, Any], *, window: str, scope: str) -> dict[str, Any]:
        admissions = self.repository.current_narrative_admissions_for_targets(
            _extract_targets(data),
            window=window,
            scope=_normalize_scope(scope),
            schema_version=NARRATIVE_SCHEMA_VERSION,
        )
        hydrated = dict(data)
        for key in ("targets", "attention", "items"):
            if isinstance(hydrated.get(key), list):
                hydrated[key] = [self._hydrate_row(row, admissions) for row in hydrated[key]]
        return hydrated

    def hydrate_token_case(self, dossier: dict[str, Any], *, window: str, scope: str) -> dict[str, Any]:
        target = _dict(dossier.get("target"))
        target_type = str(target.get("target_type") or "")
        target_id = str(target.get("target_id") or "")
        admissions = self.repository.current_narrative_admissions_for_targets(
            [{"target_type": target_type, "target_id": target_id}],
            window=window,
            scope=_normalize_scope(scope),
            schema_version=NARRATIVE_SCHEMA_VERSION,
        )
        hydrated = dict(dossier)
        hydrated["narrative_admission"] = _public_admission(
            admissions.get((target_type, target_id), _missing_admission())
        )
        return hydrated

    def _hydrate_row(
        self,
        row: dict[str, Any],
        admissions: dict[tuple[str, str], dict[str, Any]],
    ) -> dict[str, Any]:
        target_type, target_id = _target_identity(row)
        return {
            **row,
            "narrative_admission": _public_admission(admissions.get((target_type, target_id), _missing_admission())),
        }


def _extract_targets(data: dict[str, Any]) -> list[dict[str, str]]:
    targets: list[dict[str, str]] = []
    for key in ("targets", "attention", "items"):
        for row in data.get(key) or []:
            target_type, target_id = _target_identity(row)
            if target_type and target_id:
                targets.append({"target_type": target_type, "target_id": target_id})
    return targets


def _target_identity(row: dict[str, Any]) -> tuple[str, str]:
    target = _dict(row.get("target"))
    return (
        str(target.get("target_type") or ""),
        str(target.get("target_id") or ""),
    )


def _normalize_scope(scope: str) -> str:
    return "matched" if scope == "watched" else scope


def _missing_admission() -> dict[str, Any]:
    return {
        "status": "missing",
        "reason": MISSING_ADMISSION_REASON,
        "is_current": False,
        "source_event_count": 0,
        "independent_author_count": 0,
        "computed_at_ms": None,
        "currentness": {"display_status": "not_ready", "reason": MISSING_ADMISSION_REASON},
        "data_gaps_json": [{"reason": MISSING_ADMISSION_REASON}],
    }


def _public_admission(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": row.get("status") or "missing",
        "reason": row.get("reason") or MISSING_ADMISSION_REASON,
        "is_current": bool(row.get("is_current")),
        "computed_at_ms": row.get("computed_at_ms"),
        "currentness": _dict(row.get("currentness"))
        or {"display_status": "not_ready", "reason": MISSING_ADMISSION_REASON},
        "coverage": {
            "source_mentions": _int(row.get("source_event_count")),
            "independent_authors": _int(row.get("independent_author_count")),
        },
        "data_gaps": [_public_gap(gap) for gap in _list(row.get("data_gaps_json"))],
    }


def _public_gap(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    reason = value.get("reason") or value.get("message") or value.get("code")
    return {**value, "reason": reason} if reason else value


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
