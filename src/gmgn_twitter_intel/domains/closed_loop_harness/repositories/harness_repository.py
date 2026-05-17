from __future__ import annotations

import json
import time
from typing import Any

from psycopg.types.json import Jsonb

_HORIZON_MS = {
    "6h": 6 * 60 * 60 * 1000,
    "24h": 24 * 60 * 60 * 1000,
}


class HarnessRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def upsert_social_event_extraction(
        self,
        *,
        extraction_id: str,
        event_id: str,
        run_id: str | None,
        author_handle: str | None,
        received_at_ms: int,
        schema_version: str,
        model_version: str,
        event_type: str,
        source_action: str,
        subject: str,
        direction_hint: str,
        attention_mechanism: str,
        impact_hint: float,
        semantic_novelty_hint: float,
        confidence: float,
        is_signal_event: bool,
        anchor_terms: list[dict[str, Any]],
        token_candidates: list[dict[str, Any]],
        semantic_risks: list[str],
        summary_zh: str,
        raw_response: dict[str, Any],
        commit: bool = True,
    ) -> dict[str, Any]:
        now_ms = _now_ms()
        self.conn.execute(
            """
            INSERT INTO social_event_extractions(
              extraction_id, event_id, run_id, author_handle, received_at_ms, schema_version, model_version,
              event_type, source_action, subject, direction_hint, attention_mechanism, impact_hint,
              semantic_novelty_hint, confidence, is_signal_event, anchor_terms_json, token_candidates_json,
              semantic_risks_json, summary_zh, raw_response_json, created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(event_id) DO UPDATE SET
              run_id = excluded.run_id,
              author_handle = excluded.author_handle,
              received_at_ms = excluded.received_at_ms,
              schema_version = excluded.schema_version,
              model_version = excluded.model_version,
              event_type = excluded.event_type,
              source_action = excluded.source_action,
              subject = excluded.subject,
              direction_hint = excluded.direction_hint,
              attention_mechanism = excluded.attention_mechanism,
              impact_hint = excluded.impact_hint,
              semantic_novelty_hint = excluded.semantic_novelty_hint,
              confidence = excluded.confidence,
              is_signal_event = excluded.is_signal_event,
              anchor_terms_json = excluded.anchor_terms_json,
              token_candidates_json = excluded.token_candidates_json,
              semantic_risks_json = excluded.semantic_risks_json,
              summary_zh = excluded.summary_zh,
              raw_response_json = excluded.raw_response_json,
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                extraction_id,
                event_id,
                run_id,
                author_handle,
                int(received_at_ms),
                schema_version,
                model_version,
                event_type,
                source_action,
                subject,
                direction_hint,
                attention_mechanism,
                float(impact_hint),
                float(semantic_novelty_hint),
                float(confidence),
                is_signal_event,
                _json(anchor_terms),
                _json(token_candidates),
                _json(semantic_risks),
                summary_zh,
                _json(raw_response),
                now_ms,
                now_ms,
            ),
        )
        if commit:
            self.conn.commit()
        return self.social_event_for_event(event_id) or {}

    def social_event_for_event(self, event_id: str) -> dict[str, Any] | None:
        rows = self.conn.execute(
            "SELECT * FROM social_event_extractions WHERE event_id = %s",
            (event_id,),
        ).fetchall()
        return self._decode_social_event(dict(rows[0])) if rows else None

    def list_social_events(
        self,
        *,
        window_ms: int,
        limit: int,
        now_ms: int | None = None,
        handles: set[str] | None = None,
        event_types: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        now = now_ms if now_ms is not None else _now_ms()
        clauses = ["se.received_at_ms >= %s"]
        params: list[Any] = [now - window_ms]
        if handles:
            normalized = sorted(handle.lower().lstrip("@") for handle in handles)
            clauses.append(f"lower(se.author_handle) IN ({','.join('%s' for _ in normalized)})")
            params.extend(normalized)
        if event_types:
            normalized_types = sorted(event_types)
            clauses.append(f"se.event_type IN ({','.join('%s' for _ in normalized_types)})")
            params.extend(normalized_types)
        rows = self.conn.execute(
            f"""
            SELECT se.*, e.event_json
            FROM social_event_extractions se
            LEFT JOIN events e ON e.event_id = se.event_id
            WHERE {" AND ".join(clauses)}
            ORDER BY se.received_at_ms DESC
            LIMIT %s
            """,
            (*params, max(0, int(limit))),
        ).fetchall()
        return [self._decode_social_event(dict(row)) for row in rows]

    def upsert_attention_seed(
        self,
        *,
        seed_id: str,
        extraction_id: str,
        event_id: str,
        author_handle: str | None,
        received_at_ms: int,
        event_type: str,
        subject: str,
        anchor_terms: list[dict[str, Any]],
        token_uptake_count: int,
        top_linked_symbols: list[str],
        seed_status: str,
        risks: list[str],
        commit: bool = True,
    ) -> dict[str, Any]:
        now_ms = _now_ms()
        self.conn.execute(
            """
            INSERT INTO attention_seeds(
              seed_id, extraction_id, event_id, author_handle, received_at_ms, event_type, subject,
              anchor_terms_json, token_uptake_count, top_linked_symbols_json, seed_status, risks_json,
              created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(extraction_id) DO UPDATE SET
              author_handle = excluded.author_handle,
              received_at_ms = excluded.received_at_ms,
              event_type = excluded.event_type,
              subject = excluded.subject,
              anchor_terms_json = excluded.anchor_terms_json,
              token_uptake_count = excluded.token_uptake_count,
              top_linked_symbols_json = excluded.top_linked_symbols_json,
              seed_status = excluded.seed_status,
              risks_json = excluded.risks_json,
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                seed_id,
                extraction_id,
                event_id,
                author_handle,
                int(received_at_ms),
                event_type,
                subject,
                _json(anchor_terms),
                int(token_uptake_count),
                _json(top_linked_symbols),
                seed_status,
                _json(risks),
                now_ms,
                now_ms,
            ),
        )
        if commit:
            self.conn.commit()
        return self.attention_seed(seed_id) or self.attention_seed_for_extraction(extraction_id) or {}

    def attention_seed(self, seed_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM attention_seeds WHERE seed_id = %s", (seed_id,)).fetchone()
        return self._decode_seed(dict(row)) if row else None

    def attention_seed_for_extraction(self, extraction_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM attention_seeds WHERE extraction_id = %s", (extraction_id,)).fetchone()
        return self._decode_seed(dict(row)) if row else None

    def attention_seed_for_event(self, event_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM attention_seeds WHERE event_id = %s", (event_id,)).fetchone()
        return self._decode_seed(dict(row)) if row else None

    def list_attention_seeds(
        self,
        *,
        window_ms: int,
        limit: int,
        now_ms: int | None = None,
        handles: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        now = now_ms if now_ms is not None else _now_ms()
        clauses = ["received_at_ms >= %s"]
        params: list[Any] = [now - window_ms]
        if handles:
            normalized = sorted(handle.lower().lstrip("@") for handle in handles)
            clauses.append(f"lower(author_handle) IN ({','.join('%s' for _ in normalized)})")
            params.extend(normalized)
        rows = self.conn.execute(
            f"""
            SELECT * FROM attention_seeds
            WHERE {" AND ".join(clauses)}
            ORDER BY received_at_ms DESC
            LIMIT %s
            """,
            (*params, max(0, int(limit))),
        ).fetchall()
        return [self._decode_seed(dict(row)) for row in rows]

    def upsert_event_cluster(self, *, commit: bool = True, **data: Any) -> dict[str, Any]:
        now_ms = _now_ms()
        self.conn.execute(
            """
            INSERT INTO event_clusters(
              cluster_id, seed_id, extraction_id, event_id, asset, event_type, source, first_seen_at_ms,
              last_seen_at_ms, direction, impact, confidence, novelty, pricedness, base_score, event_score,
              source_list_json, raw_event_ids_json, representative_text, risks_json, created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(cluster_id) DO UPDATE SET
              last_seen_at_ms = excluded.last_seen_at_ms,
              asset = excluded.asset,
              event_score = excluded.event_score,
              source_list_json = excluded.source_list_json,
              raw_event_ids_json = excluded.raw_event_ids_json,
              risks_json = excluded.risks_json,
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                data["cluster_id"],
                data.get("seed_id"),
                data.get("extraction_id"),
                data.get("event_id"),
                data.get("asset"),
                data["event_type"],
                data.get("source"),
                int(data["first_seen_at_ms"]),
                int(data["last_seen_at_ms"]),
                int(data["direction"]),
                float(data["impact"]),
                float(data["confidence"]),
                float(data["novelty"]),
                float(data["pricedness"]),
                float(data["base_score"]),
                float(data["event_score"]),
                _json(data.get("source_list", [])),
                _json(data.get("raw_event_ids", [])),
                data.get("representative_text", ""),
                _json(data.get("risks", [])),
                now_ms,
                now_ms,
            ),
        )
        if commit:
            self.conn.commit()
        row = self.conn.execute("SELECT * FROM event_clusters WHERE cluster_id = %s", (data["cluster_id"],)).fetchone()
        return self._decode_cluster(dict(row)) if row else {}

    def create_snapshot(self, *, commit: bool = True, **data: Any) -> dict[str, Any]:
        now_ms = _now_ms()
        versions = dict(data.get("versions") or {})
        config_version = str(versions.get("config_version") or "unknown")
        self.conn.execute(
            """
            INSERT INTO harness_snapshots(
              snapshot_id, source_event_id, seed_id, asset, decision_time_ms, horizon, combined_score,
              policy_signal, shadow_signal, market_state_json, event_clusters_json, versions_json,
              config_version, outcome_status, credit_status, risks_json, created_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', 'none', %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                data["snapshot_id"],
                data.get("source_event_id"),
                data.get("seed_id"),
                data["asset"],
                int(data["decision_time_ms"]),
                data["horizon"],
                float(data["combined_score"]),
                data["policy_signal"],
                data["shadow_signal"],
                _json(data.get("market_state", {})),
                _json(data.get("event_clusters", [])),
                _json(versions),
                config_version,
                _json(data.get("risks", [])),
                now_ms,
            ),
        )
        if commit:
            self.conn.commit()
        return self.snapshot_by_id(str(data["snapshot_id"])) or self._snapshot_by_unique(data, config_version) or {}

    def snapshot_by_id(self, snapshot_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM harness_snapshots WHERE snapshot_id = %s", (snapshot_id,)).fetchone()
        return self._decode_snapshot(dict(row)) if row else None

    def list_snapshots(
        self,
        *,
        window_ms: int,
        limit: int,
        now_ms: int | None = None,
        horizon: str | None = None,
        asset: str | None = None,
    ) -> list[dict[str, Any]]:
        now = now_ms if now_ms is not None else _now_ms()
        clauses = ["decision_time_ms >= %s"]
        params: list[Any] = [now - window_ms]
        if horizon:
            clauses.append("horizon = %s")
            params.append(horizon)
        if asset:
            clauses.append("upper(asset) = %s")
            params.append(asset.upper())
        rows = self.conn.execute(
            f"""
            SELECT * FROM harness_snapshots
            WHERE {" AND ".join(clauses)}
            ORDER BY decision_time_ms DESC
            LIMIT %s
            """,
            (*params, max(0, int(limit))),
        ).fetchall()
        return [self._decode_snapshot(dict(row)) for row in rows]

    def snapshots_for_event(self, event_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM harness_snapshots
            WHERE source_event_id = %s
            ORDER BY decision_time_ms DESC, horizon ASC
            """,
            (event_id,),
        ).fetchall()
        return [self._decode_snapshot(dict(row)) for row in rows]

    def clusters_for_event(self, event_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM event_clusters
            WHERE event_id = %s
            ORDER BY first_seen_at_ms DESC
            """,
            (event_id,),
        ).fetchall()
        return [self._decode_cluster(dict(row)) for row in rows]

    def harness_for_event(self, event_id: str) -> dict[str, Any] | None:
        social_event = self.social_event_for_event(event_id)
        seed = self.attention_seed_for_event(event_id)
        clusters = self.clusters_for_event(event_id)
        snapshots = self.snapshots_for_event(event_id)
        if social_event is None and seed is None and not clusters and not snapshots:
            return None
        return {
            "social_event": social_event,
            "attention_seed": seed,
            "clusters": clusters,
            "snapshots": snapshots,
        }

    def harness_for_events(self, event_ids: tuple[str, ...]) -> dict[str, dict[str, Any] | None]:
        ids = _event_ids(event_ids)
        if not ids:
            return {}
        social_events = self._social_events_for_events(ids)
        seeds = self._attention_seeds_for_events(ids)
        clusters = self._clusters_for_events(ids)
        snapshots = self._snapshots_for_events(ids)
        payloads: dict[str, dict[str, Any] | None] = {}
        for event_id in ids:
            social_event = social_events.get(event_id)
            seed = seeds.get(event_id)
            event_clusters = clusters.get(event_id, [])
            event_snapshots = snapshots.get(event_id, [])
            if social_event is None and seed is None and not event_clusters and not event_snapshots:
                payloads[event_id] = None
                continue
            payloads[event_id] = {
                "social_event": social_event,
                "attention_seed": seed,
                "clusters": event_clusters,
                "snapshots": event_snapshots,
            }
        return payloads

    def _social_events_for_events(self, event_ids: list[str]) -> dict[str, dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM social_event_extractions
            WHERE event_id = ANY(%s)
            ORDER BY event_id, extraction_id
            """,
            (event_ids,),
        ).fetchall()
        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            item = self._decode_social_event(dict(row))
            grouped.setdefault(str(item["event_id"]), item)
        return grouped

    def _attention_seeds_for_events(self, event_ids: list[str]) -> dict[str, dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM attention_seeds
            WHERE event_id = ANY(%s)
            ORDER BY event_id, seed_id
            """,
            (event_ids,),
        ).fetchall()
        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            item = self._decode_seed(dict(row))
            grouped.setdefault(str(item["event_id"]), item)
        return grouped

    def _clusters_for_events(self, event_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM event_clusters
            WHERE event_id = ANY(%s)
            ORDER BY event_id, first_seen_at_ms DESC
            """,
            (event_ids,),
        ).fetchall()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            item = self._decode_cluster(dict(row))
            grouped.setdefault(str(item["event_id"]), []).append(item)
        return grouped

    def _snapshots_for_events(self, event_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM harness_snapshots
            WHERE source_event_id = ANY(%s)
            ORDER BY source_event_id, decision_time_ms DESC, horizon ASC
            """,
            (event_ids,),
        ).fetchall()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            item = self._decode_snapshot(dict(row))
            grouped.setdefault(str(item["source_event_id"]), []).append(item)
        return grouped

    def seed_links_for_token(
        self,
        *,
        identity_key: str | None,
        token_id: str | None,
        chain: str | None,
        address: str | None,
        symbol: str | None,
        since_ms: int,
        token_seen_ms: int | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        clauses, params = _snapshot_asset_match_clauses(
            identity_key=identity_key,
            token_id=token_id,
            chain=chain,
            address=address,
            symbol=symbol,
        )
        if not clauses:
            return []
        time_clauses = ["hs.decision_time_ms >= %s"]
        time_params: list[Any] = [int(since_ms)]
        if token_seen_ms is not None:
            time_clauses.append("hs.decision_time_ms <= %s")
            time_params.append(int(token_seen_ms))
        rows = self.conn.execute(
            f"""
            SELECT hs.*, seed.seed_id, seed.extraction_id, seed.event_id AS seed_event_id,
                   seed.author_handle AS seed_author_handle, seed.received_at_ms AS seed_received_at_ms,
                   seed.event_type AS seed_event_type, seed.subject AS seed_subject,
                   seed.anchor_terms_json AS seed_anchor_terms_json,
                   seed.token_uptake_count AS seed_token_uptake_count,
                   seed.top_linked_symbols_json AS seed_top_linked_symbols_json,
                   seed.seed_status AS seed_status, seed.risks_json AS seed_risks_json,
                   seed.created_at_ms AS seed_created_at_ms, seed.updated_at_ms AS seed_updated_at_ms
            FROM harness_snapshots hs
            JOIN attention_seeds seed ON seed.seed_id = hs.seed_id
            WHERE {" AND ".join(time_clauses)}
              AND ({" OR ".join(clauses)})
            ORDER BY
              hs.shadow_signal != 'NO_TRADE' DESC,
              ABS(hs.combined_score) DESC,
              hs.decision_time_ms DESC
            LIMIT %s
            """,
            (*time_params, *params, max(0, int(limit))),
        ).fetchall()
        links = []
        for row in rows:
            raw = dict(row)
            seed = self._decode_seed(
                {
                    "seed_id": raw.pop("seed_id"),
                    "extraction_id": raw.pop("extraction_id"),
                    "event_id": raw.pop("seed_event_id"),
                    "author_handle": raw.pop("seed_author_handle"),
                    "received_at_ms": raw.pop("seed_received_at_ms"),
                    "event_type": raw.pop("seed_event_type"),
                    "subject": raw.pop("seed_subject"),
                    "anchor_terms_json": raw.pop("seed_anchor_terms_json"),
                    "token_uptake_count": raw.pop("seed_token_uptake_count"),
                    "top_linked_symbols_json": raw.pop("seed_top_linked_symbols_json"),
                    "seed_status": raw.pop("seed_status"),
                    "risks_json": raw.pop("seed_risks_json"),
                    "created_at_ms": raw.pop("seed_created_at_ms"),
                    "updated_at_ms": raw.pop("seed_updated_at_ms"),
                }
            )
            if token_seen_ms is not None:
                seed["lag_ms"] = max(0, int(token_seen_ms) - int(seed["received_at_ms"]))
            snapshot = self._decode_snapshot(raw)
            links.append({"seed": seed, "snapshot": snapshot})
        return links

    def record_decision(self, *, commit: bool = True, **data: Any) -> dict[str, Any]:
        now_ms = _now_ms()
        self.conn.execute(
            """
            INSERT INTO harness_decisions(
              decision_id, snapshot_id, asset, decision_time_ms, execution_mode, signal, side, size,
              entry_price, risk_reject_reason, config_version, created_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(decision_id) DO NOTHING
            """,
            (
                data["decision_id"],
                data["snapshot_id"],
                data["asset"],
                int(data["decision_time_ms"]),
                data["execution_mode"],
                data["signal"],
                data["side"],
                float(data.get("size") or 0.0),
                data.get("entry_price"),
                data.get("risk_reject_reason"),
                data["config_version"],
                now_ms,
            ),
        )
        if commit:
            self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM harness_decisions WHERE decision_id = %s",
            (data["decision_id"],),
        ).fetchone()
        return dict(row) if row else {}

    def record_outcome(self, *, commit: bool = True, **data: Any) -> dict[str, Any]:
        now_ms = _now_ms()
        self.conn.execute(
            """
            INSERT INTO harness_outcomes(
              snapshot_id, settled_at_ms, actual_return, expected_return, abnormal_return, realized_vol,
              normalized_outcome, baseline_version, fees, slippage, created_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(snapshot_id) DO NOTHING
            """,
            (
                data["snapshot_id"],
                int(data["settled_at_ms"]),
                float(data["actual_return"]),
                float(data["expected_return"]),
                float(data["abnormal_return"]),
                float(data["realized_vol"]),
                float(data["normalized_outcome"]),
                data["baseline_version"],
                float(data.get("fees") or 0.0),
                float(data.get("slippage") or 0.0),
                now_ms,
            ),
        )
        self.conn.execute(
            "UPDATE harness_snapshots SET outcome_status = 'settled' WHERE snapshot_id = %s",
            (data["snapshot_id"],),
        )
        if commit:
            self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM harness_outcomes WHERE snapshot_id = %s",
            (data["snapshot_id"],),
        ).fetchone()
        return dict(row) if row else {}

    def mark_snapshot_outcome_status(
        self,
        *,
        snapshot_id: str,
        outcome_status: str,
        commit: bool = True,
    ) -> dict[str, Any] | None:
        self.conn.execute(
            """
            UPDATE harness_snapshots
            SET outcome_status = %s
            WHERE snapshot_id = %s
            """,
            (outcome_status, snapshot_id),
        )
        if commit:
            self.conn.commit()
        return self.snapshot_by_id(snapshot_id)

    def list_outcomes(
        self,
        *,
        window_ms: int,
        limit: int,
        now_ms: int | None = None,
        horizon: str | None = None,
        asset: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._list_joined_outcomes_or_credits(
            table="harness_outcomes",
            time_column="settled_at_ms",
            window_ms=window_ms,
            limit=limit,
            now_ms=now_ms,
            horizon=horizon,
            asset=asset,
        )

    def record_credits(self, credits: list[dict[str, Any]], *, commit: bool = True) -> list[dict[str, Any]]:
        now_ms = _now_ms()
        for credit in credits:
            self.conn.execute(
                """
                INSERT INTO harness_credits(
                  credit_id, snapshot_id, cluster_id, asset, event_type, source, horizon, event_score,
                  responsibility, credit, created_at_ms
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(credit_id) DO NOTHING
                """,
                (
                    credit["credit_id"],
                    credit["snapshot_id"],
                    credit["cluster_id"],
                    credit["asset"],
                    credit["event_type"],
                    credit["source"],
                    credit["horizon"],
                    float(credit["event_score"]),
                    float(credit["responsibility"]),
                    float(credit["credit"]),
                    now_ms,
                ),
            )
            self.conn.execute(
                "UPDATE harness_snapshots SET credit_status = 'assigned' WHERE snapshot_id = %s",
                (credit["snapshot_id"],),
            )
        if commit:
            self.conn.commit()
        rows = self.conn.execute(
            "SELECT * FROM harness_credits WHERE created_at_ms = %s",
            (now_ms,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_credits(
        self,
        *,
        window_ms: int,
        limit: int,
        now_ms: int | None = None,
        horizon: str | None = None,
        asset: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._list_joined_outcomes_or_credits(
            table="harness_credits",
            time_column="created_at_ms",
            window_ms=window_ms,
            limit=limit,
            now_ms=now_ms,
            horizon=horizon,
            asset=asset,
        )

    def upsert_weight(self, *, commit: bool = True, **data: Any) -> dict[str, Any]:
        now_ms = _now_ms()
        self.conn.execute(
            """
            INSERT INTO harness_weights(key, weight_type, asset, horizon, n, mean_credit, weight, status, updated_at_ms)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(key) DO UPDATE SET
              weight_type = excluded.weight_type,
              asset = excluded.asset,
              horizon = excluded.horizon,
              n = excluded.n,
              mean_credit = excluded.mean_credit,
              weight = excluded.weight,
              status = excluded.status,
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                data["key"],
                data["weight_type"],
                data.get("asset"),
                data["horizon"],
                int(data["n"]),
                float(data["mean_credit"]),
                float(data["weight"]),
                data["status"],
                now_ms,
            ),
        )
        if commit:
            self.conn.commit()
        row = self.conn.execute("SELECT * FROM harness_weights WHERE key = %s", (data["key"],)).fetchone()
        return dict(row) if row else {}

    def list_weights(self, *, limit: int, horizon: str | None = None) -> list[dict[str, Any]]:
        if horizon:
            rows = self.conn.execute(
                "SELECT * FROM harness_weights WHERE horizon = %s ORDER BY updated_at_ms DESC LIMIT %s",
                (horizon, max(0, int(limit))),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM harness_weights ORDER BY updated_at_ms DESC LIMIT %s",
                (max(0, int(limit)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def health(self, *, now_ms: int | None = None) -> dict[str, Any]:
        now = now_ms if now_ms is not None else _now_ms()
        since_24h = now - 86_400_000
        snapshots_24h = self.conn.execute(
            "SELECT COUNT(*) AS count FROM harness_snapshots WHERE decision_time_ms >= %s",
            (since_24h,),
        ).fetchone()["count"]
        pending_outcomes = self.conn.execute(
            "SELECT COUNT(*) AS count FROM harness_snapshots WHERE outcome_status = 'pending'",
        ).fetchone()["count"]
        missing_market = self.conn.execute(
            "SELECT COUNT(*) AS count FROM harness_snapshots WHERE outcome_status = 'missing_market'",
        ).fetchone()["count"]
        insufficient_market_data = self.conn.execute(
            "SELECT COUNT(*) AS count FROM harness_snapshots WHERE outcome_status = 'insufficient_market_data'",
        ).fetchone()["count"]
        settled = self.conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM harness_snapshots
            WHERE outcome_status = 'settled'
              AND decision_time_ms >= %s
            """,
            (since_24h,),
        ).fetchone()["count"]
        coverage = None if snapshots_24h == 0 else settled / snapshots_24h
        return {
            "snapshots_24h": int(snapshots_24h),
            "pending_outcomes": int(pending_outcomes),
            "missing_market": int(missing_market),
            "insufficient_market_data": int(insufficient_market_data),
            "settlement_coverage": coverage,
        }

    def _snapshot_by_unique(self, data: dict[str, Any], config_version: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT * FROM harness_snapshots
            WHERE source_event_id IS NOT DISTINCT FROM %s
              AND asset = %s
              AND horizon = %s
              AND config_version = %s
            """,
            (data.get("source_event_id"), data["asset"], data["horizon"], config_version),
        ).fetchone()
        return self._decode_snapshot(dict(row)) if row else None

    def _list_joined_outcomes_or_credits(
        self,
        *,
        table: str,
        time_column: str,
        window_ms: int,
        limit: int,
        now_ms: int | None,
        horizon: str | None,
        asset: str | None,
    ) -> list[dict[str, Any]]:
        now = now_ms if now_ms is not None else _now_ms()
        clauses = [f"{table}.{time_column} >= %s"]
        params: list[Any] = [now - window_ms]
        if horizon:
            clauses.append("harness_snapshots.horizon = %s")
            params.append(horizon)
        if asset:
            clauses.append("upper(harness_snapshots.asset) = %s")
            params.append(asset.upper())
        rows = self.conn.execute(
            f"""
            SELECT {table}.*
            FROM {table}
            JOIN harness_snapshots ON harness_snapshots.snapshot_id = {table}.snapshot_id
            WHERE {" AND ".join(clauses)}
            ORDER BY {table}.{time_column} DESC
            LIMIT %s
            """,
            (*params, max(0, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]

    # ---------------------------------------------------------------------------
    # Query methods - own all raw SQL that was previously in harness_ops / harness_service
    # ---------------------------------------------------------------------------

    def pending_market_unavailable_social_events(self, *, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT se.*
            FROM social_event_extractions se
            JOIN attention_seeds seed ON seed.extraction_id = se.extraction_id
            WHERE seed.seed_status = 'market_unavailable'
              AND NOT EXISTS (
                SELECT 1
                FROM harness_snapshots hs
                WHERE hs.source_event_id = se.event_id
              )
            ORDER BY se.received_at_ms ASC
            LIMIT %s
            """,
            (max(0, int(limit)),),
        ).fetchall()
        return [self._decode_social_event(dict(row)) for row in rows]

    def snapshot_count_for_event(self, event_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS count FROM harness_snapshots WHERE source_event_id = %s",
            (event_id,),
        ).fetchone()
        return int(row["count"] or 0)

    def due_snapshots(self, *, horizon: str, due_before_ms: int, limit: int) -> list[dict[str, Any]]:
        horizon_ms = _HORIZON_MS[horizon]
        rows = self.conn.execute(
            """
            SELECT *
            FROM harness_snapshots
            WHERE horizon = %s
              AND outcome_status = 'pending'
              AND decision_time_ms + %s <= %s
            ORDER BY decision_time_ms ASC
            LIMIT %s
            """,
            (horizon, horizon_ms, due_before_ms, max(0, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]

    def outcome_exists(self, snapshot_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM harness_outcomes WHERE snapshot_id = %s",
            (snapshot_id,),
        ).fetchone()
        return row is not None

    def outcome_for_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM harness_outcomes WHERE snapshot_id = %s",
            (snapshot_id,),
        ).fetchone()
        return dict(row) if row else None

    def snapshots_pending_credit(self, *, horizon: str, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM harness_snapshots
            WHERE horizon = %s
              AND outcome_status = 'settled'
              AND credit_status != 'assigned'
            ORDER BY decision_time_ms ASC
            LIMIT %s
            """,
            (horizon, max(0, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]

    def credit_exists(self, credit_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM harness_credits WHERE credit_id = %s",
            (credit_id,),
        ).fetchone()
        return row is not None

    def mark_credit_assigned(self, *, snapshot_id: str) -> None:
        self.conn.execute(
            "UPDATE harness_snapshots SET credit_status = 'assigned' WHERE snapshot_id = %s",
            (snapshot_id,),
        )
        self.conn.commit()

    def credit_weight_groups(self, *, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT credit_id, asset, event_type, source, horizon, credit
            FROM harness_credits
            ORDER BY created_at_ms ASC
            LIMIT %s
            """,
            (max(0, int(limit)),),
        ).fetchall()
        return [dict(row) for row in rows]

    def score_bucket_rows(self, *, horizon: str | None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if horizon:
            clauses.append("hs.horizon = %s")
            params.append(horizon)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"""
            SELECT hs.combined_score, hs.horizon, ho.normalized_outcome, ho.abnormal_return
            FROM harness_snapshots hs
            JOIN harness_outcomes ho ON ho.snapshot_id = hs.snapshot_id
            {where}
            ORDER BY hs.decision_time_ms ASC
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def pending_score_bucket_rows(self, *, horizon: str | None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if horizon:
            clauses.append("hs.horizon = %s")
            params.append(horizon)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"""
            SELECT combined_score
            FROM harness_snapshots hs
            {where}
            {"AND" if where else "WHERE"} hs.outcome_status = 'pending'
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def _decode_social_event(self, row: dict[str, Any]) -> dict[str, Any]:
        row["is_signal_event"] = bool(row["is_signal_event"])
        row["anchor_terms"] = _json_loads(row.pop("anchor_terms_json", None), [])
        row["token_candidates"] = _json_loads(row.pop("token_candidates_json", None), [])
        row["semantic_risks"] = _json_loads(row.pop("semantic_risks_json", None), [])
        row["raw_response"] = _json_loads(row.pop("raw_response_json", None), {})
        event_json = row.pop("event_json", None)
        row["event"] = _json_loads(event_json, None) if event_json is not None else None
        return row

    def _decode_seed(self, row: dict[str, Any]) -> dict[str, Any]:
        row["anchor_terms"] = _json_loads(row.pop("anchor_terms_json", None), [])
        row["top_linked_symbols"] = _json_loads(row.pop("top_linked_symbols_json", None), [])
        row["risks"] = _json_loads(row.pop("risks_json", None), [])
        return row

    def _decode_cluster(self, row: dict[str, Any]) -> dict[str, Any]:
        row["source_list"] = _json_loads(row.pop("source_list_json", None), [])
        row["raw_event_ids"] = _json_loads(row.pop("raw_event_ids_json", None), [])
        row["risks"] = _json_loads(row.pop("risks_json", None), [])
        return row

    def _decode_snapshot(self, row: dict[str, Any]) -> dict[str, Any]:
        row["market_state"] = _json_loads(row.pop("market_state_json", None), {})
        row["event_clusters"] = _json_loads(row.pop("event_clusters_json", None), [])
        row["versions"] = _json_loads(row.pop("versions_json", None), {})
        row["risks"] = _json_loads(row.pop("risks_json", None), [])
        return row


def _json(value: Any) -> Jsonb:
    return Jsonb(value, dumps=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _json_loads(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _event_ids(event_ids: tuple[str, ...]) -> list[str]:
    return [event_id for event_id in dict.fromkeys(str(item).strip() for item in event_ids) if event_id]


def _snapshot_asset_match_clauses(
    *,
    identity_key: str | None,
    token_id: str | None,
    chain: str | None,
    address: str | None,
    symbol: str | None,
) -> tuple[list[str], list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    for value in (token_id, identity_key):
        if value:
            clauses.append("upper(hs.asset) = %s")
            params.append(str(value).upper())
    if chain and address:
        clauses.append("lower(hs.asset) = %s")
        params.append(str(address).lower())
    if symbol:
        clauses.append("upper(hs.asset) = %s")
        params.append(str(symbol).lstrip("$").upper())
    return clauses, params


def _now_ms() -> int:
    return int(time.time() * 1000)
