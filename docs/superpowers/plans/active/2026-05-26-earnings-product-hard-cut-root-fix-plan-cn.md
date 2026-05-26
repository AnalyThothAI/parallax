# Earnings Product Hard-Cut Root Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `http://localhost:8765/earnings` product-usable by hard-cutting metadata-only SEC ingestion and rebuilding the chain around official evidence, honest freshness, fact extraction, brief readiness, real calendar state, and explicit frontend pagination.

**Architecture:** Keep the existing `equity_event_intel` bounded context and Kappa/CQRS shape. Add an evidence artifact layer between document metadata and processing, make brief/read-model readiness explicit, replace misleading summary metrics, and keep API/frontend read-only over persisted facts and read models.

**Tech Stack:** Python 3.13, PostgreSQL, Alembic, psycopg, FastAPI, Pydantic v2, httpx, pytest, React 19, TanStack Query, TypeScript, Vitest, Playwright, Vite.

---

**Status:** Draft, ready for execution
**Date:** 2026-05-26
**Owning spec:** `docs/superpowers/specs/active/2026-05-26-earnings-product-hard-cut-root-fix-cn.md`
**Recommended worktree:** `.worktrees/earnings-product-hard-cut/`
**Recommended branch:** `codex/earnings-product-hard-cut`

## Execution Shape

Ship in five testable slices:

1. **Contract lock:** add failing tests and architecture guards for the hard cut.
2. **Evidence layer:** add DB schema, SEC evidence hydration, provider protocol, and repository writes.
3. **Processing/readiness:** move facts/briefs/read models from raw payload text to evidence artifacts, with explicit reasons for missing work.
4. **API/frontend product contract:** replace misleading summary and feed behavior, add calendar config state and real Load More.
5. **Operational verification:** rebuild read models, verify live config paths, inspect `/earnings`, and run completion gates.

The first useful backend milestone is: a SEC filing metadata row creates an event document plus either a ready official evidence artifact or an explicit unavailable/failed artifact. The first useful product milestone is: `/earnings` can say source checked, no new material events, evidence missing, facts missing, brief pending, or product ready without hiding behind generic `pending`.

## Hard-Cut Rules

- Do not keep metadata-only brief generation.
- Do not let `raw_payload_json.title`, `raw_payload_json.description`, or `raw_payload_json.body_text` act as evidence.
- Do not keep `brief_pending_count` as the product pending metric.
- Do not sort default frontend feed priority-first.
- Do not call SEC, parse documents, or run LLMs in API handlers or React code.
- Do not print runtime secrets. For live diagnostics, report paths, booleans, counts, and redacted status only.

## File Map

### Backend Storage And Types

- Create `src/gmgn_twitter_intel/platform/db/alembic/versions/20260526_0099_equity_event_evidence_hard_cut.py`
- Modify `src/gmgn_twitter_intel/domains/equity_event_intel/types.py`
- Modify `src/gmgn_twitter_intel/domains/equity_event_intel/providers.py`
- Modify `src/gmgn_twitter_intel/domains/equity_event_intel/repositories/equity_event_repository.py`
- Modify `tests/integration/test_postgres_schema_runtime.py`
- Modify `tests/integration/test_equity_event_repository.py`
- Add `tests/architecture/test_equity_event_hard_cut_contracts.py`

### Evidence Hydration And Processing

- Create `src/gmgn_twitter_intel/domains/equity_event_intel/services/sec_evidence.py`
- Modify `src/gmgn_twitter_intel/integrations/equity_events/sec_edgar_client.py`
- Modify `src/gmgn_twitter_intel/app/runtime/provider_wiring/equity_events.py`
- Modify `src/gmgn_twitter_intel/domains/equity_event_intel/services/sec_submission_normalizer.py`
- Modify `src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_fetch_worker.py`
- Modify `src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_process_worker.py`
- Modify `src/gmgn_twitter_intel/domains/equity_event_intel/services/fact_candidates.py`
- Add `tests/unit/domains/equity_event_intel/test_sec_evidence.py`
- Modify `tests/unit/domains/equity_event_intel/test_sec_submission_normalizer.py`
- Modify `tests/unit/domains/equity_event_intel/test_fact_candidates.py`
- Modify `tests/integration/test_equity_event_workers.py`

### Briefs, Projections, API

- Modify `src/gmgn_twitter_intel/domains/equity_event_intel/services/brief_input.py`
- Modify `src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_brief_worker.py`
- Modify `src/gmgn_twitter_intel/domains/equity_event_intel/services/page_projection.py`
- Modify `src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_page_projection_worker.py`
- Modify `src/gmgn_twitter_intel/domains/equity_event_intel/queries/equity_event_query.py`
- Modify `src/gmgn_twitter_intel/app/surfaces/api/routes_equity_events.py`
- Modify `src/gmgn_twitter_intel/app/surfaces/api/schemas.py`
- Modify `tests/unit/test_api_equity_events_contract.py`
- Modify `tests/unit/domains/equity_event_intel/test_brief_input.py`
- Modify `tests/unit/domains/equity_event_intel/test_page_projection.py`

### Frontend

- Modify `web/src/features/equity-events/model/equityEventTypes.ts`
- Modify `web/src/features/equity-events/model/equityEventViewModel.ts`
- Modify `web/src/features/equity-events/api/useEquityEvents.ts`
- Modify `web/src/features/equity-events/ui/EquityEventsRoute.tsx`
- Modify `web/src/features/equity-events/ui/EquityEventFeed.tsx`
- Modify `web/src/features/equity-events/ui/EquityEventCalendar.tsx`
- Modify `web/src/features/equity-events/ui/EquityEventDetail.tsx`
- Modify `web/src/features/equity-events/ui/equityEvents.css`
- Modify `web/src/lib/api/client.ts`
- Modify `web/src/lib/types/openapi.ts`
- Modify `web/tests/routes/equity-events.route.test.tsx`
- Add `web/tests/unit/features/equity-events/equityEventViewModel.test.ts`

### Docs And Generated Artifacts

