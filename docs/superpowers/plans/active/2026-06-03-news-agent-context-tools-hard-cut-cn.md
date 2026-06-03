# News Local Research Harness Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace packet-only News item brief with a deterministic News-local research harness: host policy selects bounded News-owned read tools, builds a compact research packet, and the existing model lane synthesizes v2 from base packet + research packet.

**Architecture:** Keep shared `AgentStageSpec` and `AgentExecutionGateway` unchanged. Add a News-local research policy, research packet compiler, tool registry, read-only tool executor, context budget/redaction/hash pipeline, v2 synthesizer prompt, v2 validation, and stale serving hard cut. `NewsItemBriefWorker` remains the only runtime writer for `news_item_agent_runs` and `news_item_agent_briefs`.

**Tech Stack:** Python 3.12, Pydantic v2, existing repository/session patterns, existing model gateway, `uv run pytest`, `uv run ruff`, `make test-architecture`.

---

**Status**: Draft
**Date**: 2026-06-03
**Owning spec**: `docs/superpowers/specs/active/2026-06-03-news-agent-context-tools-hard-cut-cn.md`
**Worktree**: `.worktrees/news-agent-context-tools-spec/`
**Branch**: `codex/news-agent-context-tools-spec`

## Design Decisions From The Rework

- This is a local harness, not a global kernel rewrite.
- P0 has one model stage: the v2 synthesizer. Tool selection is host-side deterministic policy, not an LLM planner.
- Tool execution is SELECT-only and News-owned.
- Runtime audit fields never affect freshness hashes.
- Old or missing-schema current briefs serve as `stale`.
- P0 ships five tools: `get_observation_history`, `search_news_archive`, `get_source_quality`, `get_target_news_context`, `get_fact_context`.
- The harness owns concrete windows and row/character clamps.
- P0 default windows are: archive 168h, target context 72h, source quality configured windows usually `24h` and `7d`; item-scoped observation/fact tools have no time window.
- Message growth is controlled at two layers: base packet material budget and tool-result material budget. The synthesizer never receives full historical article bodies.
- Score gates eligibility; content class and base-packet evidence gate tool selection. High score alone must not cause all tools to run.
- P0 is adaptive: context-worthy items run deterministic research tools -> synthesizer; self-contained or low-information-gain items run v2 synthesizer with a harness-created empty research plan.

## Live Data Calibration To Preserve During Implementation

The plan is calibrated against the live PostgreSQL store observed on 2026-06-03 through `~/.parallax/` runtime config:

- Past 24h had roughly 3.7k processed news items, about 400 score >= 80, and about 250 score >= 85.
- Current policy-eligible 8h high-score items already had current briefs; missing score >= 80 briefs were explained by age policy, not worker failure.
- Current ready brief latency was about p50 9s and p95 19s for the single-stage path, so P0 must avoid adding a second model call.
- `opennews-news` and `opennews-listing` are distinct `source_id`s but the same observed domain (`6551.io`); this is duplicate/coverage evidence, not independent confirmation.
- Past 24h multi-source-domain confirmation was effectively absent in the sampled data. Validators must require `source_domain_count > 1` or a future explicit independence policy.
- Facts are useful but content-class concentrated: ETF/listing/regulation/security/protocol items commonly have facts; low-signal, broad crypto-market, and geopolitics items commonly do not.
- Live fact candidates were `attention` rows, not accepted facts; prompts and validation must not let the model phrase them as independently verified facts.
- Token mentions are noisy for broad symbols and market subjects: `BTC`, `ETH`, `SOL`, `CL`, and synthetic `XYZ-*` style symbols can produce huge candidate sets. Target-context queries must prefer resolved `target_type`/`target_id`.
- Live HYPE ETF sample had hundreds of HYPE mentions in 72h; target context must return aggregate counts plus top compact evidence, not all matching rows.

## File-Level Edits

### Contracts and constants

- Modify `src/parallax/domains/news_intel/_constants.py`
  - Add research policy/tool catalog constants.
  - Bump synthesizer prompt/schema/validator/guardrail constants.
  - Add `NEWS_ITEM_RESEARCH_TOOL_CATALOG_VERSION`.

- Modify `src/parallax/domains/news_intel/types/news_item_brief.py`
  - Add:
    - `NewsItemResearchTodo`
    - `NewsItemResearchToolCall`
    - `NewsItemResearchBudget`
    - `NewsItemResearchPlan`
    - `NewsResearchToolResult`
    - `NewsContextTargetRef`
    - `NewsItemBriefBudgetReport`
    - `NewsItemBriefBasePacket`
    - `NewsItemBriefSynthesisPacket`
  - Add v2 fields to `NewsItemBriefPayload`.
  - Keep `extra="forbid"`.

### Prompt assembly

- Create `src/parallax/domains/news_intel/services/news_item_brief_prompt_assembly.py`
  - Build synthesizer prompt text from sections.
  - Include the research packet contract and evidence boundary.

- Keep `src/parallax/domains/news_intel/prompts/news_item_brief.md` on the current packet contract until the synthesis packet stage is wired.
  - Task 2 creates the canonical v2 synthesizer builder but must not switch the active markdown prompt early.
  - Task 5 switches the stage to the builder and `NewsItemBriefSynthesisPacket` in one hard cut.

### Tool registry and executor

- Create `src/parallax/domains/news_intel/services/news_item_research_tools.py`
  - Own `NewsResearchToolDefinition`, registry, schema validation, tool material hash helpers.

