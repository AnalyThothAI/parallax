# News Agent Context Tools Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hard-cut News item brief from packet-only analysis to a News-owned context snapshot with bounded DB-backed read tools, without changing the shared agent workflow kernel.

**Architecture:** Keep `NewsItemBriefWorker` as the only runtime writer for `news_item_agent_runs` and `news_item_agent_briefs`. Add a deterministic `NewsItemBriefContextCompiler` and `NewsAgentReadToolFacade` that read only News-owned PostgreSQL facts/read models, hash tool envelopes into `NewsItemBriefInputPacket` v2, and pass the enriched packet through the existing `AgentStageSpec`. Prompt/schema/validator versions hard-cut together; old v1 current briefs are treated as stale/pending, never translated.

**Tech Stack:** Python 3.12, Pydantic v2 models, psycopg-style repository SQL, existing Parallax worker/session patterns, `uv run pytest`, `uv run ruff`, `make test-architecture`.

---

**Status**: Draft  
**Date**: 2026-06-03  
**Owning spec**: `docs/superpowers/specs/active/2026-06-03-news-agent-context-tools-hard-cut-cn.md`  
**Worktree**: `.worktrees/news-agent-context-tools-spec/`  
**Branch**: `codex/news-agent-context-tools-spec`

## Scope Check

The spec covers one subsystem: the News item brief agent. It explicitly excludes shared `AgentExecutionGateway` tool-calling, restored `context_items`, story projections, and cross-domain market/Token Radar context. This plan implements P0 and P1 News-owned read tools, schema/prompt hard cut, worker integration, and serving guards for old current briefs.

## Pre-flight

- [ ] Confirm spec approval from the user in the thread.
- [ ] Confirm worktree and branch:

  ```bash
  cd /Users/qinghuan/Documents/code/parallax/.worktrees/news-agent-context-tools-spec
  git branch --show-current
  git status --short
  ```

  Expected branch: `codex/news-agent-context-tools-spec`. Expected status before implementation: only this plan file is uncommitted if the plan has not yet been committed.

- [ ] Run targeted baseline lint:

  ```bash
  uv run ruff check \
    src/parallax/domains/news_intel \
    tests/unit/domains/news_intel \
    tests/integration/domains/news_intel \
    tests/unit/integrations/model_execution/test_news_item_brief_agent_client.py \
    tests/architecture/test_news_intel_boundaries.py
  ```

  Expected: exit 0.

- [ ] Run targeted baseline tests:

  ```bash
  uv run pytest \
    tests/unit/domains/news_intel/test_news_item_brief_types.py \
    tests/unit/domains/news_intel/test_news_item_brief_input.py \
    tests/unit/domains/news_intel/test_news_item_brief_stage.py \
    tests/unit/domains/news_intel/test_news_item_brief_validation.py \
    tests/unit/domains/news_intel/test_news_item_brief_worker.py \
    tests/unit/integrations/model_execution/test_news_item_brief_agent_client.py \
    tests/integration/domains/news_intel/test_news_item_agent_brief_repository.py \
    tests/integration/domains/news_intel/test_news_repository.py \
    tests/unit/domains/news_intel/test_news_page_projection.py \
    tests/architecture/test_news_intel_boundaries.py
  ```

  Expected: exit 0. If any baseline test fails before edits, record the exact failure in the verification artifact before implementing.

## File-level Edits

### Domain constants and types

- Modify `src/parallax/domains/news_intel/_constants.py:5-8`.
  - Bump:
    - `NEWS_ITEM_BRIEF_PROMPT_VERSION = "news-item-brief-v4"`
    - `NEWS_ITEM_BRIEF_SCHEMA_VERSION = "news_item_brief_v2"`
    - `NEWS_ITEM_BRIEF_VALIDATOR_VERSION = "news_item_brief_validator_v4"`
    - `NEWS_ITEM_BRIEF_GUARDRAIL_VERSION = "news_item_brief_guardrails_v4"`

- Modify `src/parallax/domains/news_intel/types/news_item_brief.py:18-236`.
  - Add `NewsItemBriefNoveltyStatus`, `NewsItemBriefConfirmationState`, `NewsContextToolResult`, and `NewsItemBriefContextBudget`.
  - Add required v2 fields to `NewsItemBriefPayload`.
  - Add `context_tool_results`, `context_budget`, and `context_snapshot_hash` to `NewsItemBriefInputPacket`.
  - Keep Pydantic `extra="forbid"` for hard-cut schema enforcement.

### Context compiler and tool facade

- Create `src/parallax/domains/news_intel/services/news_item_brief_context_tools.py`.
  - Owns tool envelope construction, hashing, deterministic row truncation, and `NewsAgentReadToolFacade`.
  - Does not import provider clients, runtime workers, Token Radar, Pulse, or market modules.

- Create `src/parallax/domains/news_intel/services/news_item_brief_context.py`.
  - Owns `NewsItemBriefContextCompiler`.
  - Receives a `NewsRepository`-like object and a `now_ms`.
  - Calls the read tool facade after eligibility passes and before packet freshness checks.

### Repository read methods

- Modify `src/parallax/domains/news_intel/repositories/news_repository.py`.
  - Add read-only, bounded methods near existing item detail/source status methods:
    - `get_news_observation_history(news_item_id: str, limit: int = 25) -> dict[str, Any]`
    - `get_source_quality_context_for_item(news_item_id: str) -> dict[str, Any]`
    - `list_news_item_agent_run_history(news_item_id: str, limit: int = 5) -> list[dict[str, Any]]`
    - `find_similar_news_items(news_item_id: str, window_ms: int, limit: int, now_ms: int | None = None) -> list[dict[str, Any]]`
  - These methods are SELECT-only and must not return `provider_item_id`, `source_item_key`, `raw_payload_json`, `feed_url`, `sync_cursor_json`, or credential-bearing JSON.

### Packet builder and stage metadata

- Modify `src/parallax/domains/news_intel/services/news_item_brief_input.py:28-90`.
  - Add `context_tool_results` and `context_budget` arguments.
  - Include tool refs in `evidence_refs`.
  - Include `context_snapshot_hash` in `packet_id` and material input hash.

- Modify `src/parallax/domains/news_intel/services/news_item_brief_stage.py:24-44`.
  - Add context snapshot metadata to `trace_metadata`:
    - `context_snapshot_hash`
    - `context_tool_names`
    - `context_truncated`

### Worker integration

- Modify `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py`.
  - Import `NewsItemBriefContextCompiler`.
  - Add `_compile_context()` that opens a repository session, runs compiler in `asyncio.to_thread`, and returns a context snapshot dict.
  - In `run_once()`, compile context after `news_item_agent_brief_eligibility()` passes and before `_packet_from_candidate()`.
  - Update `_packet_from_candidate()` to accept a context snapshot.
  - Update `_failed_brief()` to include v2 fields.
  - Preserve no DB session during `provider.request_audit()` and `provider.brief_item()`.

### Prompt, validation, projection, and public detail

- Modify `src/parallax/domains/news_intel/prompts/news_item_brief.md`.
  - Remove the line saying the agent does not use tools or packet-external knowledge.
  - State that only packet fields and precomputed `context_tool_results` may be used.
  - Add novelty/confirmation/source consensus/retrieval notes guidance.