- Modify `docs/CONTRACTS.md`
- Modify `docs/WORKERS.md`
- Modify `src/gmgn_twitter_intel/domains/equity_event_intel/ARCHITECTURE.md`
- Regenerate `docs/generated/openapi.json`
- Regenerate `web/src/lib/types/openapi.ts`

## Pre-flight

- [ ] **Step 0.1: Create an isolated worktree**

  ```bash
  git worktree add .worktrees/earnings-product-hard-cut -b codex/earnings-product-hard-cut
  cd .worktrees/earnings-product-hard-cut
  git branch --show-current
  git status --short
  ```

  Expected: branch is `codex/earnings-product-hard-cut`; status is clean except user-owned files already present in that worktree.

- [ ] **Step 0.2: Confirm real runtime config paths before live checks**

  ```bash
  uv run gmgn-twitter-intel config
  ```

  Expected: `config_path` and `workers_config_path` point under `~/.gmgn-twitter-intel/`. Record only paths, booleans, and counts.

- [ ] **Step 0.3: Run baseline targeted gates**

  ```bash
  uv run pytest tests/unit/domains/equity_event_intel tests/unit/test_api_equity_events_contract.py -q
  uv run pytest tests/integration/test_equity_event_workers.py tests/integration/test_equity_event_repository.py -q
  uv run pytest tests/architecture/test_equity_event_intel_boundaries.py tests/architecture/test_worker_runtime_contracts.py -q
  cd web && npm run lint && npm run typecheck && npm test -- --run tests/routes/equity-events.route.test.tsx
  ```

  Expected: existing tests pass before edits. Record unrelated failures before changing code.

## Task 1: Lock Hard-Cut Contracts First

**Files:**
- Add: `tests/architecture/test_equity_event_hard_cut_contracts.py`
- Modify: `tests/unit/test_api_equity_events_contract.py`
- Add: `web/tests/unit/features/equity-events/equityEventViewModel.test.ts`
- Modify: `web/tests/routes/equity-events.route.test.tsx`

- [ ] **Step 1.1: Add backend architecture guards**

  Create `tests/architecture/test_equity_event_hard_cut_contracts.py` with these static checks:

  ```python
  from __future__ import annotations

  from pathlib import Path

  ROOT = Path(__file__).resolve().parents[2]
  SRC = ROOT / "src/gmgn_twitter_intel"


  def test_equity_facts_and_briefs_do_not_read_raw_payload_text_as_evidence() -> None:
      forbidden = [
          'raw_payload.get("title")',
          'raw_payload.get("description")',
          'raw_payload.get("body_text")',
          '"press_release_text"',
          '"body_text"',
      ]
      files = [
          SRC / "domains/equity_event_intel/services/fact_candidates.py",
          SRC / "domains/equity_event_intel/services/brief_input.py",
      ]
      combined = "\n".join(path.read_text() for path in files)
      for pattern in forbidden:
          assert pattern not in combined


  def test_equity_evidence_table_and_status_columns_exist_in_migration() -> None:
      migration = SRC / "platform/db/alembic/versions/20260526_0099_equity_event_evidence_hard_cut.py"
      text = migration.read_text()
      assert "CREATE TABLE IF NOT EXISTS equity_event_evidence_artifacts" in text
      assert "evidence_status" in text
      assert "brief_readiness_status" in text


  def test_equity_api_contract_removed_global_brief_pending_count() -> None:
      api_schema = SRC / "app/surfaces/api/schemas.py"
      client = ROOT / "web/src/lib/api/client.ts"
      view_model = ROOT / "web/src/features/equity-events/model/equityEventTypes.ts"
      combined = "\n".join(path.read_text() for path in [api_schema, client, view_model])
      assert "brief_pending_count" not in combined
  ```

- [ ] **Step 1.2: Add API contract tests for new summary/source/calendar semantics**

  In `tests/unit/test_api_equity_events_contract.py`, replace the old summary assertion with:

  ```python
  def test_equity_events_summary_returns_product_freshness_not_global_pending() -> None:
      equity_events = FakeEquityEventRepository()
      equity_events.summary_payload = {
          "p0_open_count": 1,
          "today_count": 2,
          "due_brief_queue_count": 3,
          "retryable_brief_failure_count": 4,
          "stale_brief_count": 5,
          "historical_backlog_count": 6,
          "latest_material_event_at_ms": 7_000,
          "latest_source_success_at_ms": 8_000,
          "latest_evidence_ready_at_ms": 9_000,
          "latest_projection_at_ms": 10_000,
          "calendar_configured": False,
      }
      app = _app(equity_events)

      with TestClient(app) as client:
          response = client.get("/api/equity-events/summary", headers={"Authorization": "Bearer secret"})

      assert response.status_code == 200
      data = response.json()["data"]
      assert data["due_brief_queue_count"] == 3
      assert data["historical_backlog_count"] == 6
      assert data["latest_source_success_at_ms"] == 8_000
      assert "brief_pending_count" not in data
  ```

  Add a calendar test that asserts the endpoint can return no rows with explicit config state:

  ```python
  def test_equity_events_calendar_returns_not_configured_state() -> None:
      equity_events = FakeEquityEventRepository()
      equity_events.calendar_payload = {
          "items": [],
          "calendar_configured": False,
          "empty_reason": "calendar_source_not_configured",
      }
      app = _app(equity_events)

      with TestClient(app) as client:
          response = client.get("/api/equity-events/calendar", headers={"Authorization": "Bearer secret"})

      assert response.status_code == 200
      assert response.json()["data"] == {
          "items": [],
          "calendar_configured": False,
          "empty_reason": "calendar_source_not_configured",
      }
  ```

