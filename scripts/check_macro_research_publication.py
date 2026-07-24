"""Verify one persisted Macro research publication without calling a model or provider."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from pydantic import ValidationError

from tracefold.macro.research.repository import (
    MacroResearchRepository,
)
from tracefold.macro.research.service import (
    MACRO_RESEARCH_MAX_READ_REFS,
    FrozenMacroEvidenceScope,
    MacroEvidenceRecord,
    MacroResearchArtifact,
    MacroResearchArtifactDraft,
    MacroResearchAudit,
    MacroResearchCitationSelection,
    MacroResearchIntegrityError,
    MacroResearchReadPort,
    canonicalize_macro_research_artifact,
    render_macro_research_markdown,
    require_artifact_integrity,
    require_evidence_in_scope,
)
from tracefold.platform.config.settings import load_settings
from tracefold.platform.postgres.postgres_client import create_pool, with_password_from_file

_STATEMENT_TIMEOUT_SECONDS = 30.0


class MacroResearchPublicationCheckError(RuntimeError):
    """A redacted mechanical validation failure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def validate_persisted_publication(
    *,
    requested_session: date,
    state: Mapping[str, Any] | None,
    read_port: MacroResearchReadPort,
) -> dict[str, Any]:
    """Return a compact receipt after validating persisted identity and citation lineage."""

    if state is None or state.get("artifact_json") is None:
        raise MacroResearchPublicationCheckError("macro_research_publication_missing")
    if str(state.get("run_status") or "") != "published":
        raise MacroResearchPublicationCheckError("macro_research_publication_not_published")

    persisted_session = _date_value(state.get("session_date"))
    if persisted_session != requested_session:
        raise MacroResearchPublicationCheckError("macro_research_publication_session_mismatch")
    try:
        scope = FrozenMacroEvidenceScope(
            session_date=persisted_session,
            market_cutoff_ms=int(state["market_cutoff_ms"]),
            sealed_at_ms=int(state["sealed_at_ms"]),
        )
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise MacroResearchPublicationCheckError("macro_research_publication_scope_invalid") from exc

    artifact = _artifact(state["artifact_json"])
    audit = _audit(state.get("audit_json"))
    _require_publication_identity(
        state=state,
        scope=scope,
        artifact=artifact,
        audit=audit,
    )

    try:
        require_artifact_integrity(
            artifact,
            scope=scope,
            verified_evidence_refs=frozenset(audit.verified_source_refs),
        )
    except MacroResearchIntegrityError as exc:
        raise MacroResearchPublicationCheckError("macro_research_publication_artifact_integrity_failed") from exc

    evidence = _reread_citation_evidence(
        scope=scope,
        artifact=artifact,
        read_port=read_port,
    )
    _require_canonical_citations(artifact=artifact, evidence=evidence)

    computed_hash = _artifact_hash(artifact)
    stored_hash = _required_text(state.get("artifact_hash"), "artifact_hash")
    if computed_hash != stored_hash:
        raise MacroResearchPublicationCheckError("macro_research_publication_artifact_hash_mismatch")

    return {
        "ok": True,
        "session_date": requested_session.isoformat(),
        "citation_count": len(artifact.citations),
        "model_name": audit.model_name,
        "prompt_version": audit.prompt_version,
        "workflow_version": audit.workflow_version,
        "audit": {
            "scope_id": audit.scope_id,
            "deepagents_version": audit.deepagents_version,
            "model_calls": audit.model_calls,
            "tool_calls": list(audit.tool_calls),
            "subagents": list(audit.subagents),
            "verified_source_ref_count": len(audit.verified_source_refs),
        },
        "artifact_hash": stored_hash,
    }


def _load_and_validate(requested_session: date) -> dict[str, Any]:
    settings = load_settings(require_ws_token=False)
    postgres = settings.storage.postgres
    dsn = with_password_from_file(postgres.dsn, settings.postgres_password_file)
    pool = create_pool(
        dsn,
        min_size=1,
        max_size=1,
        connect_timeout_seconds=postgres.connect_timeout_seconds,
        application_name="macro_research_publication_check",
        statement_timeout_seconds=_STATEMENT_TIMEOUT_SECONDS,
        read_only=True,
    )
    try:
        with pool.connection() as conn:
            repository = MacroResearchRepository(conn)
            state = repository.research_state(requested_session)
            return validate_persisted_publication(
                requested_session=requested_session,
                state=state,
                read_port=repository,
            )
    finally:
        pool.close()


def _artifact(value: object) -> MacroResearchArtifact:
    if not isinstance(value, Mapping):
        raise MacroResearchPublicationCheckError("macro_research_publication_artifact_invalid")
    try:
        return MacroResearchArtifact.model_validate(value)
    except ValidationError as exc:
        raise MacroResearchPublicationCheckError("macro_research_publication_artifact_invalid") from exc