- Create `src/parallax/domains/news_intel/services/news_item_research_executor.py`
  - Own PreToolUse/PostToolUse hooks, budget enforcement, redaction, truncation, and result hashing.

- Create `src/parallax/domains/news_intel/services/news_item_research_policy.py`
  - Own deterministic research policy classification, tool-call selection, empty-plan construction, policy version, and reasons.

### Repository reads

- Modify `src/parallax/domains/news_intel/repositories/news_repository.py`
  - Add SELECT-only methods:
    - `get_news_observation_history(...)`
    - `search_news_archive(...)`
    - `get_source_quality_context_for_item(...)`
    - `get_target_news_context(...)`
    - `get_fact_context(...)`
    - cleanup helpers for stale current briefs.

### Model execution client

- Modify `src/parallax/integrations/model_execution/news_item_brief_agent_client.py`
  - Keep `brief_item(...)`, but make it accept synthesis packet.
  - Keep `request_audit(...)` for the synthesis stage and include research packet hashes in trace metadata.

### Worker orchestration

- Modify `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py`
  - Build budgeted base packet.
  - Run preliminary freshness gate.
  - Run deterministic research policy.
  - Execute tools with a repository session, outside model calls.
  - Build synthesis packet.
  - Run final freshness gate.
  - Call synthesizer.
  - Validate/persist.

### Validation, projection, and cleanup

- Modify `src/parallax/domains/news_intel/services/news_item_brief_validation.py`
  - Validate v2 payload and research grounding.

- Modify `src/parallax/domains/news_intel/services/news_page_projection.py`
  - Include compact v2 fields.
  - Return `stale` for old/missing schema.

- Modify `src/parallax/domains/news_intel/repositories/news_repository.py`
  - Apply same public detail stale guard.

- Create `src/parallax/domains/news_intel/services/news_item_brief_schema_hard_cut.py`
  - Cleanup through repository helpers only.

- Modify `src/parallax/app/surfaces/cli/parser.py`
- Modify `src/parallax/app/surfaces/cli/commands/ops.py`
  - Add cleanup command.

## Implementation Tasks

### Task 1: Add research harness contracts and version constants

**Files:**
- Modify: `src/parallax/domains/news_intel/_constants.py`
- Modify: `src/parallax/domains/news_intel/types/news_item_brief.py`
- Test: `tests/unit/domains/news_intel/test_news_item_brief_types.py`

- [ ] **Step 1: Write failing contract tests**

  Add tests:

  ```python
  def test_research_plan_allows_only_bounded_tool_calls() -> None:
      plan = NewsItemResearchPlan.model_validate(
          {
              "status": "ready",
              "research_todos": [
                  {"todo_id": "todo-1", "content_zh": "检查历史新闻", "status": "pending"}
              ],
              "tool_calls": [
                  {
                      "tool_call_id": "call-1",
                      "tool_name": "search_news_archive",
                      "input": {"query_terms": ["ETF"], "symbols": ["BTC"], "window_hours": 168, "limit": 8},
                      "purpose_zh": "确认数据库中是否已有同类新闻",
                      "expected_evidence": ["similar:item"],
                  }
              ],
              "budget": {"max_tool_calls": 5, "max_total_chars": 3000, "hard_max_total_chars": 6000, "max_rows_per_tool": 25},
              "policy_notes_zh": "",
              "skip_reason_zh": "",
              "evidence_refs": [],
          }
      )

      assert plan.tool_calls[0].tool_name == "search_news_archive"


  def test_research_tool_result_generated_at_is_not_material_identity() -> None:
      result = _tool_result(generated_at_ms=1_779_000_000_000)
      later = result.model_copy(update={"generated_at_ms": 1_779_000_060_000})

      assert news_research_tool_material_identity(result) == news_research_tool_material_identity(later)


  def test_base_budget_report_records_truncated_fact_lanes() -> None:
      packet = build_news_item_brief_base_packet(
          item=_item(),
          token_mentions=[],
          fact_candidates=[_long_fact(index) for index in range(60)],
          material_budget_chars=12_000,
      )

      assert packet.base_budget_report.original_fact_count == 60
      assert packet.base_budget_report.kept_fact_count < 60
      assert "fact_lanes_budget" in packet.base_budget_report.truncation_reasons


  def test_base_packet_exposes_allowed_context_targets_from_resolved_mentions() -> None:
      packet = build_news_item_brief_base_packet(
          item=_item(),
          token_mentions=[
              _mention(display_symbol="SOL", target_type="CexToken", target_id="cex_token:SOL", resolution_status="unique_by_context"),
              _mention(display_symbol="XYZ-CL", target_type=None, target_id=None, resolution_status="unknown_attention"),
          ],
          fact_candidates=[],
          material_budget_chars=12_000,
      )

      assert packet.allowed_context_targets[0].target_type == "CexToken"
      assert packet.allowed_context_targets[0].target_id == "cex_token:SOL"
      assert all(target.target_id != "XYZ-CL" for target in packet.allowed_context_targets)
  ```