- [ ] **Step 1.3: Add frontend tests for time order and Load More**

  Create `web/tests/unit/features/equity-events/equityEventViewModel.test.ts`:

  ```ts
  import { describe, expect, it } from "vitest";

  import { buildEquityEventFeedModel } from "../../../../src/features/equity-events/model/equityEventViewModel";
  import type { EquityEventRow } from "../../../../src/features/equity-events/model/equityEventTypes";

  const row = (id: string, priority: string, latest: number): EquityEventRow =>
    ({
      company_event_id: id,
      row_id: id,
      ticker: id.toUpperCase(),
      company_name: id,
      priority,
      latest_event_at_ms: latest,
      brief: { status: "pending_due" },
      facts: [],
      documents: [],
      evidence_status: "ready",
      evidence_reason: null,
    }) as EquityEventRow;

  describe("buildEquityEventFeedModel", () => {
    it("preserves backend time cursor order by default", () => {
      const rows = [row("new-p2", "P2", 3000), row("old-p0", "P0", 1000)];
      expect(buildEquityEventFeedModel(rows).rows.map((item) => item.company_event_id)).toEqual([
        "new-p2",
        "old-p0",
      ]);
    });

    it("only uses priority grouping when explicitly requested", () => {
      const rows = [row("new-p2", "P2", 3000), row("old-p0", "P0", 1000)];
      expect(
        buildEquityEventFeedModel(rows, { ordering: "priority" }).rows.map((item) => item.company_event_id),
      ).toEqual(["old-p0", "new-p2"]);
    });
  });
  ```

  Extend `web/tests/routes/equity-events.route.test.tsx` with an assertion that a `next_cursor` renders a clickable Load More action and clicking it navigates or fetches with the cursor.

- [ ] **Step 1.4: Run contract tests and keep expected failures**

  ```bash
  uv run pytest tests/architecture/test_equity_event_hard_cut_contracts.py tests/unit/test_api_equity_events_contract.py -q
  cd web && npm test -- --run tests/unit/features/equity-events/equityEventViewModel.test.ts tests/routes/equity-events.route.test.tsx
  ```

  Expected: new hard-cut tests fail before implementation because schema/API/frontend still use old semantics.

## Task 2: Add Evidence And Readiness Schema

