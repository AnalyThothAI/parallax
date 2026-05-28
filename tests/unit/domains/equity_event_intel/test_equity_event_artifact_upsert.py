from __future__ import annotations

from pathlib import Path
from typing import Any

from gmgn_twitter_intel.domains.equity_event_intel.repositories.equity_event_repository import (
    EquityEventRepository,
)
from tests.architecture.test_token_equity_workerspace_root_fix_contract import _function_source

NOW_MS = 1_765_900_000_000
ROOT = Path(__file__).resolve().parents[4]


def test_upsert_evidence_artifacts_skips_unchanged_payload() -> None:
    conn = _ArtifactConnection()
    repository = EquityEventRepository(conn)
    artifact = _artifact(
        evidence_artifact_id="artifact-same",
        event_document_id="event-doc-artifact-skip",
        content_text="Revenue grew 17%.",
    )

    first = repository.upsert_evidence_artifacts(
        event_document_id="event-doc-artifact-skip",
        artifacts=[artifact],
        now_ms=NOW_MS + 1,
        commit=False,
    )
    second = repository.upsert_evidence_artifacts(
        event_document_id="event-doc-artifact-skip",
        artifacts=[artifact],
        now_ms=NOW_MS + 2,
        commit=False,
    )
    row = conn.artifacts["artifact-same"]

    assert first == {"inserted": 1, "updated": 0, "deleted": 0}
    assert second == {"inserted": 0, "updated": 0, "deleted": 0}
    assert row["content_text"] == "Revenue grew 17%."
    assert row["created_at_ms"] == NOW_MS + 1
    assert row["updated_at_ms"] == NOW_MS + 1
    assert row["artifact_payload_hash"]


def test_upsert_evidence_artifacts_deletes_stale_after_success() -> None:
    conn = _ArtifactConnection()
    repository = EquityEventRepository(conn)
    first = _artifact(evidence_artifact_id="artifact-keep", event_document_id="event-doc-artifact-stale")
    stale = _artifact(evidence_artifact_id="artifact-stale", event_document_id="event-doc-artifact-stale")
    repository.upsert_evidence_artifacts(
        event_document_id="event-doc-artifact-stale",
        artifacts=[first, stale],
        now_ms=NOW_MS + 1,
        commit=False,
    )

    result = repository.upsert_evidence_artifacts(
        event_document_id="event-doc-artifact-stale",
        artifacts=[first],
        now_ms=NOW_MS + 2,
        commit=False,
    )

    assert result == {"inserted": 0, "updated": 0, "deleted": 1}
    assert sorted(conn.artifacts) == ["artifact-keep"]
    assert "artifact-stale" in conn.deleted_artifact_ids
    delete_all_sql = "DELETE FROM equity_event_evidence_artifacts WHERE event_document_id = %s"
    assert all(delete_all_sql not in sql for sql in conn.sql)


def test_upsert_provider_document_skips_unchanged_raw_payload() -> None:
    conn = _ProviderDocumentConnection()
    repository = EquityEventRepository(conn)
    first = repository.upsert_provider_document(
        provider_document_id="provider-doc-original",
        source_id="sec:MSFT",
        fetch_run_id="fetch-run-1",
        provider_document_key="0000789019-26-000001:10-Q",
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        cik="0000789019",
        document_url="https://sec.example/msft-10q.htm",
        payload_hash="provider-hash",
        raw_payload_json={"version": 1},
        fetched_at_ms=NOW_MS + 1,
        commit=False,
    )
    second = repository.upsert_provider_document(
        provider_document_id="provider-doc-duplicate-caller-id",
        source_id="sec:MSFT",
        fetch_run_id="fetch-run-2",
        provider_document_key="0000789019-26-000001:10-Q",
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        cik="0000789019",
        document_url="https://sec.example/msft-10q.htm",
        payload_hash="provider-hash",
        raw_payload_json={"version": 2},
        fetched_at_ms=NOW_MS + 2,
        commit=False,
    )
    stored = conn.provider_documents[("sec:MSFT", "0000789019-26-000001:10-Q")]

    assert first["status"] == "inserted"
    assert second["status"] == "duplicate"
    assert second["provider_document_id"] == "provider-doc-original"
    assert second["raw_payload_json"] == {"version": 1}
    assert second["fetched_at_ms"] == NOW_MS + 1
    assert stored["provider_document_id"] == "provider-doc-original"
    assert stored["raw_payload_json"] == {"version": 1}
    assert stored["fetched_at_ms"] == NOW_MS + 1
    assert "SELECT *" not in "\n".join(conn.sql)


def test_process_and_page_document_loaders_do_not_select_raw_payload() -> None:
    repository_path = ROOT / "src/gmgn_twitter_intel/domains/equity_event_intel/repositories/equity_event_repository.py"
    repo_text = repository_path.read_text(encoding="utf-8")
    process_loader = _function_source(
        repo_text,
        "load_process_packets_for_claims",
        context="equity_event_repository",
    )
    page_loader = _function_source(repo_text, "_list_event_documents", context="equity_event_repository")

    assert "raw_payload_json" not in process_loader
    assert "raw_payload_json" not in page_loader


def _artifact(
    *,
    evidence_artifact_id: str,
    event_document_id: str,
    content_text: str = "Revenue grew.",
) -> dict[str, object]:
    return {
        "evidence_artifact_id": evidence_artifact_id,
        "event_document_id": event_document_id,
        "provider_document_id": "provider-doc-artifact-upsert",
        "source_id": "sec:MSFT",
        "artifact_kind": "html_text",
        "extraction_status": "ready",
        "source_url": "https://sec.example/msft-10q.htm",
        "content_hash": "content-hash",
        "content_text": content_text,
        "content_json": {"ignored_large_raw": {"companyfacts": ["must", "not", "drive", "hash"]}},
        "excerpt_text": content_text,
        "fetched_at_ms": NOW_MS,
        "parsed_at_ms": NOW_MS,
    }


