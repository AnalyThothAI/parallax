from __future__ import annotations

import hashlib
import json
from datetime import date
from types import SimpleNamespace

import pytest

from parallax.domains.macro_intel.services.completed_session_macro import (
    completed_session_close_ms,
)
from parallax.domains.macro_intel.services.macro_research import (
    FrozenMacroEvidenceScope,
    MacroEvidenceRecord,
    MacroResearchArtifact,
    MacroResearchAudit,
    render_macro_research_markdown,
    resolve_observation_visibility,
)
from scripts import check_macro_research_publication as publication_check


class FakeReadPort:
    def __init__(self, records: tuple[MacroEvidenceRecord, ...]) -> None:
        self.records = {record.evidence_ref: record for record in records}
        self.calls: list[tuple[FrozenMacroEvidenceScope, tuple[str, ...]]] = []

    def read_evidence(
        self,
        *,
        scope: FrozenMacroEvidenceScope,
        source_refs: tuple[str, ...],
    ) -> tuple[MacroEvidenceRecord, ...]:
        self.calls.append((scope, source_refs))
        return tuple(self.records[source_ref] for source_ref in source_refs if source_ref in self.records)


def test_validate_persisted_publication_returns_compact_mechanical_receipt() -> None:
    scope, record, artifact, audit, state = _publication()
    read_port = FakeReadPort((record,))

    receipt = publication_check.validate_persisted_publication(
        requested_session=scope.session_date,
        state=state,
        read_port=read_port,
    )

    assert receipt == {
        "ok": True,
        "session_date": "2026-07-23",
        "citation_count": 1,
        "model_name": "openai/gpt-5.6-terra",
        "prompt_version": "macro-research-v1",
        "workflow_version": "deepagents-v1",
        "audit": {
            "scope_id": scope.scope_id,
            "deepagents_version": "0.6.12",
            "model_calls": 4,
            "tool_calls": ["write_todos", "read_evidence"],
            "subagents": ["rates", "cross_asset"],
            "verified_source_ref_count": 1,
        },
        "artifact_hash": _artifact_hash(artifact),
    }
    assert read_port.calls == [(scope, (record.evidence_ref,))]
    assert audit.scope_id == scope.scope_id


def test_validate_persisted_publication_rejects_noncanonical_citation_lineage() -> None:
    scope, record, artifact, _audit, state = _publication()
    payload = artifact.model_dump(mode="python")
    payload["citations"][0]["lineage"] = {"observation_id": "tampered"}
    tampered = MacroResearchArtifact.model_validate(payload)
    state["artifact_json"] = tampered.model_dump(mode="json")
    state["artifact_hash"] = _artifact_hash(tampered)

    with pytest.raises(
        publication_check.MacroResearchPublicationCheckError,
        match="macro_research_publication_citation_metadata_mismatch",
    ):
        publication_check.validate_persisted_publication(
            requested_session=scope.session_date,
            state=state,
            read_port=FakeReadPort((record,)),
        )


def test_validate_persisted_publication_rejects_missing_persisted_source_ref() -> None:
    scope, _record, _artifact, _audit, state = _publication()

    with pytest.raises(
        publication_check.MacroResearchPublicationCheckError,
        match="macro_research_publication_citation_source_missing",
    ):
        publication_check.validate_persisted_publication(
            requested_session=scope.session_date,
            state=state,
            read_port=FakeReadPort(()),
        )


def test_validate_persisted_publication_rejects_artifact_hash_mismatch() -> None:
    scope, record, _artifact, _audit, state = _publication()
    state["artifact_hash"] = "0" * 64

    with pytest.raises(
        publication_check.MacroResearchPublicationCheckError,
        match="macro_research_publication_artifact_hash_mismatch",
    ):
        publication_check.validate_persisted_publication(
            requested_session=scope.session_date,
            state=state,
            read_port=FakeReadPort((record,)),
        )


def test_load_and_validate_opens_database_in_read_only_mode(monkeypatch) -> None:
    scope, record, _artifact, _audit, state = _publication()
    settings = SimpleNamespace(
        storage=SimpleNamespace(
            postgres=SimpleNamespace(
                dsn="postgresql://parallax@postgres/parallax",
                connect_timeout_seconds=5,
            )
        ),
        postgres_password_file=None,
    )
    captured: dict[str, object] = {}

    class FakeConnectionContext:
        def __enter__(self):
            return object()

        def __exit__(self, *_args):
            return False

    class FakePool:
        def connection(self):
            return FakeConnectionContext()

        def close(self) -> None:
            captured["closed"] = True

    class FakeRepository(FakeReadPort):
        def __init__(self, _conn: object) -> None:
            super().__init__((record,))

        def research_state(self, session_date: date):
            assert session_date == scope.session_date
            return state

    def fake_create_pool(dsn: str, **kwargs):
        captured["dsn"] = dsn
        captured.update(kwargs)
        return FakePool()

    monkeypatch.setattr(publication_check, "load_settings", lambda require_ws_token=False: settings)
    monkeypatch.setattr(publication_check, "create_pool", fake_create_pool)
    monkeypatch.setattr(publication_check, "MacroResearchRepository", FakeRepository)

    receipt = publication_check._load_and_validate(scope.session_date)

    assert receipt["ok"] is True
    assert captured["read_only"] is True
    assert captured["application_name"] == "macro_research_publication_check"
    assert captured["closed"] is True