**Files:**
- Add: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260526_0099_equity_event_evidence_hard_cut.py`
- Modify: `tests/integration/test_postgres_schema_runtime.py`
- Modify: `tests/architecture/test_worker_runtime_contracts.py`

- [ ] **Step 2.1: Create the migration**

  Add `20260526_0099_equity_event_evidence_hard_cut.py` with `down_revision = "20260525_0098"`. The upgrade must:

  - Create `equity_event_evidence_artifacts`.
  - Create `equity_event_brief_states`.
  - Add evidence/fact extraction columns to `equity_event_documents`.
  - Add evidence/readiness columns to `equity_company_events`.
  - Add source/product freshness columns to `equity_event_sources`.
  - Backfill old rows into explicit hard-cut states.

  Required DDL shape:

  ```sql
  CREATE TABLE IF NOT EXISTS equity_event_evidence_artifacts (
    evidence_artifact_id TEXT PRIMARY KEY,
    event_document_id TEXT NOT NULL REFERENCES equity_event_documents(event_document_id) ON DELETE CASCADE,
    provider_document_id TEXT REFERENCES equity_provider_documents(provider_document_id) ON DELETE SET NULL,
    source_id TEXT REFERENCES equity_event_sources(source_id) ON DELETE SET NULL,
    artifact_kind TEXT NOT NULL,
    extraction_status TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL DEFAULT '',
    content_text TEXT NOT NULL DEFAULT '',
    content_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    excerpt_text TEXT NOT NULL DEFAULT '',
    failure_reason TEXT,
    fetched_at_ms BIGINT NOT NULL DEFAULT 0,
    parsed_at_ms BIGINT NOT NULL DEFAULT 0,
    created_at_ms BIGINT NOT NULL,
    updated_at_ms BIGINT NOT NULL,
    CHECK (artifact_kind IN ('html_text', 'xbrl', 'companyfacts', 'table', 'exhibit_text', 'transcript_text', 'ir_text')),
    CHECK (extraction_status IN ('ready', 'unavailable', 'failed'))
  );

  CREATE INDEX IF NOT EXISTS idx_equity_event_evidence_artifacts_document
    ON equity_event_evidence_artifacts(event_document_id, extraction_status, artifact_kind);

  CREATE TABLE IF NOT EXISTS equity_event_brief_states (
    company_event_id TEXT PRIMARY KEY REFERENCES equity_company_events(company_event_id) ON DELETE CASCADE,
    brief_readiness_status TEXT NOT NULL,
    reason_code TEXT NOT NULL DEFAULT '',
    reason_detail TEXT NOT NULL DEFAULT '',
    input_hash TEXT NOT NULL DEFAULT '',
    source_updated_at_ms BIGINT NOT NULL DEFAULT 0,
    next_retry_after_ms BIGINT,
    updated_at_ms BIGINT NOT NULL,
    CHECK (
      brief_readiness_status IN (
        'pending_due',
        'in_progress',
        'ready',
        'insufficient',
        'failed_retryable',
        'failed_terminal',
        'stale',
        'historical_unscheduled',
        'disabled'
      )
    )
  );
  ```

  Required added columns:

  ```sql
  ALTER TABLE equity_event_documents
    ADD COLUMN IF NOT EXISTS evidence_status TEXT NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS evidence_reason TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS evidence_ready_at_ms BIGINT,
    ADD COLUMN IF NOT EXISTS fact_extraction_status TEXT NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS fact_extraction_reason TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS fact_extracted_at_ms BIGINT;

  ALTER TABLE equity_company_events
    ADD COLUMN IF NOT EXISTS evidence_status TEXT NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS evidence_reason TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS brief_readiness_status TEXT NOT NULL DEFAULT 'pending_due',
    ADD COLUMN IF NOT EXISTS brief_readiness_reason TEXT NOT NULL DEFAULT '';

  ALTER TABLE equity_event_sources
    ADD COLUMN IF NOT EXISTS last_material_document_at_ms BIGINT,
    ADD COLUMN IF NOT EXISTS last_evidence_ready_at_ms BIGINT,
    ADD COLUMN IF NOT EXISTS last_product_projection_at_ms BIGINT,
    ADD COLUMN IF NOT EXISTS last_no_new_data_at_ms BIGINT,
    ADD COLUMN IF NOT EXISTS last_actionable_error TEXT;
  ```

  Backfill rule:

  ```sql
  UPDATE equity_event_documents
     SET evidence_status = 'unavailable',
         evidence_reason = 'historical_metadata_only',
         fact_extraction_status = 'no_evidence',
         fact_extraction_reason = 'historical_metadata_only'
   WHERE evidence_status = 'pending';

  INSERT INTO equity_event_brief_states (
    company_event_id,
    brief_readiness_status,
    reason_code,
    reason_detail,
    source_updated_at_ms,
    updated_at_ms
  )
  SELECT company_event_id,
         'historical_unscheduled',
         'historical_metadata_only',
         'Existing row predates evidence hydration hard cut.',
         updated_at_ms,
         updated_at_ms
    FROM equity_company_events
  ON CONFLICT (company_event_id) DO NOTHING;
  ```

- [ ] **Step 2.2: Update schema runtime tests**

  In `tests/integration/test_postgres_schema_runtime.py`, assert:

  - `equity_event_evidence_artifacts` exists.
  - `equity_event_brief_states` exists.
  - indexes include `idx_equity_event_evidence_artifacts_document`.
  - `equity_event_documents` has `evidence_status`, `evidence_reason`, `fact_extraction_status`.
  - `equity_event_sources` has `last_material_document_at_ms`, `last_evidence_ready_at_ms`, `last_product_projection_at_ms`.

- [ ] **Step 2.3: Update writer allowlists**

  In `tests/architecture/test_worker_runtime_contracts.py`, add:

  - `equity_event_evidence_artifacts`: repository plus `equity_event_fetch_worker.py` / `equity_event_process_worker.py` as runtime writers.
  - `equity_event_brief_states`: repository plus `equity_event_brief_worker.py` / `equity_event_page_projection_worker.py` as runtime writers only if projection updates source-visible state through repository.

  Keep API route files out of write allowlists.

- [ ] **Step 2.4: Run migration/schema tests**

  ```bash
  uv run pytest tests/integration/test_postgres_schema_runtime.py tests/architecture/test_worker_runtime_contracts.py -q
  ```

  Expected: schema and one-writer contracts pass.

## Task 3: Add SEC Evidence Hydration

**Files:**
- Create: `src/gmgn_twitter_intel/domains/equity_event_intel/services/sec_evidence.py`
- Modify: `src/gmgn_twitter_intel/integrations/equity_events/sec_edgar_client.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/provider_wiring/equity_events.py`
- Modify: `src/gmgn_twitter_intel/domains/equity_event_intel/providers.py`
- Modify: `src/gmgn_twitter_intel/domains/equity_event_intel/types.py`
- Add: `tests/unit/domains/equity_event_intel/test_sec_evidence.py`
- Modify: `tests/unit/test_equity_event_provider_wiring.py`

- [ ] **Step 3.1: Add evidence dataclasses and provider protocol**

  In `types.py`, add:

  - `EvidenceArtifactKind`
  - `EvidenceExtractionStatus`
  - `NormalizedEquityEvidenceArtifact`
  - `EquityEvidenceHydrationResult`

  Required statuses:

  ```python
  EvidenceExtractionStatus = Literal["ready", "unavailable", "failed"]
  EvidenceArtifactKind = Literal[
      "html_text",
      "xbrl",
      "companyfacts",
      "table",
      "exhibit_text",
      "transcript_text",
      "ir_text",
  ]
  ```

  In `providers.py`, extend `EquityEventDocumentProvider`:

  ```python
  def hydrate_document_evidence(
      self,
      *,
      source: dict[str, Any],
      document: NormalizedEquityDocument,
  ) -> EquityEvidenceHydrationResult: ...
  ```

- [ ] **Step 3.2: Add deterministic HTML extraction**

  Create `services/sec_evidence.py` with:

  - `extract_sec_html_text(html: str) -> str`
  - `build_ready_html_text_artifact(...) -> NormalizedEquityEvidenceArtifact`
  - `build_unavailable_evidence_artifact(...) -> NormalizedEquityEvidenceArtifact`
  - `build_failed_evidence_artifact(...) -> NormalizedEquityEvidenceArtifact`

  Unit tests in `test_sec_evidence.py`:

  ```python
  def test_extract_sec_html_text_removes_script_style_and_normalizes_whitespace() -> None:
      html = "<html><style>.x{}</style><script>alert(1)</script><body><p>Total revenue was $1.2 billion.</p></body></html>"
      assert extract_sec_html_text(html) == "Total revenue was $1.2 billion."


  def test_build_ready_html_text_artifact_hashes_content() -> None:
      artifact = build_ready_html_text_artifact(
          event_document_id="doc-1",
          provider_document_id="provider-1",
          source_id="sec:AAPL",
          source_url="https://www.sec.gov/Archives/edgar/data/1/2/a.htm",
          text="Total revenue was $1.2 billion.",
          fetched_at_ms=1000,
          parsed_at_ms=1001,
      )
      assert artifact.artifact_kind == "html_text"
      assert artifact.extraction_status == "ready"
      assert artifact.content_hash.startswith("sha256:")
      assert artifact.excerpt_text == "Total revenue was $1.2 billion."
  ```

- [ ] **Step 3.3: Extend SEC client**

  In `sec_edgar_client.py`, add:

  - `fetch_filing_document(document_url: str) -> SecEdgarDocumentFetchResult`
  - `fetch_companyfacts(cik: str) -> SecEdgarCompanyFactsFetchResult`
  - URL guard that only allows `https://www.sec.gov/Archives/edgar/data/` for filing document HTML.

  Tests use `httpx.MockTransport` and assert:

  - 200 HTML returns text bytes/string and headers.
  - 404 raises or returns a failed result classified as `sec_http_404`.
  - non-SEC archive URL raises `ValueError("SEC filing document URL must be under sec.gov Archives")`.
  - companyfacts uses `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json`.

