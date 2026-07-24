from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from parallax.domains.macro_intel.services.macro_research import (
    FrozenMacroEvidenceScope,
    MacroEvidenceRecord,
    MacroObservationQuery,
    MacroResearchArtifact,
    MacroResearchArtifactDraft,
    MacroResearchCitation,
    MacroResearchCitationSelection,
    MacroResearchGap,
    MacroResearchIntegrityError,
    MacroResearchSection,
    canonicalize_macro_research_artifact,
    news_is_visible_in_scope,
    render_macro_research_markdown,
    require_artifact_integrity,
    require_evidence_in_scope,
    resolve_observation_visibility,
)

SESSION = date(2026, 7, 23)
CUTOFF_MS = 1_784_836_800_000
SEALED_AT_MS = CUTOFF_MS + 60_000
EVIDENCE_REF = "macro:asset:spy:2026-07-23:primary"


def test_frozen_scope_and_queries_enforce_only_mechanical_bounds() -> None:
    scope = _scope()

    assert scope.scope_id == _scope().scope_id
    assert scope.scope_id.startswith("macro-scope:")

    with pytest.raises(ValidationError, match="sealed_before_cutoff"):
        FrozenMacroEvidenceScope(
            session_date=SESSION,
            market_cutoff_ms=CUTOFF_MS,
            sealed_at_ms=CUTOFF_MS - 1,
        )

    query = MacroObservationQuery(query="credit", limit=50, offset=50_000)
    assert query.limit == 50
    assert query.offset == 50_000
    with pytest.raises(ValidationError):
        MacroObservationQuery(query="credit", limit=51)
    with pytest.raises(ValidationError, match="date_range"):
        MacroObservationQuery(
            start_date=date(2026, 7, 23),
            end_date=date(2026, 7, 22),
        )


def test_evidence_scope_rejects_future_or_post_seal_records() -> None:
    scope = _scope()

    assert require_evidence_in_scope(scope, (_evidence(),)) == (_evidence(),)

    with pytest.raises(MacroResearchIntegrityError, match="future_evidence"):
        require_evidence_in_scope(
            scope,
            (
                _evidence(
                    source_timestamp="2026-07-23T16:00:00.001-04:00",
                    available_at_ms=CUTOFF_MS + 1,
                ),
            ),
        )
    with pytest.raises(MacroResearchIntegrityError, match="post_seal_evidence"):
        require_evidence_in_scope(
            scope,
            (_evidence(persisted_at_ms=SEALED_AT_MS + 1),),
        )


def test_point_in_time_visibility_preserves_source_publication_semantics() -> None:
    scope = _scope()

    exact = resolve_observation_visibility(
        scope,
        source_timestamp="2026-07-23T15:00:00-04:00",
        ingested_at_ms=SEALED_AT_MS,
    )
    assert exact is not None
    assert exact.availability == "exact_source_timestamp"
    assert exact.available_at_ms < CUTOFF_MS

    date_only_known_before_cutoff = resolve_observation_visibility(
        scope,
        source_timestamp=SESSION.isoformat(),
        ingested_at_ms=CUTOFF_MS - 1,
    )
    assert date_only_known_before_cutoff is not None
    assert date_only_known_before_cutoff.availability == "date_only_system_known"
    assert date_only_known_before_cutoff.available_at_ms == CUTOFF_MS - 1

    assert (
        resolve_observation_visibility(
            scope,
            source_timestamp=SESSION.isoformat(),
            ingested_at_ms=SEALED_AT_MS,
        )
        is None
    )
    assert (
        resolve_observation_visibility(
            scope,
            source_timestamp="2026-07-22",
            ingested_at_ms=SEALED_AT_MS,
        )
        is None
    )
    future_event_known_before_cutoff = resolve_observation_visibility(
        scope,
        source_timestamp="2026-07-31",
        ingested_at_ms=CUTOFF_MS - 1,
    )
    assert future_event_known_before_cutoff is not None
    assert future_event_known_before_cutoff.availability == "date_only_system_known"
    assert (
        resolve_observation_visibility(
            scope,
            source_timestamp="2026-07-23T16:00:00.001-04:00",
            ingested_at_ms=SEALED_AT_MS,
        )
        is None
    )
    assert (
        resolve_observation_visibility(
            scope,
            source_timestamp="unparseable",
            ingested_at_ms=SEALED_AT_MS,
        )
        is None
    )
    assert news_is_visible_in_scope(
        scope,
        published_at_ms=CUTOFF_MS,
        fetched_at_ms=SEALED_AT_MS,
    )
    assert not news_is_visible_in_scope(
        scope,
        published_at_ms=CUTOFF_MS + 1,
        fetched_at_ms=SEALED_AT_MS,
    )


def test_artifact_allows_dynamic_research_without_retired_semantic_fields() -> None:
    scope = _scope()
    artifact = _artifact(
        title="Macro research",
        executive_summary="Evidence is mixed.",
        sections=(
            MacroResearchSection(
                section_id="agent_chosen_section",
                title="A section chosen by the agent",
                body_markdown="The agent may write English; production quality is evaluated outside this model.",
                citation_ids=("C001",),
            ),
        ),
    )

    assert (
        require_artifact_integrity(
            artifact,
            scope=scope,
            verified_evidence_refs={EVIDENCE_REF},
        )
        is artifact
    )
    schema_text = str(MacroResearchArtifact.model_json_schema()).lower()
    for retired_field in ("risk_lanes", "direction", "readiness", "no_call"):
        assert retired_field not in schema_text


