from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from parallax.domains.macro_intel.services.daily_macro_judgment import (
    EvidenceAvailability,
    EvidencePackHealth,
    MacroEvidenceItem,
    MacroEvidencePack,
)
from parallax.domains.macro_intel.services.macro_cross_asset_rules import market_session_close_ms
from parallax.domains.macro_intel.services.macro_evidence_pack import compile_macro_evidence_pack


def test_pack_rejects_future_availability_and_requires_exact_six_pages() -> None:
    session = date(2026, 7, 22)
    cutoff_ms = int(datetime(2026, 7, 22, 20, 0, tzinfo=UTC).timestamp() * 1000)
    item = MacroEvidenceItem(
        evidence_ref="macro:rates:dgs10:2026-07-22:fred",
        page_id="rates_inflation",
        source_name="fred",
        concept_key="rates:dgs10",
        series_key="fred:DGS10",
        observed_at=session,
        available_at_ms=cutoff_ms,
        availability=EvidenceAvailability.PRIOR_DATE,
        source_timestamp="2026-07-21",
        ingested_at_ms=cutoff_ms + 1,
        data_quality="ok",
        selection_rule="prior_date_publication",
        content_hash="b" * 64,
        content={"value_numeric": "4.25"},
    )
    pages = {
        "overview": {},
        "cross_asset": {},
        "rates_inflation": {},
        "growth_labor": {},
        "liquidity_funding": {},
        "credit": {},
    }
    pack = MacroEvidencePack(
        session_date=session,
        market_cutoff_ms=cutoff_ms,
        sealed_at_ms=cutoff_ms + 10,
        projection_version="macro_decision_v2",
        pages=pages,
        evidence=(item,),
        health=EvidencePackHealth(status="ready"),
    )
    assert pack.pack_hash == pack.pack_hash
    assert len(pack.pack_hash) == 64

    with pytest.raises(ValueError, match="exact_six_pages"):
        MacroEvidencePack(
            session_date=session,
            market_cutoff_ms=cutoff_ms,
            sealed_at_ms=cutoff_ms + 10,
            projection_version="macro_decision_v2",
            pages={key: value for key, value in pages.items() if key != "credit"},
            evidence=(item,),
            health=EvidencePackHealth(status="ready"),
        )
    with pytest.raises(ValueError, match="future_fact"):
        MacroEvidencePack(
            session_date=session,
            market_cutoff_ms=cutoff_ms - 1,
            sealed_at_ms=cutoff_ms + 10,
            projection_version="macro_decision_v2",
            pages=pages,
            evidence=(item,),
            health=EvidencePackHealth(status="ready"),
        )


def test_compiler_excludes_unproven_or_post_cutoff_facts_and_freezes_visible_content() -> None:
    session = date(2026, 7, 22)
    cutoff_ms = market_session_close_ms(session)
    seal_ms = cutoff_ms + 3_600_000
    rows = [
        _row(
            concept_key="asset:spy",
            observed_at=session,
            source_ts=session.isoformat(),
            ingested_at_ms=cutoff_ms + 100,
            value="625.10",
        ),
        _row(
            concept_key="rates:dgs10",
            observed_at=session,
            source_ts=session.isoformat(),
            ingested_at_ms=cutoff_ms + 100,
            value="4.31",
        ),
        _row(
            concept_key="rates:dgs10",
            observed_at=date(2026, 7, 21),
            source_ts="2026-07-21",
            ingested_at_ms=cutoff_ms + 100,
            value="4.28",
        ),
        _row(
            concept_key="vol:vix",
            observed_at=session,
            source_ts="2026-07-22T21:00:00Z",
            ingested_at_ms=cutoff_ms + 100,
            value="18.5",
        ),
        _row(
            concept_key="event:fomc_decision_next",
            observed_at=date(2026, 7, 29),
            source_ts="2026-07-22T14:00:00-04:00",
            ingested_at_ms=cutoff_ms + 100,
            value=None,
            raw_payload_json={
                "value": "FOMC decision",
                "provenance": [{"source_url": "https://www.federalreserve.gov/"}],
            },
        ),
    ]

    pack = compile_macro_evidence_pack(
        session_date=session,
        market_cutoff_ms=cutoff_ms,
        sealed_at_ms=seal_ms,
        observation_rows=rows,
    )

    included = {(item.concept_key, item.observed_at) for item in pack.evidence}
    assert ("asset:spy", session) in included
    assert ("rates:dgs10", date(2026, 7, 21)) in included
    assert ("event:fomc_decision_next", date(2026, 7, 29)) in included
    assert ("rates:dgs10", session) not in included
    assert ("vol:vix", session) not in included
    assert {item.page_id for item in pack.evidence} >= {"overview", "cross_asset", "rates_inflation"}
    assert all(item.available_at_ms <= cutoff_ms for item in pack.evidence)
    assert len(pack.pages) == 6
    assert all(str(page["snapshot"]["market_cutoff"]) == session.isoformat() for page in pack.pages.values())
    assert {item.reason for item in pack.exclusions} == {"source_availability_after_or_unproven_at_cutoff"}
    assert pack.model_dump(mode="json") == pack.model_dump(mode="json")