- [ ] **Step 3.4: Wire hydration provider**

  In `provider_wiring/equity_events.py`, implement `CompositeEquityEventDocumentProvider.hydrate_document_evidence`.

  Required behavior:

  - For `document.document_type == "sec_filing"`, call `SecEdgarClient.fetch_filing_document(document.document_url)`.
  - Build a `html_text` artifact when extracted text is non-empty.
  - Build `unavailable` with reason `empty_sec_document_text` when HTML fetch succeeds but extracted text is empty.
  - Build `failed` with reason `sec_timeout`, `sec_transport_error`, `sec_http_<status>`, or `sec_invalid_url`.
  - Fetch companyfacts as a second artifact for SEC documents with CIK. Persist ready JSON when response is valid, unavailable with reason `companyfacts_unavailable` for 404, failed for transport/timeout.
  - Never copy SEC submissions `title`, `description`, or `body_text` into evidence.

- [ ] **Step 3.5: Run provider tests**

  ```bash
  uv run pytest tests/unit/domains/equity_event_intel/test_sec_evidence.py tests/unit/test_equity_event_provider_wiring.py -q
  ```

  Expected: all provider/evidence tests pass without network.

## Task 4: Hard-Cut SEC Normalization And Repository Writes

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/equity_event_intel/services/sec_submission_normalizer.py`
- Modify: `src/gmgn_twitter_intel/domains/equity_event_intel/repositories/equity_event_repository.py`
- Modify: `tests/unit/domains/equity_event_intel/test_sec_submission_normalizer.py`
- Modify: `tests/integration/test_equity_event_repository.py`

- [ ] **Step 4.1: Remove metadata text from normalized raw payload**

  In `sec_submission_normalizer.py`, remove `title`, `description`, and `body_text` from `raw_payload`. The normalized payload should contain only metadata:

  - `company_cik`
  - `company_name`
  - `accession_number`
  - `form_type`
  - `acceptance_datetime`
  - `filing_date`
  - `report_date`
  - `primary_document`

  Update tests to assert those forbidden keys are absent.

- [ ] **Step 4.2: Add repository methods for evidence artifacts**

  Add methods:

  - `replace_evidence_artifacts(event_document_id, artifacts, now_ms, commit=True)`
  - `list_event_evidence_artifacts(event_document_id)`
  - `list_event_documents_for_processing(limit)` replacing `list_unprocessed_event_documents` usage with evidence-aware rows.
  - `mark_event_document_evidence_status(event_document_id, evidence_status, evidence_reason, evidence_ready_at_ms, now_ms, commit=True)`
  - `mark_event_document_fact_extraction_status(event_document_id, fact_extraction_status, fact_extraction_reason, fact_extracted_at_ms, now_ms, commit=True)`
  - `upsert_brief_state(company_event_id, brief_readiness_status, reason_code, reason_detail, input_hash, source_updated_at_ms, next_retry_after_ms, updated_at_ms, commit=True)`

  Repository tests:

  - Ready evidence artifacts persist and replace old artifacts for the same event document.
  - A document with `evidence_status='ready'` is returned by the processing query with evidence rows.
  - A document with `evidence_status='unavailable'` is returned with reason so processing can create an explicit product row.
  - A document with `evidence_status='pending'` is not returned for processing.

- [ ] **Step 4.3: Add source product freshness repository helpers**

  Add:

  - `update_source_material_freshness(source_id, material_document_at_ms=None, evidence_ready_at_ms=None, product_projection_at_ms=None, no_new_data_at_ms=None, actionable_error=None, now_ms, commit=True)`
  - `calendar_configured()` returning true when at least one enabled expected event source/config row exists.

  Source status tests assert `list_source_status()` includes:

  - `last_success_at_ms`
  - `last_material_document_at_ms`
  - `last_evidence_ready_at_ms`
  - `last_product_projection_at_ms`
  - `last_no_new_data_at_ms`
  - `last_actionable_error`

- [ ] **Step 4.4: Run repository tests**

  ```bash
  uv run pytest tests/unit/domains/equity_event_intel/test_sec_submission_normalizer.py tests/integration/test_equity_event_repository.py -q
  ```

  Expected: normalization and repository tests pass.

## Task 5: Hydrate Evidence In The Fetch Worker

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_fetch_worker.py`
- Modify: `tests/integration/test_equity_event_workers.py`

- [ ] **Step 5.1: Persist metadata and evidence in one source fetch pass**

  In `_persist_documents`, after `upsert_event_document`, call provider hydration for each normalized document:

  - Persist `equity_event_evidence_artifacts`.
  - Mark document `evidence_status='ready'` when at least one artifact is ready.
  - Mark document `evidence_status='unavailable'` when only unavailable artifacts exist.
  - Mark document `evidence_status='failed'` when only failed artifacts exist.
  - Set `evidence_reason` to the first non-empty artifact failure/unavailable reason.
  - Update source `last_material_document_at_ms` when an event document is inserted or materially updated.
  - Update source `last_evidence_ready_at_ms` when a ready artifact is persisted.
  - Update source `last_no_new_data_at_ms` for 304 or duplicate-only fetches.

- [ ] **Step 5.2: Notify only on material work**

  Keep `notify_equity_event_document_written` for inserted/updated event documents with a terminal evidence status (`ready`, `unavailable`, `failed`). Do not notify process worker for duplicate-only source checks.

- [ ] **Step 5.3: Add worker tests**

  In `tests/integration/test_equity_event_workers.py`, add:

  - `test_fetch_worker_hydrates_sec_document_text_and_marks_evidence_ready`
  - `test_fetch_worker_marks_evidence_unavailable_for_empty_sec_document`
  - `test_fetch_worker_records_no_new_data_for_duplicate_only_fetch`

  The fake provider should return normalized SEC submissions metadata and hydration artifacts without network.

