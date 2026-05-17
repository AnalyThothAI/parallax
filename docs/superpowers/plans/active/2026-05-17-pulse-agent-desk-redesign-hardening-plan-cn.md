# Pulse Agent Desk Redesign Hardening Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `superpowers:subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the review gaps found on 2026-05-17 so the Pulse Agent Desk redesign is production-safe, contract-accurate, and release-verifiable.

**Architecture:** Keep the existing two-stage `Investigator -> DecisionMaker` pipeline. Do not rewrite the agent architecture, worker scheduling, notification framework, or frontend page shell. Fix trust boundaries and contracts at the smallest responsible edges: stage audit extraction, final evidence validation, notification query/filtering, OpenAPI schema, detail UI projection, and generated docs regeneration.

**Tech Stack:** Python 3.13, PostgreSQL, Alembic, Pydantic v2, openai-agents-python SDK, pytest, ruff, React, TypeScript, Vitest, Vite.

---

## Resolved Decisions

- DecisionMaker fallback tool budget: **observe only**. Keep the current shared `PulseToolContext` and route budgets. Add audit metadata/tests so we can see fallback tool usage and budget exhaustion, but do not introduce a separate fallback budget in this pass.
- Detail UI: **v2 decision enters the Pulse detail page UI**. Show narrative, bull/bear views, playbook, and evidence links in the existing detail rail with minimal layout changes.
- `docs/generated/pulse-agent-desk-decisions.md`: **add a generator script** and wire it into `make docs-generated` instead of keeping it as a hand-written exception.
- Release stance: local green tests are not enough. Production release still requires a short canary soak with SQL/screenshot evidence.

## Scope

- In:
  - P1 correctness fixes from the deep review.
  - Small P2 fixes that support those P1 boundaries.
  - Targeted tests that prove the real dataflow path.
  - One generated-doc script for the decision log.
  - Detail UI projection for v2 decision fields.
- Out:
  - New agent framework.
  - New worker.
  - New table.
  - New decision semantics.
  - Large visual redesign of the detail page.
  - Separate DecisionMaker fallback budget.

## File Map

- Modify: `src/gmgn_twitter_intel/integrations/openai_agents/instructor_safety_net.py`
  - Preserve `RunResult` for the safety-net strict-success path without breaking existing social/watchlist callers.
- Modify: `src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py`
  - Persist tool calls on the safety-net path.
  - Validate final evidence IDs against the same allowlist as Investigator evidence.
  - Add tool-call count audit metadata for observability only.
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/queries/agent_tool_queries.py`
  - Prefer canonical event URLs from `events.event_payload_json->>'url'` when enriching evidence links.
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py`
  - Stop producing new `abstain_critic_veto` outcomes.
- Modify: `src/gmgn_twitter_intel/domains/notifications/services/notification_rules.py`
  - Push Signal Pulse status filtering into pagination.
  - Pass `factor_snapshot` through to SurfaceCard link rendering.
  - Include stable playbook structure in notification signature.