def test_main_redacts_unexpected_database_error(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        publication_check,
        "_load_and_validate",
        lambda _session: (_ for _ in ()).throw(RuntimeError("postgresql://user:secret@db publication failed")),
    )

    exit_code = publication_check.main(["--session-date", "2026-07-23"])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "secret" not in output
    assert json.loads(output) == {
        "ok": False,
        "session_date": "2026-07-23",
        "error": "macro_research_publication_check_failed",
        "error_type": "RuntimeError",
    }


def _publication() -> tuple[
    FrozenMacroEvidenceScope,
    MacroEvidenceRecord,
    MacroResearchArtifact,
    MacroResearchAudit,
    dict[str, object],
]:
    session_date = date(2026, 7, 23)
    cutoff_ms = completed_session_close_ms(session_date)
    scope = FrozenMacroEvidenceScope(
        session_date=session_date,
        market_cutoff_ms=cutoff_ms,
        sealed_at_ms=cutoff_ms + 60_000,
    )
    source_timestamp = "2026-07-22"
    visibility = resolve_observation_visibility(
        scope,
        source_timestamp=source_timestamp,
        ingested_at_ms=cutoff_ms - 1,
    )
    assert visibility is not None
    lineage = {
        "observation_id": "macro-observation:test",
        "concept_key": "rates:dgs10",
        "series_key": "fred:DGS10",
        "source_name": "fred",
        "source_ts": source_timestamp,
        "fact_payload_hash": "sha256:fact",
        "availability": visibility.availability,
    }
    record = MacroEvidenceRecord(
        evidence_ref="macro-observation:test",
        evidence_kind="observation",
        source_label="fred",
        concept_key="rates:dgs10",
        source_timestamp=source_timestamp,
        available_at_ms=visibility.available_at_ms,
        persisted_at_ms=cutoff_ms - 1,
        observed_at=date(2026, 7, 22),
        summary="rates:dgs10=4.10 percent",
        lineage=lineage,
    )
    artifact = MacroResearchArtifact.model_validate(
        {
            "schema_version": "macro_research_artifact_v2",
            "session_date": session_date,
            "market_cutoff_ms": cutoff_ms,
            "title": "宏观研究",
            "executive_summary": "实际利率保持高位。",
            "sections": [
                {
                    "section_id": "mechanism",
                    "title": "核心机制",
                    "body_markdown": "十年期国债收益率仍在高位。",
                    "citation_ids": ["M001"],
                }
            ],
            "gaps": [],
            "citations": [
                {
                    "citation_id": "M001",
                    "source_type": "observation",
                    "source_ref": record.evidence_ref,
                    "source_label": record.source_label,
                    "available_at_ms": record.available_at_ms,
                    "observed_at": record.observed_at,
                    "published_at_ms": None,
                    "url": None,
                    "lineage": lineage,
                }
            ],
            "reviewer_notes": [],
        }
    )
    audit = MacroResearchAudit(
        scope_id=scope.scope_id,
        deepagents_version="0.6.12",
        model_name="openai/gpt-5.6-terra",
        prompt_version="macro-research-v1",
        workflow_version="deepagents-v1",
        model_calls=4,
        tool_calls=("write_todos", "read_evidence"),
        subagents=("rates", "cross_asset"),
        verified_source_refs=(record.evidence_ref,),
    )
    state: dict[str, object] = {
        "session_date": session_date,
        "market_cutoff_ms": cutoff_ms,
        "sealed_at_ms": scope.sealed_at_ms,
        "run_status": "published",
        "artifact_json": artifact.model_dump(mode="json"),
        "report_markdown": render_macro_research_markdown(artifact),
        "audit_json": audit.model_dump(mode="json"),
        "model_name": audit.model_name,
        "prompt_version": audit.prompt_version,
        "workflow_version": audit.workflow_version,
        "artifact_hash": _artifact_hash(artifact),
    }
    return scope, record, artifact, audit, state


def _artifact_hash(artifact: MacroResearchArtifact) -> str:
    canonical = json.dumps(
        artifact.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