- Modify `src/parallax/domains/news_intel/services/news_item_brief_validation.py`.
  - Validate v2 strict schema.
  - Keep unexpected action audit rejection.
  - Extend asset grounding to include bounded tool evidence rows.

- Modify `src/parallax/domains/news_intel/services/news_page_projection.py:175-203`.
  - Include compact v2 fields in `agent_brief`.
  - Return pending/stale when current brief schema version is not `NEWS_ITEM_BRIEF_SCHEMA_VERSION`; do not translate v1 to v2.

- Modify `src/parallax/domains/news_intel/repositories/news_repository.py:3946-3973`.
  - Include public v2 brief fields in `_public_agent_brief_payload`.
  - Return pending/stale for schema mismatch instead of fabricating v2 fields.

### Tests

- Modify:
  - `tests/unit/domains/news_intel/test_news_item_brief_types.py`
  - `tests/unit/domains/news_intel/test_news_item_brief_input.py`
  - `tests/unit/domains/news_intel/test_news_item_brief_stage.py`
  - `tests/unit/domains/news_intel/test_news_item_brief_validation.py`
  - `tests/unit/domains/news_intel/test_news_item_brief_worker.py`
  - `tests/unit/integrations/model_execution/test_news_item_brief_agent_client.py`
  - `tests/unit/domains/news_intel/test_news_page_projection.py`
  - `tests/integration/domains/news_intel/test_news_item_agent_brief_repository.py`
  - `tests/integration/domains/news_intel/test_news_repository.py`
  - `tests/unit/domains/news_intel/test_news_repository_queries.py`
  - `tests/architecture/test_news_intel_boundaries.py`

- Create:
  - `tests/unit/domains/news_intel/test_news_item_brief_context_tools.py`
  - `tests/unit/domains/news_intel/test_news_item_brief_context.py`

### Docs

- Modify `src/parallax/domains/news_intel/ARCHITECTURE.md:72-78`.
  - Document item brief context compiler and read-only tool facade.
  - Preserve the boundary that News agent adapter delegates execution to `AgentExecutionGateway`.

## PR Breakdown

1. **PR 1 — v2 schema and context envelope types**: constants, Pydantic types, type/input/stage unit tests. Mergeable without worker integration because old code can still build empty-context packets.
2. **PR 2 — repository read tools**: SELECT-only methods and integration/unit query tests. Mergeable without model changes because methods are unused.
3. **PR 3 — context compiler and packet integration**: new compiler/facade services, packet builder changes, context hash/evidence refs tests.
4. **PR 4 — worker, prompt, validation, and serving hard cut**: worker compiles context, prompt/schema validation v2, page/detail stale guard, architecture docs.

For speed, these can land as one branch with four commits if review bandwidth is local.

## Rollout Order

1. Merge code with version bump and stale guard.
2. Restart workers so `news_item_brief` picks up prompt/schema/validator v4.
3. Reproject News page rows after deployment by existing page dirty/rebuild flow. If old v1 current briefs remain visible in live data, run a targeted cleanup script from the implementation task that clears `news_item_agent_briefs` rows whose `schema_version != 'news_item_brief_v2'` and enqueues page reprojection for those `news_item_id`s.
4. Let normal `brief_input` dirty targets re-run eligible items with packet v2.
5. Verify `/api/news` shows pending/stale for old rows and v2 fields for newly computed rows.

## Rollback

- Code rollback: revert the branch. Existing run ledger rows written with v2 remain audit evidence; they do not mutate facts.
- Serving rollback: old v1 current briefs may have been cleared by the hard-cut cleanup. Do not attempt to reconstruct them from v1 `response_json`; instead let old code show pending or rerun the old branch only in a throwaway environment.
- Data rollback: no new tables or migrations are introduced. If page rows were cleared/reprojected, rerun page projection under the rolled-back code.

## Implementation Tasks

### Task 1: Hard-cut News item brief v2 types and versions

**Files:**
- Modify: `src/parallax/domains/news_intel/_constants.py:5-8`
- Modify: `src/parallax/domains/news_intel/types/news_item_brief.py:18-236`
- Test: `tests/unit/domains/news_intel/test_news_item_brief_types.py`
- Test: `tests/unit/domains/news_intel/test_news_item_brief_validation.py`

- [ ] **Step 1: Write failing type tests**

  Add tests that prove v2 output fields are required and context tool result envelopes are strict:

  ```python
  import pytest
  from pydantic import ValidationError

  from parallax.domains.news_intel.types.news_item_brief import (
      NewsContextToolResult,
      NewsItemBriefPayload,
  )


  def test_news_item_brief_payload_requires_v2_context_fields() -> None:
      with pytest.raises(ValidationError):
          NewsItemBriefPayload.model_validate(
              {
                  "status": "ready",
                  "direction": "neutral",
                  "decision_class": "context",
                  "title_zh": "标题",
                  "summary_zh": "摘要",
                  "market_read_zh": "市场解读",
                  "bull_view": {"strength": "absent", "thesis_zh": "", "evidence_refs": []},
                  "bear_view": {"strength": "absent", "thesis_zh": "", "evidence_refs": []},
                  "affected_assets": [],
                  "watch_triggers": [],
                  "invalidation_conditions": [],
                  "data_gaps": [],
                  "evidence_refs": [],
              }
          )


  def test_news_context_tool_result_is_strict_and_hashable() -> None:
      result = NewsContextToolResult.model_validate(
          {
              "tool_name": "get_news_observation_history",
              "schema_version": "news_item_brief_context_tools_v1",
              "query_version": "observation_history_v1",
              "input": {"news_item_id": "news-1", "limit": 25},
              "source_tables": ["news_items", "news_item_observation_edges", "news_sources"],
              "limit": 25,
              "rows": [{"evidence_ref": "tool:get_news_observation_history"}],
              "truncated": False,
              "result_hash": "sha256:abc",
              "generated_at_ms": 1_779_000_000_000,
          }
      )

      assert result.tool_name == "get_news_observation_history"
      assert result.truncated is False
  ```

