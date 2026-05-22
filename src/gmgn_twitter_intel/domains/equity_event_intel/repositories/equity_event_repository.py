from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from psycopg.types.json import Jsonb

from gmgn_twitter_intel.domains.equity_event_intel._constants import (
    EQUITY_EVENT_ALERT_PROJECTION_VERSION,
    EQUITY_EVENT_CALENDAR_PROJECTION_VERSION,
    EQUITY_EVENT_PAGE_PROJECTION_VERSION,
    EQUITY_EVENT_TIMELINE_PROJECTION_VERSION,
)

_DEFAULT_SOURCE_CLAIM_LEASE_MS = 60_000
_ALERT_SOURCE_ROLES = ("official_regulator", "official_issuer")
_ALERT_FACT_STATUSES = ("accepted", "attention")


class EquityEventRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def upsert_source(
        self,
        *,
        source_id: str,
        provider_type: str,
        company_id: str,
        ticker: str,
        cik: str | None = None,
        source_role: str,
        trust_tier: str = "standard",
        refresh_interval_seconds: int = 300,
        enabled: bool = True,
        now_ms: int,
        commit: bool = True,
    ) -> dict[str, Any]:
        row = self.conn.execute(
            """
            INSERT INTO equity_event_sources (
              source_id, provider_type, company_id, ticker, cik, source_role, trust_tier,
              enabled, refresh_interval_seconds, created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_id) DO UPDATE SET
              provider_type = EXCLUDED.provider_type,
              company_id = EXCLUDED.company_id,
              ticker = EXCLUDED.ticker,
              cik = EXCLUDED.cik,
              source_role = EXCLUDED.source_role,
              trust_tier = EXCLUDED.trust_tier,
              enabled = EXCLUDED.enabled,
              refresh_interval_seconds = EXCLUDED.refresh_interval_seconds,
              updated_at_ms = EXCLUDED.updated_at_ms
            RETURNING *
            """,
            (
                source_id,
                provider_type,
                company_id,
                ticker,
                cik,
                source_role,
                trust_tier,
                bool(enabled),
                max(1, int(refresh_interval_seconds)),
                int(now_ms),
                int(now_ms),
            ),
        ).fetchone()
        if commit:
            self.conn.commit()
        return dict(row)

    def list_source_status(self, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
              FROM equity_event_sources
             ORDER BY source_id ASC
             LIMIT %s
            """,
            (max(0, int(limit)),),
        ).fetchall()
        return [dict(row) for row in rows]

    def reconcile_sources(
        self,
        *,
        sources: Sequence[Mapping[str, Any]],
        universe_members: Sequence[Mapping[str, Any]] = (),
        now_ms: int,
        commit: bool = True,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        active_source_ids: list[str] = []
        for source in sources:
            active_source_ids.append(str(source["source_id"]))
            rows.append(
                self.upsert_source(
                    source_id=str(source["source_id"]),
                    provider_type=str(source["provider_type"]),
                    company_id=str(source["company_id"]),
                    ticker=str(source["ticker"]),
                    cik=_optional_str(source.get("cik")),
                    source_role=str(source["source_role"]),
                    trust_tier=str(source.get("trust_tier") or "standard"),
                    refresh_interval_seconds=int(source.get("refresh_interval_seconds") or 300),
                    enabled=bool(source.get("enabled", True)),
                    now_ms=now_ms,
                    commit=False,
                )
            )
            self._update_source_extra_json(
                source_id=str(source["source_id"]),
                extra_json=_json_dict(source.get("extra_json")),
                now_ms=now_ms,
                commit=False,
            )
        for member in universe_members:
            self.upsert_universe_member(member, now_ms=now_ms, commit=False)
        self.deactivate_unreconciled_universe_members(
            active_company_ids=[str(member["company_id"]) for member in universe_members],
            now_ms=now_ms,
            commit=False,
        )
        self.disable_unreconciled_sources(active_source_ids=active_source_ids, now_ms=now_ms, commit=False)
        if commit:
            self.conn.commit()
        return rows

    def upsert_universe_member(
        self,
        member: Mapping[str, Any],
        *,
        now_ms: int,
        commit: bool = True,
    ) -> dict[str, Any]:
        row = self.conn.execute(
            """
            INSERT INTO equity_event_universe_members (
              company_id, ticker, company_name, cik, exchange, active, priority,
              config_json, created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (company_id) DO UPDATE SET
              ticker = EXCLUDED.ticker,
              company_name = EXCLUDED.company_name,
              cik = EXCLUDED.cik,
              exchange = EXCLUDED.exchange,
              active = EXCLUDED.active,
              priority = EXCLUDED.priority,
              config_json = EXCLUDED.config_json,
              updated_at_ms = EXCLUDED.updated_at_ms
            RETURNING *
            """,
            (
                str(member["company_id"]),
                str(member["ticker"]).upper(),
                str(member.get("company_name") or ""),
                _optional_str(member.get("cik")),
                _optional_str(member.get("exchange")),
                bool(member.get("active", True)),
                str(member.get("priority") or "P3"),
                Jsonb(_json_dict(member.get("config_json"))),
                int(now_ms),
                int(now_ms),
            ),
        ).fetchone()
        if commit:
            self.conn.commit()
        return dict(row)

    def disable_unreconciled_sources(
        self,
        *,
        active_source_ids: Sequence[str],
        now_ms: int,
        commit: bool = True,
    ) -> int:
        cursor = self.conn.execute(
            """
            UPDATE equity_event_sources
               SET enabled = false,
                   updated_at_ms = %s
             WHERE enabled = true
               AND provider_type = 'sec_submissions'
               AND source_id LIKE %s
               AND NOT (source_id = ANY(%s::text[]))
            """,
            (int(now_ms), "sec:%", [str(source_id) for source_id in active_source_ids]),
        )
        if commit:
            self.conn.commit()
        return int(cursor.rowcount or 0)

    def deactivate_unreconciled_universe_members(
        self,
        *,
        active_company_ids: Sequence[str],
        now_ms: int,
        commit: bool = True,
    ) -> int:
        cursor = self.conn.execute(
            """
            UPDATE equity_event_universe_members
               SET active = false,
                   updated_at_ms = %s
             WHERE active = true
               AND NOT (company_id = ANY(%s::text[]))
            """,
            (int(now_ms), [str(company_id) for company_id in active_company_ids]),
        )
        if commit:
            self.conn.commit()
        return int(cursor.rowcount or 0)

    def reconcile_expected_events(
        self,
        *,
        expected_events: Sequence[Mapping[str, Any]],
        scoped_source_ids: Sequence[str] | None = None,
        now_ms: int,
        commit: bool = True,
    ) -> list[dict[str, Any]]:
        active_expected_event_ids = [str(event["expected_event_id"]) for event in expected_events]
        effective_source_ids = (
            [str(source_id) for source_id in scoped_source_ids]
            if scoped_source_ids is not None
            else sorted({str(event["source_id"]) for event in expected_events})
        )
        if effective_source_ids:
            self.mark_unreconciled_expected_events_stale(
                active_expected_event_ids=active_expected_event_ids,
                scoped_source_ids=effective_source_ids,
                now_ms=now_ms,
                commit=False,
            )
        rows = [
            self.upsert_expected_event(
                expected_event_id=str(event["expected_event_id"]),
                company_id=str(event["company_id"]),
                ticker=str(event["ticker"]),
                event_type=str(event["event_type"]),
                fiscal_period=_optional_str(event.get("fiscal_period")),
                expected_at_ms=int(event["expected_at_ms"]),
                source_id=str(event["source_id"]),
                source_role=str(event["source_role"]),
                now_ms=now_ms,
                commit=False,
            )
            for event in expected_events
        ]
        if commit:
            self.conn.commit()
        return rows

    def mark_unreconciled_expected_events_stale(
        self,
        *,
        active_expected_event_ids: Sequence[str],
        scoped_source_ids: Sequence[str],
        now_ms: int,
        commit: bool = True,
    ) -> int:
        cursor = self.conn.execute(
            """
            UPDATE equity_expected_events
               SET status = 'stale',
                   updated_at_ms = %s
             WHERE status IN ('expected', 'stale')
               AND source_id = ANY(%s::text[])
               AND NOT (expected_event_id = ANY(%s::text[]))
            """,
            (
                int(now_ms),
                [str(source_id) for source_id in scoped_source_ids],
                [str(expected_event_id) for expected_event_id in active_expected_event_ids],
            ),
        )
        if commit:
            self.conn.commit()
        return int(cursor.rowcount or 0)

    def claim_due_sources(
        self,
        *,
        now_ms: int,
        limit: int,
        claim_lease_ms: int = _DEFAULT_SOURCE_CLAIM_LEASE_MS,
        supported_provider_types: Sequence[str] = ("sec_submissions",),
        commit: bool = True,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            WITH due AS (
              SELECT source_id
                FROM equity_event_sources
               WHERE enabled = true
                 AND provider_type = ANY(%s::text[])
                 AND next_fetch_after_ms <= %s
               ORDER BY next_fetch_after_ms ASC, source_id ASC
               LIMIT %s
               FOR UPDATE SKIP LOCKED
            )
            UPDATE equity_event_sources AS sources
               SET next_fetch_after_ms = %s,
                   updated_at_ms = %s
              FROM due
             WHERE sources.source_id = due.source_id
            RETURNING sources.*
            """,
            (
                [str(provider_type) for provider_type in supported_provider_types],
                int(now_ms),
                max(0, int(limit)),
                int(now_ms) + max(1, int(claim_lease_ms)),
                int(now_ms),
            ),
        ).fetchall()
        if commit:
            self.conn.commit()
        return [dict(row) for row in rows]

    def start_fetch_run(self, *, source_id: str, started_at_ms: int, commit: bool = True) -> str:
        fetch_run_id = f"equity-event-fetch-run-{uuid.uuid4().hex}"
        self.conn.execute(
            """
            INSERT INTO equity_event_fetch_runs (fetch_run_id, source_id, started_at_ms, status)
            VALUES (%s, %s, %s, 'running')
            """,
            (fetch_run_id, source_id, int(started_at_ms)),
        )
        self.conn.execute(
            """
            UPDATE equity_event_sources
               SET last_fetch_at_ms = %s,
                   updated_at_ms = %s
             WHERE source_id = %s
            """,
            (int(started_at_ms), int(started_at_ms), source_id),
        )
        if commit:
            self.conn.commit()
        return fetch_run_id

    def finish_fetch_run(
        self,
        *,
        fetch_run_id: str,
        source_id: str,
        status: str,
        finished_at_ms: int,
        fetched_count: int = 0,
        inserted_count: int = 0,
        updated_count: int = 0,
        duplicate_count: int = 0,
        http_status: int | None = None,
        error: str | None = None,
        extra_json: Mapping[str, Any] | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        row = self.conn.execute(
            """
            UPDATE equity_event_fetch_runs
               SET finished_at_ms = %s,
                   status = %s,
                   fetched_count = %s,
                   inserted_count = %s,
                   updated_count = %s,
                   duplicate_count = %s,
                   http_status = %s,
                   error = %s,
                   extra_json = %s
             WHERE fetch_run_id = %s
            RETURNING *
            """,
            (
                int(finished_at_ms),
                str(status),
                max(0, int(fetched_count)),
                max(0, int(inserted_count)),
                max(0, int(updated_count)),
                max(0, int(duplicate_count)),
                int(http_status) if http_status is not None else None,
                _compact_error(error),
                Jsonb(_json_dict(extra_json)),
                fetch_run_id,
            ),
        ).fetchone()
        if status == "success":
            self.conn.execute(
                """
                UPDATE equity_event_sources
                   SET last_success_at_ms = %s,
                       next_fetch_after_ms = %s + refresh_interval_seconds * 1000,
                       consecutive_failures = 0,
                       last_error = NULL,
                       updated_at_ms = %s
                 WHERE source_id = %s
                """,
                (int(finished_at_ms), int(finished_at_ms), int(finished_at_ms), source_id),
            )
        else:
            self.conn.execute(
                """
                UPDATE equity_event_sources
                   SET consecutive_failures = consecutive_failures + 1,
                       last_error = %s,
                       next_fetch_after_ms = %s + refresh_interval_seconds * 1000,
                       updated_at_ms = %s
                 WHERE source_id = %s
                """,
                (_compact_error(error), int(finished_at_ms), int(finished_at_ms), source_id),
            )
        if commit:
            self.conn.commit()
        return dict(row)

    def update_source_http_cache(
        self,
        *,
        source_id: str,
        etag: str | None,
        last_modified: str | None,
        now_ms: int,
        commit: bool = True,
    ) -> None:
        self.conn.execute(
            """
            UPDATE equity_event_sources
               SET etag = COALESCE(%s, etag),
                   last_modified = COALESCE(%s, last_modified),
                   updated_at_ms = %s
             WHERE source_id = %s
            """,
            (
                str(etag) if etag else None,
                str(last_modified) if last_modified else None,
                int(now_ms),
                source_id,
            ),
        )
        if commit:
            self.conn.commit()

    def upsert_expected_event(
        self,
        *,
        expected_event_id: str,
        company_id: str,
        ticker: str,
        event_type: str,
        fiscal_period: str | None = None,
        expected_at_ms: int,
        source_id: str,
        source_role: str,
        now_ms: int,
        commit: bool = True,
    ) -> dict[str, Any]:
        row = self.conn.execute(
            """
            INSERT INTO equity_expected_events (
              expected_event_id, company_id, ticker, event_type, fiscal_period,
              expected_at_ms, source_id, source_role, created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (expected_event_id) DO UPDATE SET
              company_id = EXCLUDED.company_id,
              ticker = EXCLUDED.ticker,
              event_type = EXCLUDED.event_type,
              fiscal_period = EXCLUDED.fiscal_period,
              expected_at_ms = EXCLUDED.expected_at_ms,
              source_id = EXCLUDED.source_id,
              source_role = EXCLUDED.source_role,
              status = CASE
                WHEN equity_expected_events.status IN ('expected', 'stale') THEN 'expected'
                ELSE equity_expected_events.status
              END,
              updated_at_ms = EXCLUDED.updated_at_ms
            RETURNING *
            """,
            (
                expected_event_id,
                company_id,
                ticker,
                event_type,
                fiscal_period,
                int(expected_at_ms),
                source_id,
                source_role,
                int(now_ms),
                int(now_ms),
            ),
        ).fetchone()
        if commit:
            self.conn.commit()
        return dict(row)

    def upsert_provider_document(
        self,
        *,
        provider_document_id: str,
        source_id: str,
        fetch_run_id: str | None,
        provider_document_key: str,
        company_id: str,
        ticker: str,
        cik: str | None,
        document_url: str,
        payload_hash: str,
        raw_payload_json: Mapping[str, Any],
        fetched_at_ms: int,
        commit: bool = True,
    ) -> dict[str, Any]:
        existing = self.conn.execute(
            """
            SELECT *
              FROM equity_provider_documents
             WHERE source_id = %s
               AND provider_document_key = %s
            """,
            (source_id, provider_document_key),
        ).fetchone()
        status = "inserted"
        if existing is not None:
            status = "duplicate"
            if (
                existing["document_url"] != document_url
                or existing["payload_hash"] != payload_hash
                or dict(existing["raw_payload_json"]) != dict(raw_payload_json)
            ):
                status = "updated"
        row = self.conn.execute(
            """
            INSERT INTO equity_provider_documents (
              provider_document_id, source_id, fetch_run_id, provider_document_key,
              company_id, ticker, cik, document_url, payload_hash, raw_payload_json, fetched_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_id, provider_document_key) DO UPDATE SET
              fetch_run_id = EXCLUDED.fetch_run_id,
              company_id = EXCLUDED.company_id,
              ticker = EXCLUDED.ticker,
              cik = EXCLUDED.cik,
              document_url = EXCLUDED.document_url,
              payload_hash = EXCLUDED.payload_hash,
              raw_payload_json = EXCLUDED.raw_payload_json,
              fetched_at_ms = EXCLUDED.fetched_at_ms
            RETURNING *
            """,
            (
                provider_document_id,
                source_id,
                fetch_run_id,
                provider_document_key,
                company_id,
                ticker,
                cik,
                document_url,
                payload_hash,
                Jsonb(dict(raw_payload_json)),
                int(fetched_at_ms),
            ),
        ).fetchone()
        if commit:
            self.conn.commit()
        return {**dict(row), "status": status}

    def upsert_event_document(
        self,
        *,
        event_document_id: str,
        provider_document_id: str,
        company_id: str,
        ticker: str,
        cik: str | None,
        source_id: str,
        source_role: str,
        document_type: str,
        form_type: str | None,
        accession_number: str | None,
        fiscal_period: str | None,
        document_url: str,
        event_time_ms: int,
        discovered_at_ms: int,
        content_hash: str,
        now_ms: int,
        commit: bool = True,
    ) -> dict[str, Any]:
        existing = self.conn.execute(
            "SELECT * FROM equity_event_documents WHERE event_document_id = %s",
            (event_document_id,),
        ).fetchone()
        status = "inserted"
        if existing is not None:
            status = "duplicate"
            if (
                existing["provider_document_id"] != provider_document_id
                or existing["document_url"] != document_url
                or existing["content_hash"] != content_hash
                or existing["event_time_ms"] != int(event_time_ms)
            ):
                status = "updated"
        row = self.conn.execute(
            """
            INSERT INTO equity_event_documents (
              event_document_id, provider_document_id, company_id, ticker, cik, source_id,
              source_role, document_type, form_type, accession_number, fiscal_period, document_url,
              event_time_ms, discovered_at_ms, content_hash, created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (event_document_id) DO UPDATE SET
              provider_document_id = EXCLUDED.provider_document_id,
              company_id = EXCLUDED.company_id,
              ticker = EXCLUDED.ticker,
              cik = EXCLUDED.cik,
              source_id = EXCLUDED.source_id,
              source_role = EXCLUDED.source_role,
              document_type = EXCLUDED.document_type,
              form_type = EXCLUDED.form_type,
              accession_number = EXCLUDED.accession_number,
              fiscal_period = EXCLUDED.fiscal_period,
              document_url = EXCLUDED.document_url,
              event_time_ms = EXCLUDED.event_time_ms,
              discovered_at_ms = CASE
                WHEN equity_event_documents.content_hash = EXCLUDED.content_hash
                THEN equity_event_documents.discovered_at_ms
                ELSE EXCLUDED.discovered_at_ms
              END,
              content_hash = EXCLUDED.content_hash,
              lifecycle_status = CASE
                WHEN equity_event_documents.content_hash = EXCLUDED.content_hash
                THEN equity_event_documents.lifecycle_status
                ELSE 'raw'
              END,
              processing_attempts = CASE
                WHEN equity_event_documents.content_hash = EXCLUDED.content_hash
                THEN equity_event_documents.processing_attempts
                ELSE 0
              END,
              processing_error = CASE
                WHEN equity_event_documents.content_hash = EXCLUDED.content_hash
                THEN equity_event_documents.processing_error
                ELSE NULL
              END,
              processed_at_ms = CASE
                WHEN equity_event_documents.content_hash = EXCLUDED.content_hash
                THEN equity_event_documents.processed_at_ms
                ELSE NULL
              END,
              updated_at_ms = EXCLUDED.updated_at_ms
            RETURNING *
            """,
            (
                event_document_id,
                provider_document_id,
                company_id,
                ticker,
                cik,
                source_id,
                source_role,
                document_type,
                form_type,
                accession_number,
                fiscal_period,
                document_url,
                int(event_time_ms),
                int(discovered_at_ms),
                content_hash,
                int(now_ms),
                int(now_ms),
            ),
        ).fetchone()
        if commit:
            self.conn.commit()
        return {**dict(row), "status": status}

    def upsert_company_event(
        self,
        *,
        company_event_id: str,
        company_id: str,
        ticker: str,
        primary_document_id: str | None,
        event_type: str,
        priority: str,
        source_role: str,
        fiscal_period: str | None,
        event_time_ms: int,
        discovered_at_ms: int,
        lifecycle_status: str = "raw",
        validation_status: str = "pending",
        summary: str = "",
        now_ms: int,
        commit: bool = True,
    ) -> dict[str, Any]:
        row = self.conn.execute(
            """
            INSERT INTO equity_company_events (
              company_event_id, company_id, ticker, primary_document_id, event_type, priority,
              source_role, fiscal_period, event_time_ms, discovered_at_ms, lifecycle_status,
              validation_status, summary, created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (company_event_id) DO UPDATE SET
              company_id = EXCLUDED.company_id,
              ticker = EXCLUDED.ticker,
              primary_document_id = EXCLUDED.primary_document_id,
              event_type = EXCLUDED.event_type,
              priority = EXCLUDED.priority,
              source_role = EXCLUDED.source_role,
              fiscal_period = EXCLUDED.fiscal_period,
              event_time_ms = EXCLUDED.event_time_ms,
              discovered_at_ms = EXCLUDED.discovered_at_ms,
              lifecycle_status = EXCLUDED.lifecycle_status,
              validation_status = EXCLUDED.validation_status,
              summary = EXCLUDED.summary,
              updated_at_ms = EXCLUDED.updated_at_ms
            RETURNING *
            """,
            (
                company_event_id,
                company_id,
                ticker,
                primary_document_id,
                event_type,
                priority,
                source_role,
                fiscal_period,
                int(event_time_ms),
                int(discovered_at_ms),
                lifecycle_status,
                validation_status,
                summary,
                int(now_ms),
                int(now_ms),
            ),
        ).fetchone()
        if commit:
            self.conn.commit()
        return dict(row)

    def list_unprocessed_event_documents(self, *, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT documents.*,
                   provider.raw_payload_json
              FROM equity_event_documents AS documents
              JOIN equity_provider_documents AS provider
                ON provider.provider_document_id = documents.provider_document_id
             WHERE documents.lifecycle_status IN ('raw', 'process_failed')
               AND documents.processing_attempts < 3
             ORDER BY documents.event_time_ms ASC, documents.event_document_id ASC
             LIMIT %s
             FOR UPDATE SKIP LOCKED
            """,
            (max(0, int(limit)),),
        ).fetchall()
        return [dict(row) for row in rows]

    def replace_source_spans(
        self,
        *,
        event_document_id: str,
        company_event_id: str,
        spans: Sequence[Any],
        commit: bool = True,
    ) -> None:
        self.conn.execute(
            """
            DELETE FROM equity_event_source_spans
             WHERE event_document_id = %s
                OR company_event_id = %s
            """,
            (event_document_id, company_event_id),
        )
        for span in spans:
            payload = _span_payload(span)
            self.conn.execute(
                """
                INSERT INTO equity_event_source_spans (
                  span_id, company_event_id, event_document_id, source_id, span_type, section_key,
                  span_start, span_end, evidence_quote, confidence, created_at_ms
                )
                VALUES (
                  %(span_id)s, %(company_event_id)s, %(event_document_id)s, %(source_id)s,
                  %(span_type)s, %(section_key)s, %(span_start)s, %(span_end)s,
                  %(evidence_quote)s, %(confidence)s, %(created_at_ms)s
                )
                """,
                payload,
            )
        if commit:
            self.conn.commit()

    def replace_fact_candidates(
        self,
        *,
        event_document_id: str,
        company_event_id: str,
        candidates: Sequence[Any],
        commit: bool = True,
    ) -> None:
        self.conn.execute(
            """
            DELETE FROM equity_event_fact_candidates
             WHERE event_document_id = %s
                OR company_event_id = %s
            """,
            (event_document_id, company_event_id),
        )
        for candidate in candidates:
            payload = _fact_candidate_payload(candidate)
            self.conn.execute(
                """
                INSERT INTO equity_event_fact_candidates (
                  fact_candidate_id, company_event_id, event_document_id, source_span_id, company_id,
                  ticker, event_type, fact_type, metric_name, value_numeric, value_unit, period,
                  direction, required_slots_json, claim, evidence_quote, evidence_span_start,
                  evidence_span_end, source_role, validation_status, rejection_reasons_json,
                  extraction_method, policy_version, created_at_ms, updated_at_ms
                )
                VALUES (
                  %(fact_candidate_id)s, %(company_event_id)s, %(event_document_id)s,
                  %(source_span_id)s, %(company_id)s, %(ticker)s, %(event_type)s,
                  %(fact_type)s, %(metric_name)s, %(value_numeric)s, %(value_unit)s,
                  %(period)s, %(direction)s, %(required_slots_json)s, %(claim)s,
                  %(evidence_quote)s, %(evidence_span_start)s, %(evidence_span_end)s,
                  %(source_role)s, %(validation_status)s, %(rejection_reasons_json)s,
                  %(extraction_method)s, %(policy_version)s, %(created_at_ms)s, %(updated_at_ms)s
                )
                """,
                payload,
            )
        if commit:
            self.conn.commit()

    def clear_story_members_for_document(
        self,
        *,
        event_document_id: str,
        active_company_event_id: str | None = None,
        now_ms: int,
        commit: bool = True,
    ) -> int:
        rows = self.conn.execute(
            """
            WITH affected_stories AS (
              DELETE FROM equity_event_story_members AS members
               USING equity_company_events AS events
               WHERE events.company_event_id = members.company_event_id
                 AND events.primary_document_id = %s
              RETURNING members.story_id
            ),
            story_counts AS (
              SELECT stories.story_id,
                     COUNT(members.company_event_id)::integer AS event_count,
                     COALESCE(MAX(events.event_time_ms), stories.latest_seen_at_ms) AS latest_seen_at_ms
                FROM equity_event_story_groups AS stories
                LEFT JOIN equity_event_story_members AS members
                  ON members.story_id = stories.story_id
                LEFT JOIN equity_company_events AS events
                  ON events.company_event_id = members.company_event_id
               WHERE stories.story_id IN (SELECT story_id FROM affected_stories)
               GROUP BY stories.story_id
            )
            UPDATE equity_event_story_groups AS stories
               SET event_count = story_counts.event_count,
                   latest_seen_at_ms = story_counts.latest_seen_at_ms,
                   updated_at_ms = %s
              FROM story_counts
             WHERE stories.story_id = story_counts.story_id
            RETURNING stories.story_id
            """,
            (event_document_id, int(now_ms)),
        ).fetchall()
        if active_company_event_id is not None:
            self.conn.execute(
                """
                UPDATE equity_company_events
                   SET lifecycle_status = 'process_failed',
                       validation_status = 'rejected',
                       summary = CASE
                         WHEN summary = '' THEN 'superseded by document reprocessing'
                         ELSE summary
                       END,
                       updated_at_ms = %s
                 WHERE primary_document_id = %s
                   AND company_event_id <> %s
                """,
                (int(now_ms), event_document_id, active_company_event_id),
            )
        if commit:
            self.conn.commit()
        return len(rows)

    def mark_event_document_processed(
        self,
        *,
        event_document_id: str,
        processed_at_ms: int,
        commit: bool = True,
    ) -> None:
        self.conn.execute(
            """
            UPDATE equity_event_documents
               SET lifecycle_status = 'processed',
                   processing_error = NULL,
                   processed_at_ms = %s,
                   updated_at_ms = %s
             WHERE event_document_id = %s
            """,
            (int(processed_at_ms), int(processed_at_ms), event_document_id),
        )
        if commit:
            self.conn.commit()

    def mark_event_document_process_failed(
        self,
        *,
        event_document_id: str,
        error: str,
        now_ms: int,
        commit: bool = True,
    ) -> None:
        self.conn.execute(
            """
            UPDATE equity_event_documents
               SET lifecycle_status = 'process_failed',
                   processing_attempts = processing_attempts + 1,
                   processing_error = %s,
                   updated_at_ms = %s
             WHERE event_document_id = %s
            """,
            (_compact_error(error), int(now_ms), event_document_id),
        )
        if commit:
            self.conn.commit()

    def list_events_missing_story(self, *, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT events.*,
                   documents.accession_number
              FROM equity_company_events AS events
              LEFT JOIN equity_event_documents AS documents
                ON documents.event_document_id = events.primary_document_id
              LEFT JOIN equity_event_story_members AS members
                ON members.company_event_id = events.company_event_id
             WHERE members.company_event_id IS NULL
               AND events.validation_status <> 'rejected'
             ORDER BY events.event_time_ms ASC, events.company_event_id ASC
             LIMIT %s
             FOR UPDATE OF events SKIP LOCKED
            """,
            (max(0, int(limit)),),
        ).fetchall()
        return [dict(row) for row in rows]

    def find_story_candidates_for_event(self, event: Mapping[str, Any], *, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT stories.story_id,
                   stories.representative_headline,
                   stories.company_id,
                   stories.ticker,
                   stories.latest_seen_at_ms,
                   events.company_event_id,
                   events.primary_document_id,
                   events.event_type,
                   events.fiscal_period,
                   events.event_time_ms,
                   documents.accession_number
              FROM equity_event_story_groups AS stories
              LEFT JOIN equity_event_story_members AS members
                ON members.story_id = stories.story_id
              LEFT JOIN equity_company_events AS events
                ON events.company_event_id = members.company_event_id
              LEFT JOIN equity_event_documents AS documents
                ON documents.event_document_id = events.primary_document_id
             WHERE stories.company_id = %s
               AND stories.status = 'active'
             ORDER BY stories.latest_seen_at_ms DESC, stories.story_id ASC
             LIMIT %s
            """,
            (str(event["company_id"]), max(0, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]

    def create_story_from_event(
        self,
        *,
        story_id: str,
        event: Mapping[str, Any],
        policy_version: str,
        now_ms: int,
        commit: bool = True,
    ) -> dict[str, Any]:
        row = self.conn.execute(
            """
            INSERT INTO equity_event_story_groups (
              story_id, policy_version, representative_headline, company_id, ticker,
              first_seen_at_ms, latest_seen_at_ms, event_count, status, created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, 0, 'active', %s, %s)
            ON CONFLICT (story_id) DO UPDATE SET
              policy_version = EXCLUDED.policy_version,
              representative_headline = EXCLUDED.representative_headline,
              company_id = EXCLUDED.company_id,
              ticker = EXCLUDED.ticker,
              latest_seen_at_ms = GREATEST(equity_event_story_groups.latest_seen_at_ms, EXCLUDED.latest_seen_at_ms),
              status = 'active',
              updated_at_ms = EXCLUDED.updated_at_ms
            RETURNING *
            """,
            (
                story_id,
                policy_version,
                _headline_for_event(event),
                str(event["company_id"]),
                str(event["ticker"]).upper(),
                int(event["event_time_ms"]),
                int(event["event_time_ms"]),
                int(now_ms),
                int(now_ms),
            ),
        ).fetchone()
        if commit:
            self.conn.commit()
        return dict(row)

    def refresh_story_from_member(
        self,
        *,
        story_id: str,
        event: Mapping[str, Any],
        now_ms: int,
        commit: bool = True,
    ) -> None:
        self.conn.execute(
            """
            UPDATE equity_event_story_groups
               SET latest_seen_at_ms = GREATEST(latest_seen_at_ms, %s),
                   updated_at_ms = %s
             WHERE story_id = %s
            """,
            (int(event["event_time_ms"]), int(now_ms), story_id),
        )
        if commit:
            self.conn.commit()

    def add_story_member(
        self,
        *,
        story_id: str,
        company_event_id: str,
        relation: str,
        match_reason: str,
        match_score: float,
        now_ms: int,
        commit: bool = True,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO equity_event_story_members (
              story_id, company_event_id, relation, match_reason, match_score, created_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (story_id, company_event_id) DO UPDATE SET
              relation = EXCLUDED.relation,
              match_reason = EXCLUDED.match_reason,
              match_score = EXCLUDED.match_score
            """,
            (story_id, company_event_id, relation, match_reason, float(match_score), int(now_ms)),
        )
        self.conn.execute(
            """
            UPDATE equity_event_story_groups AS stories
               SET event_count = counts.event_count,
                   latest_seen_at_ms = counts.latest_seen_at_ms,
                   updated_at_ms = %s
              FROM (
                SELECT members.story_id,
                       COUNT(*)::integer AS event_count,
                       MAX(events.event_time_ms) AS latest_seen_at_ms
                  FROM equity_event_story_members AS members
                  JOIN equity_company_events AS events
                    ON events.company_event_id = members.company_event_id
                 WHERE members.story_id = %s
                 GROUP BY members.story_id
              ) AS counts
             WHERE stories.story_id = counts.story_id
            """,
            (int(now_ms), story_id),
        )
        if commit:
            self.conn.commit()

    def replace_page_rows(
        self,
        *,
        rows: Sequence[Mapping[str, Any]],
        company_event_ids: Sequence[str] | None = None,
        commit: bool = True,
    ) -> None:
        payloads = [_page_row_payload(row) for row in rows]
        scoped_company_event_ids = (
            [str(company_event_id) for company_event_id in company_event_ids]
            if company_event_ids is not None
            else [payload["company_event_id"] for payload in payloads]
        )
        scoped_row_ids = [payload["row_id"] for payload in payloads]
        if not scoped_company_event_ids and not scoped_row_ids:
            if commit:
                self.conn.commit()
            return

        self.conn.execute(
            """
            DELETE FROM equity_event_page_rows
             WHERE row_id = ANY(%s::text[])
                OR company_event_id = ANY(%s::text[])
            """,
            (
                scoped_row_ids,
                scoped_company_event_ids,
            ),
        )
        for payload in payloads:
            self.conn.execute(
                """
                INSERT INTO equity_event_page_rows (
                  row_id, company_event_id, story_id, company_id, ticker, company_name, event_type,
                  priority, source_role, latest_event_at_ms, lifecycle_status, headline, summary,
                  facts_json, documents_json, brief_json, computed_at_ms, projection_version
                )
                VALUES (
                  %(row_id)s, %(company_event_id)s, %(story_id)s, %(company_id)s, %(ticker)s,
                  %(company_name)s, %(event_type)s, %(priority)s, %(source_role)s,
                  %(latest_event_at_ms)s, %(lifecycle_status)s, %(headline)s, %(summary)s,
                  %(facts_json)s, %(documents_json)s, %(brief_json)s, %(computed_at_ms)s,
                  %(projection_version)s
                )
                ON CONFLICT (row_id) DO UPDATE SET
                  company_event_id = EXCLUDED.company_event_id,
                  story_id = EXCLUDED.story_id,
                  company_id = EXCLUDED.company_id,
                  ticker = EXCLUDED.ticker,
                  company_name = EXCLUDED.company_name,
                  event_type = EXCLUDED.event_type,
                  priority = EXCLUDED.priority,
                  source_role = EXCLUDED.source_role,
                  latest_event_at_ms = EXCLUDED.latest_event_at_ms,
                  lifecycle_status = EXCLUDED.lifecycle_status,
                  headline = EXCLUDED.headline,
                  summary = EXCLUDED.summary,
                  facts_json = EXCLUDED.facts_json,
                  documents_json = EXCLUDED.documents_json,
                  brief_json = EXCLUDED.brief_json,
                  computed_at_ms = EXCLUDED.computed_at_ms,
                  projection_version = EXCLUDED.projection_version
                """,
                payload,
            )
        if commit:
            self.conn.commit()

    def list_event_page_rows(
        self,
        *,
        limit: int,
        cursor: str | None = None,
        window: str | None = None,
        universe: str | None = None,
        ticker: str | None = None,
        event_type: str | None = None,
        priority: str | None = None,
        source_role: str | None = None,
        lifecycle_status: str | None = None,
        brief_status: str | None = None,
        q: str | None = None,
    ) -> list[dict[str, Any]]:
        cursor_time, cursor_id = _decode_cursor(cursor)
        filters: list[str] = []
        filter_params: list[Any] = []
        window_ms = _window_ms(window)
        if window_ms is not None:
            filters.append("latest_event_at_ms >= ((EXTRACT(EPOCH FROM now()) * 1000)::bigint - %s)")
            filter_params.append(window_ms)
        if universe:
            filters.append(
                """
                EXISTS (
                  SELECT 1
                    FROM equity_event_universe_members AS universe
                   WHERE universe.company_id = equity_event_page_rows.company_id
                     AND universe.config_json ->> 'universe' = %s
                )
                """
            )
            filter_params.append(str(universe))
        if ticker:
            filters.append("ticker = %s")
            filter_params.append(str(ticker).upper())
        if event_type:
            filters.append("event_type = %s")
            filter_params.append(str(event_type))
        if priority:
            filters.append("priority = %s")
            filter_params.append(str(priority))
        if source_role:
            filters.append("source_role = %s")
            filter_params.append(str(source_role))
        if lifecycle_status:
            filters.append("lifecycle_status = %s")
            filter_params.append(str(lifecycle_status))
        if brief_status:
            filters.append("LOWER(COALESCE(brief_json ->> 'status', 'pending')) = %s")
            filter_params.append(str(brief_status).strip().lower())
        if q:
            needle = f"%{str(q).strip()}%"
            filters.append("(headline ILIKE %s OR summary ILIKE %s OR company_name ILIKE %s OR ticker ILIKE %s)")
            filter_params.extend([needle, needle, needle, needle])
        cursor_filter = ""
        cursor_params: list[Any] = []
        if cursor_time is not None and cursor_id is not None:
            cursor_filter = """
              AND (
                latest_event_at_ms < %s
                OR (latest_event_at_ms = %s AND company_event_id > %s)
              )
            """
            cursor_params.extend([cursor_time, cursor_time, cursor_id])
        elif cursor_id is not None:
            cursor_filter = " AND company_event_id > %s"
            cursor_params.append(cursor_id)
        filter_sql = " AND " + " AND ".join(filters) if filters else ""
        rows = self.conn.execute(
            f"""
            SELECT *
              FROM equity_event_page_rows
             WHERE true
             {cursor_filter}
             {filter_sql}
             ORDER BY latest_event_at_ms DESC, company_event_id ASC
             LIMIT %s
            """,
            (*cursor_params, *filter_params, max(0, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_event_detail(self, *, company_event_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT rows.*,
                   CASE WHEN events.company_event_id IS NULL THEN NULL ELSE to_jsonb(events.*) END AS event_json,
                   CASE WHEN stories.story_id IS NULL THEN NULL ELSE to_jsonb(stories.*) END AS story_json
              FROM equity_event_page_rows AS rows
              LEFT JOIN equity_company_events AS events
                ON events.company_event_id = rows.company_event_id
              LEFT JOIN equity_event_story_groups AS stories
                ON stories.story_id = rows.story_id
             WHERE rows.company_event_id = %s
             LIMIT 1
            """,
            (str(company_event_id),),
        ).fetchone()
        if row is None:
            return None
        payload = dict(row)
        payload["event"] = payload.pop("event_json", None)
        payload["story"] = payload.pop("story_json", None)
        return payload

    def get_story_detail(self, *, story_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT stories.*,
                   COALESCE(
                     jsonb_agg(to_jsonb(rows.*) ORDER BY rows.latest_event_at_ms DESC, rows.company_event_id ASC)
                       FILTER (WHERE rows.row_id IS NOT NULL),
                     '[]'::jsonb
                   ) AS events
              FROM equity_event_story_groups AS stories
              LEFT JOIN equity_event_page_rows AS rows
                ON rows.story_id = stories.story_id
             WHERE stories.story_id = %s
             GROUP BY stories.story_id
             LIMIT 1
            """,
            (str(story_id),),
        ).fetchone()
        return dict(row) if row is not None else None

    def list_calendar_rows(
        self,
        *,
        from_ms: int | None = None,
        to_ms: int | None = None,
        universe: str | None = None,
        ticker: str | None = None,
        status: str | None = None,
        session: str | None = None,
    ) -> list[dict[str, Any]]:
        filters: list[str] = []
        filter_params: list[Any] = []
        if from_ms is not None:
            filters.append("expected_at_ms >= %s")
            filter_params.append(int(from_ms))
        if to_ms is not None:
            filters.append("expected_at_ms <= %s")
            filter_params.append(int(to_ms))
        if universe:
            filters.append(
                """
                EXISTS (
                  SELECT 1
                    FROM equity_event_universe_members AS universe
                   WHERE universe.company_id = equity_event_calendar_rows.company_id
                     AND universe.config_json ->> 'universe' = %s
                )
                """
            )
            filter_params.append(str(universe))
        if ticker:
            filters.append("ticker = %s")
            filter_params.append(str(ticker).upper())
        if status:
            filters.append("status = %s")
            filter_params.append(str(status))
        if session:
            filters.append("LOWER(COALESCE(calendar_json ->> 'session', '')) = %s")
            filter_params.append(str(session).strip().lower())
        filter_sql = " AND " + " AND ".join(filters) if filters else ""
        rows = self.conn.execute(
            f"""
            SELECT *
              FROM equity_event_calendar_rows
             WHERE true
             {filter_sql}
             ORDER BY expected_at_ms ASC, ticker ASC, row_id ASC
            """,
            tuple(filter_params),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_company_timeline_rows(
        self,
        *,
        ticker: str,
        limit: int,
        cursor: str | None = None,
    ) -> list[dict[str, Any]]:
        cursor_time, cursor_id = _decode_cursor(cursor)
        cursor_filter = ""
        cursor_params: list[Any] = []
        if cursor_time is not None and cursor_id is not None:
            cursor_filter = """
              AND (
                event_time_ms < %s
                OR (event_time_ms = %s AND row_id > %s)
              )
            """
            cursor_params.extend([cursor_time, cursor_time, cursor_id])
        elif cursor_id is not None:
            cursor_filter = " AND row_id > %s"
            cursor_params.append(cursor_id)
        rows = self.conn.execute(
            f"""
            SELECT *
              FROM equity_company_timeline_rows
             WHERE ticker = %s
             {cursor_filter}
             ORDER BY event_time_ms DESC, row_id ASC
             LIMIT %s
            """,
            (str(ticker).upper(), *cursor_params, max(0, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]

    def summary(self) -> dict[str, Any]:
        row = self.conn.execute(
            """
            SELECT
              COUNT(*) FILTER (
                WHERE priority = 'P0'
                  AND lifecycle_status IN ('raw', 'processed', 'process_failed', 'brief_stale')
              )::integer AS p0_open_count,
              COUNT(*) FILTER (
                WHERE latest_event_at_ms >= (
                  EXTRACT(EPOCH FROM date_trunc('day', now())) * 1000
                )::bigint
              )::integer AS today_count,
              COUNT(*) FILTER (
                WHERE LOWER(COALESCE(brief_json ->> 'status', 'pending')) = 'pending'
              )::integer AS brief_pending_count,
              MAX(latest_event_at_ms) AS latest_event_at_ms
              FROM equity_event_page_rows
            """
        ).fetchone()
        if row is None:
            return {
                "p0_open_count": 0,
                "today_count": 0,
                "brief_pending_count": 0,
                "latest_event_at_ms": None,
            }
        return {
            "p0_open_count": int(row["p0_open_count"] or 0),
            "today_count": int(row["today_count"] or 0),
            "brief_pending_count": int(row["brief_pending_count"] or 0),
            "latest_event_at_ms": row["latest_event_at_ms"],
        }

    def list_events_for_page_projection(self, *, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT events.*,
                   universe.company_name,
                   universe.priority AS company_priority,
                   stories.story_id,
                   stories.representative_headline,
                   stories.latest_seen_at_ms AS story_latest_seen_at_ms,
                   stories.updated_at_ms AS story_updated_at_ms,
                   briefs.agent_run_id,
                   briefs.status AS brief_status,
                   briefs.validation_status AS brief_validation_status,
                   briefs.brief_json,
                   briefs.input_hash,
                   briefs.artifact_version_hash,
                   briefs.prompt_version,
                   briefs.schema_version,
                   briefs.validator_version,
                   briefs.computed_at_ms AS brief_computed_at_ms,
                   briefs.updated_at_ms AS brief_updated_at_ms,
                   page_rows.row_id AS page_row_id,
                   page_rows.computed_at_ms AS page_computed_at_ms,
                   page_rows.projection_version AS page_projection_version,
                   alerts.alert_candidate_id,
                   alerts.computed_at_ms AS alert_computed_at_ms,
                   alerts.projection_version AS alert_projection_version,
                   timeline_rows.row_id AS timeline_row_id,
                   timeline_rows.computed_at_ms AS timeline_computed_at_ms,
                   timeline_rows.projection_version AS timeline_projection_version,
                   COALESCE(fact_state.facts_updated_at_ms, 0) AS facts_updated_at_ms,
                   COALESCE(fact_state.actionable_fact_count, 0) AS actionable_fact_count,
                   COALESCE(documents.updated_at_ms, 0) AS document_updated_at_ms
              FROM equity_company_events AS events
              LEFT JOIN equity_event_universe_members AS universe
                ON universe.company_id = events.company_id
              LEFT JOIN equity_event_story_members AS members
                ON members.company_event_id = events.company_event_id
              LEFT JOIN equity_event_story_groups AS stories
                ON stories.story_id = members.story_id
              LEFT JOIN equity_event_agent_briefs AS briefs
                ON briefs.company_event_id = events.company_event_id
              LEFT JOIN equity_event_documents AS documents
                ON documents.event_document_id = events.primary_document_id
              LEFT JOIN LATERAL (
                SELECT rows.*
                  FROM equity_event_page_rows AS rows
                 WHERE rows.company_event_id = events.company_event_id
                 ORDER BY rows.computed_at_ms DESC, rows.row_id ASC
                 LIMIT 1
              ) AS page_rows ON true
              LEFT JOIN LATERAL (
                SELECT candidates.*
                  FROM equity_event_alert_candidates AS candidates
                 WHERE candidates.company_event_id = events.company_event_id
                 ORDER BY candidates.computed_at_ms DESC, candidates.alert_candidate_id ASC
                 LIMIT 1
              ) AS alerts ON true
              LEFT JOIN LATERAL (
                SELECT rows.*
                  FROM equity_company_timeline_rows AS rows
                 WHERE rows.company_event_id = events.company_event_id
                 ORDER BY rows.computed_at_ms DESC, rows.row_id ASC
                 LIMIT 1
              ) AS timeline_rows ON true
              LEFT JOIN LATERAL (
                SELECT MAX(facts.updated_at_ms) AS facts_updated_at_ms,
                       COUNT(*) FILTER (
                         WHERE facts.validation_status = ANY(%s::text[])
                       )::integer AS actionable_fact_count
                  FROM equity_event_fact_candidates AS facts
                 WHERE facts.company_event_id = events.company_event_id
              ) AS fact_state ON true
             WHERE events.validation_status <> 'rejected'
               AND (
                 page_rows.row_id IS NULL
                 OR page_rows.projection_version <> %s
                 OR page_rows.computed_at_ms < GREATEST(
                   events.updated_at_ms,
                   COALESCE(stories.updated_at_ms, 0),
                   COALESCE(briefs.updated_at_ms, 0),
                   COALESCE(documents.updated_at_ms, 0),
                   COALESCE(fact_state.facts_updated_at_ms, 0)
                 )
                 OR timeline_rows.row_id IS NULL
                 OR timeline_rows.projection_version <> %s
                 OR timeline_rows.computed_at_ms < GREATEST(
                   events.updated_at_ms,
                   COALESCE(stories.updated_at_ms, 0),
                   COALESCE(briefs.updated_at_ms, 0),
                   COALESCE(documents.updated_at_ms, 0),
                   COALESCE(fact_state.facts_updated_at_ms, 0)
                 )
                 OR (
                   events.priority = 'P0'
                   AND events.source_role = ANY(%s::text[])
                   AND COALESCE(fact_state.actionable_fact_count, 0) > 0
                   AND (
                     alerts.alert_candidate_id IS NULL
                     OR alerts.projection_version <> %s
                     OR alerts.computed_at_ms < GREATEST(
                       events.updated_at_ms,
                       COALESCE(stories.updated_at_ms, 0),
                       COALESCE(briefs.updated_at_ms, 0),
                       COALESCE(documents.updated_at_ms, 0),
                       COALESCE(fact_state.facts_updated_at_ms, 0)
                     )
                   )
                 )
                 OR (
                   NOT (
                     events.priority = 'P0'
                     AND events.source_role = ANY(%s::text[])
                     AND COALESCE(fact_state.actionable_fact_count, 0) > 0
                   )
                   AND alerts.alert_candidate_id IS NOT NULL
                 )
               )
             ORDER BY CASE
                        WHEN page_rows.row_id IS NULL THEN 0
                        WHEN page_rows.projection_version <> %s THEN 0
                        WHEN page_rows.computed_at_ms < GREATEST(
                          events.updated_at_ms,
                          COALESCE(stories.updated_at_ms, 0),
                          COALESCE(briefs.updated_at_ms, 0),
                          COALESCE(documents.updated_at_ms, 0),
                          COALESCE(fact_state.facts_updated_at_ms, 0)
                        ) THEN 0
                        WHEN timeline_rows.row_id IS NULL THEN 0
                        WHEN timeline_rows.projection_version <> %s THEN 0
                        WHEN timeline_rows.computed_at_ms < GREATEST(
                          events.updated_at_ms,
                          COALESCE(stories.updated_at_ms, 0),
                          COALESCE(briefs.updated_at_ms, 0),
                          COALESCE(documents.updated_at_ms, 0),
                          COALESCE(fact_state.facts_updated_at_ms, 0)
                        ) THEN 0
                        WHEN events.priority = 'P0'
                          AND events.source_role = ANY(%s::text[])
                          AND COALESCE(fact_state.actionable_fact_count, 0) > 0
                          AND (
                            alerts.alert_candidate_id IS NULL
                            OR alerts.projection_version <> %s
                            OR alerts.computed_at_ms < GREATEST(
                              events.updated_at_ms,
                              COALESCE(stories.updated_at_ms, 0),
                              COALESCE(briefs.updated_at_ms, 0),
                              COALESCE(documents.updated_at_ms, 0),
                              COALESCE(fact_state.facts_updated_at_ms, 0)
                            )
                          ) THEN 0
                        WHEN NOT (
                          events.priority = 'P0'
                          AND events.source_role = ANY(%s::text[])
                          AND COALESCE(fact_state.actionable_fact_count, 0) > 0
                        )
                          AND alerts.alert_candidate_id IS NOT NULL THEN 0
                        ELSE 1
                      END ASC,
                      events.event_time_ms DESC,
                      events.company_event_id ASC
             LIMIT %s
             FOR UPDATE OF events SKIP LOCKED
            """,
            (
                list(_ALERT_FACT_STATUSES),
                EQUITY_EVENT_PAGE_PROJECTION_VERSION,
                EQUITY_EVENT_TIMELINE_PROJECTION_VERSION,
                list(_ALERT_SOURCE_ROLES),
                EQUITY_EVENT_ALERT_PROJECTION_VERSION,
                list(_ALERT_SOURCE_ROLES),
                EQUITY_EVENT_PAGE_PROJECTION_VERSION,
                EQUITY_EVENT_TIMELINE_PROJECTION_VERSION,
                list(_ALERT_SOURCE_ROLES),
                EQUITY_EVENT_ALERT_PROJECTION_VERSION,
                list(_ALERT_SOURCE_ROLES),
                max(0, int(limit)),
            ),
        ).fetchall()
        payloads: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            payloads.append(
                {
                    "event": item,
                    "company": {
                        "company_id": item["company_id"],
                        "ticker": item["ticker"],
                        "company_name": item.get("company_name") or "",
                        "priority": item.get("company_priority") or item.get("priority") or "P3",
                    },
                    "story": _story_payload(item),
                    "facts": self._list_event_facts(str(item["company_event_id"])),
                    "documents": self._list_event_documents(_optional_str(item.get("primary_document_id"))),
                    "brief": _brief_payload(item),
                }
            )
        return payloads

    def list_events_for_brief(
        self,
        *,
        limit: int,
        now_ms: int,
        backpressure_cooldown_ms: int,
        artifact_version_hash: str,
        max_attempts: int,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT events.*,
                   universe.company_name,
                   stories.story_id,
                   stories.event_count,
                   stories.representative_headline,
                   stories.updated_at_ms AS story_updated_at_ms,
                   briefs.agent_run_id,
                   briefs.status AS brief_status,
                   briefs.validation_status AS brief_validation_status,
                   briefs.brief_json,
                   briefs.input_hash,
                   briefs.artifact_version_hash,
                   briefs.prompt_version,
                   briefs.schema_version,
                   briefs.validator_version,
                   briefs.computed_at_ms AS brief_computed_at_ms,
                   briefs.updated_at_ms AS brief_updated_at_ms,
                   COALESCE(source_state.source_updated_at_ms, events.updated_at_ms) AS source_updated_at_ms,
                   COALESCE(run_state.failed_attempts, 0) AS failed_attempts,
                   run_state.latest_status AS latest_run_status,
                   run_state.latest_finished_at_ms AS latest_run_finished_at_ms
              FROM equity_company_events AS events
              LEFT JOIN equity_event_universe_members AS universe
                ON universe.company_id = events.company_id
              LEFT JOIN equity_event_story_members AS members
                ON members.company_event_id = events.company_event_id
              LEFT JOIN equity_event_story_groups AS stories
                ON stories.story_id = members.story_id
              LEFT JOIN equity_event_agent_briefs AS briefs
                ON briefs.company_event_id = events.company_event_id
              LEFT JOIN LATERAL (
                SELECT GREATEST(
                         events.updated_at_ms,
                         COALESCE((
                           SELECT MAX(documents.updated_at_ms)
                             FROM equity_event_documents AS documents
                            WHERE documents.event_document_id = events.primary_document_id
                         ), 0),
                         COALESCE((
                           SELECT MAX(facts.updated_at_ms)
                             FROM equity_event_fact_candidates AS facts
                            WHERE facts.company_event_id = events.company_event_id
                         ), 0),
                         COALESCE(stories.updated_at_ms, 0)
                       ) AS source_updated_at_ms
              ) AS source_state ON true
              LEFT JOIN LATERAL (
                SELECT COUNT(*) FILTER (
                         WHERE runs.status = 'failed'
                           AND runs.execution_started = true
                           AND runs.artifact_version_hash = %s
                           AND runs.started_at_ms >= COALESCE(source_state.source_updated_at_ms, events.updated_at_ms)
                       )::integer AS failed_attempts,
                       (ARRAY_AGG(runs.status ORDER BY runs.finished_at_ms DESC, runs.run_id DESC))[1] AS latest_status,
                       MAX(runs.finished_at_ms) AS latest_finished_at_ms
                  FROM equity_event_agent_runs AS runs
                 WHERE runs.company_event_id = events.company_event_id
              ) AS run_state ON true
             WHERE events.validation_status <> 'rejected'
               AND events.lifecycle_status IN ('raw', 'processed', 'brief_ready', 'brief_stale')
               AND COALESCE(run_state.failed_attempts, 0) < %s
               AND (
                 run_state.latest_status IS DISTINCT FROM 'backpressure'
                 OR COALESCE(run_state.latest_finished_at_ms, 0) <= %s
               )
               AND (
                 briefs.company_event_id IS NULL
                 OR briefs.status = 'failed'
                 OR briefs.artifact_version_hash <> %s
                 OR briefs.computed_at_ms < COALESCE(source_state.source_updated_at_ms, events.updated_at_ms)
               )
             ORDER BY CASE
                        WHEN briefs.company_event_id IS NULL THEN 0
                        WHEN briefs.artifact_version_hash <> %s THEN 1
                        WHEN briefs.status = 'failed' THEN 2
                        ELSE 3
                      END ASC,
                      events.event_time_ms DESC,
                      events.company_event_id ASC
             LIMIT %s
             FOR UPDATE OF events SKIP LOCKED
            """,
            (
                str(artifact_version_hash),
                max(1, int(max_attempts)),
                int(now_ms) - max(1, int(backpressure_cooldown_ms)),
                str(artifact_version_hash),
                str(artifact_version_hash),
                max(0, int(limit)),
            ),
        ).fetchall()
        payloads: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            company_event_id = str(item["company_event_id"])
            story_id = _optional_str(item.get("story_id"))
            payloads.append(
                {
                    "event": item,
                    "story": _brief_story_payload(item),
                    "story_members": self._list_brief_story_members(story_id),
                    "source_documents": self._list_event_documents(_optional_str(item.get("primary_document_id"))),
                    "source_spans": self._list_event_source_spans(company_event_id),
                    "fact_candidates": self._list_event_facts(company_event_id),
                    "current_brief": _brief_payload(item),
                    "source_updated_at_ms": int(item.get("source_updated_at_ms") or item.get("updated_at_ms") or 0),
                }
            )
        return payloads

    def get_event_brief_source_updated_at(self, *, company_event_id: str) -> int:
        row = self.conn.execute(
            """
            SELECT GREATEST(
                     events.updated_at_ms,
                     COALESCE((
                       SELECT MAX(documents.updated_at_ms)
                         FROM equity_event_documents AS documents
                        WHERE documents.event_document_id = events.primary_document_id
                     ), 0),
                     COALESCE((
                       SELECT MAX(facts.updated_at_ms)
                         FROM equity_event_fact_candidates AS facts
                        WHERE facts.company_event_id = events.company_event_id
                     ), 0),
                     COALESCE(stories.updated_at_ms, 0)
                   ) AS source_updated_at_ms
              FROM equity_company_events AS events
              LEFT JOIN equity_event_story_members AS members
                ON members.company_event_id = events.company_event_id
              LEFT JOIN equity_event_story_groups AS stories
                ON stories.story_id = members.story_id
             WHERE events.company_event_id = %s
             LIMIT 1
            """,
            (str(company_event_id),),
        ).fetchone()
        if row is None:
            return 0
        return int(row["source_updated_at_ms"] or 0)

    def insert_equity_event_agent_run(
        self,
        *,
        run_id: str,
        company_event_id: str,
        provider: str,
        model: str,
        backend: str,
        sdk_trace_id: str | None,
        workflow_name: str,
        agent_name: str,
        lane: str,
        artifact_version_hash: str,
        prompt_version: str,
        schema_version: str,
        validator_version: str,
        guardrail_version: str,
        input_hash: str,
        output_hash: str | None,
        execution_started: bool,
        status: str,
        outcome: str,
        error_class: str | None,
        error: str | None,
        request_json: Mapping[str, Any],
        response_json: Any | None,
        validation_errors_json: Sequence[Mapping[str, Any]],
        trace_metadata_json: Mapping[str, Any],
        usage_json: Mapping[str, Any],
        latency_ms: int,
        started_at_ms: int,
        finished_at_ms: int,
        created_at_ms: int,
        commit: bool = True,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO equity_event_agent_runs (
              run_id, company_event_id, provider, model, backend, sdk_trace_id,
              workflow_name, agent_name, lane, artifact_version_hash, prompt_version,
              schema_version, validator_version, guardrail_version, input_hash, output_hash,
              execution_started, status, outcome, error_class, error, request_json,
              response_json, validation_errors_json, trace_metadata_json, usage_json,
              latency_ms, started_at_ms, finished_at_ms, created_at_ms
            )
            VALUES (
              %(run_id)s, %(company_event_id)s, %(provider)s, %(model)s, %(backend)s,
              %(sdk_trace_id)s, %(workflow_name)s, %(agent_name)s, %(lane)s,
              %(artifact_version_hash)s, %(prompt_version)s, %(schema_version)s,
              %(validator_version)s, %(guardrail_version)s, %(input_hash)s,
              %(output_hash)s, %(execution_started)s, %(status)s, %(outcome)s,
              %(error_class)s, %(error)s, %(request_json)s, %(response_json)s,
              %(validation_errors_json)s, %(trace_metadata_json)s, %(usage_json)s,
              %(latency_ms)s, %(started_at_ms)s, %(finished_at_ms)s, %(created_at_ms)s
            )
            """,
            {
                "run_id": run_id,
                "company_event_id": company_event_id,
                "provider": provider,
                "model": model,
                "backend": backend,
                "sdk_trace_id": sdk_trace_id,
                "workflow_name": workflow_name,
                "agent_name": agent_name,
                "lane": lane,
                "artifact_version_hash": artifact_version_hash,
                "prompt_version": prompt_version,
                "schema_version": schema_version,
                "validator_version": validator_version,
                "guardrail_version": guardrail_version,
                "input_hash": input_hash,
                "output_hash": output_hash,
                "execution_started": bool(execution_started),
                "status": status,
                "outcome": outcome,
                "error_class": error_class,
                "error": _compact_error(error),
                "request_json": Jsonb(dict(request_json)),
                "response_json": Jsonb(response_json) if response_json is not None else None,
                "validation_errors_json": Jsonb([dict(row) for row in validation_errors_json]),
                "trace_metadata_json": Jsonb(dict(trace_metadata_json)),
                "usage_json": Jsonb(dict(usage_json)),
                "latency_ms": int(latency_ms),
                "started_at_ms": int(started_at_ms),
                "finished_at_ms": int(finished_at_ms),
                "created_at_ms": int(created_at_ms),
            },
        )
        if commit:
            self.conn.commit()

    def upsert_equity_event_agent_brief(
        self,
        *,
        company_event_id: str,
        agent_run_id: str,
        status: str,
        validation_status: str,
        brief_json: Mapping[str, Any],
        input_hash: str,
        artifact_version_hash: str,
        prompt_version: str,
        schema_version: str,
        validator_version: str,
        computed_at_ms: int,
        created_at_ms: int,
        updated_at_ms: int,
        commit: bool = True,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO equity_event_agent_briefs (
              company_event_id, agent_run_id, status, validation_status, brief_json,
              input_hash, artifact_version_hash, prompt_version, schema_version,
              validator_version, computed_at_ms, created_at_ms, updated_at_ms
            )
            VALUES (
              %(company_event_id)s, %(agent_run_id)s, %(status)s, %(validation_status)s,
              %(brief_json)s, %(input_hash)s, %(artifact_version_hash)s,
              %(prompt_version)s, %(schema_version)s, %(validator_version)s,
              %(computed_at_ms)s, %(created_at_ms)s, %(updated_at_ms)s
            )
            ON CONFLICT (company_event_id) DO UPDATE SET
              agent_run_id = EXCLUDED.agent_run_id,
              status = EXCLUDED.status,
              validation_status = EXCLUDED.validation_status,
              brief_json = EXCLUDED.brief_json,
              input_hash = EXCLUDED.input_hash,
              artifact_version_hash = EXCLUDED.artifact_version_hash,
              prompt_version = EXCLUDED.prompt_version,
              schema_version = EXCLUDED.schema_version,
              validator_version = EXCLUDED.validator_version,
              computed_at_ms = EXCLUDED.computed_at_ms,
              updated_at_ms = EXCLUDED.updated_at_ms
            """,
            {
                "company_event_id": company_event_id,
                "agent_run_id": agent_run_id,
                "status": status,
                "validation_status": validation_status,
                "brief_json": Jsonb(dict(brief_json)),
                "input_hash": input_hash,
                "artifact_version_hash": artifact_version_hash,
                "prompt_version": prompt_version,
                "schema_version": schema_version,
                "validator_version": validator_version,
                "computed_at_ms": int(computed_at_ms),
                "created_at_ms": int(created_at_ms),
                "updated_at_ms": int(updated_at_ms),
            },
        )
        lifecycle_status = "brief_ready" if status in {"ready", "insufficient"} else "brief_stale"
        self.conn.execute(
            """
            UPDATE equity_company_events
               SET lifecycle_status = %s,
                   updated_at_ms = GREATEST(updated_at_ms, %s)
             WHERE company_event_id = %s
            """,
            (lifecycle_status, int(updated_at_ms), company_event_id),
        )
        if commit:
            self.conn.commit()

    def list_expected_events_for_calendar_projection(self, *, limit: int) -> list[dict[str, Any]]:
        earnings_family = ["earnings_release", "quarterly_report"]
        rows = self.conn.execute(
            """
            SELECT expected.*,
                   universe.company_name,
                   universe.priority AS company_priority,
                   observed.company_event_id AS observed_company_event_id,
                   observed.company_id AS observed_company_id,
                   observed.ticker AS observed_ticker,
                   observed.event_type AS observed_event_type,
                   observed.priority AS observed_priority,
                   observed.source_role AS observed_source_role,
                   observed.fiscal_period AS observed_fiscal_period,
                   observed.event_time_ms AS observed_event_time_ms,
                   observed.discovered_at_ms AS observed_discovered_at_ms,
                   observed.lifecycle_status AS observed_lifecycle_status,
                   observed.validation_status AS observed_validation_status,
                   observed.summary AS observed_summary,
                   observed.updated_at_ms AS observed_updated_at_ms,
                   calendar_rows.row_id AS calendar_row_id,
                   calendar_rows.computed_at_ms AS calendar_computed_at_ms
              FROM equity_expected_events AS expected
              LEFT JOIN equity_event_universe_members AS universe
                ON universe.company_id = expected.company_id
              LEFT JOIN LATERAL (
                SELECT events.*
                  FROM equity_company_events AS events
                 WHERE events.validation_status <> 'rejected'
                   AND events.ticker = expected.ticker
                   AND (
                     events.company_id = expected.company_id
                     OR expected.company_id = ''
                   )
                   AND (
                     expected.fiscal_period IS NULL
                     OR events.fiscal_period IS NULL
                     OR events.fiscal_period = expected.fiscal_period
                   )
                   AND (
                     events.event_type = expected.event_type
                     OR (
                       expected.event_type = ANY(%s::text[])
                       AND events.event_type = ANY(%s::text[])
                     )
                   )
                 ORDER BY ABS(events.event_time_ms - expected.expected_at_ms) ASC,
                          events.event_time_ms DESC,
                          events.company_event_id ASC
                 LIMIT 1
              ) AS observed ON true
              LEFT JOIN equity_event_calendar_rows AS calendar_rows
                ON calendar_rows.expected_event_id = expected.expected_event_id
             WHERE expected.status IN ('expected', 'observed')
               AND (
                 calendar_rows.row_id IS NULL
                 OR calendar_rows.projection_version <> %s
                 OR calendar_rows.computed_at_ms < GREATEST(
                   expected.updated_at_ms,
                   COALESCE(observed.updated_at_ms, 0)
                 )
               )
             ORDER BY CASE
                        WHEN calendar_rows.row_id IS NULL THEN 0
                        WHEN calendar_rows.projection_version <> %s THEN 0
                        WHEN calendar_rows.computed_at_ms < GREATEST(
                          expected.updated_at_ms,
                          COALESCE(observed.updated_at_ms, 0)
                        ) THEN 0
                        ELSE 1
                      END ASC,
                      expected.expected_at_ms ASC,
                      expected.expected_event_id ASC
             LIMIT %s
            """,
            (
                earnings_family,
                earnings_family,
                EQUITY_EVENT_CALENDAR_PROJECTION_VERSION,
                EQUITY_EVENT_CALENDAR_PROJECTION_VERSION,
                max(0, int(limit)),
            ),
        ).fetchall()
        return [_calendar_projection_payload(dict(row)) for row in rows]

    def list_inactive_expected_event_ids_for_calendar_projection(self, *, limit: int) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT expected.expected_event_id
              FROM equity_expected_events AS expected
              JOIN equity_event_calendar_rows AS calendar_rows
                ON calendar_rows.expected_event_id = expected.expected_event_id
             WHERE expected.status NOT IN ('expected', 'observed')
             ORDER BY expected.updated_at_ms ASC, expected.expected_event_id ASC
             LIMIT %s
            """,
            (max(0, int(limit)),),
        ).fetchall()
        return [str(row["expected_event_id"]) for row in rows]

    def replace_calendar_rows(
        self,
        *,
        expected_event_ids: Sequence[str],
        rows: Sequence[Mapping[str, Any]],
        commit: bool = True,
    ) -> None:
        payloads = [_calendar_row_payload(row) for row in rows]
        scoped_expected_event_ids = [str(expected_event_id) for expected_event_id in expected_event_ids]
        scoped_row_ids = [payload["row_id"] for payload in payloads]
        if not scoped_expected_event_ids and not scoped_row_ids:
            if commit:
                self.conn.commit()
            return
        self.conn.execute(
            """
            DELETE FROM equity_event_calendar_rows
             WHERE row_id = ANY(%s::text[])
                OR expected_event_id = ANY(%s::text[])
            """,
            (scoped_row_ids, scoped_expected_event_ids),
        )
        for payload in payloads:
            self.conn.execute(
                """
                INSERT INTO equity_event_calendar_rows (
                  row_id, expected_event_id, company_id, ticker, company_name, event_type,
                  priority, source_role, fiscal_period, expected_at_ms, status, headline,
                  calendar_json, computed_at_ms, projection_version
                )
                VALUES (
                  %(row_id)s, %(expected_event_id)s, %(company_id)s, %(ticker)s,
                  %(company_name)s, %(event_type)s, %(priority)s, %(source_role)s,
                  %(fiscal_period)s, %(expected_at_ms)s, %(status)s, %(headline)s,
                  %(calendar_json)s, %(computed_at_ms)s, %(projection_version)s
                )
                ON CONFLICT (row_id) DO UPDATE SET
                  expected_event_id = EXCLUDED.expected_event_id,
                  company_id = EXCLUDED.company_id,
                  ticker = EXCLUDED.ticker,
                  company_name = EXCLUDED.company_name,
                  event_type = EXCLUDED.event_type,
                  priority = EXCLUDED.priority,
                  source_role = EXCLUDED.source_role,
                  fiscal_period = EXCLUDED.fiscal_period,
                  expected_at_ms = EXCLUDED.expected_at_ms,
                  status = EXCLUDED.status,
                  headline = EXCLUDED.headline,
                  calendar_json = EXCLUDED.calendar_json,
                  computed_at_ms = EXCLUDED.computed_at_ms,
                  projection_version = EXCLUDED.projection_version
                """,
                payload,
            )
        if commit:
            self.conn.commit()

    def replace_alert_candidates(
        self,
        *,
        company_event_ids: Sequence[str],
        rows: Sequence[Mapping[str, Any]],
        commit: bool = True,
    ) -> None:
        payloads = [_alert_candidate_payload(row) for row in rows]
        scoped_company_event_ids = [str(company_event_id) for company_event_id in company_event_ids]
        scoped_alert_ids = [payload["alert_candidate_id"] for payload in payloads]
        if not scoped_company_event_ids and not scoped_alert_ids:
            if commit:
                self.conn.commit()
            return
        self.conn.execute(
            """
            DELETE FROM equity_event_alert_candidates
             WHERE alert_candidate_id = ANY(%s::text[])
                OR company_event_id = ANY(%s::text[])
            """,
            (scoped_alert_ids, scoped_company_event_ids),
        )
        for payload in payloads:
            self.conn.execute(
                """
                INSERT INTO equity_event_alert_candidates (
                  alert_candidate_id, company_event_id, company_id, ticker, event_type, priority,
                  lifecycle_status, validation_status, alert_status, reason_codes_json,
                  payload_json, computed_at_ms, projection_version
                )
                VALUES (
                  %(alert_candidate_id)s, %(company_event_id)s, %(company_id)s, %(ticker)s,
                  %(event_type)s, %(priority)s, %(lifecycle_status)s, %(validation_status)s,
                  %(alert_status)s, %(reason_codes_json)s, %(payload_json)s,
                  %(computed_at_ms)s, %(projection_version)s
                )
                ON CONFLICT (alert_candidate_id) DO UPDATE SET
                  company_event_id = EXCLUDED.company_event_id,
                  company_id = EXCLUDED.company_id,
                  ticker = EXCLUDED.ticker,
                  event_type = EXCLUDED.event_type,
                  priority = EXCLUDED.priority,
                  lifecycle_status = EXCLUDED.lifecycle_status,
                  validation_status = EXCLUDED.validation_status,
                  alert_status = EXCLUDED.alert_status,
                  reason_codes_json = EXCLUDED.reason_codes_json,
                  payload_json = EXCLUDED.payload_json,
                  computed_at_ms = EXCLUDED.computed_at_ms,
                  projection_version = EXCLUDED.projection_version
                """,
                payload,
            )
        if commit:
            self.conn.commit()

    def replace_company_timeline_rows(
        self,
        *,
        rows: Sequence[Mapping[str, Any]],
        company_ids: Sequence[str] = (),
        company_event_ids: Sequence[str] = (),
        commit: bool = True,
    ) -> None:
        payloads = [_company_timeline_row_payload(row) for row in rows]
        scoped_company_ids = [str(company_id) for company_id in company_ids]
        scoped_company_event_ids = [str(company_event_id) for company_event_id in company_event_ids]
        scoped_row_ids = [payload["row_id"] for payload in payloads]
        if not scoped_company_ids and not scoped_company_event_ids and not scoped_row_ids:
            if commit:
                self.conn.commit()
            return
        self.conn.execute(
            """
            DELETE FROM equity_company_timeline_rows
             WHERE row_id = ANY(%s::text[])
                OR company_id = ANY(%s::text[])
                OR company_event_id = ANY(%s::text[])
            """,
            (scoped_row_ids, scoped_company_ids, scoped_company_event_ids),
        )
        for payload in payloads:
            self.conn.execute(
                """
                INSERT INTO equity_company_timeline_rows (
                  row_id, company_id, ticker, company_event_id, story_id, event_type, priority,
                  source_role, event_time_ms, lifecycle_status, headline, summary, payload_json,
                  computed_at_ms, projection_version
                )
                VALUES (
                  %(row_id)s, %(company_id)s, %(ticker)s, %(company_event_id)s, %(story_id)s,
                  %(event_type)s, %(priority)s, %(source_role)s, %(event_time_ms)s,
                  %(lifecycle_status)s, %(headline)s, %(summary)s, %(payload_json)s,
                  %(computed_at_ms)s, %(projection_version)s
                )
                ON CONFLICT (row_id) DO UPDATE SET
                  company_id = EXCLUDED.company_id,
                  ticker = EXCLUDED.ticker,
                  company_event_id = EXCLUDED.company_event_id,
                  story_id = EXCLUDED.story_id,
                  event_type = EXCLUDED.event_type,
                  priority = EXCLUDED.priority,
                  source_role = EXCLUDED.source_role,
                  event_time_ms = EXCLUDED.event_time_ms,
                  lifecycle_status = EXCLUDED.lifecycle_status,
                  headline = EXCLUDED.headline,
                  summary = EXCLUDED.summary,
                  payload_json = EXCLUDED.payload_json,
                  computed_at_ms = EXCLUDED.computed_at_ms,
                  projection_version = EXCLUDED.projection_version
                """,
                payload,
            )
        if commit:
            self.conn.commit()

    def _list_event_facts(self, company_event_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
              FROM equity_event_fact_candidates
             WHERE company_event_id = %s
             ORDER BY created_at_ms ASC, fact_candidate_id ASC
            """,
            (company_event_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _list_event_source_spans(self, company_event_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
              FROM equity_event_source_spans
             WHERE company_event_id = %s
             ORDER BY event_document_id ASC, span_start ASC, span_id ASC
            """,
            (company_event_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _list_brief_story_members(self, story_id: str | None) -> list[dict[str, Any]]:
        if story_id is None:
            return []
        rows = self.conn.execute(
            """
            SELECT events.company_event_id,
                   events.ticker,
                   events.event_type,
                   events.event_time_ms,
                   events.summary AS headline
              FROM equity_event_story_members AS members
              JOIN equity_company_events AS events
                ON events.company_event_id = members.company_event_id
             WHERE members.story_id = %s
             ORDER BY events.event_time_ms DESC, events.company_event_id ASC
            """,
            (story_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _list_event_documents(self, primary_document_id: str | None) -> list[dict[str, Any]]:
        if primary_document_id is None:
            return []
        rows = self.conn.execute(
            """
            SELECT documents.*,
                   provider.raw_payload_json
              FROM equity_event_documents AS documents
              LEFT JOIN equity_provider_documents AS provider
                ON provider.provider_document_id = documents.provider_document_id
             WHERE documents.event_document_id = %s
             ORDER BY documents.event_time_ms DESC, documents.event_document_id ASC
            """,
            (primary_document_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _update_source_extra_json(
        self,
        *,
        source_id: str,
        extra_json: Mapping[str, Any],
        now_ms: int,
        commit: bool = True,
    ) -> None:
        self.conn.execute(
            """
            UPDATE equity_event_sources
               SET extra_json = %s,
                   updated_at_ms = %s
             WHERE source_id = %s
            """,
            (Jsonb(dict(extra_json)), int(now_ms), source_id),
        )
        if commit:
            self.conn.commit()


def _page_row_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "row_id": str(row["row_id"]),
        "company_event_id": str(row["company_event_id"]),
        "story_id": row.get("story_id"),
        "company_id": str(row["company_id"]),
        "ticker": str(row["ticker"]),
        "company_name": str(row.get("company_name") or ""),
        "event_type": str(row["event_type"]),
        "priority": str(row["priority"]),
        "source_role": str(row["source_role"]),
        "latest_event_at_ms": int(row["latest_event_at_ms"]),
        "lifecycle_status": str(row["lifecycle_status"]),
        "headline": str(row["headline"]),
        "summary": str(row.get("summary") or ""),
        "facts_json": Jsonb(list(row.get("facts_json") or [])),
        "documents_json": Jsonb(list(row.get("documents_json") or [])),
        "brief_json": Jsonb(dict(row.get("brief_json") or {"status": "pending"})),
        "computed_at_ms": int(row["computed_at_ms"]),
        "projection_version": str(row["projection_version"]),
    }


def _calendar_row_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "row_id": str(row["row_id"]),
        "expected_event_id": row.get("expected_event_id"),
        "company_id": str(row["company_id"]),
        "ticker": str(row["ticker"]),
        "company_name": str(row.get("company_name") or ""),
        "event_type": str(row["event_type"]),
        "priority": str(row.get("priority") or "P2"),
        "source_role": str(row["source_role"]),
        "fiscal_period": row.get("fiscal_period"),
        "expected_at_ms": int(row["expected_at_ms"]),
        "status": str(row["status"]),
        "headline": str(row.get("headline") or ""),
        "calendar_json": Jsonb(dict(row.get("calendar_json") or {})),
        "computed_at_ms": int(row["computed_at_ms"]),
        "projection_version": str(row["projection_version"]),
    }


def _alert_candidate_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "alert_candidate_id": str(row["alert_candidate_id"]),
        "company_event_id": str(row["company_event_id"]),
        "company_id": str(row["company_id"]),
        "ticker": str(row["ticker"]),
        "event_type": str(row["event_type"]),
        "priority": str(row["priority"]),
        "lifecycle_status": str(row["lifecycle_status"]),
        "validation_status": str(row.get("validation_status") or "pending"),
        "alert_status": str(row.get("alert_status") or "pending"),
        "reason_codes_json": Jsonb(list(row.get("reason_codes_json") or [])),
        "payload_json": Jsonb(dict(row.get("payload_json") or {})),
        "computed_at_ms": int(row["computed_at_ms"]),
        "projection_version": str(row["projection_version"]),
    }


def _company_timeline_row_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "row_id": str(row["row_id"]),
        "company_id": str(row["company_id"]),
        "ticker": str(row["ticker"]),
        "company_event_id": row.get("company_event_id"),
        "story_id": row.get("story_id"),
        "event_type": str(row["event_type"]),
        "priority": str(row["priority"]),
        "source_role": str(row["source_role"]),
        "event_time_ms": int(row["event_time_ms"]),
        "lifecycle_status": str(row["lifecycle_status"]),
        "headline": str(row["headline"]),
        "summary": str(row.get("summary") or ""),
        "payload_json": Jsonb(dict(row.get("payload_json") or {})),
        "computed_at_ms": int(row["computed_at_ms"]),
        "projection_version": str(row["projection_version"]),
    }


def _story_payload(row: Mapping[str, Any]) -> dict[str, Any] | None:
    if not row.get("story_id"):
        return None
    return {
        "story_id": row.get("story_id"),
        "representative_headline": row.get("representative_headline"),
        "latest_seen_at_ms": row.get("story_latest_seen_at_ms"),
        "updated_at_ms": row.get("story_updated_at_ms"),
    }


def _brief_story_payload(row: Mapping[str, Any]) -> dict[str, Any] | None:
    if not row.get("story_id"):
        return None
    return {
        "story_id": row.get("story_id"),
        "event_count": row.get("event_count"),
        "representative_headline": row.get("representative_headline"),
        "updated_at_ms": row.get("story_updated_at_ms"),
    }


def _brief_payload(row: Mapping[str, Any]) -> dict[str, Any] | None:
    if not row.get("agent_run_id"):
        return None
    return {
        "agent_run_id": row.get("agent_run_id"),
        "status": row.get("brief_status"),
        "validation_status": row.get("brief_validation_status"),
        "brief_json": row.get("brief_json"),
        "input_hash": row.get("input_hash"),
        "artifact_version_hash": row.get("artifact_version_hash"),
        "prompt_version": row.get("prompt_version"),
        "schema_version": row.get("schema_version"),
        "validator_version": row.get("validator_version"),
        "computed_at_ms": row.get("brief_computed_at_ms"),
        "updated_at_ms": row.get("brief_updated_at_ms"),
    }


def _calendar_projection_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    observed_event = None
    if row.get("observed_company_event_id"):
        observed_event = {
            "company_event_id": row.get("observed_company_event_id"),
            "company_id": row.get("observed_company_id"),
            "ticker": row.get("observed_ticker"),
            "event_type": row.get("observed_event_type"),
            "priority": row.get("observed_priority"),
            "source_role": row.get("observed_source_role"),
            "fiscal_period": row.get("observed_fiscal_period"),
            "event_time_ms": row.get("observed_event_time_ms"),
            "discovered_at_ms": row.get("observed_discovered_at_ms"),
            "lifecycle_status": row.get("observed_lifecycle_status"),
            "validation_status": row.get("observed_validation_status"),
            "summary": row.get("observed_summary"),
            "updated_at_ms": row.get("observed_updated_at_ms"),
        }
    return {
        "expected_event": dict(row),
        "company": {
            "company_id": row.get("company_id"),
            "ticker": row.get("ticker"),
            "company_name": row.get("company_name") or "",
            "priority": row.get("company_priority") or "P2",
        },
        "observed_event": observed_event,
    }


def _span_payload(span: Any) -> dict[str, Any]:
    return {
        "span_id": _field(span, "span_id"),
        "company_event_id": _field(span, "company_event_id"),
        "event_document_id": _field(span, "event_document_id"),
        "source_id": _field(span, "source_id"),
        "span_type": _field(span, "span_type"),
        "section_key": _field(span, "section_key"),
        "span_start": int(_field(span, "span_start") or 0),
        "span_end": int(_field(span, "span_end") or 0),
        "evidence_quote": str(_field(span, "evidence_quote") or ""),
        "confidence": float(_field(span, "confidence") or 0.0),
        "created_at_ms": int(_field(span, "created_at_ms") or 0),
    }


def _fact_candidate_payload(candidate: Any) -> dict[str, Any]:
    return {
        "fact_candidate_id": _field(candidate, "fact_candidate_id"),
        "company_event_id": _field(candidate, "company_event_id"),
        "event_document_id": _field(candidate, "event_document_id"),
        "source_span_id": _field(candidate, "source_span_id"),
        "company_id": _field(candidate, "company_id"),
        "ticker": _field(candidate, "ticker"),
        "event_type": _field(candidate, "event_type"),
        "fact_type": _field(candidate, "fact_type"),
        "metric_name": _field(candidate, "metric_name"),
        "value_numeric": _field(candidate, "value_numeric"),
        "value_unit": _field(candidate, "value_unit"),
        "period": _field(candidate, "period"),
        "direction": _field(candidate, "direction"),
        "required_slots_json": Jsonb(dict(_field(candidate, "required_slots_json") or {})),
        "claim": str(_field(candidate, "claim") or ""),
        "evidence_quote": str(_field(candidate, "evidence_quote") or ""),
        "evidence_span_start": int(_field(candidate, "evidence_span_start") or 0),
        "evidence_span_end": int(_field(candidate, "evidence_span_end") or 0),
        "source_role": _field(candidate, "source_role"),
        "validation_status": _field(candidate, "validation_status"),
        "rejection_reasons_json": Jsonb(list(_field(candidate, "rejection_reasons_json") or [])),
        "extraction_method": _field(candidate, "extraction_method"),
        "policy_version": _field(candidate, "policy_version"),
        "created_at_ms": int(_field(candidate, "created_at_ms") or 0),
        "updated_at_ms": int(_field(candidate, "updated_at_ms") or 0),
    }


def _field(value: Any, key: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(key)
    return getattr(value, key, None)


def equity_event_page_cursor(row: Mapping[str, Any]) -> str:
    return f"{int(row['latest_event_at_ms'])}:{row['company_event_id']}"


def equity_event_timeline_cursor(row: Mapping[str, Any]) -> str:
    return f"{int(row['event_time_ms'])}:{row['row_id']}"


def _decode_cursor(cursor: str | None) -> tuple[int | None, str | None]:
    if not cursor:
        return None, None
    raw_time, separator, row_id = str(cursor).partition(":")
    if not separator or not raw_time.isdigit() or not row_id.strip():
        raise ValueError("invalid_cursor")
    return int(raw_time), row_id


def _window_ms(window: str | None) -> int | None:
    if not window:
        return None
    raw = str(window).strip().lower()
    if raw.endswith("ms"):
        return _required_positive_int(raw[:-2])
    if raw.endswith("m"):
        return _required_positive_int(raw[:-1]) * 60_000
    if raw.endswith("h"):
        return _required_positive_int(raw[:-1]) * 3_600_000
    if raw.endswith("d"):
        return _required_positive_int(raw[:-1]) * 86_400_000
    return _required_positive_int(raw)


def _required_positive_int(value: str) -> int:
    if not value.isdigit():
        raise ValueError("invalid_window")
    parsed = int(value)
    if parsed <= 0:
        raise ValueError("invalid_window")
    return parsed


def _headline_for_event(event: Mapping[str, Any]) -> str:
    return str(event.get("summary") or event.get("event_type") or event["company_event_id"])[:240]


def _json_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _compact_error(error: str | None) -> str | None:
    if not error:
        return None
    return str(error)[:2_000]
