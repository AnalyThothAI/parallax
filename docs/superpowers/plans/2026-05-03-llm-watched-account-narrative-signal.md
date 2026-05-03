# LLM Watched Account Narrative Signal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add production LLM enrichment for watched-account events so the system can answer what monitored accounts just said, which tokens they mentioned, and which narratives are emerging.

**Architecture:** Keep the ingest hot path deterministic and fast: GMGN public WS -> Collector -> SQLite Evidence -> Deterministic Entity -> Token Signal. Add a durable asynchronous warm path: Enrichment Jobs -> LLM watched-account enrichment -> Narrative Signal -> WebSocket / CLI / API. Do not introduce embeddings in this phase and do not preserve keyword-flow/account-keyword compatibility as a product surface.

**Tech Stack:** Python 3.13, FastAPI WebSocket, SQLite WAL/FTS5, stdlib HTTP for OpenAI-compatible chat completions, pytest, ruff.

---

## File Structure

- `src/gmgn_twitter_intel/storage/sqlite_schema.py`: add enrichment and narrative tables; remove keyword table creation from active schema.
- `src/gmgn_twitter_intel/storage/enrichment_repository.py`: own enrichment jobs, model runs, event enrichments, token candidates, event narratives, narrative alerts, narrative windows.
- `src/gmgn_twitter_intel/pipeline/llm_enrichment.py`: prompt construction, LLM JSON result schema, evidence-bound validation, label normalization.
- `src/gmgn_twitter_intel/pipeline/llm_client.py`: OpenAI-compatible HTTP client plus protocol used by tests.
- `src/gmgn_twitter_intel/pipeline/enrichment_worker.py`: claim pending watched-account jobs, call LLM outside the DB lock, persist narrative signals, publish updates.
- `src/gmgn_twitter_intel/pipeline/ingest_service.py`: enqueue watched-account enrichment jobs in the same event transaction.
- `src/gmgn_twitter_intel/api/app.py`: wire repository, write lock, optional enrichment worker, readiness counters.
- `src/gmgn_twitter_intel/api/ws.py`: include completed enrichment/narratives in replay payloads and route enrichment updates.
- `src/gmgn_twitter_intel/retrieval/narrative_service.py`: query account narratives and narrative flow.
- `src/gmgn_twitter_intel/cli.py`: add `account-narratives`, `narrative-flow`, `enrichment-jobs`; remove keyword-flow as a supported command.
- `src/gmgn_twitter_intel/settings.py`: add explicit LLM/enrichment settings; remove `WATCH_KEYWORDS` from the core config surface.
- `README.md`, `.env.example`, `AGENTS.md`, `CLAUDE.md`: document the final architecture and new commands.

## Tasks

### Task 1: Write failing storage and ingest tests

**Files:**
- Create: `tests/test_enrichment_repository.py`
- Modify: `tests/test_sqlite_schema.py`
- Modify: `tests/test_sqlite_repositories.py`

- [ ] Add tests proving migration creates enrichment tables, watched ingest enqueues one job, non-watched ingest does not enqueue jobs, duplicate ingest does not duplicate jobs, and no `keyword_windows` product table is created for new databases.
- [ ] Run `uv run python -m pytest tests/test_enrichment_repository.py tests/test_sqlite_schema.py tests/test_sqlite_repositories.py -q`.
- [ ] Expected result before implementation: failures for missing tables/repository/job enqueue behavior.

### Task 2: Implement enrichment schema and repository

**Files:**
- Modify: `src/gmgn_twitter_intel/storage/sqlite_schema.py`
- Create: `src/gmgn_twitter_intel/storage/enrichment_repository.py`
- Modify: `src/gmgn_twitter_intel/storage/__init__.py`

- [ ] Add tables: `enrichment_jobs`, `model_runs`, `event_enrichments`, `event_token_candidates`, `event_narratives`, `narrative_windows`, `account_narrative_alerts`.
- [ ] Add repository methods: enqueue watched event job, claim next job, complete job with model output, fail job with retry/dead state, query account narratives, query narrative flow, list jobs, fetch enrichment for event.
- [ ] Run the Task 1 tests and make them pass.

### Task 3: Write failing LLM validation tests

**Files:**
- Create: `tests/test_llm_enrichment.py`