- [ ] **Step 2: Run the failing tests**

  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_item_brief_types.py::test_news_item_brief_payload_requires_v2_context_fields tests/unit/domains/news_intel/test_news_item_brief_types.py::test_news_context_tool_result_is_strict_and_hashable -q
  ```

  Expected: FAIL because `NewsContextToolResult` and required v2 fields do not exist yet.

- [ ] **Step 3: Implement constants and Pydantic models**

  In `_constants.py`, change the four brief constants to:

  ```python
  NEWS_ITEM_BRIEF_PROMPT_VERSION = "news-item-brief-v4"
  NEWS_ITEM_BRIEF_SCHEMA_VERSION = "news_item_brief_v2"
  NEWS_ITEM_BRIEF_VALIDATOR_VERSION = "news_item_brief_validator_v4"
  NEWS_ITEM_BRIEF_GUARDRAIL_VERSION = "news_item_brief_guardrails_v4"
  ```

  In `types/news_item_brief.py`, add these literals and models:

  ```python
  NewsItemBriefNoveltyStatus = Literal["new", "repeat", "update", "duplicate", "unclear"]
  NewsItemBriefConfirmationState = Literal[
      "single_source",
      "multi_source_confirmed",
      "provider_only",
      "conflicting",
      "unclear",
  ]


  class NewsContextToolResult(BaseModel):
      model_config = ConfigDict(extra="forbid")

      tool_name: str = Field(min_length=1, max_length=120)
      schema_version: str = Field(min_length=1, max_length=128)
      query_version: str = Field(min_length=1, max_length=128)
      input: dict[str, object] = Field(default_factory=dict)
      source_tables: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(
          default_factory=list,
          max_length=12,
      )
      limit: int = Field(default=0, ge=0, le=100)
      rows: list[dict[str, object]] = Field(default_factory=list, max_length=100)
      truncated: bool = False
      result_hash: str = Field(min_length=1, max_length=128)
      generated_at_ms: int = Field(ge=0)
      skipped_reason: str | None = Field(default=None, max_length=160)


  class NewsItemBriefContextBudget(BaseModel):
      model_config = ConfigDict(extra="forbid")

      max_tool_results: int = Field(default=8, ge=0, le=20)
      max_rows_per_tool: int = Field(default=25, ge=0, le=100)
      truncated_tool_count: int = Field(default=0, ge=0, le=20)
  ```

  Add required v2 fields to `NewsItemBriefPayload`:

  ```python
  novelty_status: NewsItemBriefNoveltyStatus
  confirmation_state: NewsItemBriefConfirmationState
  source_consensus_zh: str = Field(max_length=600)
  retrieval_notes_zh: str = Field(max_length=600)
  retrieval_evidence_refs: list[Annotated[str, Field(min_length=1, max_length=160)]] = Field(
      default_factory=list,
      max_length=20,
  )
  ```

  Add v2 input fields to `NewsItemBriefInputPacket`:

  ```python
  context_tool_results: list[NewsContextToolResult] = Field(default_factory=list, max_length=8)
  context_budget: NewsItemBriefContextBudget = Field(default_factory=NewsItemBriefContextBudget)
  context_snapshot_hash: str = Field(default="", max_length=128)
  ```

  Add new symbols to `__all__`.

- [ ] **Step 4: Run type tests**

  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_item_brief_types.py tests/unit/domains/news_intel/test_news_item_brief_validation.py -q
  ```

  Expected: type tests pass after existing validation fixtures are updated to include v2 fields.

- [ ] **Step 5: Commit**

  ```bash
  git add src/parallax/domains/news_intel/_constants.py src/parallax/domains/news_intel/types/news_item_brief.py tests/unit/domains/news_intel/test_news_item_brief_types.py tests/unit/domains/news_intel/test_news_item_brief_validation.py
  git commit -m "feat: hard cut news item brief v2 schema"
  ```

### Task 2: Add SELECT-only repository methods for News context tools

**Files:**
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py:2021-2671`
- Test: `tests/integration/domains/news_intel/test_news_repository.py`
- Test: `tests/integration/domains/news_intel/test_news_item_agent_brief_repository.py`
- Test: `tests/unit/domains/news_intel/test_news_repository_queries.py`

- [ ] **Step 1: Write failing repository tests**

  Add integration tests with these names and assertions:

  ```python
  def test_item_brief_observation_history_is_public_safe_and_bounded(tmp_path) -> None:
      result = repo.get_news_observation_history(news_item_id=news_item_id, limit=25)
      result_json = json.dumps(result, sort_keys=True)
      assert result["news_item_id"] == news_item_id
      assert len(result["rows"]) <= 25
      assert "provider_item_id" not in result_json
      assert "source_item_key" not in result_json
      assert "raw_payload_json" not in result_json
      assert "feed_url" not in result_json
      assert "sync_cursor_json" not in result_json


  def test_item_brief_source_quality_context_uses_existing_source_status_payload(tmp_path) -> None:
      result = repo.get_source_quality_context_for_item(news_item_id=news_item_id)
      result_json = json.dumps(result, sort_keys=True)
      assert result["news_item_id"] == news_item_id
      assert result["source"]["source_quality_status"] == "healthy"
      assert "feed_url" not in result_json
      assert "sync_cursor_json" not in result_json


  def test_item_brief_run_history_is_compact_and_excludes_full_request_response(tmp_path) -> None:
      rows = repo.list_news_item_agent_run_history(news_item_id=news_item_id, limit=5)
      result_json = json.dumps(rows, sort_keys=True)
      assert len(rows) <= 5
      assert rows[0]["run_id"] == "run-current"
      assert "request_json" not in result_json
      assert "response_json" not in result_json


  def test_find_similar_news_items_returns_exact_before_heuristic_matches(tmp_path) -> None:
      rows = repo.find_similar_news_items(
          news_item_id=news_item_id,
          window_ms=7 * 24 * 3_600_000,
          limit=8,
          now_ms=NOW_MS,
      )
      assert len(rows) <= 8
      assert rows[0]["match_confidence"] in {"exact", "strong"}
      assert rows[0]["match_reason"] in {
          "same_canonical_url",
          "same_provider_article_key",
          "same_content_hash",
          "same_title_fingerprint",
      }
  ```

  Add a unit SQL guard in `test_news_repository_queries.py` that captures the similar-news SQL and asserts:

  ```python
  assert "news_story_groups" not in conn.sql
  assert "news_story_members" not in conn.sql
  assert "token_radar" not in conn.sql
  assert "market_ticks" not in conn.sql
  ```

- [ ] **Step 2: Run the failing tests**

  ```bash
  uv run pytest \
    tests/integration/domains/news_intel/test_news_repository.py::test_item_brief_observation_history_is_public_safe_and_bounded \
    tests/integration/domains/news_intel/test_news_repository.py::test_item_brief_source_quality_context_uses_existing_source_status_payload \
    tests/integration/domains/news_intel/test_news_item_agent_brief_repository.py::test_item_brief_run_history_is_compact_and_excludes_full_request_response \
    tests/integration/domains/news_intel/test_news_repository.py::test_find_similar_news_items_returns_exact_before_heuristic_matches \
    tests/unit/domains/news_intel/test_news_repository_queries.py::test_find_similar_news_items_does_not_reference_removed_or_cross_domain_tables \
    -q
  ```

  Expected: FAIL because repository methods do not exist.

- [ ] **Step 3: Implement repository methods**

  Add these methods to `NewsRepository` near `get_news_item_detail()` and source status methods:

  - `def get_news_observation_history(self, *, news_item_id: str, limit: int = 25) -> dict[str, Any]`
  - `def get_source_quality_context_for_item(self, *, news_item_id: str) -> dict[str, Any]`
  - `def list_news_item_agent_run_history(self, *, news_item_id: str, limit: int = 5) -> list[dict[str, Any]]`
  - `def find_similar_news_items(self, *, news_item_id: str, window_ms: int = 7 * 24 * 3_600_000, limit: int = 8, now_ms: int | None = None) -> list[dict[str, Any]]`

  Implementation rules:

  - `get_news_observation_history` reads `news_items`, `news_item_observation_edges`, `news_sources`, and `news_provider_items`; it returns public-safe edge rows only.
  - `get_source_quality_context_for_item` resolves the item's source and returns compact source status plus latest quality payload using the same public-safe shape as `_source_status_payload`.
  - `list_news_item_agent_run_history` returns at most five summaries and excludes full `request_json` and `response_json`.
  - `find_similar_news_items` uses `news_items`, `news_item_observation_edges`, `news_sources`, `news_page_rows`, `news_token_mentions`, and `news_item_agent_briefs`. It orders exact identity matches before strong content/title matches before heuristic token/source matches.

- [ ] **Step 4: Run repository tests**

  ```bash
  uv run pytest \
    tests/integration/domains/news_intel/test_news_repository.py \
    tests/integration/domains/news_intel/test_news_item_agent_brief_repository.py \
    tests/unit/domains/news_intel/test_news_repository_queries.py \
    -q
  ```

  Expected: pass.

- [ ] **Step 5: Commit**

  ```bash
  git add src/parallax/domains/news_intel/repositories/news_repository.py tests/integration/domains/news_intel/test_news_repository.py tests/integration/domains/news_intel/test_news_item_agent_brief_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py
  git commit -m "feat: add news item brief context repository reads"
  ```

### Task 3: Add News context tool facade and compiler

**Files:**
- Create: `src/parallax/domains/news_intel/services/news_item_brief_context_tools.py`
- Create: `src/parallax/domains/news_intel/services/news_item_brief_context.py`
- Test: `tests/unit/domains/news_intel/test_news_item_brief_context_tools.py`
- Test: `tests/unit/domains/news_intel/test_news_item_brief_context.py`

- [ ] **Step 1: Write failing context tool tests**

  Add tests that prove envelope hashing, deterministic order, empty result inclusion, truncation, and source table provenance:

  ```python
  from parallax.domains.news_intel.services.news_item_brief_context import NewsItemBriefContextCompiler
  from parallax.domains.news_intel.services.news_item_brief_context_tools import (
      NEWS_CONTEXT_TOOL_SCHEMA_VERSION,
      context_tool_result,
  )


  def test_context_tool_result_hash_changes_with_rows() -> None:
      first = context_tool_result(
          tool_name="find_similar_news_items",
          query_version="similar_news_v1",
          input_payload={"news_item_id": "news-1", "limit": 8},
          source_tables=["news_items"],
          rows=[{"news_item_id": "news-2"}],
          limit=8,
          generated_at_ms=1_779_000_000_000,
      )
      second = context_tool_result(
          tool_name="find_similar_news_items",
          query_version="similar_news_v1",
          input_payload={"news_item_id": "news-1", "limit": 8},
          source_tables=["news_items"],
          rows=[{"news_item_id": "news-3"}],
          limit=8,
          generated_at_ms=1_779_000_000_000,
      )

      assert first.schema_version == NEWS_CONTEXT_TOOL_SCHEMA_VERSION
      assert first.result_hash != second.result_hash


  def test_context_compiler_includes_empty_tool_results_with_skip_reasons() -> None:
      repo = FakeNewsContextRepository()
      compiler = NewsItemBriefContextCompiler(news_repo=repo, now_ms=1_779_000_000_000)

      snapshot = compiler.compile(candidate={"item": {"news_item_id": "news-1", "source_id": "source-1"}})

      assert [row.tool_name for row in snapshot.context_tool_results] == [
          "find_similar_news_items",
          "get_existing_brief_history",
          "get_news_observation_history",
          "get_source_quality_context",
      ]
      assert all(row.result_hash.startswith("sha256:") for row in snapshot.context_tool_results)
      assert snapshot.context_snapshot_hash.startswith("sha256:")
  ```

- [ ] **Step 2: Run failing context tests**

  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_item_brief_context_tools.py tests/unit/domains/news_intel/test_news_item_brief_context.py -q
  ```

  Expected: FAIL because new services do not exist.

