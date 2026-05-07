from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .query_parser import parse_query


@dataclass(frozen=True, slots=True)
class AssetSearchResults:
    ok: bool
    items: list[dict[str, Any]] = field(default_factory=list)
    query: dict[str, Any] = field(default_factory=dict)
    resolution: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    candidates: list[dict[str, Any]] = field(default_factory=list)
    total_count: int = 0
    returned_count: int = 0
    has_more: bool = False


class AssetSearchService:
    def __init__(self, *, evidence, assets):
        self.evidence = evidence
        self.assets = assets

    def search(self, query: str, *, limit: int = 20, scope: str = "all") -> AssetSearchResults:
        watched_only = scope == "matched"
        parsed = parse_query(query)
        parsed_query = _query(parsed, scope=scope)
        if parsed.kind == "empty":
            return AssetSearchResults(ok=False, query=parsed_query, error="empty_query")
        requested_limit = max(0, int(limit))
        if parsed.kind == "symbol":
            return self._search_symbol(
                parsed.symbol or "",
                limit=requested_limit,
                watched_only=watched_only,
                query=parsed_query,
            )
        if parsed.kind == "ca":
            return self._search_ca(
                chain=parsed.chain,
                address=parsed.ca or "",
                limit=requested_limit,
                watched_only=watched_only,
                query=parsed_query,
            )
        if parsed.kind == "handle":
            events = self.evidence.recent_events(
                limit=requested_limit,
                handles={parsed.handle},
                watched_only=watched_only,
            )
            return AssetSearchResults(
                ok=True,
                items=[_item(event, "handle", 80.0) for event in events],
                query=parsed_query,
                resolution={"status": "not_applicable", "candidates": []},
                total_count=len(events),
                returned_count=len(events),
                has_more=False,
            )
        events = self.evidence.search_fts(parsed.text, limit=requested_limit, watched_only=watched_only)
        total_count = self.evidence.count_fts(parsed.text, watched_only=watched_only)
        return AssetSearchResults(
            ok=True,
            items=[_item(event, "fts", float(event.get("score") or 0.0)) for event in events],
            query=parsed_query,
            resolution={"status": "not_applicable", "candidates": []},
            total_count=total_count,
            returned_count=len(events),
            has_more=total_count > len(events),
        )

    def _search_symbol(
        self,
        symbol: str,
        *,
        limit: int,
        watched_only: bool,
        query: dict[str, Any],
    ) -> AssetSearchResults:
        candidates = _effective_candidates(self.assets.candidates_for_symbol(symbol))
        events = self._events_for_symbol(symbol, limit=limit, watched_only=watched_only)
        fallback_total = 0
        if not events:
            events = self.evidence.search_fts(symbol, limit=limit, watched_only=watched_only)
            fallback_total = self.evidence.count_fts(symbol, watched_only=watched_only)
        status = _resolution_status(candidates)
        return AssetSearchResults(
            ok=True,
            items=[
                _item(
                    event,
                    "token_intent" if not fallback_total else "fts_symbol_fallback",
                    _score(event, fallback_total),
                )
                for event in events
            ],
            query=query,
            resolution={"status": status, "candidates": candidates},
            candidates=candidates,
            total_count=fallback_total or len(events),
            returned_count=len(events),
            has_more=bool(fallback_total and fallback_total > len(events)),
        )

    def _search_ca(
        self,
        *,
        chain: str | None,
        address: str,
        limit: int,
        watched_only: bool,
        query: dict[str, Any],
    ) -> AssetSearchResults:
        candidates = self.assets.candidates_for_ca(chain=chain, address=address)
        events = self._events_for_ca(
            chain=chain,
            address=address,
            limit=limit,
            watched_only=watched_only,
        )
        fallback_total = 0
        if not events:
            events = self.evidence.search_fts(address, limit=limit, watched_only=watched_only)
            fallback_total = self.evidence.count_fts(address, watched_only=watched_only)
        status = _resolution_status(candidates)
        return AssetSearchResults(
            ok=True,
            items=[
                _item(
                    event,
                    "token_intent" if not fallback_total else "fts_ca_fallback",
                    _score(event, fallback_total),
                )
                for event in events
            ],
            query=query,
            resolution={"status": status, "candidates": candidates},
            candidates=candidates,
            total_count=fallback_total or len(events),
            returned_count=len(events),
            has_more=bool(fallback_total and fallback_total > len(events)),
        )

    def _events_for_symbol(self, symbol: str, *, limit: int, watched_only: bool) -> list[dict[str, Any]]:
        normalized = symbol.strip().lstrip("$").upper()
        return self._events_for_evidence(
            where_sql="token_evidence.normalized_symbol = %s",
            params=[normalized],
            limit=limit,
            watched_only=watched_only,
        )

    def _events_for_ca(
        self,
        *,
        chain: str | None,
        address: str,
        limit: int,
        watched_only: bool,
    ) -> list[dict[str, Any]]:
        normalized_address = address.strip().lower()
        where = "lower(token_evidence.address_hint) = %s"
        params: list[Any] = [normalized_address]
        if chain and chain != "evm_unknown":
            where += " AND token_evidence.chain_hint = %s"
            params.append(chain.strip().lower())
        return self._events_for_evidence(where_sql=where, params=params, limit=limit, watched_only=watched_only)

    def _events_for_evidence(
        self,
        *,
        where_sql: str,
        params: list[Any],
        limit: int,
        watched_only: bool,
    ) -> list[dict[str, Any]]:
        clauses = [where_sql]
        query_params = list(params)
        if watched_only:
            clauses.append("events.is_watched = true")
        query_params.append(max(0, int(limit)))
        rows = self.assets.conn.execute(
            f"""
            WITH matched AS (
              SELECT DISTINCT ON (events.event_id)
                events.*,
                token_evidence.evidence_id,
                token_evidence.evidence_type,
                token_evidence.raw_value AS mention_raw_value,
                token_evidence.normalized_symbol,
                token_evidence.chain_hint,
                token_evidence.address_hint,
                token_intent_resolutions.asset_id,
                token_intent_resolutions.primary_venue_id AS venue_id,
                token_intent_resolutions.resolution_status,
                token_intent_resolutions.identity_status AS resolution_identity_status,
                token_intent_resolutions.confidence AS resolution_confidence
              FROM token_evidence
              JOIN events ON events.event_id = token_evidence.event_id
              LEFT JOIN token_intent_evidence
                ON token_intent_evidence.evidence_id = token_evidence.evidence_id
              LEFT JOIN token_intent_resolutions
                ON token_intent_resolutions.intent_id = token_intent_evidence.intent_id
               AND token_intent_resolutions.resolution_status <> 'superseded'
              WHERE {' AND '.join(clauses)}
              ORDER BY events.event_id, token_intent_resolutions.confidence DESC NULLS LAST
            )
            SELECT *
            FROM matched
            ORDER BY received_at_ms DESC, event_id DESC
            LIMIT %s
            """,
            query_params,
        ).fetchall()
        return [dict(row) for row in rows]


