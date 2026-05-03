from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from ..retrieval.narrative_link_scoring import score_link

WINDOW_MS = {
    "5m": 300_000,
    "1h": 3_600_000,
    "24h": 86_400_000,
}
FRESH_MARKET_MS = 30 * 60_000


class NarrativeTokenLinker:
    def __init__(self, *, evidence, signals, enrichment, tokens):
        self.evidence = evidence
        self.signals = signals
        self.enrichment = enrichment
        self.tokens = tokens

    def link_seed(self, *, seed: dict[str, Any], window: str = "1h", commit: bool = True) -> list[dict[str, Any]]:
        rows = self._candidate_rows(seed=seed, window=window)
        groups = _group_candidates(rows)
        seed_candidates = self._seed_token_candidates(seed)
        links: list[dict[str, Any]] = []
        for identity_key, items in groups.items():
            link = self._link_group(
                seed=seed,
                window=window,
                identity_key=identity_key,
                items=items,
                seed_candidates=seed_candidates,
            )
            if link is not None:
                links.append(self.enrichment.upsert_narrative_token_link(**link, commit=False))
        if commit:
            self.enrichment.conn.commit()
        return links

    def _candidate_rows(self, *, seed: dict[str, Any], window: str) -> list[dict[str, Any]]:
        size_ms = WINDOW_MS[window]
        start_ms = int(seed["received_at_ms"])
        end_ms = start_ms + size_ms
        rows = self.signals.conn.execute(
            """
            SELECT
              etm.*,
              e.text_clean,
              e.search_text,
              e.canonical_url,
              e.is_watched AS event_is_watched
            FROM event_token_mentions etm
            JOIN events e ON e.event_id = etm.event_id
            WHERE etm.received_at_ms >= ?
              AND etm.received_at_ms < ?
            ORDER BY etm.received_at_ms ASC, etm.event_id ASC
            """,
            (start_ms, end_ms),
        ).fetchall()
        return [dict(row) for row in rows]

    def _link_group(
        self,
        *,
        seed: dict[str, Any],
        window: str,
        identity_key: str,
        items: list[dict[str, Any]],
        seed_candidates: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        matched_items = [_match_item(seed, item, seed_candidates=seed_candidates) for item in items]
        matched_items = [item for item in matched_items if item is not None]
        if not matched_items:
            return None
        first = min(matched_items, key=lambda item: int(item["received_at_ms"]))
        best = _best_item(matched_items)
        author_stats = _author_stats(items)
        mention_count = len(items)
        watched_count = sum(1 for item in items if int(item.get("is_watched") or 0))
        unique_author_count = len(author_stats)
        top_author_share = _top_author_share(author_stats, mentions=mention_count)
        weighted_reach = sum(int(item.get("followers") or 0) for item in author_stats.values())
        market = self._market_block(token_id=best.get("token_id"), seed=seed, window=window)
        matched_terms = sorted({term for item in matched_items for term in item["matched_terms"]})
        lag_ms = max(0, int(first["received_at_ms"]) - int(seed["received_at_ms"]))
        scoring = score_link(
            seed=seed,
            identity_status=str(best["identity_status"]),
            link_reason=str(best["link_reason"]),
            matched_terms=matched_terms,
            mention_count=mention_count,
            watched_mention_count=watched_count,
            unique_author_count=unique_author_count,
            top_author_share=top_author_share,
            market_status=market["market_status"],
            market_cap=market["market_cap"],
            lag_ms=lag_ms,
        )
        return {
            "seed_id": seed["seed_id"],
            "narrative_label": seed["narrative_label"],
            "token_identity_key": identity_key,
            "token_id": best.get("token_id"),
            "identity_status": best["identity_status"],
            "chain": best.get("chain"),
            "address": best.get("address"),
            "symbol": best["symbol"],
            "first_linked_event_id": first["event_id"],
            "best_evidence_event_id": best["event_id"],
            "link_reason": best["link_reason"],
            "matched_terms": matched_terms,
            "link_confidence": min(1.0, scoring["token_link_score"] / 100),
            "lag_ms": lag_ms,
            "window": window,
            "mention_count_after_seed": mention_count,
            "watched_mention_count_after_seed": watched_count,
            "unique_author_count_after_seed": unique_author_count,
            "weighted_reach_after_seed": float(weighted_reach),
            "market_cap": market["market_cap"],
            "market_status": market["market_status"],
            "price_change_after_seed_pct": market["price_change_after_seed_pct"],
            "seed_score": scoring["seed_score"],
            "diffusion_score": scoring["diffusion_score"],
            "token_link_score": scoring["token_link_score"],
            "tradeability_score": scoring["tradeability_score"],
            "decision": scoring["decision"],
            "reasons": scoring["reasons"],
            "risks": scoring["risks"],
        }

    def _market_block(self, *, token_id: str | None, seed: dict[str, Any], window: str) -> dict[str, Any]:
        if not token_id:
            return {"market_status": "missing", "market_cap": None, "price_change_after_seed_pct": None}
        start_ms = int(seed["received_at_ms"])
        end_ms = start_ms + WINDOW_MS[window]
        end_snapshot = self.tokens.market_snapshot_at_or_before(token_id, end_ms)
        if end_snapshot is None:
            return {"market_status": "missing", "market_cap": None, "price_change_after_seed_pct": None}
        age_ms = max(0, end_ms - int(end_snapshot["received_at_ms"]))
        market_status = "fresh" if age_ms <= FRESH_MARKET_MS else "stale"
        start_snapshot = self.tokens.market_snapshot_at_or_before(token_id, start_ms)
        price_change = None
        if start_snapshot is not None and start_snapshot.get("snapshot_id") != end_snapshot.get("snapshot_id"):
            start_price = _float_or_none(start_snapshot.get("price"))
            end_price = _float_or_none(end_snapshot.get("price"))
            if start_price and end_price is not None:
                price_change = round((end_price - start_price) / start_price, 12)
        return {
            "market_status": market_status,
            "market_cap": end_snapshot.get("market_cap"),
            "price_change_after_seed_pct": price_change,
        }

    def _seed_token_candidates(self, seed: dict[str, Any]) -> list[dict[str, Any]]:
        rows = self.enrichment.conn.execute(
            """
            SELECT symbol, project_name, chain, address, resolution_status
            FROM event_token_candidates
            WHERE event_id = ?
            ORDER BY confidence DESC
            """,
            (seed["event_id"],),
        ).fetchall()
        return [dict(row) for row in rows]


def _match_item(
    seed: dict[str, Any],
    item: dict[str, Any],
    *,
    seed_candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    text = _normalized_text(f"{item.get('search_text') or ''} {item.get('text_clean') or ''}")
    seed_terms = [str(term).lower() for term in seed.get("seed_terms") or []]
    symbol = str(item.get("symbol") or "").lower()
    matched_terms = [term for term in seed_terms if term and _contains_term(text, term)]
    if matched_terms:
        return {**item, "matched_terms": matched_terms, "link_reason": "seed_term_and_token_mention"}
    if _matches_seed_candidate(seed_candidates, item):
        return {**item, "matched_terms": [symbol] if symbol else [], "link_reason": "seed_symbol_candidate_confirmed"}
    if symbol and symbol in seed_terms:
        return {**item, "matched_terms": [symbol], "link_reason": "name_or_alias_overlap"}
    if item.get("event_id") == seed.get("event_id"):
        return {**item, "matched_terms": [symbol] if symbol else [], "link_reason": "watched_seed_direct_token"}
    return None


def _group_candidates(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row["identity_key"])].append(row)
    return groups


def _best_item(items: list[dict[str, Any]]) -> dict[str, Any]:
    return sorted(
        items,
        key=lambda item: (
            item.get("identity_status") == "resolved_ca",
            item.get("identity_status") == "resolved_alias",
            len(item.get("matched_terms") or []),
            int(item.get("is_watched") or 0),
            -int(item.get("received_at_ms") or 0),
        ),
        reverse=True,
    )[0]


def _author_stats(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    authors: dict[str, dict[str, Any]] = {}
    for item in items:
        handle = item.get("author_handle")
        if not handle:
            continue
        current = authors.get(str(handle), {"count": 0, "followers": 0})
        current["count"] = int(current["count"]) + 1
        current["followers"] = max(int(current["followers"]), int(item.get("author_followers") or 0))
        authors[str(handle)] = current
    return authors


def _top_author_share(authors: dict[str, dict[str, Any]], *, mentions: int) -> float:
    if not authors or mentions <= 0:
        return 0.0
    return max(int(item["count"]) for item in authors.values()) / mentions


def _contains_term(text: str, term: str) -> bool:
    escaped = re.escape(term.lower())
    if " " in term:
        return re.search(escaped.replace("\\ ", r"\s+"), text) is not None
    return re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", text) is not None


def _matches_seed_candidate(seed_candidates: list[dict[str, Any]], item: dict[str, Any]) -> bool:
    item_address = str(item.get("address") or "").lower()
    item_chain = str(item.get("chain") or "").lower()
    item_symbol = str(item.get("symbol") or "").upper()
    for candidate in seed_candidates:
        candidate_address = str(candidate.get("address") or "").lower()
        candidate_chain = str(candidate.get("chain") or "").lower()
        candidate_symbol = str(candidate.get("symbol") or "").upper()
        if candidate_address and candidate_address == item_address:
            return not candidate_chain or not item_chain or candidate_chain == item_chain
        if candidate_symbol and candidate_symbol == item_symbol:
            return True
    return False


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