- [ ] **Step 2: Run failing tests**

  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_item_brief_types.py -q
  ```

  Expected: FAIL because new types/constants do not exist.

- [ ] **Step 3: Implement contracts**

  Add constants:

  ```python
  NEWS_ITEM_RESEARCH_POLICY_VERSION = "news_item_research_policy_v1"
  NEWS_ITEM_RESEARCH_TOOL_CATALOG_VERSION = "news_item_research_tools_v1"
  NEWS_ITEM_BRIEF_PROMPT_VERSION = "news-item-brief-synthesizer-v1"
  NEWS_ITEM_BRIEF_SCHEMA_VERSION = "news_item_brief_v2"
  NEWS_ITEM_BRIEF_VALIDATOR_VERSION = "news_item_brief_validator_v4"
  NEWS_ITEM_BRIEF_GUARDRAIL_VERSION = "news_item_brief_guardrails_v4"
  ```

  Add strict Pydantic models for plan, tool calls, tool results, context target refs, budget report, base packet, and synthesis packet.

  `NewsItemBriefBasePacket` must include:

  ```python
  allowed_context_targets: list[NewsContextTargetRef]
  content_class: str | None
  base_budget_report: NewsItemBriefBudgetReport
  ```

  `NewsContextTargetRef` must include target type, target id, display symbol, resolution status, confidence, and target scope (`crypto`, `non_crypto`, or `unknown`). The harness builds this list from resolved News token mentions; research policy may only reference these refs.

  Add v2 brief fields:

  ```python
  novelty_status: Literal["new", "repeat", "update", "duplicate", "unclear"]
  confirmation_state: Literal["single_source", "multi_source_confirmed", "provider_only", "conflicting", "unclear"]
  source_consensus_zh: str
  retrieval_notes_zh: str
  retrieval_evidence_refs: list[str]
  research_todos_zh: list[str]
  used_tool_call_ids: list[str]
  ```

- [ ] **Step 4: Run tests**

  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_item_brief_types.py -q
  ```

  Expected: PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add src/parallax/domains/news_intel/_constants.py src/parallax/domains/news_intel/types/news_item_brief.py tests/unit/domains/news_intel/test_news_item_brief_types.py
  git commit -m "feat: add news research harness contracts"
  ```

### Task 2: Add runtime prompt assembly and synthesizer prompt builder

**Files:**
- Create: `src/parallax/domains/news_intel/services/news_item_brief_prompt_assembly.py`
- Read/guard: `src/parallax/domains/news_intel/prompts/news_item_brief.md`
- Test: `tests/unit/domains/news_intel/test_news_item_brief_prompt_assembly.py`

- [ ] **Step 1: Write failing prompt assembly tests**

  ```python
  def test_synthesizer_prompt_forbids_runtime_tools_and_external_data() -> None:
      prompt = build_news_item_brief_synthesizer_prompt()

      assert "不调用运行时工具" in prompt
      assert "不请求外部数据" in prompt
      assert "research_packet" in prompt
      assert "tool_results" in prompt


  def test_synthesizer_prompt_contains_research_packet_semantics() -> None:
      prompt = build_news_item_brief_synthesizer_prompt()

      assert "source_domain_count" in prompt
      assert "symbol_heuristic" in prompt
      assert "market_subject_heuristic" in prompt
      assert "attention facts" in prompt


  def test_active_markdown_prompt_remains_on_current_packet_until_stage_migration() -> None:
      prompt = ACTIVE_PROMPT_PATH.read_text(encoding="utf-8")

      assert "use only base_packet and research_packet" not in prompt
      assert "News Item Brief agent" in prompt
  ```

- [ ] **Step 2: Run failing tests**

  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_item_brief_prompt_assembly.py -q
  ```

  Expected: FAIL because prompt assembler does not exist.

- [ ] **Step 3: Implement prompt assembler**

  Implement section functions:

  - identity;
  - News boundary;
  - research packet contract;
  - research budget and truncation policy;
  - synthesizer input contract;
  - evidence/uncertainty policy.

  The synthesizer prompt must say: use only base packet and research packet; output only `NewsItemBriefPayload` v2. It must explicitly forbid upgrading heuristic matches into exact confirmation, treating same-domain source lanes as independent confirmation, or treating `attention` facts as accepted facts.

  Do not update the active markdown prompt in this task. Current runtime still sends `NewsItemBriefInputPacket`; changing the active markdown before the stage accepts `NewsItemBriefSynthesisPacket` creates a prompt/payload generation mismatch. The active prompt migration happens in Task 5.

- [ ] **Step 4: Run tests**

  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_item_brief_prompt_assembly.py -q
  ```

  Expected: PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add src/parallax/domains/news_intel/services/news_item_brief_prompt_assembly.py tests/unit/domains/news_intel/test_news_item_brief_prompt_assembly.py
  git commit -m "feat: assemble news research harness prompt builder"
  ```

### Task 3: Add News research tool registry and executor

**Files:**
- Create: `src/parallax/domains/news_intel/services/news_item_research_tools.py`
- Create: `src/parallax/domains/news_intel/services/news_item_research_executor.py`
- Test: `tests/unit/domains/news_intel/test_news_item_research_tools.py`
- Test: `tests/unit/domains/news_intel/test_news_item_research_executor.py`