- [ ] **Step 5.4: Run fetch worker tests**

  ```bash
  uv run pytest tests/integration/test_equity_event_workers.py::test_fetch_worker_hydrates_sec_document_text_and_marks_evidence_ready tests/integration/test_equity_event_workers.py::test_fetch_worker_marks_evidence_unavailable_for_empty_sec_document tests/integration/test_equity_event_workers.py::test_fetch_worker_records_no_new_data_for_duplicate_only_fetch -q
  ```

  Expected: documents move out of `pending` evidence state during fetch.

## Task 6: Process Facts From Evidence Artifacts Only

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/equity_event_intel/services/fact_candidates.py`
- Modify: `src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_process_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/equity_event_intel/repositories/equity_event_repository.py`
- Modify: `tests/unit/domains/equity_event_intel/test_fact_candidates.py`
- Modify: `tests/integration/test_equity_event_workers.py`

- [ ] **Step 6.1: Replace `document_text(document)` with evidence text aggregation**

  In `fact_candidates.py`, replace `document_text(document)` with:

  - `evidence_text(artifacts)` that concatenates ready `html_text`, `exhibit_text`, `transcript_text`, and `ir_text` artifacts.
  - `companyfacts_metric_candidates(artifact)` that extracts simple `Revenues`, `NetIncomeLoss`, and `EarningsPerShareDiluted` facts from ready `companyfacts` JSON when period/context can be identified.

  Unit tests:

  - ready HTML text produces source span and revenue/EPS candidates.
  - raw payload title/body_text produces no text because raw payload is no longer accepted.
  - ready companyfacts JSON can produce accepted or attention candidates with evidence quote `companyfacts:<concept>`.
  - empty ready text returns `no_extractable_facts` reason.

- [ ] **Step 6.2: Update process worker**

  `EquityEventProcessWorker` must:

  - Claim documents whose `evidence_status` is `ready`, `unavailable`, or `failed`.
  - For `ready`, build spans/facts from evidence artifacts.
  - For `unavailable` or `failed`, create/refresh the company event with evidence status and reason, mark fact extraction `no_evidence`, and enqueue page/timeline targets so the UI can show the reason.
  - For `ready` with zero facts, mark fact extraction `no_extractable_facts`.
  - Never treat zero facts as silent success.

- [ ] **Step 6.3: Propagate evidence status to company events**

  Update `upsert_company_event` calls and repository SQL so `equity_company_events.evidence_status`, `evidence_reason`, `brief_readiness_status`, and `brief_readiness_reason` are maintained.

- [ ] **Step 6.4: Run processing tests**

  ```bash
  uv run pytest tests/unit/domains/equity_event_intel/test_fact_candidates.py -q
  uv run pytest tests/integration/test_equity_event_workers.py::test_process_worker_extracts_facts_from_evidence_artifacts tests/integration/test_equity_event_workers.py::test_process_worker_projects_explicit_no_evidence_reason -q
  ```

  Expected: facts/spans come only from evidence artifacts; no-evidence and no-facts states are explicit.

## Task 7: Make Brief Readiness Honest

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/equity_event_intel/services/brief_input.py`
- Modify: `src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_brief_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/equity_event_intel/types.py`
- Modify: `tests/unit/domains/equity_event_intel/test_brief_input.py`
- Modify: `tests/unit/domains/equity_event_intel/test_brief_validation.py`
- Modify: `tests/integration/test_equity_event_workers.py`

- [ ] **Step 7.1: Stop brief packet construction on empty evidence**

  Update `build_equity_event_brief_input_packet` so `source_documents` text excerpts come from evidence artifact excerpts supplied by repository rows. It must not read `raw_payload_json`.

  Add a helper result type:

  ```python
  class EquityEventBriefInputReadiness(BaseModel):
      status: Literal["ready", "insufficient"]
      reason_code: str = ""
      reason_detail: str = ""
      packet: EquityEventBriefInputPacket | None = None
  ```

  A row with no evidence refs returns `status="insufficient"` and `reason_code="missing_evidence_packet"`.

- [ ] **Step 7.2: Classify brief worker outcomes**

  In `equity_event_brief_worker.py`, write `equity_event_brief_states` for every claimed target:

  - no evidence packet: `insufficient`, reason `missing_evidence_packet`, no normal LLM call.
  - capacity denied or circuit open: `failed_retryable`, reason `backpressure_capacity_denied` or `backpressure_circuit_open`.
  - timeout/provider transport: `failed_retryable`.
  - schema/domain validation failure: `failed_terminal`.
  - successful cited brief: `ready`.
  - source updated after current brief: `stale`.
  - old migration rows outside due window: `historical_unscheduled`.

- [ ] **Step 7.3: Keep agent brief rows as audit output, not readiness truth**

  Keep `equity_event_agent_runs` and `equity_event_agent_briefs` for actual run audit. Page projection reads `equity_event_brief_states` for user-facing status and reads `equity_event_agent_briefs` only when readiness is `ready`, `insufficient`, or failed with a persisted audit payload.

- [ ] **Step 7.4: Run brief tests**

  ```bash
  uv run pytest tests/unit/domains/equity_event_intel/test_brief_input.py tests/unit/domains/equity_event_intel/test_brief_validation.py -q
  uv run pytest tests/integration/test_equity_event_workers.py::test_brief_worker_skips_llm_without_evidence_packet tests/integration/test_equity_event_workers.py::test_brief_worker_marks_backpressure_retryable -q
  ```

  Expected: empty evidence never triggers normal LLM execution, and retryable/terminal statuses are distinguishable.