- Modify: `src/gmgn_twitter_intel/domains/notifications/services/pulse_surface_card.py`
  - Apply final notification-boundary safety filtering.
  - Derive GMGN links from `factor_snapshot.subject` when row fields are absent.
  - Enforce final hard length cap.
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/schemas.py`
  - Make Signal Pulse OpenAPI schema match runtime shape.
- Modify: `web/src/lib/types/frontend-contracts.ts`
  - Keep hand-written frontend contract aligned until OpenAPI becomes the only source.
- Modify: `web/src/features/signal-lab/model/pulseDetail.ts`
  - Build a v2 decision surface view model and fix stale Critic copy.
- Modify: `web/src/features/signal-lab/ui/PulseDetail/PulseAgentRail.tsx`
  - Render the v2 decision surface inside the existing rail.
- Modify: `web/src/features/signal-lab/ui/PulseDetail/PulseAgentRail.module.css`
  - Add minimal styles for the v2 decision surface.
- Create: `scripts/regen_pulse_agent_desk_decisions.py`
  - Regenerate `docs/generated/pulse-agent-desk-decisions.md` deterministically.
- Modify: `Makefile`
  - Add `docs-pulse-agent-desk-decisions` and include it in `docs-generated`.
- Modify: `tests/integration/test_docs_generated.py`
  - Treat `pulse-agent-desk-decisions.md` as an auto-generated file with an `AUTO-GENERATED` header.
- Add/modify tests:
  - `tests/unit/integrations/openai_agents/test_pulse_decision_two_stage.py`
  - `tests/unit/domains/notifications/test_pulse_surface_card.py`
  - `tests/unit/test_notification_rules.py`
  - `tests/contract/test_openapi_drift.py`
  - `tests/integration/test_pulse_desk_e2e.py`
  - `tests/integration/test_pulse_agent_desk_migration.py`
  - `web/tests/unit/features/signal-lab/pulseDetail.test.ts`
  - `web/tests/component/features/signal-lab/ui/PulseAgentRail.test.tsx`

---

## Task 1: Persist Safety-Net Tool Calls And Observe Tool Budget

**Intent:** Fix the default production path where `InstructorSafetyNet` hides the SDK `RunResult`, causing `input_json.tool_calls` and `investigation_tool_calls_count` to be empty even when tools ran. Keep fallback tool budget behavior unchanged; only make usage visible.

**Files:**
- Modify: `src/gmgn_twitter_intel/integrations/openai_agents/instructor_safety_net.py`
- Modify: `src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py`
- Test: `tests/unit/integrations/openai_agents/test_pulse_decision_two_stage.py`

- [ ] Step 1: Add a failing unit test for the safety-net strict-success path.

  Test shape:

  ```python
  async def test_safety_net_strict_success_persists_tool_calls() -> None:
      # Arrange a fake safety net that returns a valid InvestigationReport,
      # audit_extra, and an SDK-like result object with new_items tool calls.
      # Run _run_stage through OpenAIAgentsPulseDecisionClient.
      # Assert stage.input_json["tool_calls"] contains get_target_recent_tweets.
      # Assert trace_metadata_json includes tool_calls_count_before/after/delta.
  ```

  Expected before implementation: `tool_calls` is `[]` or absent because `result_obj` is `None`.

- [ ] Step 2: Preserve backwards compatibility in `InstructorSafetyNet.run_with_safety_net`.

  Implementation rule:
  - Add keyword-only parameter `return_result: bool = False`.
  - When `return_result=False`, keep returning the existing two-tuple `(final_output, audit_extra)` so social/watchlist clients do not change.
  - When `return_result=True`, return `(final_output, audit_extra, result)` on strict SDK success.
  - When instructor reask is used, return `(obj, audit_extra, None)` because there is no valid SDK `RunResult` to extract.

- [ ] Step 3: Call safety net with `return_result=True` from `OpenAIAgentsPulseDecisionClient._run_stage`.

  Implementation rule:
  - Unpack `final_output, audit_extra, result_obj`.
  - Keep `_with_tool_calls(input_payload, result_obj)` unchanged so extraction remains single-source.
  - Capture `tool_calls_count_before = tool_ctx.tool_calls_count` before the run and `tool_calls_count_after` after the run.
  - Add these metadata keys to both success and failure `trace_metadata_json`:
    - `tool_calls_count_before`
    - `tool_calls_count_after`
    - `tool_calls_count_delta`

- [ ] Step 4: Add an observability-only test for DecisionMaker fallback budget.

  Test shape:

  ```python
  async def test_decision_maker_fallback_budget_is_observed_not_redefined() -> None:
      # Use one shared PulseToolContext.
      # Simulate investigator consuming part of the budget.
      # Run decision_maker with a fallback tool call.
      # Assert the same shared counter is used.
      # Assert trace metadata records before/after/delta.
      # Do not assert a new independent fallback budget.
  ```

- [ ] Step 5: Run targeted tests.

  ```bash
  uv run pytest tests/unit/integrations/openai_agents/test_pulse_decision_two_stage.py -q
  ```

---

## Task 2: Validate FinalDecision Evidence And Prefer Canonical URLs

**Intent:** Prevent DecisionMaker from persisting hallucinated or unrelated evidence IDs. Keep final evidence enrichment simple and deterministic.

**Files:**
- Modify: `src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/queries/agent_tool_queries.py`
- Test: `tests/unit/integrations/openai_agents/test_pulse_decision_two_stage.py`
- Test: `tests/unit/integrations/openai_agents/tools/test_tools.py` or a new query-focused unit test if that is the local pattern.

- [ ] Step 1: Add failing tests for final evidence allowlist.

  Test cases:
  - `FinalDecision.evidence_event_ids=["unrelated-event"]` fails when the ID is not in context, tool contributions, or Investigator supporting IDs.
  - `FinalDecision.bull_view.supporting_event_ids=["unrelated-event"]` fails the same way.
  - IDs from `context.evidence_event_ids`, `context.source_event_ids`, `tool_ctx.contributed_event_ids`, and `InvestigationReport` supporting IDs pass.

- [ ] Step 2: Add `_validate_final_evidence_ids()`.

  Implementation rule:
  - Allowed IDs are:
    - `context.evidence_event_ids`
    - `context.source_event_ids`
    - `tool_ctx.contributed_event_ids`
    - `investigation.bull_observation.supporting_event_ids`
    - `investigation.bear_observation.supporting_event_ids`
  - Validate:
    - `final.evidence_event_ids`
    - `final.bull_view.supporting_event_ids`
    - `final.bear_view.supporting_event_ids`
  - On unknown IDs, mark the DecisionMaker step failed with `_mark_step_failed(...)` and raise `PulseStageFailure`, mirroring the Investigator guard.

- [ ] Step 3: Call `_validate_final_evidence_ids()` immediately after `FinalDecision.model_validate(...)` and before `_enrich_evidence_urls(...)`.

- [ ] Step 4: Prefer canonical event URLs.

  Implementation rule in `fetch_evidence_event_urls()`:
  - Select `event_payload_json->>'url'` as `canonical_url`.
  - Return `canonical_url` when non-empty.
  - Fall back to the existing `https://x.com/{author_handle}/status/{tweet_id}` builder only when canonical URL is absent.
  - Keep DB errors best-effort, but add a warning log so schema/tool-pool problems are visible.