def test_citation_metadata_is_canonicalized_from_disclosed_evidence() -> None:
    record = _evidence()
    record = record.model_copy(
        update={
            "source_label": "Canonical source label",
            "url": "https://example.com/canonical",
            "lineage": {"concept_key": "asset:spy", "series_key": "test:SPY"},
        }
    )
    draft = MacroResearchArtifactDraft(
        session_date=SESSION,
        market_cutoff_ms=CUTOFF_MS,
        title="研究草稿",
        executive_summary="模型只选择引用身份。",
        sections=(
            MacroResearchSection(
                section_id="evidence",
                title="证据",
                body_markdown="引用元数据由应用层补齐。",
                citation_ids=("C001",),
            ),
        ),
        citations=(
            MacroResearchCitationSelection(
                citation_id="C001",
                source_ref=EVIDENCE_REF,
            ),
        ),
    )

    artifact = canonicalize_macro_research_artifact(
        draft,
        disclosed_evidence={EVIDENCE_REF: record},
    )

    citation = artifact.citations[0]
    assert citation.source_type == "observation"
    assert citation.source_label == "Canonical source label"
    assert citation.observed_at == SESSION
    assert citation.url == "https://example.com/canonical"
    assert citation.lineage == {
        "concept_key": "asset:spy",
        "series_key": "test:SPY",
    }


def test_ordered_sections_are_the_only_narrative_authority() -> None:
    artifact = _artifact()

    assert "report_markdown" not in MacroResearchArtifact.model_fields
    assert render_macro_research_markdown(artifact) == (
        "# 截至完成交易日的宏观研究\n\n"
        "证据显示增长与信用之间存在张力。\n\n"
        "## 增长与信用\n\n"
        "增长放缓，但信用证据尚未显示系统性压力。\n\n"
        "引用：[C001]"
    )


def test_artifact_integrity_checks_only_identity_and_citation_closure() -> None:
    scope = _scope()
    artifact = _artifact()

    with pytest.raises(MacroResearchIntegrityError, match="session_mismatch"):
        require_artifact_integrity(
            artifact.model_copy(update={"session_date": date(2026, 7, 22)}),
            scope=scope,
            verified_evidence_refs={EVIDENCE_REF},
        )
    with pytest.raises(MacroResearchIntegrityError, match="cutoff_mismatch"):
        require_artifact_integrity(
            artifact.model_copy(update={"market_cutoff_ms": CUTOFF_MS - 1}),
            scope=scope,
            verified_evidence_refs={EVIDENCE_REF},
        )
    with pytest.raises(MacroResearchIntegrityError, match="unknown_citations"):
        require_artifact_integrity(
            artifact,
            scope=scope,
            verified_evidence_refs={"macro:other"},
        )

    with pytest.raises(ValidationError, match="citation_closure"):
        _artifact(
            sections=(
                MacroResearchSection(
                    section_id="unknown_reference",
                    title="Unknown reference",
                    body_markdown="This section references evidence absent from citations.",
                    citation_ids=("C999",),
                ),
            )
        )


def _scope() -> FrozenMacroEvidenceScope:
    return FrozenMacroEvidenceScope(
        session_date=SESSION,
        market_cutoff_ms=CUTOFF_MS,
        sealed_at_ms=SEALED_AT_MS,
    )


def _evidence(
    *,
    source_timestamp: str = SESSION.isoformat(),
    available_at_ms: int = CUTOFF_MS - 1,
    persisted_at_ms: int = CUTOFF_MS - 1,
) -> MacroEvidenceRecord:
    return MacroEvidenceRecord(
        evidence_ref=EVIDENCE_REF,
        evidence_kind="observation",
        source_label="Primary source",
        concept_key="asset:spy",
        source_timestamp=source_timestamp,
        available_at_ms=available_at_ms,
        persisted_at_ms=persisted_at_ms,
        observed_at=SESSION,
        summary="SPY close",
        payload={"value_numeric": 635.34, "unit": "price"},
    )


def _artifact(
    *,
    title: str = "截至完成交易日的宏观研究",
    executive_summary: str = "证据显示增长与信用之间存在张力。",
    sections: tuple[MacroResearchSection, ...] | None = None,
) -> MacroResearchArtifact:
    return MacroResearchArtifact(
        session_date=SESSION,
        market_cutoff_ms=CUTOFF_MS,
        title=title,
        executive_summary=executive_summary,
        sections=sections
        or (
            MacroResearchSection(
                section_id="growth_credit",
                title="增长与信用",
                body_markdown="增长放缓，但信用证据尚未显示系统性压力。",
                citation_ids=("C001",),
            ),
        ),
        gaps=(
            MacroResearchGap(
                gap_id="limited_history",
                summary="历史锚点有限",
                details="需要更长历史来检验当前组合是否罕见。",
            ),
        ),
        citations=(
            MacroResearchCitation(
                citation_id="C001",
                source_type="observation",
                source_ref=EVIDENCE_REF,
                source_label="Primary source",
                available_at_ms=CUTOFF_MS,
                observed_at=SESSION,
                lineage={"concept_key": "asset:spy", "series_key": "test:SPY"},
            ),
        ),
        reviewer_notes=("反证已在正文中展开。",),
    )