- [ ] **Step 1: Write failing tool registry tests**

  ```python
  def test_tool_registry_exposes_only_p0_news_tools() -> None:
      registry = build_news_research_tool_registry()

      assert sorted(registry.tool_names()) == [
          "get_fact_context",
          "get_observation_history",
          "get_source_quality",
          "get_target_news_context",
          "search_news_archive",
      ]


  def test_tool_registry_semantic_capabilities_are_explicit() -> None:
      registry = build_news_research_tool_registry()

      assert registry["get_source_quality"].supports_confirmation is False
      assert registry["get_source_quality"].supports_source_health is True
      assert registry["get_target_news_context"].requires_allowed_context_target is True
      assert "symbol_heuristic" in registry["get_target_news_context"].result_basis_values


  def test_executor_rejects_unknown_and_mutation_tool_calls() -> None:
      result = execute_news_research_plan(
          news_repo=FakeNewsRepo(),
          plan=_plan_with_tool("delete_news_item", {}),
          now_ms=NOW_MS,
      )

      assert result.status == "failed"
      assert "unknown_tool" in result.error_codes


  def test_executor_rejects_target_context_ref_outside_base_allowlist() -> None:
      result = execute_news_research_plan(
          news_repo=FakeNewsRepo(),
          base_packet=_base_packet(allowed_context_targets=[_target_ref("CexToken", "cex_token:SOL")]),
          plan=_plan_with_tool(
              "get_target_news_context",
              {"target_refs": [{"target_type": "CexToken", "target_id": "cex_token:DOGE"}], "window_hours": 72, "limit": 12},
          ),
          now_ms=NOW_MS,
      )

      assert result.status == "failed"
      assert "target_ref_not_allowed" in result.error_codes
  ```

- [ ] **Step 2: Write failing budget/redaction tests**

  ```python
  def test_executor_redacts_sensitive_fields_and_hashes_material_result() -> None:
      repo = FakeNewsRepo(
          archive_rows=[
              {
                  "news_item_id": "news-2",
                  "title": "ETF update",
                  "provider_item_id": "secret",
                  "raw_payload_json": {"secret": True},
                  "evidence_ref": "similar:item:news-2",
              }
          ]
      )

      result = execute_news_research_plan(news_repo=repo, plan=_archive_plan(), now_ms=NOW_MS)
      payload = json.dumps(result.tool_results[0].model_dump(mode="json"), sort_keys=True)

      assert "provider_item_id" not in payload
      assert "raw_payload_json" not in payload
      assert result.tool_results[0].result_hash.startswith("sha256:")
  ```

- [ ] **Step 3: Run failing tests**

  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_item_research_tools.py tests/unit/domains/news_intel/test_news_item_research_executor.py -q
  ```

  Expected: FAIL because registry/executor do not exist.

- [ ] **Step 4: Implement registry and executor**

  Registry requirements:

  - one definition per P0 tool;
  - JSON input schema;
  - handler name;
  - source tables;
  - max rows/chars;
  - query version;
  - `supports_confirmation`;
  - `supports_source_health`;
  - `requires_allowed_context_target`;
  - allowed `result_basis` values;
  - concurrency-safe flag.

  Executor requirements:

  - validate tool name and input;
  - enforce max 5 calls and max 2 archive searches;
  - clamp archive to default/max 168h and limit 8;
  - clamp target context to default 72h, max 168h, and limit 12;
  - clamp observation history to limit 25;
  - clamp fact context to limit 20;
  - clamp query terms/symbols to max 5 for archive search;
  - clamp target refs to max 5 and reject refs absent from the base packet's `allowed_context_targets`;
  - clamp symbol fallbacks to max 3 and label all fallback-only rows as heuristic;
  - compact total material research output to target 3,000 chars and hard max 6,000 chars;
  - run PreToolUse checks;
  - call repository handler;
  - allow-list output fields;
  - truncate rows/chars deterministically;
  - compute material result hash excluding `generated_at_ms`, latency, usage, and run ids;
  - return skipped/failed tool results instead of raising for bounded query timeouts.

- [ ] **Step 5: Run tests**

  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_item_research_tools.py tests/unit/domains/news_intel/test_news_item_research_executor.py -q
  ```

  Expected: PASS.

- [ ] **Step 6: Commit**

  ```bash
  git add src/parallax/domains/news_intel/services/news_item_research_tools.py src/parallax/domains/news_intel/services/news_item_research_executor.py tests/unit/domains/news_intel/test_news_item_research_tools.py tests/unit/domains/news_intel/test_news_item_research_executor.py
  git commit -m "feat: add news research tool registry"
  ```

### Task 4: Add SELECT-only repository methods