- [ ] Step 5: Run targeted tests.

  ```bash
  uv run pytest tests/unit/integrations/openai_agents/test_pulse_decision_two_stage.py tests/unit/integrations/openai_agents/tools/test_tools.py -q
  ```

---

## Task 3: Fix Notification Pagination And Harden SurfaceCard

**Intent:** Stop status-specific notifications from being starved by unrelated statuses, and make the notification renderer safe even if old/manual data bypassed upstream validators.

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/notifications/services/notification_rules.py`
- Modify: `src/gmgn_twitter_intel/domains/notifications/services/pulse_surface_card.py`
- Test: `tests/unit/test_notification_rules.py`
- Test: `tests/unit/domains/notifications/test_pulse_surface_card.py`

- [ ] Step 1: Add failing pagination test.

  Test shape:

  ```python
  def test_signal_pulse_notification_status_filter_is_pushed_into_pagination() -> None:
      # Configure rule.statuses=["trade_candidate"].
      # Fake pulse.list_candidates should record calls.
      # Return many token_watch rows for status=None and one trade_candidate row for status="trade_candidate".
      # Assert engine calls list_candidates(status="trade_candidate", ...).
      # Assert the trade_candidate notification is emitted.
  ```

- [ ] Step 2: Push status filtering into `list_candidates`.

  Implementation rule:
  - Loop `for scope in scopes` and `for status in sorted(statuses)`.
  - Call `self.pulse.list_candidates(..., status=status, ...)`.
  - Keep the `seen` set so candidates duplicated across scopes/statuses are still emitted once.
  - Keep the post-query status guard as a defensive assertion, but it should no longer be the primary filter.

- [ ] Step 3: Add SurfaceCard safety tests.

  Test cases:
  - `narrative_thesis_zh` containing forbidden execution language is not rendered.
  - bull/bear `thesis_zh` containing forbidden execution language is not rendered.
  - playbook `watch_signals` / `exit_triggers` entries containing forbidden execution language are removed.
  - final body length is always `<= 2500`.
  - GMGN link is rendered from `factor_snapshot.subject.chain/address` when `row.chain/address` are missing.

- [ ] Step 4: Harden `render_pulse_surface_card`.

  Implementation rule:
  - Import and use `contains_trading_execution_instruction` from `gmgn_twitter_intel.domains.pulse_lab.types.agent_decision`.
  - Add `_safe_text(value: Any) -> str` that returns `""` for forbidden text.
  - Add `_safe_list(values: Any) -> list[str]` that filters forbidden entries and empty strings.
  - Use safe text/list in narrative, bull, bear, and playbook rendering.
  - Change `_render_links(...)` to accept `factor_snapshot` and `asset_profile`.
  - Resolve GMGN chain/address in this order:
    1. `row.chain` / `row.address`
    2. `factor_snapshot.subject.chain` / `factor_snapshot.subject.address`
    3. `asset_profile.identity.chain` / `asset_profile.identity.address`
  - After degradation tiers, apply a final hard cap:

    ```python
    return body if len(body) <= _MAX_BODY_CHARS else body[: _MAX_BODY_CHARS - 3].rstrip() + "..."
    ```

- [ ] Step 5: Include stable playbook structure in notification signature.

  Implementation rule:
  - Continue excluding free text.
  - Add stable fields:
    - `playbook_has_playbook`
    - `playbook_monitoring_horizon`
    - counts of safe `watch_signals` and `exit_triggers`
  - Do not hash raw thesis text.

- [ ] Step 6: Run targeted tests.

  ```bash
  uv run pytest tests/unit/test_notification_rules.py tests/unit/domains/notifications/test_pulse_surface_card.py -q
  ```

---

## Task 4: Align Signal Pulse OpenAPI With Runtime Shape

**Intent:** Make generated OpenAPI types describe the actual `/signal-lab/pulse` payload so future frontend/API callers do not rely on stale `recommendation` or generic `JsonObject[]`.

**Files:**
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/schemas.py`
- Modify after generation: `docs/generated/openapi.json`
- Modify after generation: `web/src/lib/types/openapi.ts`
- Test: `tests/contract/test_openapi_drift.py`

