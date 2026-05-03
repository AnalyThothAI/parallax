from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from typing import Any

from ..pipeline.llm_enrichment import EnrichmentResult
from .sqlite_client import transaction

WINDOW_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "1h": 3_600_000,
    "24h": 86_400_000,
}


class EnrichmentRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def enqueue_watched_event(
        self,
        *,
        event_id: str,
        received_at_ms: int,
        priority: int = 100,
        commit: bool = True,
    ) -> str | None:
        job_id = _id("job", event_id, "watched_event_enrichment")
        now_ms = _now_ms()
        try:
            self.conn.execute(
                """
                INSERT INTO enrichment_jobs(
                  job_id, event_id, job_type, priority, status, attempt_count, max_attempts,
                  next_run_at_ms, last_error, created_at_ms, updated_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    event_id,
                    "watched_event_enrichment",
                    priority,
                    "pending",
                    0,
                    3,
                    received_at_ms,
                    None,
                    now_ms,
                    now_ms,
                ),
            )
            if commit:
                self.conn.commit()
        except sqlite3.IntegrityError:
            return self._job_id_for_event(event_id, "watched_event_enrichment")
        return job_id

    def claim_next_job(self, *, now_ms: int | None = None) -> dict[str, Any] | None:
        now = now_ms if now_ms is not None else _now_ms()
        with transaction(self.conn):
            row = self.conn.execute(
                """
                SELECT * FROM enrichment_jobs
                WHERE status IN ('pending', 'failed')
                  AND attempt_count < max_attempts
                  AND next_run_at_ms <= ?
                ORDER BY priority DESC, next_run_at_ms ASC, created_at_ms ASC
                LIMIT 1
                """,
                (now,),
            ).fetchone()
            if row is None:
                return None
            self.conn.execute(
                """
                UPDATE enrichment_jobs
                SET status = 'running',
                    attempt_count = attempt_count + 1,
                    updated_at_ms = ?,
                    last_error = NULL
                WHERE job_id = ?
                """,
                (now, row["job_id"]),
            )
            claimed = self.conn.execute(
                "SELECT * FROM enrichment_jobs WHERE job_id = ?",
                (row["job_id"],),
            ).fetchone()
        return dict(claimed) if claimed else None

    def complete_job(
        self,
        *,
        job: dict[str, Any],
        event: dict[str, Any],
        result: EnrichmentResult,
        provider: str,
        model: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        now_ms = _now_ms()
        run_id = _id("run", str(job["job_id"]), str(now_ms))
        with transaction(self.conn):
            self.conn.execute(
                """
                INSERT INTO model_runs(
                  run_id, job_id, event_id, provider, model, status, request_json,
                  response_json, error, started_at_ms, finished_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    job["job_id"],
                    job["event_id"],
                    provider,
                    model,
                    "done",
                    _json(request),
                    _json(result.raw_response),
                    None,
                    now_ms,
                    now_ms,
                ),
            )
            self._replace_event_enrichment(
                event=event,
                result=result,
                run_id=run_id,
                provider=provider,
                model=model,
                now_ms=now_ms,
            )
            self.conn.execute(
                """
                UPDATE enrichment_jobs
                SET status = 'done', updated_at_ms = ?, last_error = NULL
                WHERE job_id = ?
                """,
                (now_ms, job["job_id"]),
            )
        stored = self.enrichment_for_event(str(job["event_id"]))
        return stored or {}

    def fail_job(self, *, job: dict[str, Any], error: str) -> None:
        now_ms = _now_ms()
        attempts = int(job.get("attempt_count") or 0)
        max_attempts = int(job.get("max_attempts") or 3)
        status = "dead" if attempts >= max_attempts else "failed"
        delay_ms = min(300_000, 5_000 * max(1, attempts))
        self.conn.execute(
            """
            UPDATE enrichment_jobs
            SET status = ?, last_error = ?, next_run_at_ms = ?, updated_at_ms = ?
            WHERE job_id = ?
            """,
            (status, error[:1000], now_ms + delay_ms, now_ms, job["job_id"]),
        )
        self.conn.commit()

    def list_jobs(self, *, limit: int, status: str | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"""
            SELECT * FROM enrichment_jobs
            {where}
            ORDER BY created_at_ms DESC
            LIMIT ?
            """,
            (*params, max(0, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]

    def job_counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) AS count FROM enrichment_jobs GROUP BY status"
        ).fetchall()
        counts = {str(row["status"]): int(row["count"]) for row in rows}
        for status in ("pending", "running", "failed", "dead", "done"):
            counts.setdefault(status, 0)
        return counts

    def enrichment_for_event(self, event_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM event_enrichments WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        if row is None:
            return None
        token_rows = self.conn.execute(
            "SELECT * FROM event_token_candidates WHERE event_id = ? ORDER BY confidence DESC",
            (event_id,),
        ).fetchall()
        narrative_rows = self.conn.execute(
            "SELECT * FROM event_narratives WHERE event_id = ? ORDER BY confidence DESC",
            (event_id,),
        ).fetchall()
        alert_rows = self.conn.execute(
            "SELECT 'account_narrative' AS alert_type, * FROM account_narrative_alerts WHERE event_id = ?",
            (event_id,),
        ).fetchall()
        data = dict(row)
        data["raw_response"] = _json_loads(data.pop("raw_response_json", None), {})
        data["token_candidates"] = [dict(item) for item in token_rows]
        data["narratives"] = [dict(item) for item in narrative_rows]
        data["alerts"] = [dict(item) for item in alert_rows]
        return data

    def account_narratives(
        self,
        *,
        window_ms: int,
        now_ms: int | None = None,
        limit: int,
        handles: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        now = now_ms if now_ms is not None else _now_ms()
        since = now - window_ms
        clauses = ["ana.received_at_ms >= ?"]
        params: list[Any] = [since]
        normalized = sorted(handle.strip().lstrip("@").lower() for handle in handles or set() if handle.strip())
        if normalized:
            placeholders = ",".join("?" for _ in normalized)
            clauses.append(f"ana.author_handle IN ({placeholders})")
            params.extend(normalized)
        rows = self.conn.execute(
            f"""
            SELECT ana.*, e.canonical_url, e.text_clean
            FROM account_narrative_alerts ana
            JOIN events e ON e.event_id = ana.event_id
            WHERE {" AND ".join(clauses)}
            ORDER BY ana.received_at_ms DESC
            LIMIT ?
            """,
            (*params, max(0, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]

    def narrative_flow(self, *, window: str, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM narrative_windows
            WHERE window = ?
            ORDER BY watched_mention_count DESC, velocity DESC, mention_count DESC, window_end_ms DESC
            LIMIT ?
            """,
            (window, max(0, int(limit))),
        ).fetchall()
        return [_decode_json_fields(dict(row)) for row in rows]

    def _replace_event_enrichment(
        self,
        *,
        event: dict[str, Any],
        result: EnrichmentResult,
        run_id: str,
        provider: str,
        model: str,
        now_ms: int,
    ) -> None:
        event_id = str(event["event_id"])
        received_at_ms = int(event.get("received_at_ms") or now_ms)
        author_handle = _event_author_handle(event)
        author_followers = _event_author_followers(event)
        is_watched = bool(event.get("is_watched"))
        self.conn.execute("DELETE FROM event_token_candidates WHERE event_id = ?", (event_id,))
        self.conn.execute("DELETE FROM event_narratives WHERE event_id = ?", (event_id,))
        self.conn.execute("DELETE FROM account_narrative_alerts WHERE event_id = ?", (event_id,))
        self.conn.execute(
            """
            INSERT INTO event_enrichments(
              event_id, run_id, provider, model, summary, stance, intent, confidence,
              raw_response_json, created_at_ms, updated_at_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id) DO UPDATE SET
              run_id = excluded.run_id,
              provider = excluded.provider,
              model = excluded.model,
              summary = excluded.summary,
              stance = excluded.stance,
              intent = excluded.intent,
              confidence = excluded.confidence,
              raw_response_json = excluded.raw_response_json,
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                event_id,
                run_id,
                provider,
                model,
                result.summary,
                result.stance,
                result.intent,
                result.confidence,
                _json(result.raw_response),
                now_ms,
                now_ms,
            ),
        )
        for candidate in result.token_candidates:
            self.conn.execute(
                """
                INSERT INTO event_token_candidates(
                  candidate_id, event_id, symbol, project_name, chain, address, evidence,
                  confidence, resolution_status, created_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _id("candidate", event_id, candidate.symbol or "", candidate.evidence),
                    event_id,
                    candidate.symbol,
                    candidate.project_name,
                    candidate.chain,
                    candidate.address,
                    candidate.evidence,
                    candidate.confidence,
                    "resolved_ca" if candidate.address else "unresolved_llm_candidate",
                    now_ms,
                ),
            )
        for narrative in result.narratives:
            self.conn.execute(
                """
                INSERT INTO event_narratives(
                  narrative_id, event_id, narrative_label, description, evidence, confidence,
                  stance, intent, received_at_ms, author_handle, is_watched, created_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _id("narrative", event_id, narrative.label),
                    event_id,
                    narrative.label,
                    narrative.description,
                    narrative.evidence,
                    narrative.confidence,
                    result.stance,
                    result.intent,
                    received_at_ms,
                    author_handle,
                    1 if is_watched else 0,
                    now_ms,
                ),
            )
            if is_watched and author_handle:
                self._insert_account_narrative_alert(
                    event_id=event_id,
                    author_handle=author_handle,
                    label=narrative.label,
                    stance=result.stance,
                    intent=result.intent,
                    confidence=narrative.confidence,
                    summary=result.summary,
                    evidence=narrative.evidence,
                    received_at_ms=received_at_ms,
                    now_ms=now_ms,
                )
            for window, size_ms in WINDOW_MS.items():
                start_ms = (received_at_ms // size_ms) * size_ms
                self._upsert_narrative_window(
                    label=narrative.label,
                    window=window,
                    window_start_ms=start_ms,
                    window_end_ms=start_ms + size_ms,
                    event_id=event_id,
                    author_handle=author_handle,
                    author_followers=author_followers,
                    is_watched=is_watched,
                    now_ms=now_ms,
                )

    def _insert_account_narrative_alert(
        self,
        *,
        event_id: str,
        author_handle: str,
        label: str,
        stance: str,
        intent: str,
        confidence: float,
        summary: str,
        evidence: str,
        received_at_ms: int,
        now_ms: int,
    ) -> None:
        seen_global = self.conn.execute(
            """
            SELECT COUNT(*) FROM event_narratives
            WHERE narrative_label = ? AND received_at_ms < ?
            """,
            (label, received_at_ms),
        ).fetchone()[0]
        seen_author = self.conn.execute(
            """
            SELECT COUNT(*) FROM event_narratives
            WHERE narrative_label = ? AND author_handle = ? AND received_at_ms < ?
            """,
            (label, author_handle, received_at_ms),
        ).fetchone()[0]
        self.conn.execute(
            """
            INSERT OR IGNORE INTO account_narrative_alerts(
              alert_id, event_id, author_handle, narrative_label, stance, intent, confidence,
              summary, evidence, is_first_seen_global, is_first_seen_by_author, received_at_ms, created_at_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _id("account_narrative", event_id, label),
                event_id,
                author_handle,
                label,
                stance,
                intent,
                confidence,
                summary,
                evidence,
                0 if seen_global else 1,
                0 if seen_author else 1,
                received_at_ms,
                now_ms,
            ),
        )

    def _upsert_narrative_window(
        self,
        *,
        label: str,
        window: str,
        window_start_ms: int,
        window_end_ms: int,
        event_id: str,
        author_handle: str | None,
        author_followers: int | None,
        is_watched: bool,
        now_ms: int,
    ) -> None:
        existing = self.conn.execute(
            """
            SELECT * FROM narrative_windows
            WHERE narrative_label = ? AND window = ? AND window_start_ms = ?
            """,
            (label, window, window_start_ms),
        ).fetchone()
        if existing is None:
            row = {
                "window_id": _id("narrative_window", label, window, str(window_start_ms)),
                "narrative_label": label,
                "window": window,
                "window_start_ms": window_start_ms,
                "window_end_ms": window_end_ms,
                "mention_count": 0,
                "watched_mention_count": 0,
                "unique_author_count": 0,
                "weighted_reach": 0.0,
                "market_mindshare": 0.0,
                "watched_mindshare": 0.0,
                "velocity": 0.0,
                "top_authors_json": "[]",
                "top_events_json": "[]",
                "created_at_ms": now_ms,
                "updated_at_ms": now_ms,
            }
        else:
            row = dict(existing)
        _apply_window_increment(row, event_id, author_handle, author_followers, is_watched)
        row["updated_at_ms"] = now_ms
        self.conn.execute(
            """
            INSERT INTO narrative_windows(
              window_id, narrative_label, window, window_start_ms, window_end_ms,
              mention_count, watched_mention_count, unique_author_count, weighted_reach,
              market_mindshare, watched_mindshare, velocity, top_authors_json, top_events_json,
              created_at_ms, updated_at_ms
            )
            VALUES (
              :window_id, :narrative_label, :window, :window_start_ms, :window_end_ms,
              :mention_count, :watched_mention_count, :unique_author_count, :weighted_reach,
              :market_mindshare, :watched_mindshare, :velocity, :top_authors_json, :top_events_json,
              :created_at_ms, :updated_at_ms
            )
            ON CONFLICT(narrative_label, window, window_start_ms) DO UPDATE SET
              mention_count = excluded.mention_count,
              watched_mention_count = excluded.watched_mention_count,
              unique_author_count = excluded.unique_author_count,
              weighted_reach = excluded.weighted_reach,
              market_mindshare = excluded.market_mindshare,
              watched_mindshare = excluded.watched_mindshare,
              velocity = excluded.velocity,
              top_authors_json = excluded.top_authors_json,
              top_events_json = excluded.top_events_json,
              updated_at_ms = excluded.updated_at_ms
            """,
            row,
        )

    def _job_id_for_event(self, event_id: str, job_type: str) -> str | None:
        row = self.conn.execute(
            "SELECT job_id FROM enrichment_jobs WHERE event_id = ? AND job_type = ?",
            (event_id, job_type),
        ).fetchone()
        return str(row["job_id"]) if row else None


def _apply_window_increment(
    row: dict[str, Any],
    event_id: str,
    author_handle: str | None,
    author_followers: int | None,
    is_watched: bool,
) -> None:
    top_events = _json_loads(row.get("top_events_json"), [])
    if event_id in {item.get("event_id") for item in top_events if isinstance(item, dict)}:
        return
    top_events.append({"event_id": event_id})
    top_events = top_events[-20:]
    authors = _json_loads(row.get("top_authors_json"), [])
    author_map = {item.get("handle"): dict(item) for item in authors if isinstance(item, dict) and item.get("handle")}
    if author_handle:
        current = author_map.get(
            author_handle,
            {"handle": author_handle, "count": 0, "followers": author_followers or 0},
        )
        current["count"] = int(current.get("count") or 0) + 1
        current["followers"] = max(int(current.get("followers") or 0), int(author_followers or 0))
        author_map[author_handle] = current
    row["mention_count"] = int(row.get("mention_count") or 0) + 1
    row["watched_mention_count"] = int(row.get("watched_mention_count") or 0) + (1 if is_watched else 0)
    row["unique_author_count"] = len(author_map)
    row["weighted_reach"] = float(row.get("weighted_reach") or 0.0) + float(author_followers or 0)
    row["market_mindshare"] = float(row["mention_count"])
    row["watched_mindshare"] = float(row["watched_mention_count"])
    window_ms = max(1, int(row["window_end_ms"]) - int(row["window_start_ms"]))
    row["velocity"] = float(row["mention_count"]) / (window_ms / 60_000)
    sorted_authors = sorted(
        author_map.values(),
        key=lambda item: (item.get("count") or 0, item.get("followers") or 0),
        reverse=True,
    )
    row["top_authors_json"] = _json(sorted_authors[:20])
    row["top_events_json"] = _json(top_events)


def _decode_json_fields(row: dict[str, Any]) -> dict[str, Any]:
    row["top_authors"] = _json_loads(row.pop("top_authors_json", None), [])
    row["top_events"] = _json_loads(row.pop("top_events_json", None), [])
    return row


def _event_author_handle(event: dict[str, Any]) -> str | None:
    if event.get("author_handle"):
        return str(event["author_handle"]).lower()
    author = event.get("author")
    if isinstance(author, dict) and author.get("handle"):
        return str(author["handle"]).lower()
    return None


def _event_author_followers(event: dict[str, Any]) -> int | None:
    author = event.get("author")
    if isinstance(author, dict) and author.get("followers") is not None:
        return int(author["followers"])
    return None


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_loads(value: Any, default: Any) -> Any:
    if not isinstance(value, str) or not value.strip():
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _now_ms() -> int:
    return int(time.time() * 1000)