def _audit(value: object) -> MacroResearchAudit:
    if not isinstance(value, Mapping):
        raise MacroResearchPublicationCheckError("macro_research_publication_audit_invalid")
    try:
        return MacroResearchAudit.model_validate(value)
    except ValidationError as exc:
        raise MacroResearchPublicationCheckError("macro_research_publication_audit_invalid") from exc


def _require_publication_identity(
    *,
    state: Mapping[str, Any],
    scope: FrozenMacroEvidenceScope,
    artifact: MacroResearchArtifact,
    audit: MacroResearchAudit,
) -> None:
    if artifact.session_date != scope.session_date:
        raise MacroResearchPublicationCheckError("macro_research_publication_artifact_session_mismatch")
    if artifact.market_cutoff_ms != scope.market_cutoff_ms:
        raise MacroResearchPublicationCheckError("macro_research_publication_artifact_cutoff_mismatch")
    if audit.scope_id != scope.scope_id:
        raise MacroResearchPublicationCheckError("macro_research_publication_audit_scope_mismatch")
    if str(state.get("report_markdown") or "") != render_macro_research_markdown(artifact):
        raise MacroResearchPublicationCheckError("macro_research_publication_report_mismatch")
    persisted_versions = (
        _required_text(state.get("model_name"), "model_name"),
        _required_text(state.get("prompt_version"), "prompt_version"),
        _required_text(state.get("workflow_version"), "workflow_version"),
    )
    audit_versions = (
        audit.model_name,
        audit.prompt_version,
        audit.workflow_version,
    )
    if persisted_versions != audit_versions:
        raise MacroResearchPublicationCheckError("macro_research_publication_audit_version_mismatch")


def _reread_citation_evidence(
    *,
    scope: FrozenMacroEvidenceScope,
    artifact: MacroResearchArtifact,
    read_port: MacroResearchReadPort,
) -> dict[str, MacroEvidenceRecord]:
    source_refs = tuple(dict.fromkeys(citation.source_ref for citation in artifact.citations))
    records: list[MacroEvidenceRecord] = []
    try:
        for offset in range(0, len(source_refs), MACRO_RESEARCH_MAX_READ_REFS):
            batch = source_refs[offset : offset + MACRO_RESEARCH_MAX_READ_REFS]
            records.extend(read_port.read_evidence(scope=scope, source_refs=batch))
        validated = require_evidence_in_scope(scope, tuple(records))
    except (ValueError, MacroResearchIntegrityError) as exc:
        raise MacroResearchPublicationCheckError("macro_research_publication_evidence_invalid") from exc
    by_ref = {record.evidence_ref: record for record in validated}
    if set(by_ref) != set(source_refs):
        raise MacroResearchPublicationCheckError("macro_research_publication_citation_source_missing")
    return by_ref


def _require_canonical_citations(
    *,
    artifact: MacroResearchArtifact,
    evidence: Mapping[str, MacroEvidenceRecord],
) -> None:
    draft_payload = artifact.model_dump(mode="python", exclude={"citations"})
    draft_payload["citations"] = [
        MacroResearchCitationSelection(
            citation_id=citation.citation_id,
            source_ref=citation.source_ref,
        ).model_dump(mode="python")
        for citation in artifact.citations
    ]
    try:
        draft = MacroResearchArtifactDraft.model_validate(draft_payload)
        canonical = canonicalize_macro_research_artifact(
            draft,
            disclosed_evidence=evidence,
        )
    except (ValidationError, MacroResearchIntegrityError) as exc:
        raise MacroResearchPublicationCheckError("macro_research_publication_citation_invalid") from exc
    if canonical != artifact:
        raise MacroResearchPublicationCheckError("macro_research_publication_citation_metadata_mismatch")


def _artifact_hash(artifact: MacroResearchArtifact) -> str:
    canonical = json.dumps(
        artifact.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _date_value(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise MacroResearchPublicationCheckError("macro_research_publication_session_invalid") from exc


def _required_text(value: object, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise MacroResearchPublicationCheckError(f"macro_research_publication_{field_name}_missing")
    return normalized


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate one persisted Macro research publication",
    )
    parser.add_argument(
        "--session-date",
        required=True,
        type=date.fromisoformat,
        metavar="YYYY-MM-DD",
        help="completed U.S. market session to validate",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    requested_session = args.session_date
    try:
        summary = _load_and_validate(requested_session)
    except MacroResearchPublicationCheckError as exc:
        summary = {
            "ok": False,
            "session_date": requested_session.isoformat(),
            "error": exc.code,
        }
        exit_code = 1
    except Exception as exc:
        summary = {
            "ok": False,
            "session_date": requested_session.isoformat(),
            "error": "macro_research_publication_check_failed",
            "error_type": type(exc).__name__,
        }
        exit_code = 1
    else:
        exit_code = 0
    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
