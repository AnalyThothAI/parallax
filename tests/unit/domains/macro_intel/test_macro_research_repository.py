from __future__ import annotations

from datetime import date
from typing import Any

from parallax.domains.macro_intel.repositories.macro_research_repository import (
    MacroResearchRepository,
)
from parallax.domains.macro_intel.services.macro_research import (
    FrozenMacroEvidenceScope,
    MacroNewsQuery,
    MacroObservationQuery,
)


def test_run_lease_renewal_is_an_owner_compare_and_set() -> None:
    conn = _FakeConnection([[{"session_date": date(2026, 7, 23)}], []])
    repository = MacroResearchRepository(conn)

    renewed = repository.renew_run_lease(
        session_date=date(2026, 7, 23),
        lease_owner="owner-a",
        lease_ms=900_000,
        now_ms=1_000,
    )
    stale_owner_renewed = repository.renew_run_lease(
        session_date=date(2026, 7, 23),
        lease_owner="owner-b",
        lease_ms=900_000,
        now_ms=2_000,
    )

    normalized_sql = " ".join(conn.calls[0]["sql"].split())
    assert renewed is True
    assert stale_owner_renewed is False
    assert "leased_until_ms = GREATEST(leased_until_ms, %s)" in normalized_sql
    assert "status = 'running'" in normalized_sql
    assert "lease_owner = %s" in normalized_sql
    assert conn.calls[0]["params"] == (
        901_000,
        1_000,
        date(2026, 7, 23),
        "owner-a",
    )


def test_observation_reference_is_canonical_and_read_uses_full_id() -> None:
    row = _observation_row("macro-observation:sha256:abc")
    conn = _FakeConnection([[row], [row]])
    repository = MacroResearchRepository(conn)
    scope = _scope()

    searched = repository.search_observations(
        scope=scope,
        query=MacroObservationQuery(limit=1),
    )
    read = repository.read_evidence(
        scope=scope,
        source_refs=(searched[0].evidence_ref,),
    )

    assert searched[0].evidence_ref == "macro-observation:sha256:abc"
    assert read[0].evidence_ref == "macro-observation:sha256:abc"
    assert searched[0].lineage == {
        "observation_id": "macro-observation:sha256:abc",
        "concept_key": "rates:fed_funds",
        "series_key": "official:fed_funds",
        "source_name": "official",
        "source_ts": "2026-07-22",
        "fact_payload_hash": "sha256:def",
        "availability": "date_only_system_known",
    }
    assert conn.calls[0]["params"][-2:] == (250, 0)
    assert conn.calls[1]["params"][0] == ["macro-observation:sha256:abc"]


def test_legacy_observation_id_receives_one_canonical_prefix() -> None:
    conn = _FakeConnection([[_observation_row("legacy-id")]])
    repository = MacroResearchRepository(conn)

    records = repository.search_observations(
        scope=_scope(),
        query=MacroObservationQuery(limit=1),
    )

    assert records[0].evidence_ref == "macro-observation:legacy-id"


def test_search_offsets_are_applied_after_visibility_for_observations_and_in_sql_for_news() -> None:
    observation_rows = [
        _observation_row("first"),
        _observation_row("second"),
    ]
    news_row = {
        "news_item_id": "news-1",
        "source_id": "fed",
        "source_domain": "federalreserve.gov",
        "canonical_url": "https://www.federalreserve.gov/example",
        "title": "Policy statement",
        "summary": "The committee published its decision.",
        "body_text": "",
        "language": "en",
        "published_at_ms": 1_784_800_000_000,
        "fetched_at_ms": 1_784_801_000_000,
        "lifecycle_status": "processed",
    }
    conn = _FakeConnection([observation_rows, [news_row]])
    repository = MacroResearchRepository(conn)

    observations = repository.search_observations(
        scope=_scope(),
        query=MacroObservationQuery(limit=1, offset=1),
    )
    repository.search_news(
        scope=_scope(),
        query=MacroNewsQuery(limit=1, offset=7),
    )

    assert observations[0].evidence_ref == "macro-observation:second"
    assert conn.calls[0]["params"][-2:] == (250, 0)
    assert conn.calls[1]["params"][-2:] == (1, 7)