## Task 8: Rebuild Page, Calendar, Summary, And Source Status Contracts

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/equity_event_intel/services/page_projection.py`
- Modify: `src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_page_projection_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/equity_event_intel/repositories/equity_event_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/equity_event_intel/queries/equity_event_query.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/routes_equity_events.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/schemas.py`
- Modify: `tests/unit/domains/equity_event_intel/test_page_projection.py`
- Modify: `tests/unit/test_api_equity_events_contract.py`
- Modify: `tests/integration/test_equity_event_workers.py`

- [ ] **Step 8.1: Add readiness/freshness to page rows**

  `build_equity_event_page_row` must include:

  - `evidence_status`
  - `evidence_reason`
  - `fact_extraction_status`
  - `fact_extraction_reason`
  - `brief_json.status` from `equity_event_brief_states.brief_readiness_status`
  - `brief_json.reason_code`
  - `brief_json.reason_detail`
  - `freshness_json` with source/material/evidence/facts/brief/projection timestamps.

- [ ] **Step 8.2: Add calendar configured state**

  `list_calendar_rows` and `EquityEventQuery.list_calendar` must return:

  ```python
  {
      "items": rows,
      "calendar_configured": bool,
      "empty_reason": "calendar_source_not_configured" | "no_calendar_rows_in_window" | "",
  }
  ```

  `build_equity_event_calendar_row` should keep `expected`, `matched`, and `missed`, and include configured source/confidence/session inside `calendar_json`.

- [ ] **Step 8.3: Replace summary payload**

  Repository `summary()` must return:

  - `p0_open_count`
  - `today_count`
  - `due_brief_queue_count`
  - `retryable_brief_failure_count`
  - `stale_brief_count`
  - `historical_backlog_count`
  - `latest_material_event_at_ms`
  - `latest_source_success_at_ms`
  - `latest_evidence_ready_at_ms`
  - `latest_projection_at_ms`
  - `calendar_configured`

  Remove `brief_pending_count` from API schemas, typed client, frontend model, docs, and tests.

- [ ] **Step 8.4: Expand source status payload**

  `source_status()` must return, per source:

  - `source_id`
  - `ticker`
  - `enabled`
  - `provider_type`
  - `last_success_at_ms`
  - `last_material_document_at_ms`
  - `last_evidence_ready_at_ms`
  - `last_product_projection_at_ms`
  - `last_no_new_data_at_ms`
  - `last_error`
  - `last_actionable_error`
  - `product_status`: `fresh`, `source_checked_no_new_data`, `evidence_pending`, `evidence_failed`, `stale_projection`, or `unknown`

- [ ] **Step 8.5: Run API/projection tests**

  ```bash
  uv run pytest tests/unit/domains/equity_event_intel/test_page_projection.py tests/unit/test_api_equity_events_contract.py -q
  uv run pytest tests/integration/test_equity_event_workers.py::test_page_projection_includes_evidence_and_brief_reasons tests/integration/test_equity_event_workers.py::test_calendar_projection_reports_not_configured_state -q
  ```

  Expected: API and projection tests pass with no `brief_pending_count`.

## Task 9: Make `/earnings` Match Product Semantics

**Files:**
- Modify: `web/src/features/equity-events/model/equityEventTypes.ts`
- Modify: `web/src/features/equity-events/model/equityEventViewModel.ts`
- Modify: `web/src/features/equity-events/api/useEquityEvents.ts`
- Modify: `web/src/features/equity-events/ui/EquityEventsRoute.tsx`
- Modify: `web/src/features/equity-events/ui/EquityEventFeed.tsx`
- Modify: `web/src/features/equity-events/ui/EquityEventCalendar.tsx`
- Modify: `web/src/features/equity-events/ui/EquityEventDetail.tsx`
- Modify: `web/src/features/equity-events/ui/equityEvents.css`
- Modify: `web/src/lib/api/client.ts`
- Modify: `web/tests/routes/equity-events.route.test.tsx`
- Modify: `web/tests/unit/features/equity-events/equityEventViewModel.test.ts`

- [ ] **Step 9.1: Update TypeScript types and API normalizers**

  Add fields to `EquityEventRow`:

  - `evidence_status`
  - `evidence_reason`
  - `fact_extraction_status`
  - `fact_extraction_reason`
  - `freshness`

  Replace `EquityEventSummary.brief_pending_count` with:

  - `due_brief_queue_count`
  - `retryable_brief_failure_count`
  - `stale_brief_count`
  - `historical_backlog_count`
  - `latest_material_event_at_ms`
  - `latest_source_success_at_ms`
  - `latest_evidence_ready_at_ms`
  - `latest_projection_at_ms`
  - `calendar_configured`

- [ ] **Step 9.2: Preserve backend order by default**

  Change `buildEquityEventFeedModel(rows)` to keep `rows` in incoming order. Add an optional `{ ordering: "time" | "priority" }` argument, defaulting to `"time"`.

  Summary labels should count:

  - `ready`
  - `pending_due`
  - `retryable`
  - `insufficient`
  - `historical`

- [ ] **Step 9.3: Add real Load More**

  In `EquityEventsRoute`, add an `onLoadMore` callback that navigates to the same route with `cursor=nextCursor`.

  In `EquityEventFeed`, replace the `next page` text with a `<button type="button">Load more</button>` when `nextCursor` exists. The button must have an accessible label and stable dimensions in CSS.

- [ ] **Step 9.4: Make missing reasons visible**

  Row rendering must show:

  - evidence status and reason.
  - facts count plus `fact_extraction_reason` when count is zero.
  - brief status and reason code.
  - source freshness vs product freshness in summary metrics.

  Calendar rendering must show `calendar_source_not_configured` as an explicit empty state.

- [ ] **Step 9.5: Keep CSS within feature namespace**

  Use only `.equity-event-*` selectors in `equityEvents.css`. Do not restyle shared `PageState`, notification, shell, or `.ods-*` internals. Keep the file under the CSS side-effect budget.

- [ ] **Step 9.6: Run frontend gates**

  ```bash
  cd web && npm run lint
  cd web && npm run typecheck
  cd web && npm test -- --run tests/unit/features/equity-events/equityEventViewModel.test.ts tests/routes/equity-events.route.test.tsx
  cd web && npm run build
  ```

  Expected: frontend tests and build pass.

## Task 10: Regenerate Contracts And Docs

**Files:**
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/WORKERS.md`
- Modify: `src/gmgn_twitter_intel/domains/equity_event_intel/ARCHITECTURE.md`
- Modify: `docs/generated/openapi.json`
- Modify: `web/src/lib/types/openapi.ts`