- [ ] **Step 3: Implement `news_item_brief_context_tools.py`**

  Required public API:

  - `NEWS_CONTEXT_TOOL_SCHEMA_VERSION = "news_item_brief_context_tools_v1"`
  - `def context_tool_result(*, tool_name: str, query_version: str, input_payload: Mapping[str, object], source_tables: Sequence[str], rows: Sequence[Mapping[str, object]], limit: int, generated_at_ms: int, skipped_reason: str | None = None) -> NewsContextToolResult`
  - `class NewsAgentReadToolFacade`
  - `NewsAgentReadToolFacade.__init__(self, *, news_repo: Any, now_ms: int) -> None`
  - `NewsAgentReadToolFacade.get_news_observation_history(self, *, news_item_id: str) -> NewsContextToolResult`
  - `NewsAgentReadToolFacade.get_source_quality_context(self, *, news_item_id: str) -> NewsContextToolResult`
  - `NewsAgentReadToolFacade.get_existing_brief_history(self, *, news_item_id: str) -> NewsContextToolResult`
  - `NewsAgentReadToolFacade.find_similar_news_items(self, *, news_item_id: str) -> NewsContextToolResult`

  Envelope hash must be:

  ```python
  result_hash = json_sha256(
      {
          "tool_name": tool_name,
          "query_version": query_version,
          "input": normalized_input,
          "source_tables": sorted(source_tables),
          "limit": limit,
          "rows": normalized_rows,
          "truncated": truncated,
          "skipped_reason": skipped_reason,
      }
  )
  ```

- [ ] **Step 4: Implement `news_item_brief_context.py`**

  Required public API:

  ```python
  class NewsItemBriefContextSnapshot(BaseModel):
      model_config = ConfigDict(extra="forbid")

      context_tool_results: list[NewsContextToolResult]
      context_budget: NewsItemBriefContextBudget
      context_snapshot_hash: str


  class NewsItemBriefContextCompiler:
      def __init__(self, *, news_repo: Any, now_ms: int) -> None:
          self.news_repo = news_repo
          self.now_ms = int(now_ms)

      def compile(self, *, candidate: Mapping[str, Any]) -> NewsItemBriefContextSnapshot:
          news_item_id = str(_dict(candidate.get("item") or candidate).get("news_item_id") or "")
          facade = NewsAgentReadToolFacade(news_repo=self.news_repo, now_ms=self.now_ms)
          tool_results = [
              facade.find_similar_news_items(news_item_id=news_item_id),
              facade.get_existing_brief_history(news_item_id=news_item_id),
              facade.get_news_observation_history(news_item_id=news_item_id),
              facade.get_source_quality_context(news_item_id=news_item_id),
          ]
          context_snapshot_hash = json_sha256([row.model_dump(mode="json") for row in tool_results])
          return NewsItemBriefContextSnapshot(
              context_tool_results=tool_results,
              context_budget=NewsItemBriefContextBudget(
                  max_tool_results=8,
                  max_rows_per_tool=25,
                  truncated_tool_count=sum(1 for row in tool_results if row.truncated),
              ),
              context_snapshot_hash=context_snapshot_hash,
          )
  ```

  The compiler order is fixed:

  ```python
  tool_results = [
      facade.find_similar_news_items(news_item_id=news_item_id),
      facade.get_existing_brief_history(news_item_id=news_item_id),
      facade.get_news_observation_history(news_item_id=news_item_id),
      facade.get_source_quality_context(news_item_id=news_item_id),
  ]
  ```

  `context_snapshot_hash` is `json_sha256([row.model_dump(mode="json") for row in tool_results])`.

