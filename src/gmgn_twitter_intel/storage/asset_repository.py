from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

from psycopg.types.json import Jsonb


@dataclass(frozen=True, slots=True)
class AssetResolutionResult:
    asset: dict[str, Any]
    venue: dict[str, Any] | None = None
    aliases: list[dict[str, Any]] = field(default_factory=list)


class AssetRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def insert_mention(
        self,
        *,
        event_id: str,
        mention_type: str,
        raw_value: str,
        source: str,
        mention_confidence: float,
        created_at_ms: int,
        normalized_symbol: str | None = None,
        chain_hint: str | None = None,
        address_hint: str | None = None,
        source_entity_id: str | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        symbol = _normalize_symbol(normalized_symbol) if normalized_symbol else None
        address = _normalize_address(address_hint)
        mention_id = _stable_id(
            "asset-mention",
            event_id,
            mention_type,
            raw_value,
            symbol or "",
            chain_hint or "",
            address or "",
        )
        self.conn.execute(
            """
            INSERT INTO asset_mentions(
              mention_id, event_id, mention_type, raw_value, normalized_symbol,
              chain_hint, address_hint, source_entity_id, source,
              mention_confidence, created_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(mention_id) DO UPDATE SET
              normalized_symbol = excluded.normalized_symbol,
              chain_hint = excluded.chain_hint,
              address_hint = excluded.address_hint,
              source_entity_id = COALESCE(excluded.source_entity_id, asset_mentions.source_entity_id),
              mention_confidence = excluded.mention_confidence
            """,
            (
                mention_id,
                event_id,
                mention_type,
                raw_value,
                symbol,
                _clean_text(chain_hint),
                address,
                source_entity_id,
                source,
                float(mention_confidence),
                int(created_at_ms),
            ),
        )
        if commit:
            self.conn.commit()
        return self.get_mention(mention_id) or {}

    def insert_mentions(self, mentions: list[Any], *, commit: bool = True) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for mention in mentions:
            rows.append(
                self.insert_mention(
                    event_id=_field(mention, "event_id"),
                    mention_type=_field(mention, "mention_type"),
                    raw_value=_field(mention, "raw_value"),
                    normalized_symbol=_field(mention, "normalized_symbol"),
                    chain_hint=_field(mention, "chain_hint"),
                    address_hint=_field(mention, "address_hint"),
                    source_entity_id=_field(mention, "source_entity_id"),
                    source=_field(mention, "source"),
                    mention_confidence=float(_field(mention, "mention_confidence")),
                    created_at_ms=int(_field(mention, "created_at_ms")),
                    commit=False,
                )
            )
        if commit:
            self.conn.commit()
        return rows

    def get_mention(self, mention_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM asset_mentions WHERE mention_id = %s", (mention_id,)).fetchone()
        return dict(row) if row else None

    def upsert_unresolved_symbol(
        self,
        symbol: str,
        *,
        event_id: str,
        observed_at_ms: int,
        commit: bool = True,
    ) -> dict[str, Any]:
        normalized = _normalize_symbol(symbol)
        asset_id = f"asset:unresolved:{normalized}"
        asset = self._upsert_asset(
            asset_id=asset_id,
            asset_type="unresolved_symbol",
            canonical_symbol=normalized,
            display_name=None,
            identity_status="unresolved",
            confidence=0.2,
            primary_source="deterministic",
            first_seen_event_id=event_id,
            first_seen_at_ms=observed_at_ms,
        )
        self._upsert_alias(
            asset_id=asset_id,
            alias_type="symbol",
            alias_value=normalized,
            normalized_alias=normalized,
            source="deterministic",
            confidence=0.2,
            created_at_ms=observed_at_ms,
        )
        if commit:
            self.conn.commit()
        return asset

    def upsert_ambiguous_symbol(
        self,
        symbol: str,
        *,
        event_id: str,
        observed_at_ms: int,
        commit: bool = True,
    ) -> dict[str, Any]:
        normalized = _normalize_symbol(symbol)
        asset_id = f"asset:ambiguous:{normalized}"
        asset = self._upsert_asset(
            asset_id=asset_id,
            asset_type="ambiguous_symbol",
            canonical_symbol=normalized,
            display_name=None,
            identity_status="ambiguous",
            confidence=0.5,
            primary_source="deterministic",
            first_seen_event_id=event_id,
            first_seen_at_ms=observed_at_ms,
        )
        self._upsert_alias(
            asset_id=asset_id,
            alias_type="symbol",
            alias_value=normalized,
            normalized_alias=normalized,
            source="deterministic",
            confidence=0.5,
            created_at_ms=observed_at_ms,
        )
        if commit:
            self.conn.commit()
        return asset

    def upsert_unresolved_ca(
        self,
        address: str,
        *,
        event_id: str,
        observed_at_ms: int,
        chain_hint: str | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        normalized_address = (_normalize_address(address) or address).lower()
        asset_id = f"asset:unresolved_ca:{normalized_address}"
        display_name = f"{chain_hint}:{address}" if chain_hint else address
        asset = self._upsert_asset(
            asset_id=asset_id,
            asset_type="unresolved_ca",
            canonical_symbol=normalized_address,
            display_name=display_name,
            identity_status="unresolved",
            confidence=0.35,
            primary_source="deterministic",
            first_seen_event_id=event_id,
            first_seen_at_ms=observed_at_ms,
        )
        self._upsert_alias(
            asset_id=asset_id,
            alias_type="ca",
            alias_value=address,
            normalized_alias=normalized_address,
            source="deterministic",
            confidence=0.7,
            created_at_ms=observed_at_ms,
        )
        if commit:
            self.conn.commit()
        return asset

    def upsert_cex_instrument(
        self,
        *,
        exchange: str,
        inst_type: str,
        inst_id: str,
        base_symbol: str,
        quote_symbol: str,
        observed_at_ms: int,
        source_payload_hash: str | None = None,
        commit: bool = True,
    ) -> AssetResolutionResult:
        normalized_exchange = _normalize_key(exchange)
        normalized_inst_type = _normalize_symbol(inst_type)
        normalized_inst_id = inst_id.strip().upper()
        normalized_base = _normalize_symbol(base_symbol)
        normalized_quote = _normalize_symbol(quote_symbol)
        asset_id = f"asset:cex:{normalized_base}"
        venue_id = f"venue:cex:{normalized_exchange}:{normalized_inst_type}:{normalized_inst_id}"
        asset = self._upsert_asset(
            asset_id=asset_id,
            asset_type="cex_asset",
            canonical_symbol=normalized_base,
            display_name=normalized_base,
            identity_status="resolved",
            confidence=0.95,
            primary_source=f"{normalized_exchange}_cex",
            first_seen_event_id=None,
            first_seen_at_ms=observed_at_ms,
        )
        self.conn.execute(
            """
            INSERT INTO asset_venues(
              venue_id, asset_id, venue_type, provider, exchange, chain, address,
              inst_id, base_symbol, quote_symbol, inst_type, is_active, confidence,
              source_payload_hash, created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, 'cex', %s, %s, NULL, NULL, %s, %s, %s, %s, true, 0.95, %s, %s, %s)
            ON CONFLICT(venue_id) DO UPDATE SET
              is_active = true,
              confidence = excluded.confidence,
              source_payload_hash = COALESCE(excluded.source_payload_hash, asset_venues.source_payload_hash),
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                venue_id,
                asset_id,
                normalized_exchange,
                normalized_exchange,
                normalized_inst_id,
                normalized_base,
                normalized_quote,
                normalized_inst_type,
                source_payload_hash,
                int(observed_at_ms),
                _now_ms(),
            ),
        )
        alias = self._upsert_alias(
            asset_id=asset_id,
            alias_type="symbol",
            alias_value=normalized_base,
            normalized_alias=normalized_base,
            source=f"{normalized_exchange}_cex_instrument",
            confidence=0.95,
            created_at_ms=observed_at_ms,
        )
        if commit:
            self.conn.commit()
        return AssetResolutionResult(asset=asset, venue=self.get_venue(venue_id), aliases=[alias])

    def upsert_dex_asset(
        self,
        *,
        chain: str,
        address: str,
        symbol: str,
        observed_at_ms: int,
        event_id: str | None = None,
        provider: str = "deterministic",
        source_payload_hash: str | None = None,
        commit: bool = True,
    ) -> AssetResolutionResult:
        normalized_chain = _normalize_key(chain)
        normalized_address = _normalize_address(address) or address
        normalized_symbol = _normalize_symbol(symbol)
        asset_id = f"asset:dex:{normalized_chain}:{normalized_address.lower()}"
        venue_id = f"venue:dex:{normalized_chain}:{normalized_address.lower()}"
        asset = self._upsert_asset(
            asset_id=asset_id,
            asset_type="dex_asset",
            canonical_symbol=normalized_symbol,
            display_name=normalized_symbol,
            identity_status="resolved",
            confidence=0.95,
            primary_source=provider,
            first_seen_event_id=event_id,
            first_seen_at_ms=observed_at_ms,
        )
        self.conn.execute(
            """
            INSERT INTO asset_venues(
              venue_id, asset_id, venue_type, provider, exchange, chain, address,
              inst_id, base_symbol, quote_symbol, inst_type, is_active, confidence,
              source_payload_hash, created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, 'dex', %s, NULL, %s, %s, NULL, NULL, NULL, NULL, true, 0.95, %s, %s, %s)
            ON CONFLICT(venue_id) DO UPDATE SET
              is_active = true,
              confidence = excluded.confidence,
              source_payload_hash = COALESCE(excluded.source_payload_hash, asset_venues.source_payload_hash),
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                venue_id,
                asset_id,
                provider,
                normalized_chain,
                normalized_address,
                source_payload_hash,
                int(observed_at_ms),
                _now_ms(),
            ),
        )
        aliases = [
            self._upsert_alias(
                asset_id=asset_id,
                alias_type="symbol",
                alias_value=normalized_symbol,
                normalized_alias=normalized_symbol,
                source=provider,
                confidence=0.95,
                created_at_ms=observed_at_ms,
            ),
            self._upsert_alias(
                asset_id=asset_id,
                alias_type="ca",
                alias_value=normalized_address,
                normalized_alias=normalized_address.lower(),
                source=provider,
                confidence=1.0,
                created_at_ms=observed_at_ms,
            ),
        ]
        if commit:
            self.conn.commit()
        return AssetResolutionResult(asset=asset, venue=self.get_venue(venue_id), aliases=aliases)

    def get_asset(self, asset_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM assets WHERE asset_id = %s", (asset_id,)).fetchone()
        return dict(row) if row else None

    def get_venue(self, venue_id: str | None) -> dict[str, Any] | None:
        if not venue_id:
            return None
        row = self.conn.execute("SELECT * FROM asset_venues WHERE venue_id = %s", (venue_id,)).fetchone()
        return dict(row) if row else None

    def candidates_for_symbol(self, symbol: str) -> list[dict[str, Any]]:
        normalized = _normalize_symbol(symbol)
        rows = self.conn.execute(
            """
            SELECT
              assets.asset_id,
              assets.asset_type,
              assets.canonical_symbol,
              assets.display_name,
              assets.identity_status,
              assets.confidence AS asset_confidence,
              assets.primary_source,
              asset_aliases.alias_id,
              asset_aliases.alias_type,
              asset_aliases.source AS alias_source,
              asset_aliases.confidence AS alias_confidence,
              asset_venues.venue_id,
              asset_venues.venue_type,
              asset_venues.provider AS venue_provider,
              asset_venues.exchange,
              asset_venues.chain,
              asset_venues.address,
              asset_venues.inst_id,
              asset_venues.base_symbol,
              asset_venues.quote_symbol,
              asset_venues.inst_type,
              asset_venues.is_active
            FROM asset_aliases
            JOIN assets ON assets.asset_id = asset_aliases.asset_id
            LEFT JOIN asset_venues
              ON asset_venues.asset_id = assets.asset_id AND asset_venues.is_active = true
            WHERE asset_aliases.alias_type = 'symbol'
              AND asset_aliases.normalized_alias = %s
            ORDER BY
              asset_aliases.confidence DESC,
              assets.confidence DESC,
              CASE asset_venues.venue_type WHEN 'cex' THEN 0 WHEN 'dex' THEN 1 ELSE 2 END,
              asset_venues.inst_id NULLS LAST,
              asset_venues.chain NULLS LAST
            """,
            (normalized,),
        ).fetchall()
        return [dict(row) for row in rows]

    def insert_resolution_candidate(
        self,
        *,
        mention_id: str,
        provider: str,
        candidate_kind: str,
        score: float,
        decision: str,
        asset_id: str | None = None,
        venue_id: str | None = None,
        reasons: list[str] | None = None,
        risks: list[str] | None = None,
        raw_observation_id: str | None = None,
        created_at_ms: int | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        candidate_id = _stable_id(
            "asset-candidate",
            mention_id,
            provider,
            candidate_kind,
            asset_id or "",
            venue_id or "",
            str(score),
            decision,
        )
        self.conn.execute(
            """
            INSERT INTO asset_resolution_candidates(
              candidate_id, mention_id, asset_id, venue_id, provider, candidate_kind,
              score, decision, reasons_json, risks_json, raw_observation_id, created_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(candidate_id) DO UPDATE SET
              score = excluded.score,
              decision = excluded.decision,
              reasons_json = excluded.reasons_json,
              risks_json = excluded.risks_json
            """,
            (
                candidate_id,
                mention_id,
                asset_id,
                venue_id,
                provider,
                candidate_kind,
                float(score),
                decision,
                Jsonb(reasons or []),
                Jsonb(risks or []),
                raw_observation_id,
                int(created_at_ms or _now_ms()),
            ),
        )
        if commit:
            self.conn.commit()
        return self._row_by_id("asset_resolution_candidates", "candidate_id", candidate_id) or {}

    def insert_attribution(
        self,
        *,
        event_id: str,
        mention_id: str,
        asset_id: str,
        venue_id: str | None,
        attribution_status: str,
        attribution_weight: float,
        confidence: float,
        identity_status: str,
        reasons: list[str] | None,
        risks: list[str] | None,
        decision_time_ms: int,
        created_at_ms: int,
        commit: bool = True,
    ) -> dict[str, Any]:
        attribution_id = _stable_id("asset-attribution", mention_id, asset_id, venue_id or "")
        self.conn.execute(
            """
            INSERT INTO asset_attributions(
              attribution_id, event_id, mention_id, asset_id, venue_id,
              attribution_status, attribution_weight, confidence, identity_status,
              reasons_json, risks_json, decision_time_ms, created_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(attribution_id) DO UPDATE SET
              attribution_status = excluded.attribution_status,
              attribution_weight = excluded.attribution_weight,
              confidence = excluded.confidence,
              identity_status = excluded.identity_status,
              reasons_json = excluded.reasons_json,
              risks_json = excluded.risks_json,
              decision_time_ms = excluded.decision_time_ms
            """,
            (
                attribution_id,
                event_id,
                mention_id,
                asset_id,
                venue_id,
                attribution_status,
                float(attribution_weight),
                float(confidence),
                identity_status,
                Jsonb(reasons or []),
                Jsonb(risks or []),
                int(decision_time_ms),
                int(created_at_ms),
            ),
        )
        if commit:
            self.conn.commit()
        return self._row_by_id("asset_attributions", "attribution_id", attribution_id) or {}

    def insert_market_snapshot(
        self,
        *,
        asset_id: str,
        venue_id: str,
        provider: str,
        observed_at_ms: int,
        price_usd: float | None = None,
        market_cap_usd: float | None = None,
        liquidity_usd: float | None = None,
        volume_24h_usd: float | None = None,
        open_interest_usd: float | None = None,
        holders: int | None = None,
        price_change_5m_pct: float | None = None,
        price_change_1h_pct: float | None = None,
        price_change_24h_pct: float | None = None,
        source_payload_hash: str | None = None,
        raw_observation_id: str | None = None,
        created_at_ms: int | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        snapshot_id = _stable_id("asset-market", asset_id, venue_id, provider, str(observed_at_ms))
        self.conn.execute(
            """
            INSERT INTO asset_market_snapshots(
              snapshot_id, asset_id, venue_id, provider, observed_at_ms, price_usd,
              market_cap_usd, liquidity_usd, volume_24h_usd, open_interest_usd,
              holders, price_change_5m_pct, price_change_1h_pct, price_change_24h_pct,
              source_payload_hash, raw_observation_id, created_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(snapshot_id) DO UPDATE SET
              price_usd = excluded.price_usd,
              market_cap_usd = excluded.market_cap_usd,
              liquidity_usd = excluded.liquidity_usd,
              volume_24h_usd = excluded.volume_24h_usd,
              open_interest_usd = excluded.open_interest_usd,
              holders = excluded.holders,
              source_payload_hash = COALESCE(excluded.source_payload_hash, asset_market_snapshots.source_payload_hash)
            """,
            (
                snapshot_id,
                asset_id,
                venue_id,
                provider,
                int(observed_at_ms),
                price_usd,
                market_cap_usd,
                liquidity_usd,
                volume_24h_usd,
                open_interest_usd,
                holders,
                price_change_5m_pct,
                price_change_1h_pct,
                price_change_24h_pct,
                source_payload_hash,
                raw_observation_id,
                int(created_at_ms or _now_ms()),
            ),
        )
        if commit:
            self.conn.commit()
        return self._row_by_id("asset_market_snapshots", "snapshot_id", snapshot_id) or {}

    def queue_resolution_job(
        self,
        *,
        job_type: str,
        normalized_symbol: str | None = None,
        chain_hint: str | None = None,
        address_hint: str | None = None,
        next_run_at_ms: int | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        symbol = _normalize_symbol(normalized_symbol) if normalized_symbol else None
        address = _normalize_address(address_hint)
        job_id = _stable_id("asset-job", job_type, symbol or "", chain_hint or "", address or "")
        now_ms = _now_ms()
        self.conn.execute(
            """
            INSERT INTO asset_resolution_jobs(
              job_id, job_type, normalized_symbol, chain_hint, address_hint, status,
              attempt_count, next_run_at_ms, last_error, created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, 'queued', 0, %s, NULL, %s, %s)
            ON CONFLICT(job_id) DO UPDATE SET
              status = CASE
                WHEN asset_resolution_jobs.status IN ('succeeded', 'running') THEN asset_resolution_jobs.status
                ELSE 'queued'
              END,
              next_run_at_ms = LEAST(asset_resolution_jobs.next_run_at_ms, excluded.next_run_at_ms),
              updated_at_ms = excluded.updated_at_ms
            """,
            (job_id, job_type, symbol, _clean_text(chain_hint), address, int(next_run_at_ms or now_ms), now_ms, now_ms),
        )
        if commit:
            self.conn.commit()
        return self._row_by_id("asset_resolution_jobs", "job_id", job_id) or {}

    def events_for_symbol_mentions(
        self,
        symbol: str,
        *,
        limit: int,
        watched_only: bool = False,
    ) -> list[dict[str, Any]]:
        normalized = _normalize_symbol(symbol)
        clauses = ["asset_mentions.normalized_symbol = %s"]
        params: list[Any] = [normalized]
        if watched_only:
            clauses.append("events.is_watched = true")
        params.append(max(0, int(limit)))
        rows = self.conn.execute(
            f"""
            SELECT
              events.*,
              asset_mentions.mention_id,
              asset_mentions.mention_type,
              asset_mentions.raw_value AS mention_raw_value,
              asset_mentions.normalized_symbol,
              asset_attributions.asset_id,
              asset_attributions.venue_id,
              asset_attributions.attribution_status,
              asset_attributions.confidence AS attribution_confidence,
              asset_attributions.identity_status AS attribution_identity_status
            FROM asset_mentions
            JOIN events ON events.event_id = asset_mentions.event_id
            LEFT JOIN asset_attributions ON asset_attributions.mention_id = asset_mentions.mention_id
            WHERE {' AND '.join(clauses)}
            ORDER BY events.received_at_ms DESC, asset_mentions.mention_id ASC
            LIMIT %s
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def asset_attributions_for_asset(self, asset_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT asset_attributions.*, assets.canonical_symbol, asset_venues.venue_type,
                   asset_venues.exchange, asset_venues.chain, asset_venues.address, asset_venues.inst_id
            FROM asset_attributions
            JOIN assets ON assets.asset_id = asset_attributions.asset_id
            LEFT JOIN asset_venues ON asset_venues.venue_id = asset_attributions.venue_id
            WHERE asset_attributions.asset_id = %s
            ORDER BY asset_attributions.decision_time_ms DESC
            LIMIT %s
            """,
            (asset_id, max(0, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]

    def asset_attributions_for_symbol(self, symbol: str, *, limit: int = 50) -> list[dict[str, Any]]:
        normalized = _normalize_symbol(symbol)
        rows = self.conn.execute(
            """
            SELECT asset_attributions.*, assets.canonical_symbol, assets.asset_type,
                   asset_venues.venue_type, asset_venues.exchange, asset_venues.chain,
                   asset_venues.address, asset_venues.inst_id
            FROM asset_attributions
            JOIN assets ON assets.asset_id = asset_attributions.asset_id
            LEFT JOIN asset_venues ON asset_venues.venue_id = asset_attributions.venue_id
            WHERE assets.canonical_symbol = %s
            ORDER BY asset_attributions.decision_time_ms DESC
            LIMIT %s
            """,
            (normalized, max(0, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]

    def recent_asset_attributions(
        self,
        *,
        since_ms: int,
        watched_only: bool,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        clauses = ["asset_attributions.decision_time_ms >= %s"]
        params: list[Any] = [int(since_ms)]
        if watched_only:
            clauses.append("events.is_watched = true")
        params.append(max(0, int(limit)))
        rows = self.conn.execute(
            f"""
            SELECT
              asset_attributions.*,
              assets.asset_type,
              assets.canonical_symbol,
              assets.display_name,
              asset_venues.venue_type,
              asset_venues.exchange,
              asset_venues.chain,
              asset_venues.address,
              asset_venues.inst_id,
              asset_venues.base_symbol,
              asset_venues.quote_symbol,
              asset_venues.inst_type,
              events.author_handle,
              events.is_watched,
              events.received_at_ms
            FROM asset_attributions
            JOIN assets ON assets.asset_id = asset_attributions.asset_id
            JOIN events ON events.event_id = asset_attributions.event_id
            LEFT JOIN asset_venues ON asset_venues.venue_id = asset_attributions.venue_id
            WHERE {' AND '.join(clauses)}
            ORDER BY asset_attributions.decision_time_ms DESC
            LIMIT %s
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def asset_timeline_rows(
        self,
        *,
        asset_id: str,
        since_ms: int,
        watched_only: bool,
        limit: int,
        cursor_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["asset_attributions.asset_id = %s", "events.received_at_ms >= %s"]
        params: list[Any] = [asset_id, int(since_ms)]
        if cursor_ms is not None:
            clauses.append("events.received_at_ms < %s")
            params.append(int(cursor_ms))
        if watched_only:
            clauses.append("events.is_watched = true")
        params.append(max(0, int(limit)))
        rows = self.conn.execute(
            f"""
            SELECT
              events.event_id,
              events.author_handle,
              events.text,
              events.is_watched,
              events.received_at_ms,
              asset_attributions.asset_id,
              asset_attributions.attribution_status,
              asset_attributions.confidence,
              assets.asset_type,
              assets.canonical_symbol,
              assets.identity_status,
              asset_venues.venue_id,
              asset_venues.venue_type,
              asset_venues.exchange,
              asset_venues.chain,
              asset_venues.address,
              asset_venues.inst_id,
              asset_venues.base_symbol,
              asset_venues.quote_symbol,
              asset_venues.inst_type
            FROM asset_attributions
            JOIN events ON events.event_id = asset_attributions.event_id
            JOIN assets ON assets.asset_id = asset_attributions.asset_id
            LEFT JOIN asset_venues ON asset_venues.venue_id = asset_attributions.venue_id
            WHERE {' AND '.join(clauses)}
            ORDER BY events.received_at_ms DESC, events.event_id ASC
            LIMIT %s
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def asset_seen_before(
        self,
        *,
        asset_id: str,
        author_handle: str | None,
        before_ms: int,
    ) -> tuple[bool, bool]:
        global_row = self.conn.execute(
            """
            SELECT 1 AS found
            FROM asset_attributions
            WHERE asset_id = %s AND decision_time_ms < %s
            LIMIT 1
            """,
            (asset_id, int(before_ms)),
        ).fetchone()
        author_seen = False
        if author_handle:
            author_row = self.conn.execute(
                """
                SELECT 1 AS found
                FROM asset_attributions
                JOIN events ON events.event_id = asset_attributions.event_id
                WHERE asset_attributions.asset_id = %s
                  AND asset_attributions.decision_time_ms < %s
                  AND events.author_handle = %s
                LIMIT 1
                """,
                (asset_id, int(before_ms), author_handle),
            ).fetchone()
            author_seen = bool(author_row)
        return bool(global_row), author_seen

    def _upsert_asset(
        self,
        *,
        asset_id: str,
        asset_type: str,
        canonical_symbol: str,
        display_name: str | None,
        identity_status: str,
        confidence: float,
        primary_source: str,
        first_seen_event_id: str | None,
        first_seen_at_ms: int,
    ) -> dict[str, Any]:
        self.conn.execute(
            """
            INSERT INTO assets(
              asset_id, asset_type, canonical_symbol, display_name, identity_status,
              confidence, primary_source, first_seen_event_id, first_seen_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(asset_id) DO UPDATE SET
              canonical_symbol = excluded.canonical_symbol,
              display_name = COALESCE(excluded.display_name, assets.display_name),
              identity_status = excluded.identity_status,
              confidence = GREATEST(assets.confidence, excluded.confidence),
              primary_source = CASE
                WHEN excluded.confidence >= assets.confidence THEN excluded.primary_source
                ELSE assets.primary_source
              END,
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                asset_id,
                asset_type,
                _normalize_symbol(canonical_symbol),
                display_name,
                identity_status,
                float(confidence),
                primary_source,
                first_seen_event_id,
                int(first_seen_at_ms),
                _now_ms(),
            ),
        )
        return self.get_asset(asset_id) or {}

    def _upsert_alias(
        self,
        *,
        asset_id: str,
        alias_type: str,
        alias_value: str,
        normalized_alias: str,
        source: str,
        confidence: float,
        created_at_ms: int,
    ) -> dict[str, Any]:
        alias_id = _stable_id("asset-alias", alias_type, normalized_alias, asset_id, source)
        self.conn.execute(
            """
            INSERT INTO asset_aliases(
              alias_id, asset_id, alias_type, alias_value, normalized_alias,
              source, confidence, created_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(alias_type, normalized_alias, asset_id, source) DO UPDATE SET
              alias_value = excluded.alias_value,
              confidence = GREATEST(asset_aliases.confidence, excluded.confidence)
            """,
            (
                alias_id,
                asset_id,
                alias_type,
                alias_value,
                normalized_alias,
                source,
                float(confidence),
                int(created_at_ms),
            ),
        )
        return self._row_by_id("asset_aliases", "alias_id", alias_id) or {}

    def _row_by_id(self, table: str, column: str, value: str) -> dict[str, Any] | None:
        row = self.conn.execute(f"SELECT * FROM {table} WHERE {column} = %s", (value,)).fetchone()
        return dict(row) if row else None


def _normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def _normalize_key(value: str) -> str:
    return value.strip().lower()


def _normalize_address(address: str | None) -> str | None:
    if not address:
        return None
    return address.strip()


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _stable_id(prefix: str, *parts: str) -> str:
    payload = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:{digest}"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _field(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value[name]
    return getattr(value, name)