- [ ] **Step 10.1: Update docs**

  Document:

  - Evidence hydration stage.
  - New `equity_event_evidence_artifacts` table.
  - New `equity_event_brief_states` table.
  - Summary/source status fields.
  - Calendar not-configured state.
  - Hard-cut removal of metadata-only brief path.

- [ ] **Step 10.2: Regenerate OpenAPI and frontend types**

  Run the repo's OpenAPI generation command used in existing workflows. If the command is not obvious from scripts, inspect `scripts/` and `docs/generated/` before running. The final generated artifacts must update:

  ```bash
  docs/generated/openapi.json
  web/src/lib/types/openapi.ts
  ```

  Then run:

  ```bash
  cd web && npm run generate:types
  ```

  Expected: generated TypeScript types no longer include `brief_pending_count`.

- [ ] **Step 10.3: Run contract drift checks**

  ```bash
  uv run pytest tests/contract/test_openapi_drift.py -q
  cd web && npm run typecheck
  ```

  Expected: OpenAPI drift and TypeScript types pass.

## Task 11: Product Rebuild And Live Verification

**Files:**
- No new source files expected.
- Update implementation notes in the plan or a verification artifact after commands run.

- [ ] **Step 11.1: Run targeted backend gates**

  ```bash
  uv run pytest tests/unit/domains/equity_event_intel -q
  uv run pytest tests/unit/test_api_equity_events_contract.py -q
  uv run pytest tests/integration/test_equity_event_repository.py tests/integration/test_equity_event_workers.py tests/integration/test_postgres_schema_runtime.py -q
  uv run pytest tests/architecture/test_equity_event_intel_boundaries.py tests/architecture/test_equity_event_hard_cut_contracts.py tests/architecture/test_worker_runtime_contracts.py -q
  ```

  Expected: all targeted backend gates pass.

- [ ] **Step 11.2: Run full gates**

  ```bash
  make check-all
  ```

  Expected: exit code 0.

- [ ] **Step 11.3: Confirm runtime config without exposing secrets**

  ```bash
  uv run gmgn-twitter-intel config
  uv run gmgn-twitter-intel db health
  ```

  Expected:

  - config paths under `~/.gmgn-twitter-intel/`.
  - equity event enabled.
  - SEC User-Agent configured.
  - company count reported.
  - expected event count reported.
  - DB health OK.

- [ ] **Step 11.4: Rebuild dirty read models for a bounded recent window**

  After migration and worker deployment, enqueue recent read-model targets:

  ```bash
  uv run gmgn-twitter-intel ops enqueue-projection-dirty-targets --domain equity --projection page --since-hours 168
  uv run gmgn-twitter-intel ops enqueue-projection-dirty-targets --domain equity --projection calendar --since-hours 168
  uv run gmgn-twitter-intel ops enqueue-projection-dirty-targets --domain equity --projection brief_input --since-hours 168
  ```

  Expected: commands report target counts. If the CLI does not support one of these projection names after the hard cut, update the CLI in the same change so the command names match the projection names used by workers.

- [ ] **Step 11.5: Browser verify `/earnings`**

  Open `http://localhost:8765/earnings` and verify:

  - Summary distinguishes source success from latest material event.
  - No global `brief_pending_count` label appears.
  - Rows remain in backend time order on default feed.
  - Rows with `facts=0` show `evidence_reason` or `fact_extraction_reason`.
  - `Load more` appears when API returns `next_cursor` and changes the cursor.
  - Calendar empty state says `calendar source not configured` when expected events are absent.
  - Browser console has no new errors.

- [ ] **Step 11.6: Live data sanity check**

  Query API through the running app with frontend auth token from the existing browser session or bootstrap flow, without printing the token:

  - `/api/equity-events/summary`
  - `/api/equity-events?limit=5`
  - `/api/equity-events/calendar`
  - `/api/equity-events/sources/status`

  Expected:

  - summary includes `latest_source_success_at_ms` and `latest_material_event_at_ms`.
  - summary includes `due_brief_queue_count`, `retryable_brief_failure_count`, and `historical_backlog_count`.
  - rows include `evidence_status`.
  - `docs > 0, facts = 0` rows include machine-readable reason.
  - sources status includes `product_status`.

## Commit Checkpoints

Commit after each green slice:

1. `test: lock earnings hard-cut contracts`
2. `feat: add equity event evidence schema`
3. `feat: hydrate SEC evidence artifacts`
4. `feat: process equity facts from evidence`
5. `feat: make equity brief readiness explicit`
6. `feat: refresh earnings API and frontend contract`
7. `docs: document earnings hard-cut runtime`

Each commit should include only files from that slice and passing targeted tests for that slice.

## Spec Coverage Map

- AC1 to AC3: Tasks 4, 5, 8, 11.
- AC4 to AC7: Tasks 2, 3, 4, 5, 6.
- AC8 to AC10: Task 7.
- AC11 to AC13: Tasks 8, 11.
- AC14 to AC18: Tasks 8, 9.
- AC19 to AC22: Tasks 1, 2, 6, 7, 8, 10, 11.

## Stop Conditions

Pause and ask before continuing when:

- SEC returns a response pattern that cannot be represented as `ready`, `unavailable`, or `failed`.
- Runtime config lacks SEC User-Agent or company CIKs and live verification cannot exercise evidence hydration.
- The current DB migration head is not `20260525_0098`.
- Existing user changes overlap the same files and change equity event semantics.
- Adding a paid calendar provider or credential becomes necessary.

## Done Signal

The implementation is done when:

- `make check-all` passes.
- Targeted backend/frontend gates in Task 11 pass.
- `/earnings` clearly separates source freshness, product freshness, evidence status, fact extraction status, and brief readiness.
- No runtime path treats SEC submissions metadata text as evidence.
- No public frontend/API contract exposes `brief_pending_count`.
- Calendar not configured is explicit instead of silent empty.
- Live rows with missing facts have machine-readable reasons.