- [ ] Test that valid evidence-bound JSON creates summary, token candidates, and narratives.
- [ ] Test that token/narrative items whose evidence is not present in the event text are dropped.
- [ ] Test that labels are normalized to snake_case and low-confidence items are dropped.
- [ ] Run `uv run python -m pytest tests/test_llm_enrichment.py -q`.
- [ ] Expected result before implementation: import/function failures.

### Task 4: Implement LLM enrichment parser and client

**Files:**
- Create: `src/gmgn_twitter_intel/pipeline/llm_enrichment.py`
- Create: `src/gmgn_twitter_intel/pipeline/llm_client.py`
- Modify: `src/gmgn_twitter_intel/settings.py`

- [ ] Build an evidence-bound prompt from event text and deterministic entities.
- [ ] Parse strict JSON from the model response.
- [ ] Validate evidence by substring containment against event text plus referenced text.
- [ ] Store only high-confidence token candidates and narratives.
- [ ] Implement `OpenAIChatEnrichmentClient` using `OPENAI_API_KEY`, `OPENAI_MODEL`, and `OPENAI_BASE_URL`.
- [ ] Run the Task 3 tests and make them pass.

### Task 5: Write failing worker/runtime tests

**Files:**
- Create: `tests/test_enrichment_worker.py`
- Modify: `tests/test_api_health.py`
- Modify: `tests/test_api_websocket.py`

- [ ] Test a fake LLM client processes one watched-account job into `event_enrichments`, `event_narratives`, `account_narrative_alerts`, and `narrative_windows`.
- [ ] Test readiness exposes enrichment job counters and whether LLM is configured.
- [ ] Test WebSocket replay includes completed enrichment and narrative alerts.
- [ ] Run `uv run python -m pytest tests/test_enrichment_worker.py tests/test_api_health.py tests/test_api_websocket.py -q`.
- [ ] Expected result before implementation: missing worker/runtime fields.

### Task 6: Implement worker, runtime wiring, and WebSocket enrichment updates

**Files:**
- Create: `src/gmgn_twitter_intel/pipeline/enrichment_worker.py`
- Modify: `src/gmgn_twitter_intel/pipeline/ingest_service.py`
- Modify: `src/gmgn_twitter_intel/api/app.py`
- Modify: `src/gmgn_twitter_intel/api/ws.py`

- [ ] Pass a shared `RLock` to ingest and the enrichment worker for all writes on the shared SQLite connection.
- [ ] Enqueue `watched_event_enrichment` jobs only for inserted watched events with text.
- [ ] Start the enrichment worker only when LLM config is complete.
- [ ] Persist worker results and publish `enrichment_update` messages.
- [ ] Include enrichment/narratives in replay payloads.
- [ ] Run Task 5 tests and make them pass.

### Task 7: Replace keyword product surface with narrative product surface

**Files:**
- Create: `src/gmgn_twitter_intel/retrieval/narrative_service.py`
- Modify: `src/gmgn_twitter_intel/cli.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_project_structure.py`
- Modify: `README.md`, `.env.example`, `AGENTS.md`, `CLAUDE.md`

- [ ] Remove `keyword-flow` and `WATCH_KEYWORDS` as supported product behavior.
- [ ] Add `account-narratives --window --limit --handles`.
- [ ] Add `narrative-flow --window --limit`.
- [ ] Add `enrichment-jobs --status --limit`.
- [ ] Update docs to show the final pipeline.
- [ ] Run `uv run python -m pytest tests/test_cli.py tests/test_project_structure.py -q`.

### Task 8: Final verification and container smoke

**Files:**
- All touched files.

- [ ] Run `uv run python -m pytest -q`.
- [ ] Run `uv run ruff check .`.
- [ ] Run `uv run python -m compileall src tests`.
- [ ] Run `docker compose up -d --build app`.
- [ ] Run `/readyz`, `token-flow`, `account-narratives`, `narrative-flow`, and `enrichment-jobs` smoke checks.
- [ ] Commit with `feat: add watched account narrative enrichment`.

## Acceptance Criteria

- GMGN ingest remains independent of LLM availability.
- Watched account token alerts remain immediate and deterministic.
- Watched account events enqueue durable enrichment jobs.
- LLM output is rejected unless it is evidence-bound.
- Narrative alerts and narrative windows are materialized and queryable.
- WebSocket replay/live update surfaces enrichment.
- CLI can answer account narratives and narrative flow.
- No embeddings are introduced.
- Keyword-flow and WATCH_KEYWORDS are not retained as core product compatibility paths.
