from __future__ import annotations

import hashlib
import sqlite3
import time
from collections import defaultdict
from typing import Any

from eth_utils import is_address, to_checksum_address

from .token_baseline import token_baseline

BASELINE_LIMITS = {
    "1m": 60,
    "5m": 24,
    "1h": 48,
    "24h": 14,
}
EVM_CHAINS = {"eth", "base", "bsc", "arbitrum", "optimism", "polygon", "avalanche", "evm", "evm_unknown"}
WINDOW_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "1h": 3_600_000,
    "24h": 86_400_000,
}


class RollingTokenFlow:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def token_flow(
        self,
        *,
        window: str,
        limit: int,
        watched_only: bool = False,
        now_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        size_ms = WINDOW_MS[window]
        reference_ms = now_ms if now_ms is not None else _now_ms()
        return self._token_flow_window(
            window=window,
            window_start_ms=reference_ms - size_ms,
            window_end_ms=reference_ms,
            limit=limit,
            watched_only=watched_only,
        )

    def _token_flow_window(
        self,
        *,
        window: str,
        window_start_ms: int,
        window_end_ms: int,
        limit: int,
        watched_only: bool,
    ) -> list[dict[str, Any]]:
        mention_rows = self._token_mentions_for_window(
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            watched_only=watched_only,
        )
        if not mention_rows:
            return []

        candidates = _mention_candidates(mention_rows)
        maps = self._token_identity_maps(candidates=candidates)
        groups = self._group_mentions(
            mention_rows,
            maps=maps,
            window=window,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
        )
        candidates = _merge_candidates(candidates, _identity_candidates(groups.values()))
        maps = self._token_identity_maps(candidates=candidates)
        current_identity_keys = set(groups)
        baseline_counts = self._baseline_slot_counts(
            maps=maps,
            candidates=candidates,
            current_identity_keys=current_identity_keys,
            window_start_ms=window_start_ms,
            window_size_ms=WINDOW_MS[window],
            sample_count=BASELINE_LIMITS.get(window, 24),
            watched_only=watched_only,
        )
        bounds = self._mention_bounds(
            maps=maps,
            candidates=_bound_candidates_for_current_identities(groups.values()),
            current_identity_keys=current_identity_keys,
            watched_only=watched_only,
        )
        for identity_key, group in groups.items():
            slot_counts = baseline_counts.get(identity_key, [0] * BASELINE_LIMITS.get(window, 24))
            baseline = token_baseline(slot_counts=slot_counts, current_mentions=int(group["mention_count"]))
            group["baseline"] = baseline
            group["previous_mentions"] = int(slot_counts[-1]) if slot_counts else 0
            group.update(bounds.get(identity_key, {}))

        rows = sorted(
            groups.values(),
            key=lambda item: (
                int(item["watched_mention_count"]),
                float(item["velocity"]),
                int(item["mention_count"]),
                int(item["window_end_ms"]),
            ),
            reverse=True,
        )
        return rows[: max(0, int(limit))]

    def _group_mentions(
        self,
        rows: list[sqlite3.Row],
        *,
        maps: dict[str, Any],
        window: str,
        window_start_ms: int,
        window_end_ms: int,
    ) -> dict[str, dict[str, Any]]:
        groups: dict[str, dict[str, Any]] = {}
        author_maps: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        total_mentions = 0
        total_watched_mentions = 0
        for raw_row in rows:
            row = dict(raw_row)
            identity = self._canonical_token_identity(row, maps)
            identity_key = str(identity["identity_key"])
            group = groups.get(identity_key)
            if group is None:
                group = {
                    **identity,
                    "window_id": _id("token_window", identity_key, window, str(window_start_ms)),
                    "window": window,
                    "window_start_ms": window_start_ms,
                    "window_end_ms": window_end_ms,
                    "mention_count": 0,
                    "watched_mention_count": 0,
                    "unique_author_count": 0,
                    "watched_author_count": 0,
                    "weighted_reach": 0.0,
                    "market_mindshare": 0.0,
                    "watched_mindshare": 0.0,
                    "velocity": 0.0,
                    "top_authors": [],
                    "top_events": [],
                    "events_for_diffusion": [],
                    "first_seen_ms": None,
                    "latest_seen_ms": None,
                    "first_watched_seen_ms": None,
                    "created_at_ms": window_start_ms,
                    "updated_at_ms": window_end_ms,
                }
                groups[identity_key] = group

            is_watched = bool(row.get("is_watched"))
            followers = int(row.get("author_followers") or 0)
            received_at_ms = int(row["received_at_ms"])
            group["mention_count"] = int(group["mention_count"]) + 1
            group["watched_mention_count"] = int(group["watched_mention_count"]) + (1 if is_watched else 0)
            group["velocity"] = float(group["mention_count"]) / ((window_end_ms - window_start_ms) / 60_000)
            group["first_seen_ms"] = _min_or_value(group["first_seen_ms"], received_at_ms)
            group["latest_seen_ms"] = _max_or_value(group["latest_seen_ms"], received_at_ms)
            if is_watched:
                group["first_watched_seen_ms"] = _min_or_value(group["first_watched_seen_ms"], received_at_ms)

            author_handle = row.get("author_handle")
            if author_handle:
                author_map = author_maps[identity_key]
                author = author_map.get(
                    str(author_handle),
                    {
                        "handle": str(author_handle),
                        "count": 0,
                        "followers": 0,
                        "watched_count": 0,
                        "latest_received_at_ms": 0,
                    },
                )
                author["count"] = int(author["count"]) + 1
                author["followers"] = max(int(author["followers"]), followers)
                author["watched_count"] = int(author["watched_count"]) + (1 if is_watched else 0)
                author["latest_received_at_ms"] = max(int(author["latest_received_at_ms"]), received_at_ms)
                author_map[str(author_handle)] = author

            group["top_events"].append(
                {
                    "event_id": row.get("event_id"),
                    "author_handle": row.get("event_author_handle") or row.get("author_handle"),
                    "text_clean": row.get("text_clean"),
                    "canonical_url": row.get("canonical_url"),
                    "is_watched": (
                        row.get("event_is_watched")
                        if row.get("event_is_watched") is not None
                        else row.get("is_watched")
                    ),
                    "received_at_ms": received_at_ms,
                    "mention_source": row.get("source"),
                    "source": row.get("source"),
                }
            )
            group["events_for_diffusion"].append(
                {
                    "event_id": row.get("event_id"),
                    "author_handle": row.get("event_author_handle") or row.get("author_handle"),
                    "author_followers": row.get("author_followers"),
                    "text_clean": row.get("text_clean"),
                    "search_text": row.get("search_text"),
                    "received_at_ms": received_at_ms,
                    "is_watched": (
                        row.get("event_is_watched")
                        if row.get("event_is_watched") is not None
                        else row.get("is_watched")
                    ),
                    "mention_source": row.get("source"),
                    "source": row.get("source"),
                }
            )
            total_mentions += 1
            total_watched_mentions += 1 if is_watched else 0

        for identity_key, group in groups.items():
            authors = sorted(
                author_maps[identity_key].values(),
                key=lambda item: (
                    int(item.get("count") or 0),
                    int(item.get("followers") or 0),
                    int(item.get("latest_received_at_ms") or 0),
                ),
                reverse=True,
            )
            group["top_authors"] = authors[:20]
            group["unique_author_count"] = len(authors)
            group["watched_author_count"] = sum(1 for item in authors if int(item.get("watched_count") or 0) > 0)
            group["weighted_reach"] = sum(int(item.get("followers") or 0) for item in authors)
            group["top_events"] = sorted(
                group["top_events"],
                key=lambda item: int(item.get("received_at_ms") or 0),
                reverse=True,
            )[:20]
            group["market_mindshare"] = (float(group["mention_count"]) / total_mentions) if total_mentions else 0.0
            group["watched_mindshare"] = (
                float(group["watched_mention_count"]) / total_watched_mentions if total_watched_mentions else 0.0
            )
        return groups

    def _token_mentions_for_window(
        self,
        *,
        window_start_ms: int,
        window_end_ms: int,
        watched_only: bool,
    ) -> list[sqlite3.Row]:
        watched_clause = "AND etm.is_watched = 1" if watched_only else ""
        return self.conn.execute(
            f"""
            SELECT
              etm.*,
              e.author_handle AS event_author_handle,
              e.text_clean,
              e.search_text,
              e.canonical_url,
              e.is_watched AS event_is_watched
            FROM event_token_mentions etm
            LEFT JOIN events e ON e.event_id = etm.event_id
            WHERE etm.received_at_ms >= ?
              AND etm.received_at_ms < ?
              {watched_clause}
            ORDER BY etm.received_at_ms DESC, etm.event_id DESC
            """,
            (window_start_ms, window_end_ms),
        ).fetchall()

    def _baseline_slot_counts(
        self,
        *,
        maps: dict[str, Any],
        candidates: dict[str, set[str]],
        current_identity_keys: set[str],
        window_start_ms: int,
        window_size_ms: int,
        sample_count: int,
        watched_only: bool,
    ) -> dict[str, list[int]]:
        baseline_start_ms = window_start_ms - sample_count * window_size_ms
        rows = self._raw_token_mentions(
            start_ms=baseline_start_ms,
            end_ms=window_start_ms,
            candidates=candidates,
            watched_only=watched_only,
        )
        counts: dict[str, list[int]] = defaultdict(lambda: [0] * sample_count)
        for raw_row in rows:
            row = dict(raw_row)
            identity_key = str(self._canonical_token_identity(row, maps)["identity_key"])
            if identity_key not in current_identity_keys:
                continue
            slot_index = (int(row["received_at_ms"]) - baseline_start_ms) // window_size_ms
            if 0 <= slot_index < sample_count:
                counts[identity_key][slot_index] += 1
        return counts

    def _mention_bounds(
        self,
        *,
        maps: dict[str, Any],
        candidates: dict[str, set[str]],
        current_identity_keys: set[str],
        watched_only: bool,
    ) -> dict[str, dict[str, Any]]:
        bounds: dict[str, dict[str, Any]] = {}
        for raw_row in self._indexed_mention_bound_rows(candidates=candidates, watched_only=watched_only):
            row = dict(raw_row)
            identity_key = str(self._canonical_token_identity(row, maps)["identity_key"])
            if identity_key not in current_identity_keys:
                continue
            current = bounds.setdefault(
                identity_key,
                {"first_seen_ms": None, "latest_seen_ms": None, "first_watched_seen_ms": None},
            )
            current["first_seen_ms"] = _min_or_value(current["first_seen_ms"], int(row["first_seen_ms"]))
            current["latest_seen_ms"] = _max_or_value(current["latest_seen_ms"], int(row["latest_seen_ms"]))
            if row.get("first_watched_seen_ms") is not None:
                current["first_watched_seen_ms"] = _min_or_value(
                    current["first_watched_seen_ms"],
                    int(row["first_watched_seen_ms"]),
                )
        return bounds

    def _indexed_mention_bound_rows(
        self,
        *,
        candidates: dict[str, set[str]],
        watched_only: bool,
    ) -> list[sqlite3.Row]:
        rows: list[sqlite3.Row] = []
        for clause, params in _candidate_bound_queries(candidates):
            watched_clause = "AND is_watched = 1" if watched_only else ""
            rows.extend(
                self.conn.execute(
                    f"""
                    SELECT
                      identity_key,
                      token_id,
                      identity_status,
                      chain,
                      address,
                      symbol,
                      MIN(received_at_ms) AS first_seen_ms,
                      MAX(received_at_ms) AS latest_seen_ms,
                      MIN(CASE WHEN is_watched = 1 THEN received_at_ms END) AS first_watched_seen_ms
                    FROM event_token_mentions
                    WHERE {clause}
                      {watched_clause}
                    GROUP BY identity_key, token_id, identity_status, chain, address, symbol
                    """,
                    params,
                ).fetchall()
            )
        return rows

    def _raw_token_mentions(
        self,
        *,
        start_ms: int | None,
        end_ms: int | None,
        candidates: dict[str, set[str]],
        watched_only: bool,
    ) -> list[sqlite3.Row]:
        clauses = []
        params: list[Any] = []
        if start_ms is not None:
            clauses.append("received_at_ms >= ?")
            params.append(start_ms)
        if end_ms is not None:
            clauses.append("received_at_ms < ?")
            params.append(end_ms)
        candidate_clause, candidate_params = _candidate_mention_sql(candidates, prefix="")
        clauses.append(candidate_clause)
        params.extend(candidate_params)
        if watched_only:
            clauses.append("is_watched = 1")
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return self.conn.execute(f"SELECT * FROM event_token_mentions {where_clause}", params).fetchall()

    def _token_identity_maps(self, *, candidates: dict[str, set[str]]) -> dict[str, Any]:
        alias_rows = self._candidate_alias_rows(candidates)
        alias_token_ids = {str(row["token_id"]) for row in alias_rows}
        token_rows = self._candidate_token_rows(candidates, token_ids=alias_token_ids | candidates["token_ids"])
        canonical_by_token_id: dict[str, dict[str, Any]] = {}
        token_by_canonical_id: dict[str, dict[str, Any]] = {}
        address_candidates: dict[tuple[str, str], set[str]] = defaultdict(set)
        address_any_candidates: dict[str, set[str]] = defaultdict(set)
        for row in token_rows:
            canonical = _canonical_token_row(row)
            canonical_id = str(canonical["token_id"])
            existing = token_by_canonical_id.get(canonical_id)
            if (
                existing is None
                or row.get("token_id") == canonical_id
                or int(row.get("updated_at_ms") or 0) > int(existing.get("updated_at_ms") or 0)
            ):
                token_by_canonical_id[canonical_id] = canonical
            canonical_by_token_id[str(row["token_id"])] = canonical
            address_key = _address_key(canonical.get("address"))
            chain = canonical.get("chain")
            if address_key and chain:
                address_candidates[(str(chain), address_key)].add(canonical_id)
                if str(chain) in EVM_CHAINS:
                    address_any_candidates[address_key].add(canonical_id)

        symbol_candidates: dict[str, set[str]] = defaultdict(set)
        for row in alias_rows:
            canonical = canonical_by_token_id.get(str(row["token_id"]))
            canonical_id = (
                str(canonical["token_id"])
                if canonical
                else _canonical_token_id_from_token_id(str(row["token_id"]))
            )
            symbol_candidates[_normalize_symbol(str(row["symbol"]))].add(canonical_id)

        return {
            "canonical_by_token_id": canonical_by_token_id,
            "token_by_canonical_id": token_by_canonical_id,
            "unique_symbol_alias": {
                symbol: next(iter(ids))
                for symbol, ids in symbol_candidates.items()
                if len(ids) == 1
            },
            "address_candidates": address_candidates,
            "address_any_candidates": address_any_candidates,
        }

    def _candidate_alias_rows(self, candidates: dict[str, set[str]]) -> list[sqlite3.Row]:
        rows_by_key: dict[tuple[str, str], sqlite3.Row] = {}
        if candidates["symbols"]:
            placeholders = ",".join("?" for _ in candidates["symbols"])
            for row in self.conn.execute(
                f"SELECT symbol, token_id FROM token_aliases WHERE symbol IN ({placeholders})",
                sorted(candidates["symbols"]),
            ).fetchall():
                rows_by_key[(str(row["symbol"]), str(row["token_id"]))] = row
        if candidates["token_ids"]:
            placeholders = ",".join("?" for _ in candidates["token_ids"])
            for row in self.conn.execute(
                f"SELECT symbol, token_id FROM token_aliases WHERE token_id IN ({placeholders})",
                sorted(candidates["token_ids"]),
            ).fetchall():
                rows_by_key[(str(row["symbol"]), str(row["token_id"]))] = row
        return list(rows_by_key.values())

    def _candidate_token_rows(self, candidates: dict[str, set[str]], *, token_ids: set[str]) -> list[dict[str, Any]]:
        rows_by_token_id: dict[str, dict[str, Any]] = {}
        if token_ids:
            placeholders = ",".join("?" for _ in token_ids)
            for row in self.conn.execute(
                f"SELECT * FROM tokens WHERE token_id IN ({placeholders})",
                sorted(token_ids),
            ).fetchall():
                rows_by_token_id[str(row["token_id"])] = dict(row)
        if candidates["symbols"]:
            placeholders = ",".join("?" for _ in candidates["symbols"])
            for row in self.conn.execute(
                f"SELECT * FROM tokens WHERE symbol IN ({placeholders})",
                sorted(candidates["symbols"]),
            ).fetchall():
                rows_by_token_id[str(row["token_id"])] = dict(row)
        if candidates["address_keys"]:
            placeholders = ",".join("?" for _ in candidates["address_keys"])
            for row in self.conn.execute(
                f"SELECT * FROM tokens WHERE lower(address) IN ({placeholders})",
                sorted(candidates["address_keys"]),
            ).fetchall():
                rows_by_token_id[str(row["token_id"])] = dict(row)
        return list(rows_by_token_id.values())

    def _canonical_token_identity(self, row: dict[str, Any], maps: dict[str, Any]) -> dict[str, Any]:
        token_id = row.get("token_id")
        if token_id:
            canonical = maps["canonical_by_token_id"].get(str(token_id))
            if canonical:
                return _identity_from_token(canonical)

        symbol = _normalize_symbol(str(row.get("symbol") or "UNKNOWN"))
        alias_token_id = maps["unique_symbol_alias"].get(symbol)
        if alias_token_id:
            token = maps["token_by_canonical_id"].get(alias_token_id)
            return (
                _identity_from_token(token)
                if token
                else _identity_from_canonical_token_id(alias_token_id, symbol=symbol)
            )

        address_key = _address_key(row.get("address"))
        chain = row.get("chain")
        candidates: set[str] = set()
        if address_key and chain and str(chain) not in {"evm_unknown", "evm"}:
            candidates = set(maps["address_candidates"].get((str(chain), address_key), set()))
        elif address_key:
            candidates = set(maps["address_any_candidates"].get(address_key, set()))
        if len(candidates) == 1:
            canonical_id = next(iter(candidates))
            token = maps["token_by_canonical_id"].get(canonical_id)
            return (
                _identity_from_token(token)
                if token
                else _identity_from_canonical_token_id(canonical_id, symbol=symbol)
            )

        return {
            "identity_key": str(row["identity_key"]),
            "token_id": row.get("token_id"),
            "identity_status": str(row["identity_status"]),
            "chain": row.get("chain"),
            "address": row.get("address"),
            "symbol": symbol,
        }


def _identity_from_token(token: dict[str, Any]) -> dict[str, Any]:
    return {
        "identity_key": str(token["token_id"]),
        "token_id": str(token["token_id"]),
        "identity_status": str(token.get("identity_status") or "resolved_ca"),
        "chain": token.get("chain"),
        "address": token.get("address"),
        "symbol": token.get("symbol"),
    }


def _mention_candidates(rows: list[sqlite3.Row]) -> dict[str, set[str]]:
    candidates = {
        "identity_keys": set(),
        "token_ids": set(),
        "symbols": set(),
        "address_keys": set(),
    }
    for raw_row in rows:
        row = dict(raw_row)
        if row.get("identity_key"):
            candidates["identity_keys"].add(str(row["identity_key"]))
        if row.get("token_id"):
            candidates["token_ids"].add(str(row["token_id"]))
        if row.get("symbol"):
            candidates["symbols"].add(_normalize_symbol(str(row["symbol"])))
        address_key = _address_key(row.get("address"))
        if address_key:
            candidates["address_keys"].add(address_key)
    return candidates


def _identity_candidates(rows: Any) -> dict[str, set[str]]:
    candidates = {
        "identity_keys": set(),
        "token_ids": set(),
        "symbols": set(),
        "address_keys": set(),
    }
    for row in rows:
        if row.get("identity_key"):
            candidates["identity_keys"].add(str(row["identity_key"]))
        if row.get("token_id"):
            candidates["token_ids"].add(str(row["token_id"]))
        if row.get("symbol"):
            candidates["symbols"].add(_normalize_symbol(str(row["symbol"])))
        address_key = _address_key(row.get("address"))
        if address_key:
            candidates["address_keys"].add(address_key)
    return candidates


def _bound_candidates_for_current_identities(rows: Any) -> dict[str, set[str]]:
    candidates = {
        "identity_keys": set(),
        "token_ids": set(),
        "symbols": set(),
        "address_keys": set(),
    }
    for row in rows:
        if row.get("identity_key"):
            candidates["identity_keys"].add(str(row["identity_key"]))

        token_id = row.get("token_id")
        if token_id:
            candidates["token_ids"].add(str(token_id))
            continue

        address_key = _address_key(row.get("address"))
        if address_key:
            candidates["address_keys"].add(address_key)
            continue

        identity_status = str(row.get("identity_status") or "")
        if identity_status in {"unresolved_symbol", "ambiguous_symbol"} and row.get("symbol"):
            candidates["symbols"].add(_normalize_symbol(str(row["symbol"])))
    return candidates


def _merge_candidates(*items: dict[str, set[str]]) -> dict[str, set[str]]:
    merged = {
        "identity_keys": set(),
        "token_ids": set(),
        "symbols": set(),
        "address_keys": set(),
    }
    for item in items:
        for key, values in item.items():
            merged[key].update(values)
    return merged


def _candidate_mention_sql(candidates: dict[str, set[str]], *, prefix: str) -> tuple[str, list[Any]]:
    clauses = []
    params: list[Any] = []
    column_prefix = f"{prefix}." if prefix else ""
    if candidates["identity_keys"]:
        placeholders = ",".join("?" for _ in candidates["identity_keys"])
        clauses.append(f"{column_prefix}identity_key IN ({placeholders})")
        params.extend(sorted(candidates["identity_keys"]))
    if candidates["token_ids"]:
        placeholders = ",".join("?" for _ in candidates["token_ids"])
        clauses.append(f"{column_prefix}token_id IN ({placeholders})")
        params.extend(sorted(candidates["token_ids"]))
    if candidates["symbols"]:
        placeholders = ",".join("?" for _ in candidates["symbols"])
        clauses.append(f"{column_prefix}symbol IN ({placeholders})")
        params.extend(sorted(candidates["symbols"]))
    if candidates["address_keys"]:
        placeholders = ",".join("?" for _ in candidates["address_keys"])
        clauses.append(f"lower({column_prefix}address) IN ({placeholders})")
        params.extend(sorted(candidates["address_keys"]))
    if not clauses:
        return "0 = 1", []
    return f"({' OR '.join(clauses)})", params


def _candidate_bound_queries(candidates: dict[str, set[str]]) -> list[tuple[str, list[Any]]]:
    queries: list[tuple[str, list[Any]]] = []
    if candidates["identity_keys"]:
        placeholders = ",".join("?" for _ in candidates["identity_keys"])
        queries.append((f"identity_key IN ({placeholders})", sorted(candidates["identity_keys"])))
    if candidates["token_ids"]:
        placeholders = ",".join("?" for _ in candidates["token_ids"])
        queries.append((f"token_id IN ({placeholders})", sorted(candidates["token_ids"])))
    if candidates["symbols"]:
        placeholders = ",".join("?" for _ in candidates["symbols"])
        queries.append((f"symbol IN ({placeholders})", sorted(candidates["symbols"])))
    if candidates["address_keys"]:
        placeholders = ",".join("?" for _ in candidates["address_keys"])
        queries.append((f"lower(address) IN ({placeholders})", sorted(candidates["address_keys"])))
    return queries


def _identity_from_canonical_token_id(token_id: str, *, symbol: str) -> dict[str, Any]:
    parts = token_id.split(":", 2)
    if len(parts) != 3:
        return {
            "identity_key": token_id,
            "token_id": token_id,
            "identity_status": "resolved_alias",
            "chain": None,
            "address": None,
            "symbol": symbol,
        }
    return {
        "identity_key": token_id,
        "token_id": token_id,
        "identity_status": "resolved_alias",
        "chain": parts[1],
        "address": parts[2],
        "symbol": symbol,
    }


def _canonical_token_row(row: dict[str, Any]) -> dict[str, Any]:
    chain = _normalize_chain(str(row["chain"]))
    address = _normalize_address(str(row["address"]), chain)
    row["chain"] = chain
    row["address"] = address
    row["token_id"] = _token_id(chain, address)
    row["symbol"] = _normalize_symbol(str(row["symbol"]))
    return row


def _canonical_token_id_from_token_id(token_id: str) -> str:
    parts = token_id.split(":", 2)
    if len(parts) != 3 or parts[0] != "token":
        return token_id
    chain = _normalize_chain(parts[1])
    return _token_id(chain, _normalize_address(parts[2], chain))


def _normalize_symbol(symbol: str) -> str:
    text = symbol.strip().lstrip("$")
    return text.upper() if text.isascii() else text


def _normalize_chain(chain: str) -> str:
    normalized = chain.strip().lower()
    if normalized == "ethereum":
        return "eth"
    if normalized == "bnb":
        return "bsc"
    if normalized == "sol":
        return "solana"
    return normalized


def _normalize_address(address: str, chain: str) -> str:
    text = address.strip()
    if chain in EVM_CHAINS and is_address(text):
        return to_checksum_address(text)
    return text


def _address_key(address: Any) -> str | None:
    if not address:
        return None
    return str(address).strip().lower()


def _token_id(chain: str, address: str) -> str:
    return f"token:{chain}:{address}"


def _id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _min_or_value(current: Any, value: int) -> int:
    return value if current is None else min(int(current), value)


def _max_or_value(current: Any, value: int) -> int:
    return value if current is None else max(int(current), value)


def _now_ms() -> int:
    return int(time.time() * 1000)
