from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.narrative_intel._constants import (
    MENTION_SEMANTICS_PROMPT_VERSION,
    NARRATIVE_SCHEMA_VERSION,
)
from gmgn_twitter_intel.domains.narrative_intel.types.mention_semantics import (
    MentionSemanticsBatchRequest,
    MentionSemanticsBatchResult,
)


class MentionSemanticsService:
    def build_batch_request(
        self,
        rows: list[dict[str, Any]],
        *,
        run_id: str,
        schema_version: str = NARRATIVE_SCHEMA_VERSION,
        prompt_version: str = MENTION_SEMANTICS_PROMPT_VERSION,
    ) -> MentionSemanticsBatchRequest:
        mentions = [
            {
                "event_id": str(row.get("event_id") or ""),
                "target_type": str(row.get("target_type") or ""),
                "target_id": str(row.get("target_id") or ""),
                "text": str(row.get("text_clean") or row.get("text") or ""),
                "text_fingerprint": str(row.get("text_fingerprint") or ""),
                "allowed_refs": [{"ref_id": f"event:{row.get('event_id')}", "kind": "event"}],
            }
            for row in rows
        ]
        return MentionSemanticsBatchRequest(
            run_id=run_id,
            schema_version=schema_version,
            prompt_version=prompt_version,
            mentions=mentions,
            raw_request={"mention_count": len(mentions)},
        )

    def validate_batch_result(
        self,
        rows: list[dict[str, Any]],
        result: MentionSemanticsBatchResult,
    ) -> MentionSemanticsBatchResult:
        row_by_key = {
            (
                _canonical_event_id(row.get("event_id")),
                str(row.get("target_type")),
                str(row.get("target_id")),
            ): row
            for row in rows
        }
        valid_labels = []
        for label in result.labels:
            key = (_canonical_event_id(label.event_id), label.target_type, label.target_id)
            row = row_by_key.get(key)
            if row is None:
                continue
            if label.event_id != str(row.get("event_id")):
                label = label.model_copy(update={"event_id": str(row.get("event_id") or "")})
            valid_labels.append(label)
        if len(valid_labels) == len(result.labels):
            return result.model_copy(update={"labels": valid_labels})
        unknown = sorted(
            {
                label.event_id
                for label in result.labels
                if (_canonical_event_id(label.event_id), label.target_type, label.target_id) not in row_by_key
            }
        )
        failures = list(result.failures)
        failures.append({"error": f"provider_returned_unknown_labels:{','.join(unknown)}"})
        audit = {
            **dict(result.agent_run_audit or {}),
            "unknown_label_count": len(result.labels) - len(valid_labels),
        }
        return result.model_copy(
            update={
                "labels": valid_labels,
                "failures": failures,
                "agent_run_audit": audit,
            }
        )

    def normalize_failures(
        self,
        rows: list[dict[str, Any]],
        failures: list[dict[str, Any]],
        *,
        labeled_keys: set[tuple[str, str, str]],
        default_next_retry_at_ms: int,
    ) -> list[dict[str, Any]]:
        row_by_key = {
            (str(row.get("event_id")), str(row.get("target_type")), str(row.get("target_id"))): row for row in rows
        }
        rows_by_event: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            event_id = _canonical_event_id(row.get("event_id"))
            if not event_id:
                continue
            rows_by_event.setdefault(event_id, []).append(row)

        normalized: list[dict[str, Any]] = []
        global_errors: list[str] = []
        seen: set[tuple[str, str, str]] = set()
        for failure in failures:
            failure_rows = self._failure_rows(failure, row_by_key, rows_by_event)
            if failure_rows is None:
                global_errors.append(str(failure.get("error") or "provider_failure"))
                continue
            for row in failure_rows:
                key = (str(row.get("event_id")), str(row.get("target_type")), str(row.get("target_id")))
                if key in labeled_keys or key in seen:
                    continue
                seen.add(key)
                normalized.append(_failure_for_row(row, failure, default_next_retry_at_ms=default_next_retry_at_ms))

        if global_errors:
            error = "; ".join(sorted(set(global_errors)))
            for key, row in row_by_key.items():
                if key in labeled_keys or key in seen:
                    continue
                seen.add(key)
                normalized.append(
                    _failure_for_row(
                        row,
                        {"error": error, "next_retry_at_ms": default_next_retry_at_ms},
                        default_next_retry_at_ms=default_next_retry_at_ms,
                    )
                )
        return normalized

    def _failure_rows(
        self,
        failure: dict[str, Any],
        row_by_key: dict[tuple[str, str, str], dict[str, Any]],
        rows_by_event: dict[str, list[dict[str, Any]]],
    ) -> list[dict[str, Any]] | None:
        event_id = _canonical_event_id(failure.get("event_id"))
        target_type = str(failure.get("target_type") or "")
        target_id = str(failure.get("target_id") or "")
        if event_id and target_type and target_id:
            row = row_by_key.get((event_id, target_type, target_id))
            return [row] if row else []
        if event_id:
            return list(rows_by_event.get(event_id, []))
        if target_type or target_id:
            return []
        return None


def _failure_for_row(
    row: dict[str, Any],
    failure: dict[str, Any],
    *,
    default_next_retry_at_ms: int,
) -> dict[str, Any]:
    return {
        **failure,
        "event_id": str(row.get("event_id") or ""),
        "target_type": str(row.get("target_type") or ""),
        "target_id": str(row.get("target_id") or ""),
        "error": str(failure.get("error") or "provider_failure"),
        "next_retry_at_ms": int(failure.get("next_retry_at_ms") or default_next_retry_at_ms),
    }


def _canonical_event_id(value: Any) -> str:
    event_id = str(value or "").strip()
    if event_id.startswith("event:"):
        return event_id.removeprefix("event:")
    return event_id