def _resolution_status(candidates: list[dict[str, Any]]) -> str:
    asset_ids = {str(candidate.get("asset_id")) for candidate in candidates if candidate.get("asset_id")}
    if not candidates:
        return "unresolved"
    if any(str(candidate.get("identity_status") or "") == "unresolved" for candidate in candidates):
        return "unresolved"
    if any(str(candidate.get("identity_status") or "") == "ambiguous" for candidate in candidates):
        return "ambiguous"
    if len(asset_ids) == 1:
        return "resolved"
    return "ambiguous"


def _effective_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    real = [candidate for candidate in candidates if _is_real_candidate(candidate)]
    cex = [candidate for candidate in real if candidate.get("venue_type") == "cex"]
    cex_asset_ids = {str(candidate.get("asset_id")) for candidate in cex if candidate.get("asset_id")}
    if len(cex_asset_ids) == 1:
        return cex
    return real or candidates


def _is_real_candidate(candidate: dict[str, Any]) -> bool:
    asset_id = str(candidate.get("asset_id") or "")
    asset_type = str(candidate.get("asset_type") or "")
    identity_status = str(candidate.get("identity_status") or "")
    if identity_status in {"unresolved", "ambiguous"}:
        return False
    if asset_type.startswith(("unresolved", "ambiguous")):
        return False
    return not asset_id.startswith(("asset:unresolved", "asset:ambiguous"))


def _item(event: dict[str, Any], match_type: str, score: float) -> dict[str, Any]:
    return {"event": event, "match_type": match_type, "score": score}


def _score(event: dict[str, Any], fallback_total: int) -> float:
    if not fallback_total:
        return 100.0
    return float(event.get("score") or 0.0)


def _query(parsed, *, scope: str) -> dict[str, Any]:
    payload: dict[str, Any] = {"kind": parsed.kind, "text": parsed.text, "scope": scope}
    if parsed.ca:
        payload["ca"] = parsed.ca
    if parsed.chain:
        payload["chain"] = parsed.chain
    if parsed.symbol:
        payload["symbol"] = parsed.symbol
    if parsed.handle:
        payload["handle"] = parsed.handle
    return payload