- [ ] **Step 5: Run context tests**

  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_item_brief_context_tools.py tests/unit/domains/news_intel/test_news_item_brief_context.py -q
  ```

  Expected: pass.

- [ ] **Step 6: Commit**

  ```bash
  git add src/parallax/domains/news_intel/services/news_item_brief_context_tools.py src/parallax/domains/news_intel/services/news_item_brief_context.py tests/unit/domains/news_intel/test_news_item_brief_context_tools.py tests/unit/domains/news_intel/test_news_item_brief_context.py
  git commit -m "feat: add news item brief context compiler"
  ```

### Task 4: Integrate context snapshot into packet input and stage trace

**Files:**
- Modify: `src/parallax/domains/news_intel/services/news_item_brief_input.py:28-90`
- Modify: `src/parallax/domains/news_intel/services/news_item_brief_stage.py:24-44`
- Modify: `tests/unit/domains/news_intel/test_news_item_brief_input.py`
- Modify: `tests/unit/domains/news_intel/test_news_item_brief_stage.py`
- Modify: `tests/unit/integrations/model_execution/test_news_item_brief_agent_client.py`

- [ ] **Step 1: Write failing packet tests**

  Add tests:

  ```python
  def test_packet_includes_context_tool_results_refs_and_hash() -> None:
      tool_result = _tool_result(
          tool_name="find_similar_news_items",
          rows=[{"news_item_id": "similar-1", "evidence_ref": "similar:item:similar-1"}],
      )

      packet = build_news_item_brief_input_packet(
          item=_item(),
          token_mentions=[],
          fact_candidates=[],
          context_tool_results=[tool_result],
          agent_config=_agent_config(),
      )

      assert packet.context_tool_results[0].tool_name == "find_similar_news_items"
      assert packet.context_snapshot_hash.startswith("sha256:")
      assert "tool:find_similar_news_items" in packet.evidence_refs
      assert "similar:item:similar-1" in packet.evidence_refs
      assert packet.input_hash == json_sha256(news_item_brief_material_input_payload(packet))
  ```

  Add a stage test:

  ```python
  def test_stage_trace_metadata_includes_context_snapshot() -> None:
      packet = _packet_with_context()
      stage = build_news_item_brief_stage(packet=packet, run_id="run-1")

      assert stage.trace_metadata["context_snapshot_hash"] == packet.context_snapshot_hash
      assert stage.trace_metadata["context_tool_names"] == ["find_similar_news_items"]
      assert stage.trace_metadata["context_truncated"] is False
  ```

- [ ] **Step 2: Run failing packet/stage tests**

  ```bash
  uv run pytest \
    tests/unit/domains/news_intel/test_news_item_brief_input.py::test_packet_includes_context_tool_results_refs_and_hash \
    tests/unit/domains/news_intel/test_news_item_brief_stage.py::test_stage_trace_metadata_includes_context_snapshot \
    -q
  ```

  Expected: FAIL until packet builder and stage metadata accept context.

- [ ] **Step 3: Update packet builder**

  Change signature to `def build_news_item_brief_input_packet(*, item: Mapping[str, Any], token_mentions: Sequence[Mapping[str, Any]], fact_candidates: Sequence[Mapping[str, Any]], agent_config: NewsItemBriefAgentConfig, context_tool_results: Sequence[NewsContextToolResult | Mapping[str, Any]] | None = None, context_budget: NewsItemBriefContextBudget | Mapping[str, Any] | None = None) -> NewsItemBriefInputPacket`.

  Add helper behavior:

  - Normalize all context results through `NewsContextToolResult.model_validate`.
  - Sort by `(tool_name, query_version)`.
  - `context_snapshot_hash = json_sha256([result.model_dump(mode="json") for result in normalized_results])`.
  - Add refs:

    ```python
    refs.extend(f"tool:{result.tool_name}" for result in context_tool_results)
    for result in context_tool_results:
        for row in result.rows:
            evidence_ref = str(row.get("evidence_ref") or "")
            if evidence_ref:
                refs.append(evidence_ref)
    ```

  - Include `context_snapshot_hash` in `_packet_id()`.

- [ ] **Step 4: Update stage metadata and client tests**

  In `build_news_item_brief_stage()`, add:

  ```python
  context_tool_names = [row.tool_name for row in packet.context_tool_results]
  context_truncated = any(row.truncated for row in packet.context_tool_results)
  ```

  Add these keys to `trace_metadata`:

  ```python
  "context_snapshot_hash": packet.context_snapshot_hash,
  "context_tool_names": context_tool_names,
  "context_truncated": context_truncated,
  ```

- [ ] **Step 5: Run packet/stage/client tests**

  ```bash
  uv run pytest \
    tests/unit/domains/news_intel/test_news_item_brief_input.py \
    tests/unit/domains/news_intel/test_news_item_brief_stage.py \
    tests/unit/integrations/model_execution/test_news_item_brief_agent_client.py \
    -q
  ```

  Expected: pass.

- [ ] **Step 6: Commit**

  ```bash
  git add src/parallax/domains/news_intel/services/news_item_brief_input.py src/parallax/domains/news_intel/services/news_item_brief_stage.py tests/unit/domains/news_intel/test_news_item_brief_input.py tests/unit/domains/news_intel/test_news_item_brief_stage.py tests/unit/integrations/model_execution/test_news_item_brief_agent_client.py
  git commit -m "feat: include news context tools in brief packet"
  ```

### Task 5: Wire context compiler into `NewsItemBriefWorker`

**Files:**
- Modify: `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py:141-186`
- Modify: `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py:677-687`
- Modify: `tests/unit/domains/news_intel/test_news_item_brief_worker.py`

- [ ] **Step 1: Write failing worker tests**

  Add or update tests:

  ```python
  async def _test_worker_compiles_context_before_provider_execution() -> None:
      db = FakeDB([_candidate()])
      provider = FakeBriefProvider(payload=_ready_payload())
      worker = _worker(db=db, provider=provider)

      result = await worker.run_once()

      assert result.processed == 1
      packet = provider.seen_packets[0]
      assert packet.context_tool_results
      assert packet.context_snapshot_hash.startswith("sha256:")
      assert db.news.context_calls == ["find_similar_news_items", "get_existing_brief_history", "get_news_observation_history", "get_source_quality_context"]
      assert provider.saw_db_session_during_execution is False
      assert db.news.runs[0]["request_json"]["packet"]["context_snapshot_hash"] == packet.context_snapshot_hash
  ```

  Add a freshness test:

  ```python
  async def _test_worker_reprocesses_when_context_hash_changes() -> None:
      candidate = _candidate()
      db = FakeDB([candidate])
      provider = FakeBriefProvider(payload=_ready_payload())
      old_packet = provider.packet_for_candidate(candidate)
      candidate["current_brief"] = {
          "news_item_id": "news-item-1",
          "status": "ready",
          "input_hash": old_packet.input_hash,
          "artifact_version_hash": provider.artifact_version_hash,
          "prompt_version": old_packet.prompt_version,
          "schema_version": old_packet.schema_version,
          "validator_version": provider.agent_config().validator_version,
          "computed_at_ms": NOW_MS - 60_000,
          "brief_json": _ready_payload(),
      }

      result = await _worker(db=db, provider=provider).run_once()

      assert result.processed == 1
      assert provider.execution_calls == 1
  ```

- [ ] **Step 2: Run failing worker tests**

  ```bash
  uv run pytest \
    tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_compiles_context_before_provider_execution \
    tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_reprocesses_when_context_hash_changes \
    -q
  ```

  Expected: FAIL until worker compiles context.

- [ ] **Step 3: Implement worker context compilation**

  Add import:

  ```python
  from parallax.domains.news_intel.services.news_item_brief_context import NewsItemBriefContextCompiler
  ```

  Add method:

  ```python
  def _compile_context(self, *, candidate: Mapping[str, Any], now_ms: int) -> dict[str, Any]:
      with self._repository_session() as repos:
          snapshot = NewsItemBriefContextCompiler(news_repo=repos.news, now_ms=now_ms).compile(candidate=candidate)
      return snapshot.model_dump(mode="json")
  ```

  In the main loop after eligibility passes:

  ```python
  context_snapshot = await asyncio.to_thread(self._compile_context, candidate=candidate, now_ms=now)
  packet = _packet_from_candidate(
      candidate,
      agent_config=agent_config,
      context_snapshot=context_snapshot,
  )
  ```

  Change `_packet_from_candidate()`:

  ```python
  def _packet_from_candidate(
      candidate: Mapping[str, Any],
      *,
      agent_config: NewsItemBriefAgentConfig,
      context_snapshot: Mapping[str, Any] | None = None,
  ) -> NewsItemBriefInputPacket:
      snapshot = _dict(context_snapshot)
      return build_news_item_brief_input_packet(
          item=_dict(candidate.get("item") or candidate),
          token_mentions=_list_of_dicts(candidate.get("token_mentions")),
          fact_candidates=_list_of_dicts(candidate.get("fact_candidates")),
          agent_config=agent_config,
          context_tool_results=_list_of_dicts(snapshot.get("context_tool_results")),
          context_budget=_dict(snapshot.get("context_budget")),
      )
  ```

  Update `_failed_brief()` to include:

  ```python
  "novelty_status": "unclear",
  "confirmation_state": "unclear",
  "source_consensus_zh": "",
  "retrieval_notes_zh": "",
  "retrieval_evidence_refs": [],
  ```

- [ ] **Step 4: Update worker fake repository**

  In `FakeNewsRepository`, add compact methods used by the compiler:

  ```python
  def get_news_observation_history(self, *, news_item_id: str, limit: int = 25) -> dict[str, Any]:
      self.context_calls.append("get_news_observation_history")
      return {"news_item_id": news_item_id, "rows": [{"evidence_ref": "observation:news-item-1"}]}

  def get_source_quality_context_for_item(self, *, news_item_id: str) -> dict[str, Any]:
      self.context_calls.append("get_source_quality_context")
      return {"news_item_id": news_item_id, "source_quality_status": "healthy"}

  def list_news_item_agent_run_history(self, *, news_item_id: str, limit: int = 5) -> list[dict[str, Any]]:
      self.context_calls.append("get_existing_brief_history")
      return []

  def find_similar_news_items(self, *, news_item_id: str, window_ms: int, limit: int, now_ms: int | None = None) -> list[dict[str, Any]]:
      self.context_calls.append("find_similar_news_items")
      return [{"news_item_id": "similar-1", "match_confidence": "heuristic", "evidence_ref": "similar:item:similar-1"}]
  ```

- [ ] **Step 5: Run worker tests**

  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py -q
  ```

  Expected: pass, including existing capacity-denied and no-DB-session-during-execution tests.