- [ ] Step 1: Add schema classes for the v2 decision surface.

  Minimum schema classes:
  - `SignalPulseBullBearView`
  - `SignalPulsePlaybook`
  - `SignalPulseDecision`
  - Optional small schemas for `target` / `fact_card` only if it keeps the file readable; otherwise leave those as `JsonObject`.

  Required `SignalPulseDecision` fields:
  - `route`
  - `recommendation`
  - `confidence`
  - `summary_zh`
  - `abstain_reason`
  - `narrative_archetype`
  - `narrative_thesis_zh`
  - `bull_view`
  - `bear_view`
  - `playbook`
  - `evidence_event_ids`
  - `evidence_event_urls`
  - `invalidation_conditions`
  - `residual_risks`

- [ ] Step 2: Change `SignalPulseData.items` from `list[JsonObject]` to `list[SignalPulseItem]`.

- [ ] Step 3: Add missing list metadata fields to `SignalPulseData`.

  Required fields:
  - `health: JsonObject | None`
  - `returned_count: int | None`

- [ ] Step 4: Change `SignalPulseItem`.

  Implementation rule:
  - Replace old `recommendation` field with `decision: SignalPulseDecision | None`.
  - Keep broad `JsonObject` fields for existing large nested objects to avoid over-modeling.
  - Keep `stages: SignalPulseStages | None`.

- [ ] Step 5: Regenerate contracts.

  ```bash
  make regen-contract
  uv run pytest tests/contract -m contract -q
  ```

---

## Task 5: Render v2 Decision In The Pulse Detail UI

**Intent:** Surface the actual v2 decision in the detail page without redesigning the page. Put it in the existing Agent rail so the operator sees narrative, bull/bear, playbook, and evidence links together with stage audit cards.

**Files:**
- Modify: `web/src/features/signal-lab/model/pulseDetail.ts`
- Modify: `web/src/features/signal-lab/ui/PulseDetail/PulseAgentRail.tsx`
- Modify: `web/src/features/signal-lab/ui/PulseDetail/PulseAgentRail.module.css`
- Modify: `web/tests/fixtures/appRouteFixtures.ts`
- Test: `web/tests/unit/features/signal-lab/pulseDetail.test.ts`
- Test: `web/tests/component/features/signal-lab/ui/PulseAgentRail.test.tsx`

- [ ] Step 1: Add `DecisionSurfaceView` to `pulseDetail.ts`.

  Shape:

  ```ts
  export type DecisionSurfaceView = {
    route: string;
    recommendation: string;
    confidenceLabel: string;
    narrative: { archetype: string; thesis: string } | null;
    bull: DecisionViewSide | null;
    bear: DecisionViewSide | null;
    playbook: {
      monitoringHorizon: string;
      watchSignals: string[];
      exitTriggers: string[];
    } | null;
    evidenceLinks: Array<{ eventId: string; url: string }>;
  };
  ```