**Files:**
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py`
- Test: `tests/integration/domains/news_intel/test_news_repository.py`
- Test: `tests/unit/domains/news_intel/test_news_repository_queries.py`

- [ ] **Step 1: Write failing repository tests**

  Add tests for:

  - observation history is bounded and public-safe;
  - archive search excludes the current item and is deterministic;
  - archive search does not scan full historical `body_text`;
  - archive search uses bounded branches rather than one broad multi-table `OR` scan;
  - token-only archive matches for broad subjects such as `BTC`, `ETH`, `SOL`, `CL`, or synthetic provider symbols stay `symbol_heuristic`;
  - source quality is targeted to item source and does not full-scan all sources;
  - source quality rows are exposed as lane/source health and cannot support independent confirmation;
  - target context returns only News-owned rows;
  - target context rejects target refs absent from `allowed_context_targets`;
  - target context uses exact `target_type`/`target_id` values from `news_token_mentions` and never synthesizes ids from display symbols;
  - target context prefers indexed `target_type`/`target_id` lookup over display-symbol lookup;
  - target context labels symbol-only matches as heuristic;
  - target context SQL for resolved refs uses `news_token_mentions.target_type` and `news_token_mentions.target_id`, not only `display_symbol` or `observed_symbol`;
  - broad fallback symbols are applied after a recent-item prefilter and return at most heuristic rows;
  - target context returns aggregate counts plus top compact evidence rows, not every matching news item;
  - observation history reports `source_domain_count` and marks same-domain multiple lanes as not independently confirmed;
  - fact context is item-scoped and bounded;
  - SQL does not reference Token Radar, Pulse, market, `news_story_*`, or `news_context_items`.

- [ ] **Step 2: Run failing tests**

  ```bash
  uv run pytest tests/integration/domains/news_intel/test_news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py -q
  ```

  Expected: FAIL for missing methods.

- [ ] **Step 3: Implement repository methods**

  Add:

  ```python
  def get_news_observation_history(self, *, news_item_id: str, limit: int = 25) -> dict[str, Any]: ...
  def search_news_archive(self, *, current_news_item_id: str, query_terms: Sequence[str], symbols: Sequence[str], window_hours: int, match_modes: Sequence[str], limit: int, now_ms: int | None = None) -> list[dict[str, Any]]: ...
  def get_source_quality_context_for_item(self, *, news_item_id: str) -> dict[str, Any]: ...
  def get_target_news_context(self, *, current_news_item_id: str, target_refs: Sequence[NewsContextTargetRef], symbol_fallbacks: Sequence[str], window_hours: int, limit: int, now_ms: int | None = None) -> list[dict[str, Any]]: ...
  def get_fact_context(self, *, news_item_id: str, include_rejected: bool = False, limit: int = 20) -> list[dict[str, Any]]: ...
  ```

  Implementation rules:

  - use allow-listed columns only;
  - fact context reads `news_fact_candidates`;
  - source quality reads current rows from `news_source_quality_rows`;
  - no raw payloads or provider internals;
  - archive search uses bounded branches and stable sort;
  - archive search returns compact rows only: item id, short title, published time, source role/trust tier, matched symbols, match reason, matching basis, match confidence, and compact current brief fields;
  - archive search must not return full historical body text;
  - source quality does not call all-source `list_source_status()`;
  - source quality returns health/classification context only, not `multi_source_confirmed`;
  - target context uses resolved target refs from the base packet first and marks symbol fallback as `symbol_heuristic` or `market_subject_heuristic`;
  - target context returns `counts`, `top_items`, `latest_items`, `source_domain_count`, `high_score_count`, `matching_basis`, and `truncated`, not a raw unbounded list;
  - target context does not use symbol fallback when an equivalent resolved target ref is available;
  - same aggregator domain with multiple source ids, such as `opennews-news` plus `opennews-listing`, is duplicate/coverage evidence, not `multi_source_confirmed`;
  - every method has deterministic ordering.

- [ ] **Step 4: Run tests**

  ```bash
  uv run pytest tests/integration/domains/news_intel/test_news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py -q
  ```

  Expected: PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add src/parallax/domains/news_intel/repositories/news_repository.py tests/integration/domains/news_intel/test_news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py
  git commit -m "feat: add news research repository reads"
  ```

### Task 5: Update the News item brief client for synthesis packets

**Files:**
- Modify: `src/parallax/domains/news_intel/services/news_item_brief_stage.py`
- Modify: `src/parallax/integrations/model_execution/news_item_brief_agent_client.py`
- Modify or retire active loading of: `src/parallax/domains/news_intel/prompts/news_item_brief.md`
- Test: `tests/unit/integrations/model_execution/test_news_item_brief_agent_client.py`

- [ ] **Step 1: Write failing client tests**

  ```python
  async def test_brief_item_uses_synthesis_packet_and_stage() -> None:
      gateway = FakeGateway(output=_ready_payload())
      client = NewsItemBriefAgentClient(agent_gateway=gateway)

      await client.brief_item(run_id="run-1", packet=_synthesis_packet(), reservation=_reservation())

      assert gateway.seen_stages[0].stage == "news_item_brief_synthesis"
      assert gateway.seen_stages[0].input_payload["research_packet"]["research_packet_hash"].startswith("sha256:")


  def test_request_audit_includes_research_hash_metadata() -> None:
      gateway = FakeGateway(output=_ready_payload())
      client = NewsItemBriefAgentClient(agent_gateway=gateway)

      audit = client.request_audit(run_id="run-1", packet=_synthesis_packet())

      assert audit["trace_metadata"]["research_packet_hash"].startswith("sha256:")
      assert audit["trace_metadata"]["tool_catalog_version"] == NEWS_ITEM_RESEARCH_TOOL_CATALOG_VERSION
  ```

- [ ] **Step 2: Run failing tests**

  ```bash
  uv run pytest tests/unit/integrations/model_execution/test_news_item_brief_agent_client.py -q
  ```

  Expected: FAIL until client accepts synthesis packets.

- [ ] **Step 3: Implement client methods**

  - Update `build_news_item_brief_stage(...)` to accept `NewsItemBriefSynthesisPacket`, set stage name `news_item_brief_synthesis`, use `build_news_item_brief_synthesizer_prompt()`, and send the synthesis packet material payload.
  - `brief_item(...)` builds synthesizer stage with synthesis packet.
  - Keep reservation lane `news.item_brief`; P0 still has one model call.
  - `request_audit(...)` uses the synthesis stage.
  - Trace metadata includes `phase="synthesis"`, `base_input_hash`, `research_packet_hash`, `tool_catalog_version`, and `synthesis_input_hash`.
  - Do not add `tools=` or native tool-call metadata to `AgentStageSpec`.

