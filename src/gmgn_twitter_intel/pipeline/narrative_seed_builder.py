from __future__ import annotations

from typing import Any

from .llm_enrichment import EnrichmentResult, NarrativeItem


class NarrativeSeedBuilder:
    def __init__(self, enrichment):
        self.enrichment = enrichment

    def build_for_event(self, *, event: dict[str, Any], result: EnrichmentResult) -> list[dict[str, Any]]:
        if not event.get("is_watched") or not event.get("author_handle"):
            return []
        rows: list[dict[str, Any]] = []
        for narrative in result.narratives:
            rows.append(
                self.enrichment.upsert_narrative_seed(
                    event_id=str(event["event_id"]),
                    narrative_label=narrative.label,
                    seed_family=narrative.seed_family,
                    seed_terms=_seed_terms(narrative),
                    market_interpretation=narrative.market_interpretation_zh,
                    display_name_zh=narrative.display_name_zh,
                    headline_zh=narrative.headline_zh,
                    market_interpretation_zh=narrative.market_interpretation_zh,
                    stance=result.stance,
                    intent=result.intent,
                    confidence=narrative.confidence,
                    source_weight=_source_weight(event),
                    novelty_status=self._novelty_status(event=event, narrative=narrative),
                    received_at_ms=int(event["received_at_ms"]),
                    author_handle=str(event["author_handle"]).lower(),
                    evidence=narrative.evidence,
                    summary=result.summary_zh,
                    commit=False,
                )
            )
        return rows

    def _novelty_status(self, *, event: dict[str, Any], narrative: NarrativeItem) -> str:
        received_at_ms = int(event["received_at_ms"])
        author_handle = str(event["author_handle"]).lower()
        global_count = self.enrichment.conn.execute(
            """
            SELECT COUNT(*) FROM narrative_seeds
            WHERE narrative_label = ? AND received_at_ms < ?
            """,
            (narrative.label, received_at_ms),
        ).fetchone()[0]
        if not global_count:
            return "new_global"
        author_count = self.enrichment.conn.execute(
            """
            SELECT COUNT(*) FROM narrative_seeds
            WHERE narrative_label = ? AND author_handle = ? AND received_at_ms < ?
            """,
            (narrative.label, author_handle, received_at_ms),
        ).fetchone()[0]
        return "new_author" if not author_count else "repeat"


def _seed_terms(narrative: NarrativeItem) -> list[str]:
    deduped: list[str] = []
    for term in narrative.trigger_terms:
        normalized = str(term or "").strip().lower()
        if not normalized or normalized in deduped:
            continue
        deduped.append(normalized)
    return deduped[:12]


def _source_weight(event: dict[str, Any]) -> float:
    followers = int(event.get("author_followers") or 0)
    if followers >= 10_000_000:
        return 1.0
    if followers >= 1_000_000:
        return 0.9
    if followers >= 100_000:
        return 0.75
    if followers > 0:
        return 0.6
    return 0.5