def test_news_selection_requires_trust_quality_cutoff_and_seal() -> None:
    session = date(2026, 7, 22)
    cutoff_ms = market_session_close_ms(session)
    pack = compile_macro_evidence_pack(
        session_date=session,
        market_cutoff_ms=cutoff_ms,
        sealed_at_ms=cutoff_ms + 10_000,
        observation_rows=[
            _row(
                concept_key="asset:spy",
                observed_at=session,
                source_ts=session.isoformat(),
                ingested_at_ms=cutoff_ms + 1,
                value="625.10",
            )
        ],
        news_rows=[
            {
                "news_item_id": "official-1",
                "source_id": "fed",
                "source_name": "Federal Reserve",
                "trust_tier": "official",
                "source_quality_status": "healthy",
                "published_at_ms": cutoff_ms - 1_000,
                "fetched_at_ms": cutoff_ms + 1,
                "title": "Statement",
                "summary": "Policy statement",
                "body_text": "Official text",
                "canonical_url": "https://www.federalreserve.gov/example",
                "content_hash": "source-hash",
            },
            {
                "news_item_id": "standard-1",
                "source_id": "aggregator",
                "source_name": "Aggregator",
                "trust_tier": "standard",
                "source_quality_status": "healthy",
                "published_at_ms": cutoff_ms - 1_000,
                "fetched_at_ms": cutoff_ms + 1,
                "title": "Ignored",
                "summary": "",
                "body_text": "",
                "canonical_url": "",
                "content_hash": "ignored",
            },
        ],
    )

    assert [item.source_id for item in pack.texts] == ["fed"]
    assert pack.texts[0].source_content_hash == "source-hash"
    assert pack.texts[0].content_hash != "source-hash"
    assert any(item.reason == "news_trust_tier_ineligible" for item in pack.exclusions)


def _row(
    *,
    concept_key: str,
    observed_at: date,
    source_ts: str,
    ingested_at_ms: int,
    value: str | None,
    raw_payload_json: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "observation_id": f"{concept_key}:{observed_at.isoformat()}:{source_ts}",
        "source_name": "test",
        "concept_key": concept_key,
        "series_key": f"test:{concept_key}",
        "source_priority": 1,
        "observed_at": observed_at,
        "value_numeric": value,
        "unit": "price" if concept_key.startswith("asset:") else "percent",
        "frequency": "event" if concept_key.startswith("event:") else "daily",
        "data_quality": "ok",
        "source_ts": source_ts,
        "raw_payload_json": raw_payload_json or {},
        "ingested_at_ms": ingested_at_ms,
        "fact_payload_hash": f"hash:{concept_key}:{observed_at.isoformat()}",
    }