- [ ] **Step 4: Run tests**

  ```bash
  uv run pytest tests/unit/integrations/model_execution/test_news_item_brief_agent_client.py -q
  ```

  Expected: PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add src/parallax/domains/news_intel/services/news_item_brief_stage.py src/parallax/integrations/model_execution/news_item_brief_agent_client.py tests/unit/integrations/model_execution/test_news_item_brief_agent_client.py
  git commit -m "feat: pass news research packet to brief client"
  ```

### Task 6: Wire research policy, tools, and synthesizer into the worker

**Files:**
- Modify: `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py`
- Modify: `src/parallax/domains/news_intel/services/news_item_brief_input.py`
- Create: `src/parallax/domains/news_intel/services/news_item_research_policy.py`
- Test: `tests/unit/domains/news_intel/test_news_item_brief_worker.py`
- Test: `tests/unit/domains/news_intel/test_news_item_brief_input.py`
- Test: `tests/unit/domains/news_intel/test_news_item_research_policy.py`

- [ ] **Step 1: Write failing worker orchestration tests**

  ```python
  def test_research_policy_selects_fact_context_for_fact_bearing_truncated_item() -> None:
      decision = classify_news_item_research_policy(
          _base_packet(content_class="exchange_listing", fact_count=30, fact_truncated=True)
      )

      assert decision.needs_research is True
      assert "get_fact_context" in [call.tool_name for call in decision.research_plan.tool_calls]
      assert "fact_lanes_truncated" in decision.reasons


  def test_research_policy_empty_plan_for_low_signal_without_facts_or_resolved_targets() -> None:
      decision = classify_news_item_research_policy(
          _base_packet(content_class="low_signal", fact_count=0, allowed_context_targets=[])
      )

      assert decision.needs_research is False
      assert decision.empty_plan.status == "skip"


  async def test_worker_runs_research_tools_then_synthesizer() -> None:
      db = FakeDB([_candidate()])
      provider = FakeProvider(payload=_ready_payload())

      result = await _worker(db=db, provider=provider).run_once()

      assert result.processed == 1
      assert provider.call_sequence == ["brief_item"]
      assert db.news.tool_calls == ["search_news_archive"]
      run = db.news.runs[0]
      assert run["request_json"]["research_plan"]["tool_calls"][0]["tool_name"] == "search_news_archive"
      assert run["request_json"]["tool_results"][0]["result_hash"].startswith("sha256:")


  async def test_worker_does_not_hold_db_session_during_model_calls() -> None:
      db = FakeDB([_candidate()])
      provider = FakeProvider(payload=_ready_payload())

      await _worker(db=db, provider=provider).run_once()

      assert provider.db_session_seen_during_synthesis is False


  async def test_worker_fails_invalid_policy_tool_before_execution() -> None:
      db = FakeDB([_candidate()])
      provider = FakeProvider(payload=_ready_payload(), research_plan=_plan_with_unknown_tool())

      result = await _worker(db=db, provider=provider).run_once()

      assert result.failed == 1
      assert db.news.tool_calls == []
      assert db.news.current_briefs == []


  async def test_worker_empty_research_path_skips_tools_but_writes_v2() -> None:
      db = FakeDB([_candidate(content_class="low_signal", fact_candidates=[])])
      provider = FakeProvider(payload=_ready_payload())

      result = await _worker(db=db, provider=provider).run_once()

      assert result.processed == 1
      assert provider.call_sequence == ["brief_item"]
      assert db.news.tool_calls == []
      run = db.news.runs[0]
      assert run["request_json"]["research_plan"]["status"] == "skip"
      assert run["request_json"]["research_plan"]["tool_calls"] == []
      assert run["request_json"]["synthesis_input_hash"].startswith("sha256:")


  async def test_worker_parent_reservation_no_start_backpressure_does_not_claim() -> None:
      db = FakeDB([_candidate()])
      provider = FakeProvider(reservation_acquired=False)

      result = await _worker(db=db, provider=provider).run_once()

      assert result.skipped == 1
      assert db.news.claimed_targets == []
      assert db.news.runs == []
  ```

- [ ] **Step 2: Run failing tests**

  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_input.py tests/unit/domains/news_intel/test_news_item_research_policy.py -q
  ```

  Expected: FAIL until worker is wired.

- [ ] **Step 3: Implement worker orchestration**

  Worker sequence:

  ```text
  reserve -> claim -> load candidate -> eligibility
  -> build budgeted base packet with base_budget_report
  -> preliminary freshness skip
  -> deterministic research policy
  -> if context-worthy: execute research tools with repository session
  -> else: create empty NewsItemResearchPlan(status=skip, tool_calls=[])
  -> build synthesis packet
  -> final freshness skip
  -> synthesizer model call
  -> validate
  -> insert run
  -> upsert current brief
  -> enqueue page
  ```

  The base packet builder must enforce a deterministic material character budget before research policy runs. It records original and kept token/fact counts, truncation reasons, and excluded oversized lanes so the policy can decide whether `get_fact_context` is needed.

  Keep DB sessions closed during `brief_item()`.

  If reservation is denied before claim, behavior remains no claim and no ledger write.

- [ ] **Step 4: Run worker tests**

  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_input.py tests/unit/domains/news_intel/test_news_item_research_policy.py -q
  ```

  Expected: PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add src/parallax/domains/news_intel/runtime/news_item_brief_worker.py src/parallax/domains/news_intel/services/news_item_brief_input.py src/parallax/domains/news_intel/services/news_item_research_policy.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_input.py tests/unit/domains/news_intel/test_news_item_research_policy.py
  git commit -m "feat: orchestrate news local research harness"
  ```

