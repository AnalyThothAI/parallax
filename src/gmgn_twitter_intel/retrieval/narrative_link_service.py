from __future__ import annotations

from typing import Any

WINDOW_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "1h": 3_600_000,
    "24h": 86_400_000,
}


class NarrativeLinkService:
    def __init__(self, *, enrichment):
        self.enrichment = enrichment

    def narrative_seeds(
        self,
        *,
        window: str = "24h",
        limit: int = 50,
        handles: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        seeds = self.enrichment.narrative_seeds(
            window_ms=WINDOW_MS[window],
            limit=limit,
            handles=handles,
        )
        return [self._seed_item(seed) for seed in seeds]

    def narrative_token_flow(self, *, seed_id: str, window: str, limit: int) -> dict[str, Any]:
        seed = self.enrichment.narrative_seed(seed_id)
        if seed is None:
            return {"seed": None, "links": []}
        links = self.enrichment.narrative_token_links(seed_id=seed_id, window=window, limit=limit)
        return {"seed": seed, "links": [self._link_item(link) for link in links]}

    def attention_frontier(self, *, window: str, limit: int) -> list[dict[str, Any]]:
        return [self._frontier_item(item) for item in self.enrichment.attention_frontier(window=window, limit=limit)]

    def _seed_item(self, seed: dict[str, Any]) -> dict[str, Any]:
        links = self.enrichment.narrative_token_links(seed_id=seed["seed_id"], window="1h", limit=100)
        top_decision = _top_decision(link.get("decision") for link in links)
        return {
            "seed": seed,
            "linked_token_count": len(links),
            "top_decision": top_decision,
        }

    def _link_item(self, link: dict[str, Any]) -> dict[str, Any]:
        return {
            "identity": {
                "identity_key": link["token_identity_key"],
                "identity_status": link["identity_status"],
                "token_id": link.get("token_id"),
                "chain": link.get("chain"),
                "address": link.get("address"),
                "symbol": link.get("symbol"),
            },
            "flow": {
                "window": link["window"],
                "mentions": link["mention_count_after_seed"],
                "watched_mentions": link["watched_mention_count_after_seed"],
                "unique_authors": link["unique_author_count_after_seed"],
                "weighted_reach": link["weighted_reach_after_seed"],
                "lag_ms": link["lag_ms"],
            },
            "market": {
                "market_status": link["market_status"],
                "market_cap": link.get("market_cap"),
                "price_change_after_seed_pct": link.get("price_change_after_seed_pct"),
            },
            "scores": {
                "seed": link["seed_score"],
                "diffusion": link["diffusion_score"],
                "token_link": link["token_link_score"],
                "tradeability": link["tradeability_score"],
            },
            "signal": {
                "decision": link["decision"],
                "reasons": link["reasons"],
                "risks": link["risks"],
            },
            "evidence": {
                "first_linked_event_id": link["first_linked_event_id"],
                "best_evidence_event_id": link["best_evidence_event_id"],
                "link_reason": link["link_reason"],
                "matched_terms": link["matched_terms"],
                "link_confidence": link["link_confidence"],
            },
        }

    def _frontier_item(self, item: dict[str, Any]) -> dict[str, Any]:
        return {"seed": item["seed"], "link": self._link_item(item["link"])}


def _top_decision(decisions) -> str | None:
    values = set(decision for decision in decisions if decision)
    for decision in ("driver", "watch", "discard"):
        if decision in values:
            return decision
    return None
