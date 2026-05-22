from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from psycopg.types.json import Jsonb


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
        return dict(row)

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
        return dict(row)

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
        commit: bool = True,
    ) -> None:
        payloads = [_page_row_payload(row) for row in rows]
        if not payloads:
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
                [payload["row_id"] for payload in payloads],
                [payload["company_event_id"] for payload in payloads],
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
