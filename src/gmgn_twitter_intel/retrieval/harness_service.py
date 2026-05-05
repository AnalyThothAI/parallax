from __future__ import annotations

import time
from contextlib import suppress
from typing import Any

WINDOW_MS = {
    "5m": 300_000,
    "1h": 3_600_000,
    "4h": 4 * 3_600_000,
    "24h": 86_400_000,
}
SIGNAL_LAB_STAGES = {"extracted", "seeded", "frozen", "settled", "credited"}


class HarnessService:
    def __init__(self, harness):
        self.harness = harness

    def social_events(
        self,
        *,
        window: str,
        limit: int,
        handles: set[str] | None = None,
        event_types: set[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "items": self.harness.list_social_events(
                window_ms=WINDOW_MS.get(window, WINDOW_MS["1h"]),
                limit=limit,
                handles=handles,
                event_types=event_types,
            )
        }

    def attention_seeds(self, *, window: str, limit: int, handles: set[str] | None = None) -> dict[str, Any]:
        return {
            "items": self.harness.list_attention_seeds(
                window_ms=WINDOW_MS.get(window, WINDOW_MS["1h"]),
                limit=limit,
                handles=handles,
            )
        }

    def snapshots(self, *, window: str, horizon: str | None, limit: int, asset: str | None = None) -> dict[str, Any]:
        return {
            "items": self.harness.list_snapshots(
                window_ms=WINDOW_MS.get(window, WINDOW_MS["1h"]),
                horizon=horizon,
                asset=asset,
                limit=limit,
            )
        }

    def outcomes(self, *, window: str, horizon: str | None, limit: int, asset: str | None = None) -> dict[str, Any]:
        return {
            "items": self.harness.list_outcomes(
                window_ms=WINDOW_MS.get(window, WINDOW_MS["1h"]),
                horizon=horizon,
                asset=asset,
                limit=limit,
            )
        }

    def credits(self, *, window: str, horizon: str | None, limit: int, asset: str | None = None) -> dict[str, Any]:
        return {
            "items": self.harness.list_credits(
                window_ms=WINDOW_MS.get(window, WINDOW_MS["1h"]),
                horizon=horizon,
                asset=asset,
                limit=limit,
            )
        }

    def chains(
        self,
        *,
        window: str,
        horizon: str,
        scope: str,
        limit: int,
        stage: str | None = None,
        asset: str | None = None,
        handle: str | None = None,
        q: str | None = None,
        handles: set[str] | None = None,
        cursor: str | None = None,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        handle_filter = _chain_handle_filter(handles=handles, handle=handle)
        social_events = self._chain_social_events(
            window_ms=WINDOW_MS.get(window, WINDOW_MS["1h"]),
            now_ms=now_ms,
            handles=handle_filter,
        )
        seeds_by_extraction, seeds_by_event = self._chain_seeds(social_events)
        snapshots_by_seed, snapshots_by_event = self._chain_snapshots(
            horizon=horizon,
            event_ids={str(item["event_id"]) for item in social_events},
            seed_ids={str(seed["seed_id"]) for seed in seeds_by_extraction.values()},
        )
        snapshot_ids = {
            str(snapshot["snapshot_id"])
            for snapshots in [*snapshots_by_seed.values(), *snapshots_by_event.values()]
            for snapshot in snapshots
        }
        outcomes = self._chain_outcomes(snapshot_ids)
        credits = self._chain_credits(snapshot_ids)

        chains: list[dict[str, Any]] = []
        for social_event in social_events:
            seed = seeds_by_extraction.get(str(social_event["extraction_id"])) or seeds_by_event.get(
                str(social_event["event_id"])
            )
            snapshots = _snapshots_for_social_event(
                social_event=social_event,
                seed=seed,
                snapshots_by_seed=snapshots_by_seed,
                snapshots_by_event=snapshots_by_event,
            )
            if snapshots:
                for snapshot in snapshots:
                    snapshot_id = str(snapshot["snapshot_id"])
                    chains.append(
                        _signal_chain(
                            horizon=horizon,
                            social_event=social_event,
                            seed=seed,
                            snapshot=snapshot,
                            outcome=outcomes.get(snapshot_id),
                            credits=credits.get(snapshot_id, []),
                        )
                    )
                continue
            chains.append(
                _signal_chain(
                    horizon=horizon,
                    social_event=social_event,
                    seed=seed,
                    snapshot=None,
                    outcome=None,
                    credits=[],
                )
            )

        chains = _filter_signal_chains(chains, asset=asset, q=q)
        summary = _stage_summary(chains)
        parsed_stage = stage if stage in SIGNAL_LAB_STAGES else None
        if parsed_stage:
            chains = [chain for chain in chains if chain["stage"] == parsed_stage]
        requested_limit = max(0, int(limit))
        offset = _cursor_offset(cursor)
        limited = chains[offset : offset + requested_limit]
        next_offset = offset + requested_limit
        has_more = next_offset < len(chains)
        return {
            "query": {
                "window": window,
                "horizon": horizon,
                "scope": scope,
                "stage": parsed_stage,
                "asset": asset or None,
                "handle": handle or None,
                "q": q or None,
            },
            "summary": summary,
            "items": limited,
            "returned_count": len(limited),
            "has_more": has_more,
            "next_cursor": str(next_offset) if has_more else None,
        }

    def weights(self, *, horizon: str | None, limit: int) -> dict[str, Any]:
        return {"items": self.harness.list_weights(horizon=horizon, limit=limit)}

    def score_buckets(self, *, horizon: str | None = None) -> dict[str, Any]:
        clauses: list[str] = []
        params: list[Any] = []
        if horizon:
            clauses.append("hs.horizon = ?")
            params.append(horizon)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.harness.conn.execute(
            f"""
            SELECT hs.combined_score, hs.horizon, ho.normalized_outcome, ho.abnormal_return
            FROM harness_snapshots hs
            JOIN harness_outcomes ho ON ho.snapshot_id = hs.snapshot_id
            {where}
            ORDER BY hs.decision_time_ms ASC
            """,
            params,
        ).fetchall()
        pending_rows = self.harness.conn.execute(
            f"""
            SELECT combined_score
            FROM harness_snapshots hs
            {where}
            """,
            params,
        ).fetchall()
        buckets = [_empty_bucket(label) for label in ["<= -0.8", "-0.8 to -0.4", "-0.4 to 0.4", "0.4 to 0.8", ">= 0.8"]]
        by_label = {item["bucket"]: item for item in buckets}
        for row in pending_rows:
            by_label[_bucket_label(float(row["combined_score"]))]["pending_count"] += 1
        for row in rows:
            score = float(row["combined_score"])
            outcome = float(row["normalized_outcome"])
            abnormal = float(row["abnormal_return"])
            bucket = by_label[_bucket_label(score)]
            bucket["sample_count"] += 1
            bucket["settled_count"] += 1
            bucket["pending_count"] -= 1
            bucket["_normalized_sum"] += outcome
            bucket["_abnormal_sum"] += abnormal
            bucket["_hit_count"] += int(_directional_hit(score=score, outcome=outcome))
        for bucket in buckets:
            sample_count = int(bucket["sample_count"])
            normalized_sum = float(bucket.pop("_normalized_sum"))
            abnormal_sum = float(bucket.pop("_abnormal_sum"))
            hit_count = int(bucket.pop("_hit_count"))
            bucket["avg_normalized_outcome"] = 0.0 if sample_count == 0 else round(normalized_sum / sample_count, 12)
            bucket["avg_abnormal_return"] = 0.0 if sample_count == 0 else round(abnormal_sum / sample_count, 12)
            bucket["hit_rate"] = 0.0 if sample_count == 0 else round(hit_count / sample_count, 12)
        return {"items": buckets}

    def health(
        self,
        *,
        llm_configured: bool,
        extractor_running: bool,
        pending_jobs: int,
        schema_success_rate: float | None,
    ) -> dict[str, Any]:
        health = self.harness.health()
        return {
            "llm_configured": llm_configured,
            "extractor_running": extractor_running,
            "schema_success_rate": schema_success_rate,
            "pending_jobs": pending_jobs,
            **health,
        }

    def _chain_social_events(
        self,
        *,
        window_ms: int,
        now_ms: int | None,
        handles: set[str] | None,
    ) -> list[dict[str, Any]]:
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        clauses = ["se.received_at_ms >= ?"]
        params: list[Any] = [now - window_ms]
        if handles is not None:
            if not handles:
                return []
            normalized = sorted(handle.lower().lstrip("@") for handle in handles)
            clauses.append(f"lower(se.author_handle) IN ({','.join('?' for _ in normalized)})")
            params.extend(normalized)
        rows = self.harness.conn.execute(
            f"""
            SELECT se.*, e.event_json
            FROM social_event_extractions se
            LEFT JOIN events e ON e.event_id = se.event_id
            WHERE {" AND ".join(clauses)}
            ORDER BY se.received_at_ms DESC
            """,
            params,
        ).fetchall()
        return [self.harness._decode_social_event(dict(row)) for row in rows]

    def _chain_seeds(
        self, social_events: list[dict[str, Any]]
    ) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        extraction_ids = sorted({str(item["extraction_id"]) for item in social_events})
        event_ids = sorted({str(item["event_id"]) for item in social_events})
        clauses: list[str] = []
        params: list[Any] = []
        if extraction_ids:
            clauses.append(f"extraction_id IN ({','.join('?' for _ in extraction_ids)})")
            params.extend(extraction_ids)
        if event_ids:
            clauses.append(f"event_id IN ({','.join('?' for _ in event_ids)})")
            params.extend(event_ids)
        if not clauses:
            return {}, {}
        rows = self.harness.conn.execute(
            f"""
            SELECT *
            FROM attention_seeds
            WHERE {" OR ".join(clauses)}
            ORDER BY received_at_ms DESC
            """,
            params,
        ).fetchall()
        seeds = [self.harness._decode_seed(dict(row)) for row in rows]
        return (
            {str(seed["extraction_id"]): seed for seed in seeds},
            {str(seed["event_id"]): seed for seed in seeds},
        )

    def _chain_snapshots(
        self,
        *,
        horizon: str,
        seed_ids: set[str],
        event_ids: set[str],
    ) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
        clauses = ["horizon = ?"]
        params: list[Any] = [horizon]
        lineage_clauses: list[str] = []
        sorted_seed_ids = sorted(seed_ids)
        sorted_event_ids = sorted(event_ids)
        if sorted_seed_ids:
            lineage_clauses.append(f"seed_id IN ({','.join('?' for _ in sorted_seed_ids)})")
            params.extend(sorted_seed_ids)
        if sorted_event_ids:
            lineage_clauses.append(f"source_event_id IN ({','.join('?' for _ in sorted_event_ids)})")
            params.extend(sorted_event_ids)
        if not lineage_clauses:
            return {}, {}
        clauses.append(f"({' OR '.join(lineage_clauses)})")
        rows = self.harness.conn.execute(
            f"""
            SELECT *
            FROM harness_snapshots
            WHERE {" AND ".join(clauses)}
            ORDER BY decision_time_ms DESC
            """,
            params,
        ).fetchall()
        by_seed: dict[str, list[dict[str, Any]]] = {}
        by_event: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            snapshot = self.harness._decode_snapshot(dict(row))
            if snapshot.get("seed_id"):
                by_seed.setdefault(str(snapshot["seed_id"]), []).append(snapshot)
            if snapshot.get("source_event_id"):
                by_event.setdefault(str(snapshot["source_event_id"]), []).append(snapshot)
        return by_seed, by_event

    def _chain_outcomes(self, snapshot_ids: set[str]) -> dict[str, dict[str, Any]]:
        if not snapshot_ids:
            return {}
        ids = sorted(snapshot_ids)
        rows = self.harness.conn.execute(
            f"""
            SELECT *
            FROM harness_outcomes
            WHERE snapshot_id IN ({','.join('?' for _ in ids)})
            """,
            ids,
        ).fetchall()
        return {str(row["snapshot_id"]): dict(row) for row in rows}

    def _chain_credits(self, snapshot_ids: set[str]) -> dict[str, list[dict[str, Any]]]:
        if not snapshot_ids:
            return {}
        ids = sorted(snapshot_ids)
        rows = self.harness.conn.execute(
            f"""
            SELECT *
            FROM harness_credits
            WHERE snapshot_id IN ({','.join('?' for _ in ids)})
            ORDER BY created_at_ms DESC
            """,
            ids,
        ).fetchall()
        by_snapshot: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            credit = dict(row)
            by_snapshot.setdefault(str(credit["snapshot_id"]), []).append(credit)
        return by_snapshot


def _empty_bucket(label: str) -> dict[str, Any]:
    return {
        "bucket": label,
        "sample_count": 0,
        "avg_normalized_outcome": 0.0,
        "avg_abnormal_return": 0.0,
        "hit_rate": 0.0,
        "settled_count": 0,
        "pending_count": 0,
        "_normalized_sum": 0.0,
        "_abnormal_sum": 0.0,
        "_hit_count": 0,
    }


def _bucket_label(score: float) -> str:
    if score <= -0.8:
        return "<= -0.8"
    if score < -0.4:
        return "-0.8 to -0.4"
    if score < 0.4:
        return "-0.4 to 0.4"
    if score < 0.8:
        return "0.4 to 0.8"
    return ">= 0.8"


def _directional_hit(*, score: float, outcome: float) -> bool:
    if score > 0:
        return outcome > 0
    if score < 0:
        return outcome < 0
    return abs(outcome) < 1e-12


def _chain_handle_filter(*, handles: set[str] | None, handle: str | None) -> set[str] | None:
    base = {item.strip().lstrip("@").lower() for item in handles or set() if item.strip()}
    requested = {item.strip().lstrip("@").lower() for item in (handle or "").split(",") if item.strip()}
    if handles is None:
        return requested or None
    if not requested:
        return base
    return base & requested


def _cursor_offset(cursor: str | None) -> int:
    if not cursor:
        return 0
    with suppress(ValueError):
        return max(0, int(cursor))
    return 0


def _snapshots_for_social_event(
    *,
    social_event: dict[str, Any],
    seed: dict[str, Any] | None,
    snapshots_by_seed: dict[str, list[dict[str, Any]]],
    snapshots_by_event: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    seen: set[str] = set()
    if seed:
        for snapshot in snapshots_by_seed.get(str(seed["seed_id"]), []):
            seen.add(str(snapshot["snapshot_id"]))
            snapshots.append(snapshot)
    for snapshot in snapshots_by_event.get(str(social_event["event_id"]), []):
        snapshot_id = str(snapshot["snapshot_id"])
        if snapshot_id not in seen:
            snapshots.append(snapshot)
    return snapshots


def _signal_chain(
    *,
    horizon: str,
    social_event: dict[str, Any],
    seed: dict[str, Any] | None,
    snapshot: dict[str, Any] | None,
    outcome: dict[str, Any] | None,
    credits: list[dict[str, Any]],
) -> dict[str, Any]:
    stage = _signal_chain_stage(seed=seed, snapshot=snapshot, outcome=outcome, credits=credits)
    asset = _signal_chain_asset(social_event=social_event, seed=seed, snapshot=snapshot)
    chain_horizon = snapshot.get("horizon") if snapshot else None
    snapshot_id = snapshot.get("snapshot_id") if snapshot else None
    seed_id = seed.get("seed_id") if seed else None
    chain_id = (
        f"snapshot:{snapshot_id}"
        if snapshot_id
        else f"seed:{seed_id}:{horizon}"
        if seed_id
        else f"event:{social_event['extraction_id']}"
    )
    return {
        "chain_id": chain_id,
        "stage": stage,
        "received_at_ms": int(social_event["received_at_ms"]),
        "updated_at_ms": _signal_chain_updated_at(
            social_event=social_event,
            seed=seed,
            snapshot=snapshot,
            outcome=outcome,
            credits=credits,
        ),
        "asset": asset,
        "horizon": chain_horizon,
        "source": social_event.get("author_handle"),
        "event_type": social_event.get("event_type"),
        "title": _signal_chain_title(social_event=social_event, asset=asset, horizon=chain_horizon),
        "summary": social_event.get("summary_zh") or social_event.get("subject") or "",
        "score": snapshot.get("combined_score") if snapshot else social_event.get("confidence"),
        "outcome_status": snapshot.get("outcome_status") if snapshot else None,
        "credit_status": snapshot.get("credit_status") if snapshot else None,
        "risks": _chain_risks(social_event=social_event, seed=seed, snapshot=snapshot),
        "evidence_chips": _chain_chips(social_event=social_event, seed=seed, snapshot=snapshot),
        "lineage": {
            "extraction_id": social_event.get("extraction_id"),
            "event_id": social_event.get("event_id"),
            "seed_id": seed_id,
            "snapshot_id": snapshot_id,
            "source_event_id": snapshot.get("source_event_id") if snapshot else None,
        },
        "social_event": social_event,
        "seed": seed,
        "snapshot": snapshot,
        "outcome": outcome,
        "credits": credits,
    }


def _signal_chain_stage(
    *,
    seed: dict[str, Any] | None,
    snapshot: dict[str, Any] | None,
    outcome: dict[str, Any] | None,
    credits: list[dict[str, Any]],
) -> str:
    if credits:
        return "credited"
    if outcome:
        return "settled"
    if snapshot:
        return "frozen"
    if seed:
        return "seeded"
    return "extracted"


def _signal_chain_asset(
    *,
    social_event: dict[str, Any],
    seed: dict[str, Any] | None,
    snapshot: dict[str, Any] | None,
) -> str | None:
    if snapshot:
        return str(snapshot["asset"])
    if seed:
        symbols = seed.get("top_linked_symbols") or []
        if symbols:
            return str(symbols[0])
    for candidate in social_event.get("token_candidates") or []:
        value = candidate.get("symbol") or candidate.get("address") or candidate.get("project_name")
        if value:
            return str(value).lstrip("$").upper()
    return None


def _signal_chain_updated_at(
    *,
    social_event: dict[str, Any],
    seed: dict[str, Any] | None,
    snapshot: dict[str, Any] | None,
    outcome: dict[str, Any] | None,
    credits: list[dict[str, Any]],
) -> int:
    values = [int(social_event["received_at_ms"])]
    if seed:
        values.append(int(seed["received_at_ms"]))
    if snapshot:
        values.append(int(snapshot["decision_time_ms"]))
    if outcome:
        values.append(int(outcome["settled_at_ms"]))
    values.extend(int(credit["created_at_ms"]) for credit in credits)
    return max(values)


def _signal_chain_title(*, social_event: dict[str, Any], asset: str | None, horizon: str | None) -> str:
    if asset and horizon:
        return f"{asset} · {horizon}"
    if asset:
        return f"{asset} · unresolved horizon"
    return f"@{social_event.get('author_handle') or 'watched'} · {social_event.get('event_type') or 'event'}"


def _chain_risks(
    *,
    social_event: dict[str, Any],
    seed: dict[str, Any] | None,
    snapshot: dict[str, Any] | None,
) -> list[str]:
    values: list[str] = []
    for risk in social_event.get("semantic_risks") or []:
        values.append(str(risk))
    if seed:
        values.extend(str(risk) for risk in seed.get("risks") or [])
    if snapshot:
        values.extend(str(risk) for risk in snapshot.get("risks") or [])
    return list(dict.fromkeys(values))


def _chain_chips(
    *,
    social_event: dict[str, Any],
    seed: dict[str, Any] | None,
    snapshot: dict[str, Any] | None,
) -> list[str]:
    chips = [
        str(social_event.get("source_action") or "").replace("_", " "),
        str(social_event.get("attention_mechanism") or "").replace("_", " "),
    ]
    if seed:
        chips.extend(str(symbol) for symbol in seed.get("top_linked_symbols") or [])
    if snapshot:
        chips.append(str(snapshot.get("shadow_signal") or "").replace("_", " "))
    return [chip for chip in dict.fromkeys(chips) if chip][:3]


def _filter_signal_chains(chains: list[dict[str, Any]], *, asset: str | None, q: str | None) -> list[dict[str, Any]]:
    filtered = chains
    if asset:
        normalized_asset = asset.strip().lstrip("$").upper()
        filtered = [chain for chain in filtered if str(chain.get("asset") or "").upper() == normalized_asset]
    if q:
        needle = q.strip().lower()
        filtered = [chain for chain in filtered if needle in _chain_search_text(chain)]
    return filtered


def _chain_search_text(chain: dict[str, Any]) -> str:
    values = [
        chain.get("chain_id"),
        chain.get("asset"),
        chain.get("source"),
        chain.get("event_type"),
        chain.get("title"),
        chain.get("summary"),
        chain.get("lineage", {}).get("event_id"),
        chain.get("lineage", {}).get("extraction_id"),
        chain.get("lineage", {}).get("seed_id"),
        chain.get("lineage", {}).get("snapshot_id"),
    ]
    return " ".join(str(value).lower() for value in values if value is not None)


def _stage_summary(chains: list[dict[str, Any]]) -> dict[str, int]:
    summary = {stage: 0 for stage in ["extracted", "seeded", "frozen", "settled", "credited"]}
    for chain in chains:
        summary[str(chain["stage"])] += 1
    return summary