class _Cursor:
    def __init__(self, row: dict[str, Any] | None = None, rows: list[dict[str, Any]] | None = None, rowcount: int = 0):
        self._row = row
        self._rows = [] if rows is None else rows
        self.rowcount = rowcount

    def fetchone(self) -> dict[str, Any] | None:
        return self._row

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class _ProviderDocumentConnection:
    def __init__(self) -> None:
        self.sql: list[str] = []
        self.provider_documents: dict[tuple[str, str], dict[str, Any]] = {}
        self.commits = 0

    def execute(self, sql: str, params: Any = None) -> _Cursor:
        self.sql.append(sql)
        if "FROM equity_provider_documents" in sql and "WHERE source_id = %s" in sql:
            source_id, provider_document_key = params
            return _Cursor(row=self.provider_documents.get((source_id, provider_document_key)))
        if "INSERT INTO equity_provider_documents" in sql:
            payload = _provider_payload(params)
            key = (payload["source_id"], payload["provider_document_key"])
            existing = self.provider_documents.get(key)
            if existing is None:
                self.provider_documents[key] = payload
                return _Cursor(row=payload | {"status": "inserted"}, rowcount=1)
            if "payload_hash IS DISTINCT FROM EXCLUDED.payload_hash" in sql:
                changed_scalars = any(
                    existing[field] != payload[field]
                    for field in ("company_id", "ticker", "cik", "document_url", "payload_hash")
                )
                if not changed_scalars:
                    return _Cursor(row=None, rowcount=0)
                updated = existing | {
                    "fetch_run_id": payload["fetch_run_id"],
                    "company_id": payload["company_id"],
                    "ticker": payload["ticker"],
                    "cik": payload["cik"],
                    "document_url": payload["document_url"],
                    "payload_hash": payload["payload_hash"],
                }
                if existing["payload_hash"] != payload["payload_hash"]:
                    updated["raw_payload_json"] = payload["raw_payload_json"]
                    updated["fetched_at_ms"] = payload["fetched_at_ms"]
                self.provider_documents[key] = updated
                return _Cursor(row=updated | {"status": "updated"}, rowcount=1)
            updated = existing | {
                "fetch_run_id": payload["fetch_run_id"],
                "company_id": payload["company_id"],
                "ticker": payload["ticker"],
                "cik": payload["cik"],
                "document_url": payload["document_url"],
                "payload_hash": payload["payload_hash"],
                "raw_payload_json": payload["raw_payload_json"],
                "fetched_at_ms": payload["fetched_at_ms"],
            }
            self.provider_documents[key] = updated
            return _Cursor(row=updated, rowcount=1)
        if "FROM equity_provider_documents" in sql and "LIMIT 1" in sql:
            if isinstance(params, dict):
                key = (params["source_id"], params["provider_document_key"])
            else:
                key = (params[0], params[1])
            row = self.provider_documents.get(key)
            return _Cursor(row=None if row is None else row | {"status": "duplicate"})
        raise AssertionError(sql)

    def commit(self) -> None:
        self.commits += 1


class _ArtifactConnection:
    def __init__(self) -> None:
        self.sql: list[str] = []
        self.artifacts: dict[str, dict[str, Any]] = {}
        self.deleted_artifact_ids: list[str] = []
        self.commits = 0

    def execute(self, sql: str, params: Any = None) -> _Cursor:
        self.sql.append(sql)
        if "INSERT INTO equity_event_evidence_artifacts" in sql:
            payload = dict(params)
            artifact_id = payload["evidence_artifact_id"]
            existing = self.artifacts.get(artifact_id)
            if existing is None:
                self.artifacts[artifact_id] = payload
                return _Cursor(row={"status": "inserted"}, rowcount=1)
            if existing["artifact_payload_hash"] == payload["artifact_payload_hash"]:
                return _Cursor(row=None, rowcount=0)
            self.artifacts[artifact_id] = existing | {
                key: value for key, value in payload.items() if key != "created_at_ms"
            }
            return _Cursor(row={"status": "updated"}, rowcount=1)
        if "DELETE FROM equity_event_evidence_artifacts" in sql:
            event_document_id = _param(params, "event_document_id", 0)
            incoming_ids = set(_param(params, "incoming_ids", 1) or [])
            deleted = [
                artifact_id
                for artifact_id, artifact in self.artifacts.items()
                if artifact["event_document_id"] == event_document_id and artifact_id not in incoming_ids
            ]
            for artifact_id in deleted:
                self.artifacts.pop(artifact_id)
            self.deleted_artifact_ids.extend(deleted)
            return _Cursor(rowcount=len(deleted))
        raise AssertionError(sql)

    def commit(self) -> None:
        self.commits += 1


def _provider_payload(params: Any) -> dict[str, Any]:
    if isinstance(params, dict):
        raw_payload = params["raw_payload_json"]
        return {
            key: (raw_payload.obj if key == "raw_payload_json" and hasattr(raw_payload, "obj") else value)
            for key, value in params.items()
        }
    raw_payload = params[9]
    return {
        "provider_document_id": params[0],
        "source_id": params[1],
        "fetch_run_id": params[2],
        "provider_document_key": params[3],
        "company_id": params[4],
        "ticker": params[5],
        "cik": params[6],
        "document_url": params[7],
        "payload_hash": params[8],
        "raw_payload_json": raw_payload.obj if hasattr(raw_payload, "obj") else raw_payload,
        "fetched_at_ms": params[10],
    }


def _param(params: Any, name: str, index: int) -> Any:
    if isinstance(params, dict):
        return params[name]
    return params[index]