### Task 7: Update validation, serving, and schema cleanup

**Files:**
- Modify: `src/parallax/domains/news_intel/services/news_item_brief_validation.py`
- Modify: `src/parallax/domains/news_intel/services/news_page_projection.py`
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py`
- Create: `src/parallax/domains/news_intel/services/news_item_brief_schema_hard_cut.py`
- Modify: `src/parallax/app/surfaces/cli/parser.py`
- Modify: `src/parallax/app/surfaces/cli/commands/ops.py`
- Test: `tests/unit/domains/news_intel/test_news_item_brief_validation.py`
- Test: `tests/unit/domains/news_intel/test_news_page_projection.py`
- Test: `tests/integration/domains/news_intel/test_news_repository.py`
- Test: `tests/integration/domains/news_intel/test_news_item_brief_schema_hard_cut.py`
- Test: `tests/unit/test_cli.py`
- Test: `tests/integration/test_cli.py`

- [ ] **Step 1: Write failing validation/serving tests**

  Add tests proving:

  - heuristic archive matches cannot support `multi_source_confirmed`;
  - multiple observation source ids under the same source domain cannot support `multi_source_confirmed`;
  - affected assets/targets can be grounded by base-packet or exact tool evidence;
  - `symbol_heuristic` and `market_subject_heuristic` rows cannot ground exact asset confirmation;
  - non-empty `tool_calls`, `tools`, or `handoffs` in synthesizer audit still reject publishable output;
  - old/missing schema page/detail payload is `stale`;
  - cleanup clears stale current briefs through repository helper and enqueues `page` + `brief_input`;
  - CLI parser requires exactly one of `--dry-run`/`--execute`.

- [ ] **Step 2: Run failing tests**

  ```bash
  uv run pytest \
    tests/unit/domains/news_intel/test_news_item_brief_validation.py \
    tests/unit/domains/news_intel/test_news_page_projection.py \
    tests/integration/domains/news_intel/test_news_repository.py \
    tests/integration/domains/news_intel/test_news_item_brief_schema_hard_cut.py \
    tests/unit/test_cli.py \
    tests/integration/test_cli.py \
    -q
  ```

  Expected: FAIL until validation/serving/cleanup are updated.

- [ ] **Step 3: Implement validation and serving**

  - Add v2 fields to compact serving payloads.
  - Return `status: "stale"` when schema is missing/mismatched.
  - Validate tool evidence and confidence semantics.
  - Keep no v1/v2 parser and no v1 translation.

- [ ] **Step 4: Implement cleanup**

  - Add repository methods:
    - `list_current_brief_ids_outside_schema(...)`
    - `clear_current_briefs_outside_schema(...)`
  - Service calls repository helpers, not direct service SQL writes.
  - CLI command: `ops cleanup-news-item-brief-schema-hard-cut --dry-run|--execute`.

- [ ] **Step 5: Run tests**

  ```bash
  uv run pytest \
    tests/unit/domains/news_intel/test_news_item_brief_validation.py \
    tests/unit/domains/news_intel/test_news_page_projection.py \
    tests/integration/domains/news_intel/test_news_repository.py \
    tests/integration/domains/news_intel/test_news_item_brief_schema_hard_cut.py \
    tests/unit/test_cli.py \
    tests/integration/test_cli.py \
    -q
  ```

  Expected: PASS.

- [ ] **Step 6: Commit**

  ```bash
  git add src/parallax/domains/news_intel/services/news_item_brief_validation.py src/parallax/domains/news_intel/services/news_page_projection.py src/parallax/domains/news_intel/repositories/news_repository.py src/parallax/domains/news_intel/services/news_item_brief_schema_hard_cut.py src/parallax/app/surfaces/cli/parser.py src/parallax/app/surfaces/cli/commands/ops.py tests/unit/domains/news_intel/test_news_item_brief_validation.py tests/unit/domains/news_intel/test_news_page_projection.py tests/integration/domains/news_intel/test_news_repository.py tests/integration/domains/news_intel/test_news_item_brief_schema_hard_cut.py tests/unit/test_cli.py tests/integration/test_cli.py
  git commit -m "feat: enforce news research brief serving contract"
  ```

### Task 8: Architecture docs and final verification

**Files:**
- Modify: `src/parallax/domains/news_intel/ARCHITECTURE.md`
- Modify: `docs/AGENT_EXECUTION.md`
- Test: `tests/architecture/test_news_intel_boundaries.py`
- Test: `tests/architecture/test_worker_runtime_contracts.py`

- [ ] **Step 1: Update architecture docs**

  Document:

  - News item brief is now adaptive: empty-plan synthesis or deterministic research policy -> local read-only tool executor -> synthesis.
  - There is no shared runtime tool loop.
  - Tools are input evidence, not business facts.
  - `NewsItemBriefWorker` remains the writer.

- [ ] **Step 2: Add architecture tests**

  Add guards that new News research harness files do not reference:

  - `token_radar`
  - `market_ticks`
  - `pulse_candidates`
  - `news_story_groups`
  - `news_story_members`
  - `news_context_items`
  - `tools=` on `AgentStageSpec`
  - raw provider payload fields in public tool outputs

- [ ] **Step 3: Run targeted verification**

  ```bash
  uv run ruff check \
    src/parallax/domains/news_intel \
    src/parallax/integrations/model_execution/news_item_brief_agent_client.py \
    src/parallax/app/surfaces/cli/parser.py \
    src/parallax/app/surfaces/cli/commands/ops.py \
    tests/unit/domains/news_intel \
    tests/integration/domains/news_intel \
    tests/unit/integrations/model_execution/test_news_item_brief_agent_client.py \
    tests/architecture/test_news_intel_boundaries.py
  ```

  ```bash
  uv run pytest \
    tests/unit/domains/news_intel/test_news_item_brief_types.py \
    tests/unit/domains/news_intel/test_news_item_brief_prompt_assembly.py \
    tests/unit/domains/news_intel/test_news_item_research_tools.py \
    tests/unit/domains/news_intel/test_news_item_research_executor.py \
    tests/unit/domains/news_intel/test_news_item_brief_input.py \
    tests/unit/domains/news_intel/test_news_item_research_policy.py \
    tests/unit/domains/news_intel/test_news_item_brief_worker.py \
    tests/unit/domains/news_intel/test_news_item_brief_validation.py \
    tests/unit/domains/news_intel/test_news_page_projection.py \
    tests/unit/integrations/model_execution/test_news_item_brief_agent_client.py \
    tests/integration/domains/news_intel/test_news_repository.py \
    tests/integration/domains/news_intel/test_news_item_brief_schema_hard_cut.py \
    tests/unit/domains/news_intel/test_news_repository_queries.py \
    tests/unit/test_cli.py \
    tests/integration/test_cli.py \
    tests/architecture/test_news_intel_boundaries.py \
    -q
  ```

  ```bash
  make test-architecture
  ```

  Expected: all exit 0.

- [ ] **Step 4: Run full gate**

  ```bash
  make check-all
  ```

  Expected: exit 0. If unrelated failures exist, capture exact failures and targeted suite output.

- [ ] **Step 5: Commit docs**

  ```bash
  git add src/parallax/domains/news_intel/ARCHITECTURE.md docs/AGENT_EXECUTION.md tests/architecture/test_news_intel_boundaries.py
  git commit -m "docs: document news local research harness"
  ```

## Acceptance Test Mapping

- AC1, AC2: `test_news_item_brief_worker.py`, `test_news_item_research_policy.py`, `test_news_item_brief_agent_client.py`
- AC3, AC4: `test_news_item_research_tools.py`, `test_news_item_research_executor.py`
- AC5, AC6: `test_news_repository.py`, `test_news_repository_queries.py`
- AC7: `test_news_item_brief_types.py`, `test_news_item_brief_input.py`
- AC8, AC9: `test_news_item_brief_validation.py`
- AC10, AC11, AC13: `make test-architecture`
- AC12: `test_news_page_projection.py`, `test_news_repository.py`
- AC14, AC15: `test_news_item_brief_worker.py`

## Latency Budget

Observed live baseline on 2026-06-03: current single-stage ready briefs were roughly p50 9s and p95 19s. The tool SQL itself is cheap at current scale; the P0 design avoids a second model stage. Treat the table below as an end-to-end budget for eligible non-skipped work, not as a guaranteed improvement.

| Phase | P50 | P95 | Notes |
|---|---:|---:|---|
| Empty-plan v2 path | 7-12s | 18-30s | No research tools; similar to current single-stage but v2 prompt/schema |
| Research tool execution | 50-500ms | 500-1500ms | Current DB is fast; broad symbol fallback is the main risk |
| Synthesizer stage | 7-12s | 18-30s | Similar to current model call, possibly larger due tool evidence |
| Context-worthy deterministic research path | 10-14s | 22-28s | Preliminary freshness skip avoids this on no-op work |

Regression guardrails:

- P50 total non-skipped latency should not exceed 2x the previous single-stage p50 after rollout.
- P95 total non-skipped latency should not exceed 2.5x the previous single-stage p95 after rollout.
- Research tool-call average should stay below 3 calls per synthesized ready brief.
- Symbol-fallback target-context calls should stay rare and observable as a separate metric.

Mitigations:

- no research tools for ineligible targets;
- preliminary freshness gate;
- max 5 tool calls;
- max 2 archive searches;
- content-class aware tool selection;
- prefer resolved target lookup over display-symbol fallback;
- bounded rows/chars;
- deterministic truncation;
- no DB session during model calls.

## Post-P0 Evolution Boundary

- P1 may add an LLM planner only for context-worthy ambiguous cases after P0 metrics prove deterministic policy misses important evidence.
- If P1 adds a planner, it must use `AgentExecutionGateway.try_reserve(..., scope="parent", child_lanes=("news.item_brief.planner", "news.item_brief.synthesizer"))` before claim, so no-start backpressure still does not claim work or write the business ledger.
- P1 planner output remains JSON intents only; tools stay host-side, read-only, registry-validated, compacted, and audited.
- Native `tools=` on `AgentStageSpec` remains out of scope until a separate shared-kernel spec exists.

## Verification Artifact

Before declaring implementation complete, create:

`docs/superpowers/plans/active/2026-06-03-news-local-research-harness-verification.md`

Include:

- full `make check-all` output or exact unrelated failure excerpts;
- targeted News suite output;
- E2E golden path summary;
- latency observations from unit/integration timings if available;
- list of P0 tools and their query versions;
- confirmation that no shared gateway/kernel changes were made.