- [ ] **Step 6: Commit**

  ```bash
  git add src/parallax/domains/news_intel/runtime/news_item_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_worker.py
  git commit -m "feat: compile news context before item brief execution"
  ```

### Task 6: Update prompt, validation, and v2 serving payloads

**Files:**
- Modify: `src/parallax/domains/news_intel/prompts/news_item_brief.md:1-50`
- Modify: `src/parallax/domains/news_intel/services/news_item_brief_validation.py:29-123`
- Modify: `src/parallax/domains/news_intel/services/news_page_projection.py:175-203`
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py:3946-3973`
- Test: `tests/unit/domains/news_intel/test_news_item_brief_validation.py`
- Test: `tests/unit/domains/news_intel/test_news_page_projection.py`
- Test: `tests/integration/domains/news_intel/test_news_repository.py`

- [ ] **Step 1: Write failing validation and serving tests**

  Add validation test:

  ```python
  def test_validation_allows_asset_backed_by_tool_evidence() -> None:
      packet = _packet_with_context_tool_rows(
          rows=[{"symbol": "SOL", "target_id": "cex:SOL", "evidence_ref": "similar:item:sol"}]
      )
      payload = _valid_payload(affected_assets=[{"symbol": "SOL", "resolution_status": "known_symbol"}])

      result = validate_news_item_brief_output(payload=payload, packet=packet, audit={})

      assert result.publishable is True
      assert result.payload["affected_assets"][0]["symbol"] == "SOL"
  ```

  Add page projection test:

  ```python
  def test_page_projection_marks_old_schema_brief_pending_not_translated() -> None:
      row = build_news_page_row(
          item=_item(),
          token_mentions=[],
          fact_candidates=[],
          agent_brief={
              "status": "ready",
              "schema_version": "news_item_brief_v1",
              "brief_json": {"status": "ready", "summary_zh": "旧摘要"},
          },
          computed_at_ms=NOW_MS,
      )

      assert row["agent_brief"]["status"] == "pending"
      assert row["agent_brief"]["stale_schema_version"] == "news_item_brief_v1"
      assert row["signal"]["agent_signal"]["status"] == "pending"
  ```

- [ ] **Step 2: Run failing tests**

  ```bash
  uv run pytest \
    tests/unit/domains/news_intel/test_news_item_brief_validation.py::test_validation_allows_asset_backed_by_tool_evidence \
    tests/unit/domains/news_intel/test_news_page_projection.py::test_page_projection_marks_old_schema_brief_pending_not_translated \
    -q
  ```

  Expected: FAIL until validation and projection are updated.

- [ ] **Step 3: Update prompt**

  Replace the role sentence with:

  ```markdown
  你把单条新闻、deterministic facts、provider evidence 和预先计算的 `context_tool_results` 转成一个 source-backed `NewsItemBriefPayload`。你不调用运行时工具，不请求外部数据，不使用 packet 与 `context_tool_results` 之外的知识。
  ```

  Add output guidance:

  ```markdown
  - `novelty_status`: 判断该新闻是 new / repeat / update / duplicate / unclear。
  - `confirmation_state`: 判断来源确认状态；heuristic similar news 不能当成 canonical confirmation。
  - `source_consensus_zh`: 用中文说明来源质量、多源观察、重复观测或冲突。
  - `retrieval_notes_zh`: 用中文说明相似新闻、旧 brief/run history、source quality 对判断的影响。
  ```

- [ ] **Step 4: Update validation grounding**

  In `_source_backed_asset_labels()`, add a bounded recursive extraction over `packet.context_tool_results` rows:

  ```python
  for tool_result in packet.context_tool_results:
      for row in tool_result.rows:
          labels.update(_tool_asset_labels(row))
  ```

  Add helper:

  ```python
  def _tool_asset_labels(value: Any) -> set[str]:
      labels: set[str] = set()
      if isinstance(value, Mapping):
          for key, child in value.items():
              if str(key) in {"symbol", "display_symbol", "target_id", "target_type", "headline", "title"}:
                  labels.add(_norm(child))
              labels.update(_tool_asset_labels(child))
      elif isinstance(value, list):
          for child in value[:20]:
              labels.update(_tool_asset_labels(child))
      elif isinstance(value, str):
          labels.update(_norm(token) for token in re.findall(r"[A-Za-z0-9]{2,20}", value[:500]))
      return {label for label in labels if label}
  ```

- [ ] **Step 5: Update page/detail serving hard cut**

  Import `NEWS_ITEM_BRIEF_SCHEMA_VERSION` into `news_page_projection.py`.

  In `_compact_agent_brief()`, before reading `brief_json` as current:

  ```python
  schema_version = str(agent_brief.get("schema_version") or brief_json.get("schema_version") or "")
  if schema_version and schema_version != NEWS_ITEM_BRIEF_SCHEMA_VERSION:
      return {
          "status": "pending",
          "stale_schema_version": schema_version,
          "required_schema_version": NEWS_ITEM_BRIEF_SCHEMA_VERSION,
      }
  ```

  Add v2 compact fields when schema matches:

  ```python
  "novelty_status": brief_json.get("novelty_status"),
  "confirmation_state": brief_json.get("confirmation_state"),
  "source_consensus_zh": brief_json.get("source_consensus_zh"),
  "retrieval_notes_zh": brief_json.get("retrieval_notes_zh"),
  "retrieval_evidence_refs": _json_list(brief_json.get("retrieval_evidence_refs")),
  ```

  In `_public_agent_brief_payload()`, apply the same stale schema guard and include the same v2 fields.

- [ ] **Step 6: Run validation/projection/detail tests**

  ```bash
  uv run pytest \
    tests/unit/domains/news_intel/test_news_item_brief_validation.py \
    tests/unit/domains/news_intel/test_news_page_projection.py \
    tests/integration/domains/news_intel/test_news_repository.py \
    -q
  ```

  Expected: pass.

- [ ] **Step 7: Commit**

  ```bash
  git add src/parallax/domains/news_intel/prompts/news_item_brief.md src/parallax/domains/news_intel/services/news_item_brief_validation.py src/parallax/domains/news_intel/services/news_page_projection.py src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_item_brief_validation.py tests/unit/domains/news_intel/test_news_page_projection.py tests/integration/domains/news_intel/test_news_repository.py
  git commit -m "feat: enforce news brief v2 prompt and serving contract"
  ```

### Task 7: Hard-cut old current briefs without deleting run ledger

**Files:**
- Create: `src/parallax/domains/news_intel/services/news_item_brief_schema_hard_cut.py`
- Modify: `src/parallax/app/surfaces/cli/commands/ops.py`
- Modify: `tests/unit/test_cli.py`
- Create: `tests/integration/domains/news_intel/test_news_item_brief_schema_hard_cut.py`

- [ ] **Step 1: Write failing cleanup tests**

  Add integration test:

  ```python
  def test_news_item_brief_schema_hard_cut_clears_old_current_briefs_and_reprojects(tmp_path) -> None:
      conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
      try:
          migrate(conn)
          repo = NewsRepository(conn)
          news_item_id = _seed_item_with_old_current_brief(repo)

          result = cleanup_news_item_brief_schema_hard_cut(_repos(conn), execute=True, now_ms=NOW_MS)

          assert result["execute"] is True
          assert result["cleared_current_briefs"] == 1
          assert conn.execute("SELECT COUNT(*) AS count FROM news_item_agent_runs").fetchone()["count"] == 1
          assert conn.execute("SELECT COUNT(*) AS count FROM news_item_agent_briefs").fetchone()["count"] == 0
          dirty = conn.execute("SELECT * FROM news_projection_dirty_targets WHERE target_id = %s", (news_item_id,)).fetchone()
          assert dirty["projection_name"] == "page"
      finally:
          conn.close()
  ```

  Add CLI parser test:

  ```python
  def test_ops_news_item_brief_schema_hard_cut_parser_requires_mode() -> None:
      parser = build_parser()
      dry_run = parser.parse_args(["ops", "cleanup-news-item-brief-schema-hard-cut", "--dry-run"])
      execute = parser.parse_args(["ops", "cleanup-news-item-brief-schema-hard-cut", "--execute"])

      assert dry_run.ops_command == "cleanup-news-item-brief-schema-hard-cut"
      assert execute.ops_command == "cleanup-news-item-brief-schema-hard-cut"
  ```

- [ ] **Step 2: Run failing cleanup tests**

  ```bash
  uv run pytest \
    tests/integration/domains/news_intel/test_news_item_brief_schema_hard_cut.py \
    tests/unit/test_cli.py::test_ops_news_item_brief_schema_hard_cut_parser_requires_mode \
    -q
  ```

  Expected: FAIL until cleanup service and CLI command exist.

- [ ] **Step 3: Implement cleanup service**

  Create `news_item_brief_schema_hard_cut.py` with:

  ```python
  from __future__ import annotations

  from typing import Any

  from parallax.domains.news_intel._constants import NEWS_ITEM_BRIEF_SCHEMA_VERSION
  from parallax.domains.news_intel.runtime.news_projection_work import enqueue_page_reprojection


  def cleanup_news_item_brief_schema_hard_cut(repos: Any, *, execute: bool, now_ms: int) -> dict[str, Any]:
      rows = repos.conn.execute(
          """
          SELECT news_item_id, schema_version
            FROM news_item_agent_briefs
           WHERE schema_version IS DISTINCT FROM %s
           ORDER BY news_item_id ASC
          """,
          (NEWS_ITEM_BRIEF_SCHEMA_VERSION,),
      ).fetchall()
      news_item_ids = [str(row["news_item_id"]) for row in rows]
      result = {
          "execute": bool(execute),
          "dry_run": not bool(execute),
          "required_schema_version": NEWS_ITEM_BRIEF_SCHEMA_VERSION,
          "stale_current_briefs": len(news_item_ids),
          "cleared_current_briefs": 0,
          "page_reprojection_targets": 0,
      }
      if not execute or not news_item_ids:
          return result
      with repos.conn.transaction():
          deleted = repos.conn.execute(
              """
              DELETE FROM news_item_agent_briefs
               WHERE schema_version IS DISTINCT FROM %s
              """,
              (NEWS_ITEM_BRIEF_SCHEMA_VERSION,),
          ).rowcount
          enqueued = enqueue_page_reprojection(
              repos,
              news_item_ids=news_item_ids,
              reason="news_item_brief_schema_hard_cut",
              now_ms=now_ms,
              commit=False,
          )
      result["cleared_current_briefs"] = int(deleted or 0)
      result["page_reprojection_targets"] = int(enqueued or 0)
      return result
  ```

  This preserves `news_item_agent_runs`.

- [ ] **Step 4: Wire CLI command**

  In `ops.py`, register `cleanup-news-item-brief-schema-hard-cut` with mutually exclusive `--dry-run` and `--execute`, mirroring `cleanup-news-intel-hard-cut`. The command opens repositories, calls `cleanup_news_item_brief_schema_hard_cut`, writes JSON to stdout, and returns 0.

- [ ] **Step 5: Run cleanup tests**

  ```bash
  uv run pytest \
    tests/integration/domains/news_intel/test_news_item_brief_schema_hard_cut.py \
    tests/unit/test_cli.py \
    tests/integration/test_cli.py \
    -q
  ```

  Expected: pass.

- [ ] **Step 6: Commit**

  ```bash
  git add src/parallax/domains/news_intel/services/news_item_brief_schema_hard_cut.py src/parallax/app/surfaces/cli/commands/ops.py tests/unit/test_cli.py tests/integration/test_cli.py tests/integration/domains/news_intel/test_news_item_brief_schema_hard_cut.py
  git commit -m "feat: add news item brief schema hard cut cleanup"
  ```

### Task 8: Architecture docs and final verification

**Files:**
- Modify: `src/parallax/domains/news_intel/ARCHITECTURE.md:72-78`
- Modify: `docs/AGENT_EXECUTION.md`
- Test: `tests/architecture/test_news_intel_boundaries.py`
- Test: `tests/architecture/test_worker_runtime_contracts.py`

- [ ] **Step 1: Update architecture docs**

  In News Intel architecture, update the Item brief stage responsibility to:

  ```text
  Build bounded item/token/fact/provider packets plus a News-owned read-only context snapshot, reserve `news.item_brief`, execute through the shared `AgentExecutionGateway`, shape-validate the standard brief output, write the run ledger, upsert the current brief, and dirty page rows. Context tool results are DB-backed audit/input evidence, not business facts or mutation hooks.
  ```

  In `docs/AGENT_EXECUTION.md`, add a News-specific note:

  ```text
  News item brief does not use shared runtime tool-calling. Its context tools are deterministic, read-only News repository queries compiled into the material input packet before gateway execution.
  ```

- [ ] **Step 2: Add architecture guards**

  Extend `tests/architecture/test_news_intel_boundaries.py` with:

  ```python
  def test_news_item_brief_context_tools_do_not_use_runtime_tool_calling_or_cross_domain_tables() -> None:
      paths = [
          NEWS_INTEL_ROOT / "services/news_item_brief_context_tools.py",
          NEWS_INTEL_ROOT / "services/news_item_brief_context.py",
      ]
      combined = "\n".join(path.read_text() for path in paths if path.exists())

      forbidden_tokens = (
          "AgentStageSpec",
          "tools=",
          "tool_calls",
          "token_radar",
          "market_ticks",
          "pulse_candidates",
          "news_story_groups",
          "news_story_members",
          "news_context_items",
      )
      for token in forbidden_tokens:
          assert token not in combined
  ```

- [ ] **Step 3: Run final targeted verification**

  ```bash
  uv run ruff check \
    src/parallax/domains/news_intel \
    src/parallax/app/surfaces/cli/commands/ops.py \
    tests/unit/domains/news_intel \
    tests/integration/domains/news_intel \
    tests/unit/integrations/model_execution/test_news_item_brief_agent_client.py \
    tests/architecture/test_news_intel_boundaries.py
  ```

  Expected: exit 0.

  ```bash
  uv run pytest \
    tests/unit/domains/news_intel/test_news_item_brief_types.py \
    tests/unit/domains/news_intel/test_news_item_brief_context_tools.py \
    tests/unit/domains/news_intel/test_news_item_brief_context.py \
    tests/unit/domains/news_intel/test_news_item_brief_input.py \
    tests/unit/domains/news_intel/test_news_item_brief_stage.py \
    tests/unit/domains/news_intel/test_news_item_brief_validation.py \
    tests/unit/domains/news_intel/test_news_item_brief_worker.py \
    tests/unit/integrations/model_execution/test_news_item_brief_agent_client.py \
    tests/unit/domains/news_intel/test_news_page_projection.py \
    tests/integration/domains/news_intel/test_news_item_agent_brief_repository.py \
    tests/integration/domains/news_intel/test_news_repository.py \
    tests/integration/domains/news_intel/test_news_item_brief_schema_hard_cut.py \
    tests/unit/domains/news_intel/test_news_repository_queries.py \
    tests/unit/test_cli.py \
    tests/integration/test_cli.py \
    tests/architecture/test_news_intel_boundaries.py \
    -q
  ```

  Expected: exit 0.

  ```bash
  make test-architecture
  ```

  Expected: exit 0.

- [ ] **Step 4: Run full gate**

  ```bash
  make check-all
  ```

  Expected: exit 0. If full gate fails from unrelated pre-existing failures, capture exact failures in verification and run the targeted suite above to prove the News agent work.

- [ ] **Step 5: Commit docs and verification prep**

  ```bash
  git add src/parallax/domains/news_intel/ARCHITECTURE.md docs/AGENT_EXECUTION.md tests/architecture/test_news_intel_boundaries.py
  git commit -m "docs: document news item brief context tools"
  ```

## Acceptance Test Commands

- AC1, AC3, AC4:

  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_item_brief_input.py tests/unit/domains/news_intel/test_news_item_brief_worker.py -q
  ```