def test_observation_search_continues_past_invisible_raw_batches() -> None:
    invisible = _observation_row("invisible")
    invisible["source_ts"] = "2026-07-23T16:00:00.001-04:00"
    visible = _observation_row("visible")
    conn = _FakeConnection([[invisible] * 250, [visible]])

    records = MacroResearchRepository(conn).search_observations(
        scope=_scope(),
        query=MacroObservationQuery(limit=1),
    )

    assert [record.evidence_ref for record in records] == ["macro-observation:visible"]
    assert len(conn.calls) == 2
    assert conn.calls[0]["params"][-2:] == (250, 0)
    assert conn.calls[1]["params"][-2:] == (250, 250)


def test_news_record_contains_canonical_mechanical_lineage() -> None:
    body = "full-news-body-" + ("evidence" * 2_000)
    row = {
        "news_item_id": "news-1",
        "source_id": "fed",
        "source_domain": "federalreserve.gov",
        "canonical_url": "https://www.federalreserve.gov/example",
        "title": "Policy statement",
        "summary": "The committee published its decision.",
        "body_text": body,
        "language": "en",
        "published_at_ms": 1_784_800_000_000,
        "fetched_at_ms": 1_784_801_000_000,
        "lifecycle_status": "processed",
    }
    repository = MacroResearchRepository(_FakeConnection([[row]]))

    records = repository.search_news(
        scope=_scope(),
        query=MacroNewsQuery(limit=1),
    )

    assert records[0].lineage == {
        "news_item_id": "news-1",
        "source_id": "fed",
        "source_domain": "federalreserve.gov",
        "published_at_ms": 1_784_800_000_000,
        "fetched_at_ms": 1_784_801_000_000,
    }
    assert records[0].payload["body_text"] == body


def test_prior_research_is_pageable_without_a_total_depth_cap() -> None:
    row = {
        "session_date": date(2026, 7, 22),
        "artifact_json": {
            "title": "Prior research",
            "executive_summary": "Prior context",
        },
        "published_at_ms": 1_784_800_000_000,
    }
    conn = _FakeConnection([[row]])

    records = MacroResearchRepository(conn).prior_research(
        scope=_scope(),
        limit=5,
        offset=25,
    )

    assert records[0].publication_ref == "macro-research:2026-07-22"
    assert conn.calls[0]["params"][-2:] == (5, 25)


class _FakeConnection:
    def __init__(self, result_sets: list[list[dict[str, Any]]]) -> None:
        self._result_sets = list(result_sets)
        self.calls: list[dict[str, Any]] = []

    def execute(self, sql: str, params: Any = None) -> _FakeCursor:
        self.calls.append({"sql": sql, "params": params})
        return _FakeCursor(self._result_sets.pop(0))


class _FakeCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)

    def fetchone(self) -> dict[str, Any] | None:
        return dict(self._rows[0]) if self._rows else None


def _scope() -> FrozenMacroEvidenceScope:
    return FrozenMacroEvidenceScope(
        session_date=date(2026, 7, 23),
        market_cutoff_ms=1_784_836_800_000,
        sealed_at_ms=1_784_840_400_000,
    )


def _observation_row(observation_id: str) -> dict[str, Any]:
    return {
        "observation_id": observation_id,
        "source_name": "official",
        "concept_key": "rates:fed_funds",
        "series_key": "official:fed_funds",
        "source_priority": 1,
        "observed_at": date(2026, 7, 22),
        "value_numeric": 4.5,
        "unit": "percent",
        "frequency": "daily",
        "data_quality": "ok",
        "source_ts": "2026-07-22",
        "raw_payload_json": {},
        "ingested_at_ms": 1_753_200_000_000,
        "fact_payload_hash": "sha256:def",
    }