- [ ] Step 2: Add `decisionSurface: DecisionSurfaceView | null` to `AgentRailView`.

  Implementation rule:
  - Build it from `item.decision`.
  - Return `null` only when no v2 fields are present.
  - Do not parse legacy analyst/critic/judge response bodies.

- [ ] Step 3: Fix mixed v2 + legacy stage visibility.

  KISS rule:
  - Always render v2 stages if present.
  - Also append legacy placeholder cards if legacy stage rows exist.
  - `isLegacy` should mean "only legacy stages exist"; add `hasLegacyStages` if the UI needs a notice for mixed rows.

- [ ] Step 4: Replace stale mismatch copy.

  New note:

  ```ts
  "策略门将该资产推到 top 区间，但 Agent 最终置信度偏低。请核对调研、决策和证据链接。"
  ```

- [ ] Step 5: Render `DecisionSurfaceCard` in `PulseAgentRail.tsx`.

  Placement:
  - After mismatch.
  - Before stage cards.

  Display:
  - compact header: route, recommendation, confidence
  - narrative: archetype + thesis
  - bull and bear cards when present
  - playbook watch/exit lists when present
  - evidence links as normal anchors

- [ ] Step 6: Add minimal CSS.

  Constraints:
  - No nested cards inside cards.
  - Keep compact rail typography.
  - No new hero or decorative layout.
  - Ensure long Chinese/URLs wrap.

- [ ] Step 7: Add tests.

  Test cases:
  - `buildPulseDetailView` exposes narrative, bull/bear, playbook, and evidence links.
  - `PulseAgentRail` renders these v2 decision fields.
  - legacy-only rows still render placeholder cards.
  - mixed v2+legacy rows render v2 stages and legacy placeholders.
  - mismatch copy no longer mentions three-stage/Critic.

- [ ] Step 8: Run frontend targeted tests.

  ```bash
  cd web
  npm test -- --run web/tests/unit/features/signal-lab/pulseDetail.test.ts web/tests/component/features/signal-lab/ui/PulseAgentRail.test.tsx
  ```

---

## Task 6: Generate `pulse-agent-desk-decisions.md`

**Intent:** Keep `docs/generated/` honest. The decision log can live there only if it is regenerated by a script and checked by `make docs-generated`.

**Files:**
- Create: `scripts/regen_pulse_agent_desk_decisions.py`
- Modify: `Makefile`
- Modify: `docs/generated/README.md`
- Modify: `docs/generated/pulse-agent-desk-decisions.md`
- Modify: `tests/integration/test_docs_generated.py`

- [ ] Step 1: Create `scripts/regen_pulse_agent_desk_decisions.py`.

  Implementation rule:
  - Write deterministic Markdown.
  - First line must contain `AUTO-GENERATED`.
  - Include the six original OQ decisions plus the 2026-05-17 hardening decisions:
    - fallback budget observe-only
    - detail UI includes v2 decision
    - generated script owns this file
    - live canary remains release gate
  - Do not read runtime DB.

- [ ] Step 2: Add Makefile target.

  Change:

  ```make
  .PHONY: docs-generated docs-db-schema docs-cli-help docs-score-versions docs-ws-protocol docs-pulse-agent-desk-decisions

  docs-generated: docs-db-schema docs-cli-help docs-score-versions docs-ws-protocol docs-pulse-agent-desk-decisions

  docs-pulse-agent-desk-decisions:
  	@uv run python scripts/regen_pulse_agent_desk_decisions.py
  ```

- [ ] Step 3: Move `pulse-agent-desk-decisions.md` from `GENERATED_REPORTS` to `AUTO_GENERATED` in `tests/integration/test_docs_generated.py`.

- [ ] Step 4: Run docs generation.

  ```bash
  make docs-generated
  uv run pytest tests/integration/test_docs_generated.py -q
  ```

---

## Task 7: Add Real Integration Coverage For The Dataflow

**Intent:** Replace false confidence from fake-only E2E with one small real Postgres path. Stub only the LLM output; use real tables/repositories for persistence and read models.