- AC2, AC9, AC10, AC11, AC12:

  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_item_brief_context_tools.py tests/unit/domains/news_intel/test_news_item_brief_context.py tests/integration/domains/news_intel/test_news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py -q
  ```

- AC5, AC6, AC13:

  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_item_brief_types.py tests/unit/domains/news_intel/test_news_item_brief_validation.py tests/unit/domains/news_intel/test_news_item_brief_stage.py -q
  ```

- AC7, AC8:

  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py tests/integration/domains/news_intel/test_news_item_brief_schema_hard_cut.py tests/integration/domains/news_intel/test_news_repository.py -q
  ```

- AC14, AC15, AC16:

  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py -q
  ```

- AC17, AC18:

  ```bash
  make test-architecture
  ```

## Verification

Create `docs/superpowers/plans/active/2026-06-03-news-agent-context-tools-hard-cut-verification.md` before declaring implementation complete. Include:

- Full `make check-all` output.
- If `make check-all` fails for unrelated reasons, exact failure excerpts and targeted News suite output.
- Coverage notes for P0/P1 tools.
- Skipped tests section.
- E2E golden path: one eligible provider-score news item produces packet v2 with four tool results, writes `news_item_agent_runs`, upserts v2 current brief, and page projection exposes compact v2 fields.
- Remaining risks and whether any should be appended to `docs/TECH_DEBT.md`.
