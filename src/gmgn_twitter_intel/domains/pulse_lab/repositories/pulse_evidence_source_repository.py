from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from gmgn_twitter_intel.domains.pulse_lab.repositories._pulse_repository_shared import (
    _now_ms,
    _optional_row,
    _row,
)


class PulseEvidenceSourceRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def list_source_events(self, event_ids: Sequence[str]) -> list[dict[str, Any]]:
        ids = _stable_ids(event_ids)
        if not ids:
            return []
        rows = self.conn.execute(
            """
            SELECT *
            FROM events
            WHERE event_id = ANY(%s)
            ORDER BY timestamp_ms DESC, event_id ASC
            """,
            (ids,),
        ).fetchall()
        return [_row(row) for row in rows]

    def list_enriched_events(self, event_ids: Sequence[str]) -> list[dict[str, Any]]:
        ids = _stable_ids(event_ids)
        if not ids:
            return []
        rows = self.conn.execute(
            """
            SELECT enriched_events.*
            FROM enriched_events
            WHERE event_id = ANY(%s)
            ORDER BY t_event_ms DESC, event_id ASC, intent_id ASC
            """,
            (ids,),
        ).fetchall()
        return [_row(row) for row in rows]

    def get_asset_identity(self, target_type: str, target_id: str) -> dict[str, Any] | None:
        if str(target_type).strip().lower() not in {"asset", "chain_token", "cex_symbol"}:
            return None
        return _optional_row(
            self.conn.execute(
                """
                SELECT *
                FROM asset_identity_current
                WHERE asset_id = %s
                """,
                (target_id,),
            ).fetchone()
        )

    def get_latest_profile(self, target_type: str, target_id: str) -> dict[str, Any] | None:
        token_profile = _optional_row(
            self.conn.execute(
                """
                SELECT *
                FROM token_profile_current
                WHERE target_type = %s
                  AND target_id = %s
                """,
                (target_type, target_id),
            ).fetchone()
        )
        if token_profile is not None:
            return token_profile
        if str(target_type).strip() != "cex_symbol":
            return None
        return _optional_row(
            self.conn.execute(
                """
                SELECT *
                FROM cex_token_profiles
                WHERE cex_token_id = %s
                ORDER BY updated_at_ms DESC, provider ASC
                LIMIT 1
                """,
                (target_id,),
            ).fetchone()
        )

    def get_latest_market_tick(
        self,
        target_type: str,
        target_id: str,
        max_age_ms: int,
        *,
        now_ms: int,
    ) -> dict[str, Any] | None:
        min_observed_at_ms = max(0, int(now_ms) - max(0, int(max_age_ms)))
        return _optional_row(
            self.conn.execute(
                """
                SELECT *
                FROM market_ticks
                WHERE target_type = %s
                  AND target_id = %s
                  AND observed_at_ms >= %s
                ORDER BY observed_at_ms DESC, tick_id DESC
                LIMIT 1
                """,
                (target_type, target_id, min_observed_at_ms),
            ).fetchone()
        )

    def get_latest_market_tick_by_pricefeed(
        self,
        pricefeed_id: str,
        max_age_ms: int,
        *,
        now_ms: int,
    ) -> dict[str, Any] | None:
        min_observed_at_ms = max(0, int(now_ms) - max(0, int(max_age_ms)))
        return _optional_row(
            self.conn.execute(
                """
                SELECT *
                FROM market_ticks
                WHERE pricefeed_id = %s
                  AND observed_at_ms >= %s
                ORDER BY observed_at_ms DESC, tick_id DESC
                LIMIT 1
                """,
                (pricefeed_id, min_observed_at_ms),
            ).fetchone()
        )

    def list_market_facts(
        self,
        context: Any,
        *,
        max_age_ms: int = 3_600_000,
        now_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        effective_now_ms = _now_ms() if now_ms is None else int(now_ms)
        rows: list[dict[str, Any]] = []
        seen_ticks: set[str] = set()
        for target_type, target_id in _market_lookup_keys(context):
            tick = self.get_latest_market_tick(target_type, target_id, max_age_ms, now_ms=effective_now_ms)
            if tick is not None and str(tick.get("tick_id") or "") not in seen_ticks:
                seen_ticks.add(str(tick.get("tick_id") or ""))
                rows.append(_market_fact_from_tick(tick))
        for pricefeed_id in _market_pricefeed_ids(context):
            tick = self.get_latest_market_tick_by_pricefeed(pricefeed_id, max_age_ms, now_ms=effective_now_ms)
            if tick is not None and str(tick.get("tick_id") or "") not in seen_ticks:
                seen_ticks.add(str(tick.get("tick_id") or ""))
                rows.append(_market_fact_from_tick(tick))
        return rows

    def list_identity_facts(self, context: Any) -> list[dict[str, Any]]:
        target_type = _context_value(context, "target_type")
        target_id = _context_value(context, "target_id")
        if not target_type or not target_id:
            return []
        rows: list[dict[str, Any]] = []
        identity = self.get_asset_identity(target_type, target_id)
        if identity is not None:
            rows.append(
                {
                    **identity,
                    "source_id": f"identity:{target_id}",
                    "source_table": "asset_identity_current",
                    "summary_zh": _identity_summary(identity, fallback=f"目标身份 {target_id}"),
                    "quality": "high",
                }
            )
        profile = self.get_latest_profile(target_type, target_id)
        if profile is not None:
            rows.append(
                {
                    **profile,
                    "source_id": f"profile:{target_id}",
                    "source_table": _profile_source_table(target_type),
                    "summary_zh": _identity_summary(profile, fallback=f"目标 Profile {target_id}"),
                    "quality": "medium",
                }
            )
        return rows

    def get_current_discussion_digest(
        self,
        *,
        target_type: str,
        target_id: str,
        window: str,
        scope: str,
        schema_version: str,
    ) -> dict[str, Any] | None:
        normalized_scope = "matched" if scope == "watched" else scope
        return _optional_row(
            self.conn.execute(
                """
                SELECT digest_id, target_type, target_id, "window", scope, schema_version,
                       status, headline_zh, dominant_narratives_json, bull_view_json,
                       bear_view_json, stance_mix_json, attention_valence_mix_json,
                       propagation_read_json, reflexivity_read_json, watch_triggers_json,
                       invalidation_conditions_json, data_gaps_json, semantic_coverage,
                       source_event_count, labeled_event_count, independent_author_count,
                       evidence_refs_json, computed_at_ms, expires_at_ms
                FROM token_discussion_digests
                WHERE target_type = %s
                  AND target_id = %s
                  AND "window" = %s
                  AND scope = %s
                  AND schema_version = %s
                  AND is_current
                  AND status = 'ready'
                ORDER BY computed_at_ms DESC, digest_id DESC
                LIMIT 1
                """,
                (target_type, target_id, window, normalized_scope, schema_version),
            ).fetchone()
        )

    def list_semantic_refs(self, semantic_ids: Sequence[str]) -> list[dict[str, Any]]:
        ids = _stable_ids(semantic_ids)
        if not ids:
            return []
        rows = self.conn.execute(
            """
            SELECT semantic_id, event_id, target_type, target_id, schema_version,
                   status, trade_stance, attention_valence, narrative_cluster_key,
                   claim_type, evidence_type, semantic_confidence, evidence_refs_json,
                   computed_at_ms, source_received_at_ms
            FROM token_mention_semantics
            WHERE semantic_id = ANY(%s)
            ORDER BY source_received_at_ms DESC, semantic_id ASC
            """,
            (ids,),
        ).fetchall()
        return [_row(row) for row in rows]


def _stable_ids(values: Sequence[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _context_value(context: Any, key: str) -> str:
    value = context.get(key) if isinstance(context, dict) else getattr(context, key, None)
    return str(value or "").strip()


def _market_lookup_keys(context: Any) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    _append_market_key(keys, _context_value(context, "target_type"), _context_value(context, "target_id"))
    factor_snapshot = _mapping(_context_raw(context, "factor_snapshot"))
    _append_market_key_from_mapping(keys, _mapping(factor_snapshot.get("subject")))
    market = _mapping(factor_snapshot.get("market"))
    _append_market_key_from_mapping(keys, _mapping(market.get("decision_latest")))
    _append_market_key_from_mapping(keys, _mapping(market.get("event_anchor")))
    return _dedupe_pairs(keys)


def _market_pricefeed_ids(context: Any) -> list[str]:
    factor_snapshot = _mapping(_context_raw(context, "factor_snapshot"))
    market = _mapping(factor_snapshot.get("market"))
    ids = [
        _clean(_mapping(market.get("decision_latest")).get("pricefeed_id")),
        _clean(_mapping(market.get("event_anchor")).get("pricefeed_id")),
        _clean(_mapping(factor_snapshot.get("subject")).get("pricefeed_id")),
    ]
    return sorted({value for value in ids if value})


def _append_market_key_from_mapping(keys: list[tuple[str, str]], row: dict[str, Any]) -> None:
    _append_market_key(keys, _clean(row.get("target_type")), _clean(row.get("target_id")))
    chain = _clean(row.get("chain") or row.get("chain_id"))
    address = _clean(row.get("address") or row.get("token_address") or row.get("asset_address"))
    if chain and address:
        keys.append(("chain_token", f"{chain}:{address}"))
    provider = _clean(row.get("provider") or row.get("exchange"))
    native_market_id = _clean(row.get("native_market_id") or row.get("instrument"))
    if provider and native_market_id:
        keys.append(("cex_symbol", f"{provider.lower()}:{native_market_id.upper()}"))


def _append_market_key(keys: list[tuple[str, str]], target_type: str | None, target_id: str | None) -> None:
    target_type = _clean(target_type)
    target_id = _clean(target_id)
    if not target_type or not target_id:
        return
    if target_type in {"chain_token", "cex_symbol"}:
        keys.append((target_type, target_id))
        return
    if target_type == "Asset":
        parsed = _chain_token_key_from_asset_id(target_id)
        if parsed is not None:
            keys.append(parsed)


def _chain_token_key_from_asset_id(target_id: str) -> tuple[str, str] | None:
    parts = target_id.split(":")
    if len(parts) < 4 or parts[0] != "asset":
        return None
    chain = ":".join(parts[1:-2]).strip()
    address = parts[-1].strip()
    if not chain or not address:
        return None
    return "chain_token", f"{chain}:{address}"


def _dedupe_pairs(values: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    result: list[tuple[str, str]] = []
    for target_type, target_id in values:
        pair = (target_type, target_id)
        if pair in seen:
            continue
        seen.add(pair)
        result.append(pair)
    return result


def _context_raw(context: Any, key: str) -> Any:
    return context.get(key) if isinstance(context, dict) else getattr(context, key, None)


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _market_fact_from_tick(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "source_table": "market_ticks",
        "route": _route_from_target(row.get("target_type")),
        "target_market_type": _target_market_type(row.get("target_type")),
        "instrument_ref": row.get("pricefeed_id") or row.get("target_id"),
        "source_provider": row.get("source_provider"),
        "observed_at_ms": row.get("observed_at_ms"),
    }


def _route_from_target(value: Any) -> str:
    text = str(value or "").lower()
    if "cex" in text or text in {"spot", "perp", "perpetual"}:
        return "cex"
    if "chain" in text or "dex" in text:
        return "meme"
    return "unknown"


def _target_market_type(value: Any) -> str:
    text = str(value or "").strip()
    if text == "chain_token":
        return "dex"
    if text == "cex_symbol":
        return "cex"
    if text:
        return text
    return "unknown"


def _identity_summary(row: dict[str, Any], *, fallback: str) -> str:
    for key in ("summary_zh", "name", "symbol", "description"):
        value = row.get(key)
        if value:
            return str(value)
    return fallback


def _profile_source_table(target_type: str) -> str:
    return "cex_token_profiles" if target_type == "cex_symbol" else "token_profile_current"