**Files:**
- Modify: `tests/integration/test_pulse_desk_e2e.py`
- Modify: `tests/integration/test_pulse_agent_desk_migration.py`
- Optional helper: `tests/postgres_test_utils.py` only if an existing helper is missing.

- [ ] Step 1: Keep the existing synthetic E2E if useful, but rename its test/docstring so it is not presented as the only full E2E.

- [ ] Step 2: Add one real Postgres integration test.

  Required setup:
  - Use `connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)`.
  - Run `reset_postgres_schema(conn)`.
  - Use real `PulseRepository`.
  - Insert candidate/job/run/step data through repository methods where possible.
  - Stub only the LLM client result.

  Required assertions:
  - `pulse_candidates.decision_json` contains v2 fields.
  - `pulse_agent_run_steps` contains `investigator` and `decision_maker`.
  - investigator step `input_json.tool_calls` is non-empty when the stub simulates tool calls.
  - `SignalPulseService.candidate(...)` projects `decision.playbook`, `bull_view`, and stage data.
  - `NotificationRuleEngine.evaluate(...)` emits one `signal_pulse_candidate` notification.
  - notification dedup key contains the stable signature.
  - notification body contains v2 decision surface and evidence URL.

- [ ] Step 3: Add a read-only tool pool integration test.

  Required assertions:
  - A pool/connection created with `read_only=True` rejects an `INSERT`.
  - Tool query functions can read seeded rows through a read-only connection.

- [ ] Step 4: Add migration rollback-after-v2-rows test.

  Flow:
  - Upgrade to `20260516_0050`.
  - Insert `investigator` / `decision_maker` rows.
  - Downgrade to `20260516_0049`.
  - Assert downgrade succeeds because the old constraint is also `NOT VALID`.
  - Assert historical v2 rows remain queryable.

- [ ] Step 5: Run integration tests.

  ```bash
  uv run pytest tests/integration/test_pulse_desk_e2e.py tests/integration/test_pulse_agent_desk_migration.py -q
  ```

---

## Task 8: Final Verification And Release Gate

**Intent:** Finish with evidence, not vibes. Local correctness and canary behavior both need proof before full release.

**Files:**
- Modify: `docs/superpowers/plans/active/2026-05-16-pulse-agent-desk-redesign-verification-cn.md`
- Optional modify: `docs/superpowers/plans/active/2026-05-16-pulse-agent-desk-redesign-plan-cn.md`

- [ ] Step 1: Run full local gates.

  ```bash
  uv run ruff check .
  uv run pytest -x
  cd web && npm test -- --run && npm run build && cd ..
  make regen-contract
  make docs-generated
  uv run alembic upgrade head
  uv run alembic downgrade -1
  uv run alembic upgrade head
  ```

- [ ] Step 2: Verify generated artefacts are clean.

  ```bash
  git diff -- docs/generated/openapi.json web/src/lib/types/openapi.ts docs/generated/pulse-agent-desk-decisions.md
  uv run pytest tests/contract -m contract tests/integration/test_docs_generated.py -q
  ```

- [ ] Step 3: Run frontend browser smoke after implementation.

  Required checks:
  - Pulse detail page loads.
  - v2 decision card is visible.
  - narrative/bull/bear/playbook text wraps.
  - evidence links are clickable anchors.
  - legacy placeholder still renders for legacy fixtures.

- [ ] Step 4: Run 30-minute canary before full release.

  Required evidence:
  - stage distribution SQL output
  - sample `input_json.tool_calls` from investigator stage
  - sample `decision_json.evidence_event_urls`
  - notification sample with GMGN/X/Pulse links
  - detail page screenshot
  - error count / timeout count

- [ ] Step 5: Update verification doc honestly.

  Rule:
  - Mark local gates complete only after commands pass.
  - Keep canary/live items unchecked until they are actually run.
  - Note any skipped command and why.

---

## Definition Of Done

- No P1 review finding remains reproducible.
- OpenAPI generated types describe the real Signal Pulse item/list shape.
- Detail page visibly renders v2 decision fields.
- Signal Pulse notifications cannot be starved by unrelated statuses.
- SurfaceCard applies a final safety boundary and hard length cap.
- `docs/generated/pulse-agent-desk-decisions.md` is script-generated.
- At least one real Postgres integration test covers persistence/read-model/notification flow.
- Full local gates pass.
- Canary gate is documented before full production rollout.
