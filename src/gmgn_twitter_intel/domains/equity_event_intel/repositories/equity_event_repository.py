from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from psycopg.types.json import Jsonb

_DEFAULT_SOURCE_CLAIM_LEASE_MS = 60_000


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

    def reconcile_expected_events(
        self,
        *,
        expected_events: Sequence[Mapping[str, Any]],
        now_ms: int,
        commit: bool = True,
    ) -> list[dict[str, Any]]:
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

    def claim_due_sources(
        self,
        *,
        now_ms: int,
        limit: int,
        claim_lease_ms: int = _DEFAULT_SOURCE_CLAIM_LEASE_MS,
        commit: bool = True,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            WITH due AS (
              SELECT source_id
                FROM equity_event_sources
               WHERE enabled = true
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
              status = 'expected',
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
              discovered_at_ms = EXCLUDED.discovered_at_ms,
              content_hash = EXCLUDED.content_hash,
              lifecycle_status = CASE
                WHEN equity_event_documents.content_hash = EXCLUDED.content_hash
                THEN equity_event_documents.lifecycle_status
                ELSE 'raw'
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
        now_ms: int,
        commit: bool = True,
    ) -> dict[str, Any]:
        row = self.conn.execute(
            """
            INSERT INTO equity_company_events (
              company_event_id, company_id, ticker, primary_document_id, event_type, priority,
              source_role, fiscal_period, event_time_ms, discovered_at_ms, lifecycle_status,
              created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                int(now_ms),
                int(now_ms),
            ),
        ).fetchone()
        if commit:
            self.conn.commit()
        return dict(row)

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

    def list_event_page_rows(self, *, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
              FROM equity_event_page_rows
             ORDER BY latest_event_at_ms DESC, company_event_id ASC
             LIMIT %s
            """,
            (max(0, int(limit)),),
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
