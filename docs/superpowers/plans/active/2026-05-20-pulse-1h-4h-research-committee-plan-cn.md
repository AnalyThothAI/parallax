# Pulse 1h/4h Research Committee Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hard-cut Signal Lab Pulse away from unstable 5m/watched-only flow and rebuild Pulse Agent around 1h/4h discovery plus a packet-only research committee.

**Architecture:** Keep `PulseCandidateWorker` as the only Pulse read-model writer. Add explicit horizon/source-quality policy before admission, make material evidence changes visible to the edge state machine, replace the two-stage agent with `signal_analyst -> bear_case -> risk_portfolio_judge`, and update API/frontend defaults to 4h/all with 1h as the early-confirmation lane.

**Tech Stack:** Python 3.13, FastAPI, psycopg, Pydantic v2, OpenAI Agents gateway, pytest, React 19, TanStack Query, Vite/Vitest.

---

**Status**: Draft
**Date**: 2026-05-20
**Owning spec**: `docs/superpowers/specs/active/2026-05-20-pulse-1h-4h-research-committee-cn.md`
**Worktree**: `.worktrees/pulse-1h-4h-research-committee/`
**Branch**: `codex/pulse-1h-4h-research-committee`

## Non-Compatibility Rule

This is a hard cut. Do not add aliases, fallback branches, dual stage names, config compatibility shims, or runtime paths that keep old 5m Pulse behavior alive.

Allowed:

- Existing historical `pulse_candidates` rows remain readable by candidate id if they already exist.
- Token Radar may continue to compute 5m rows for non-Pulse surfaces.
- Existing Pydantic helper primitives can remain if they are still used by new stage schemas.

Forbidden:

- Accepting `pulse_candidate.windows` containing `5m` or `24h`.
- Silently filtering old worker config and continuing startup.
- Keeping `evidence_debate` or `decision_maker` as new-run stage names.
- Publishing watched-only or matched-only single-author rows in default discovery.
- Adding `legacy_`, `compat_`, `old_`, or `v1` runtime branches to support removed behavior.

## Pre-flight

- [ ] Confirm spec approval in this thread: user asked to write the plan and explicitly requested no compatibility code.
- [ ] Create implementation worktree:
  ```bash
  git worktree add .worktrees/pulse-1h-4h-research-committee -b codex/pulse-1h-4h-research-committee main
  ```
- [ ] Verify worktree state:
  ```bash
  cd .worktrees/pulse-1h-4h-research-committee
  git worktree list
  git status --short
  git branch --show-current
  ```
  Expected: current branch is `codex/pulse-1h-4h-research-committee`; status is clean except files intentionally edited by this plan.
- [ ] Confirm real runtime config paths before live-data evaluation:
  ```bash
  uv run gmgn-twitter-intel config
  ```
  Expected: `config_path` and `workers_config_path` point to `/Users/qinghuan/.gmgn-twitter-intel/`. Do not print secrets.
- [ ] Run focused baseline tests before edits:
  ```bash
  uv run pytest tests/unit/test_pulse_candidate_worker.py tests/unit/test_pulse_edge_events.py tests/unit/test_pulse_decision_agent_client.py tests/unit/test_signal_pulse_service.py tests/unit/test_api_signal_pulse_contract.py -q
  ```
- [ ] Run frontend baseline build:
  ```bash
  cd web && npm run build
  ```

Known-failing baseline tests:

- None expected. If a baseline command fails, record exact failure in the eventual verification artefact before implementation begins.

## File-Level Edits

### New policy and evaluation modules

- Create `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_horizon_policy.py`
  - Owns Pulse-specific horizon constants and validation.
  - Public functions:
    ```python
    PULSE_PRIMARY_WINDOWS: tuple[str, ...] = ("1h", "4h")
    PULSE_CONTEXT_WINDOWS: tuple[str, ...] = ("24h",)
    PULSE_EXCLUDED_WINDOWS: tuple[str, ...] = ("5m",)
    PULSE_DEFAULT_PUBLIC_WINDOW = "4h"
    PULSE_EARLY_CONFIRMATION_WINDOW = "1h"

    def validate_pulse_agent_windows(windows: tuple[str, ...]) -> tuple[str, ...]:
        invalid = tuple(window for window in windows if window not in PULSE_PRIMARY_WINDOWS)
        if invalid:
            raise ValueError(f"Pulse Agent windows must be 1h/4h only: {invalid}")
        return tuple(windows)

    def is_primary_pulse_window(window: str) -> bool:
        return str(window or "").strip() in PULSE_PRIMARY_WINDOWS

    def normalize_signal_pulse_window(window: str) -> str:
        value = str(window or "").strip() or PULSE_DEFAULT_PUBLIC_WINDOW
        if value not in PULSE_PRIMARY_WINDOWS:
            raise ValueError(f"invalid Signal Pulse window: {value}")
        return value
    ```
  - `validate_pulse_agent_windows` raises `ValueError` for anything outside `("1h", "4h")`; no filtering.

- Create `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_source_quality.py`
  - Owns Pulse-only source quality gating; do not modify Token Radar scoring in `token_intel`.
  - Public model and functions:
    ```python
    @dataclass(frozen=True, slots=True)
    class PulseSourceQuality:
        independent_author_count: int
        effective_author_count: float | None
        top_author_share: float | None
        duplicate_text_share: float | None
        watched_mentions: int
        matched_only: bool
        public_corroboration_seen: bool
        single_author_dependency: bool
        public_trade_watch_allowed: bool
        default_public_risk_reject_allowed: bool
        reasons: tuple[str, ...]

    def source_quality_from_factor_snapshot(
        factor_snapshot: dict[str, Any],
        *,
        scope: str,
    ) -> PulseSourceQuality:
        return PulseSourceQuality(
            independent_author_count=independent_author_count,
            effective_author_count=effective_author_count,
            top_author_share=top_author_share,
            duplicate_text_share=duplicate_text_share,
            watched_mentions=watched_mentions,
            matched_only=scope == "matched",
            public_corroboration_seen=independent_author_count >= 2,
            single_author_dependency=independent_author_count < 2,
            public_trade_watch_allowed=public_trade_watch_allowed,
            default_public_risk_reject_allowed=default_public_risk_reject_allowed,
            reasons=tuple(reasons),
        )

    def public_trade_watch_allowed(quality: PulseSourceQuality) -> bool:
        return quality.public_trade_watch_allowed

    def default_risk_reject_allowed(quality: PulseSourceQuality) -> bool:
        return quality.default_public_risk_reject_allowed
    ```
  - Rule: `public_trade_watch_allowed` requires `independent_author_count >= 2` or `watched_mentions > 0 and public_corroboration_seen is True`.
  - Rule: `default_public_risk_reject_allowed` is false when `matched_only`, `single_author_dependency`, or `top_author_share >= 0.7`.

- Create `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_policy_evaluator.py`
  - Pure SQL/read-only evaluation helpers for current vs proposed policy.
  - Public function:
    ```python
    def build_pulse_policy_evaluation(conn: Any, *, now_ms: int, lookback_hours: int = 24) -> dict[str, Any]:
        radar_rows = fetch_radar_rows(conn, now_ms=now_ms, lookback_hours=lookback_hours)
        candidate_rows = fetch_candidate_rows(conn, now_ms=now_ms, lookback_hours=lookback_hours)
        run_rows = fetch_run_rows(conn, now_ms=now_ms, lookback_hours=lookback_hours)
        return {
            "radar": summarize_radar_policy_rows(radar_rows),
            "candidates": summarize_candidate_policy_rows(candidate_rows),
            "runs": summarize_pulse_run_rows(run_rows),
        }
    ```
  - Do not write to DB from this module.

- Create `scripts/evaluate_pulse_1h_4h_policy.py`
  - CLI script loads real settings, confirms redacted config paths, runs `build_pulse_policy_evaluation`, and writes a markdown report under `docs/generated/`.
  - Command:
    ```bash
    uv run python scripts/evaluate_pulse_1h_4h_policy.py --lookback-hours 24
    ```
  - Output path pattern:
    `docs/generated/pulse-1h-4h-research-committee-evaluation-YYYY-MM-DD.md`

### Existing backend files

- Modify `src/gmgn_twitter_intel/platform/config/settings.py:720-731`
  - Change `PulseCandidateWorkerSettings.windows` default to `("1h", "4h")`.
  - Change `stale_job_ttl_by_window_seconds` default to `{}`.
  - Add a validator that calls `validate_pulse_agent_windows`.
  - Update generated default workers YAML at `src/gmgn_twitter_intel/platform/config/settings.py:1508-1522` to remove `5m`, `24h`, and the `5m` stale TTL.

- Modify `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py:137-199`
  - Import `validate_pulse_agent_windows` and enforce it during worker construction or scan setup.
  - Import `source_quality_from_factor_snapshot`.
  - `_is_asset_trigger` must remove the `watched_mentions > 0` shortcut.
  - Scan must not enqueue `scope="matched"` rows as discovery jobs unless a matching `all` row already passes public quality policy.
  - Result notes must include `asset_suppressed_source_quality` and `asset_suppressed_non_primary_window`.

- Modify `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_gate.py:50-108`
  - Accept optional `source_quality`.
  - If source quality blocks public trade/watch, downgrade `trade_candidate` and `token_watch` to `blocked_low_information`.
  - If source quality blocks default risk-reject display, keep the audit status but force downstream display status to hidden via gate reasons.
  - Do not modify Token Radar factor snapshot gate.

- Modify `src/gmgn_twitter_intel/domains/pulse_lab/services/write_gate.py:43-103`
  - Read source-quality gate reasons from `gate` or `factor_snapshot`.
  - Convert single-author/matched-only risk rejects to hidden display status.
  - Keep `decision_status` auditable, but do not publish default display rows for blocked source quality.

- Modify `src/gmgn_twitter_intel/domains/pulse_lab/types/pulse_state.py:43-90`
  - Add deterministic display mapping for source-quality hidden states.
  - Public statuses remain `display_trade_candidate`, `display_token_watch`, `display_risk_rejected_high_info`, but source-quality-blocked risk rejects map to `hidden_source_quality`.

- Modify `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_edge_events.py:35-84`
  - Emit:
    - `timeline_evidence_changed` when `timeline_signature` changes.
    - `trigger_evidence_changed` when `trigger_signature` changes.
    - `independent_author_bucket_changed` when `independent_author_count_bucket` changes.
  - Keep score-band confirmation behavior in `PulseAdmissionPolicy`; do not turn every score-only twitch into an immediate agent run.

- Modify `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_admission_policy.py:6-48`
  - Add material evidence events to accepted non-escalation edge set.
  - Keep failure circuit behavior, but evidence-change events should record explicit reasons rather than generic `unchanged`.

- Modify `src/gmgn_twitter_intel/domains/pulse_lab/types/agent_decision.py:12-285`
  - Replace stage names with:
    ```python
    StageName = Literal[
        "evidence_pack",
        "evidence_completeness_gate",
        "signal_analyst",
        "bear_case",
        "risk_portfolio_judge",
        "claim_verifier",
        "recommendation_clipper",
        "deterministic_eval",
        "write_gate",
    ]
    ```
  - Add Pydantic models:
    ```python
    class SignalAnalystMemo(BaseModel):
        bull_claims: tuple[EvidenceClaim, ...] = Field(default=(), max_length=3)
        what_changed_zh: str = Field(max_length=240)
        allowed_evidence_ref_ids: tuple[str, ...] = Field(default=(), max_length=20)

    class BearCaseMemo(BaseModel):
        risk_claims: tuple[EvidenceClaim, ...] = Field(default=(), max_length=4)
        confidence_ceiling: float = Field(ge=0, le=1)
        missing_fact_impacts: tuple[EvidenceClaim, ...] = Field(default=(), max_length=3)
        allowed_evidence_ref_ids: tuple[str, ...] = Field(default=(), max_length=20)
    ```
  - Keep `FinalDecision` as the risk/portfolio judge output.
  - Do not keep `EvidenceDebateMemo` in the runtime path. If the class is left for reusable claim primitives, no new code may instantiate it.

- Delete old prompts:
  - `src/gmgn_twitter_intel/domains/pulse_lab/prompts/evidence_debate.md`
  - `src/gmgn_twitter_intel/domains/pulse_lab/prompts/decision_maker.md`

- Create new prompts:
  - `src/gmgn_twitter_intel/domains/pulse_lab/prompts/signal_analyst.md`
  - `src/gmgn_twitter_intel/domains/pulse_lab/prompts/bear_case.md`
  - `src/gmgn_twitter_intel/domains/pulse_lab/prompts/risk_portfolio_judge.md`
  - All prompts must state: no tools, no outside facts, cite only `allowed_evidence_refs`, no execution language.

- Modify `src/gmgn_twitter_intel/domains/pulse_lab/services/prompt_loader.py`
  - Remove loaders for old stage prompts.
  - Add:
    ```python
    def load_signal_analyst_prompt(route: DecisionRoute) -> str:
        return _load_route_prompt("signal_analyst", route)

    def load_bear_case_prompt(route: DecisionRoute) -> str:
        return _load_route_prompt("bear_case", route)

    def load_risk_portfolio_judge_prompt(route: DecisionRoute) -> str:
        return _load_route_prompt("risk_portfolio_judge", route)
    ```

- Modify `src/gmgn_twitter_intel/domains/pulse_lab/providers.py:26-80`
  - Default runtime contract stage names become `("signal_analyst", "bear_case", "risk_portfolio_judge")`.
  - Tool names remain empty for all stages.
  - Protocol methods become `signal_analyst_stage_spec`, `bear_case_stage_spec`, `risk_portfolio_judge_stage_spec`, plus ref validators for each memo/final output.

- Modify `src/gmgn_twitter_intel/domains/pulse_lab/services/agent_runtime.py:13-113`
  - Bump runtime version to `pulse-research-committee-runtime-v1`.
  - Default stage names become the new three-stage committee.
  - Remove old stage names from manifest defaults.

- Modify `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_decision_runtime.py:37-145`
  - Replace `evidence_debate_stage_spec` and `decision_maker_stage_spec` with `signal_analyst_stage_spec`, `bear_case_stage_spec`, and `risk_portfolio_judge_stage_spec`.
  - `signal_analyst` input gets packet and source quality summary.
  - `bear_case` input gets packet plus signal memo.
  - `risk_portfolio_judge` input gets packet, signal memo, bear memo, evidence gate, and recommendation constraints.
  - Replace `validate_debate_refs` with `validate_signal_refs` and `validate_bear_refs`.
  - Update `validate_final_evidence_refs` to accept signal and bear memos, not debate memo.

- Modify `src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py:52-220`
  - Rename class docstring to packet-only research committee.
  - Artifact hash schema includes `SignalAnalystMemo`, `BearCaseMemo`, and `FinalDecision`.
  - `runtime_contract` exposes new stage names and max-turn maps.
  - `run_decision_pipeline` runs exactly three LLM stages in order.
  - `try_reserve_execution` child lanes become:
    `("pulse.signal_analyst", "pulse.bear_case", "pulse.risk_portfolio_judge")`.
  - Stage failures still persist collected audits and abstain/hide on unknown refs.

- Modify `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_job_service.py`
  - Update expected child lanes and stage persistence to new stage names.
  - Hard-blocked evidence gate still avoids provider calls.
  - Deterministic eval and write gate continue after final decision.

- Modify `src/gmgn_twitter_intel/app/surfaces/api/validators.py:5-40`
  - Split general observation windows from Signal Pulse windows.
  - Keep `WINDOWS = {"5m", "1h", "4h", "24h"}` for other routes.
  - Add `SIGNAL_PULSE_WINDOWS = {"1h", "4h"}`.
  - Add `_signal_pulse_window(value: str) -> str` that raises `invalid_window` for `5m` and `24h`.

- Modify `src/gmgn_twitter_intel/app/surfaces/api/routes_pulse.py:21-46`
  - Default `window` becomes `"4h"`.
  - Use `_signal_pulse_window` instead of `_window`.
  - Add response metadata for lane semantics when `scope="matched"` through service query metadata.

- Modify `src/gmgn_twitter_intel/domains/pulse_lab/read_models/signal_pulse_service.py:27-88`
  - Add `lane` to `query`: `"discovery"` for `all`, `"watchlist_alert"` for `matched`.
  - Default filtering excludes source-quality-hidden risk rejects.
  - Summary separates discovery counts from hidden source-quality counts.
  - Candidate payload includes source quality fields for UI badges.

- Modify `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_read_repository.py:13-81`
  - Public list query excludes `hidden_source_quality`.
  - `risk_rejected_high_info` status filter may include visible risk rejects only, not single-author hidden risk rejects.
  - Add selected source-quality fields from `factor_snapshot_json` or `gate_json` to rows consumed by service.

### Frontend files

- Modify `web/src/features/signal-lab/api/useSignalLabCompactQuery.ts:7-39`
  - Change compact window to `"4h"`.
  - Keep scope `"all"`.
  - Remove `sort: "recent"` param if unsupported by API.

- Modify `web/src/features/signal-lab/state/signalLabRouteState.ts:12-74`
  - Default `window` becomes `"4h"`.
  - Pulse route parse accepts only `"1h"` or `"4h"`; invalid or missing windows normalize to `"4h"`.
  - Do not modify global `OBSERVATION_WINDOWS` for Token Radar/Search unless compiler forces a specific Pulse-only options export.

- Modify `web/src/features/signal-lab/ui/SignalLabPulse.tsx`
  - Summary labels should not make risk rejects look like primary candidates.
  - Show discovery count and optional alert count if API provides lane metadata.

- Modify `web/src/features/signal-lab/model/signalPulseQueue.ts`
  - Add chips for independent author count, top author share warning, watched-only, and matched-only.
  - A matched lane item gets alert tone, not discovery tone.

- Modify `web/src/features/signal-lab/ui/SignalPulseQueue.tsx`
  - Render lane/source quality chips from model.
  - Keep layout dimensions stable; do not add marketing copy or explanatory in-app text beyond concise chips.

- Add frontend tests under `web/src/features/signal-lab/tests/`
  - `signalLabRouteState.test.ts`
  - `signalPulseQueue.test.ts`
  - Use Vitest; keep tests pure where possible.

### Docs and generated contracts

- Modify `docs/CONTRACTS.md`
  - Document `/api/signal-lab/pulse` valid windows as `1h | 4h`.
  - Document default query as `4h/all`.
  - Document `scope=matched` as watchlist alert/context, not default discovery.

- Modify `docs/WORKERS.md`
  - Update `pulse_candidate` worker input windows and semantics.
  - State that `5m` Token Radar remains upstream observation, not Pulse Agent admission.

- Modify `src/gmgn_twitter_intel/domains/pulse_lab/ARCHITECTURE.md`
  - Replace two-stage EvidenceDebate/DecisionMaker description with research committee stages.
  - State no tools and no compatibility stage aliases.

- Regenerate OpenAPI after backend schema changes:
  ```bash
  uv run python scripts/regen_openapi.py
  cd web && npm run generate:types
  ```

## Task Breakdown

### Task 1: Add read-only policy evaluator

**Files:**

- Create: `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_policy_evaluator.py`
- Create: `scripts/evaluate_pulse_1h_4h_policy.py`
- Test: `tests/unit/domains/pulse_lab/test_pulse_policy_evaluator.py`

- [ ] Write failing unit tests for evaluator summary buckets.
  ```bash
  uv run pytest tests/unit/domains/pulse_lab/test_pulse_policy_evaluator.py -q
  ```
  Expected before implementation: import or assertion failure.

- [ ] Implement pure aggregation helpers over row dictionaries before adding SQL.
  Required helper signatures:
  ```python
  def summarize_radar_policy_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
      return summarize_by_window_scope(rows)

  def summarize_pulse_run_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
      return summarize_by_window_scope_and_outcome(rows)
  ```

- [ ] Implement `build_pulse_policy_evaluation(conn, now_ms, lookback_hours=24)` using read-only SQL.
  It must query `token_radar_rows`, `pulse_candidates`, `pulse_agent_jobs`, and `pulse_agent_runs`.

- [ ] Implement the script writer.
  It must write the report to `docs/generated/` and print only the output path plus redacted config path booleans.

- [ ] Run:
  ```bash
  uv run pytest tests/unit/domains/pulse_lab/test_pulse_policy_evaluator.py -q
  uv run python scripts/evaluate_pulse_1h_4h_policy.py --lookback-hours 24
  ```

- [ ] Commit:
  ```bash
  git add src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_policy_evaluator.py scripts/evaluate_pulse_1h_4h_policy.py tests/unit/domains/pulse_lab/test_pulse_policy_evaluator.py docs/generated/
  git commit -m "test: evaluate pulse 1h 4h policy"
  ```

### Task 2: Hard-cut Pulse horizons in config and API validators

**Files:**

- Create: `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_horizon_policy.py`
- Modify: `src/gmgn_twitter_intel/platform/config/settings.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/validators.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/routes_pulse.py`
- Test: `tests/unit/test_api_signal_pulse_contract.py`
- Test: `tests/unit/test_pulse_candidate_worker.py`

- [ ] Write failing tests:
  - API default is `4h/all`.
  - `/api/signal-lab/pulse?window=5m` returns `invalid_window`.
  - `PulseCandidateWorkerSettings(windows=("5m",))` raises `ValueError`.
  - default pulse worker windows are `("1h", "4h")`.

- [ ] Create `pulse_horizon_policy.py` with constants and validation functions.

- [ ] Wire settings validator to fail fast.
  Do not silently strip invalid windows from operator config.

- [ ] Change route default and validator.

- [ ] Run:
  ```bash
  uv run pytest tests/unit/test_api_signal_pulse_contract.py tests/unit/test_pulse_candidate_worker.py -q
  ```

- [ ] Commit:
  ```bash
  git add src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_horizon_policy.py src/gmgn_twitter_intel/platform/config/settings.py src/gmgn_twitter_intel/app/surfaces/api/validators.py src/gmgn_twitter_intel/app/surfaces/api/routes_pulse.py tests/unit/test_api_signal_pulse_contract.py tests/unit/test_pulse_candidate_worker.py
  git commit -m "feat: hard cut pulse horizons to 1h 4h"
  ```

### Task 3: Add source-quality policy and block watched-only public display

**Files:**

- Create: `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_source_quality.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_gate.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/services/write_gate.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/types/pulse_state.py`
- Test: `tests/unit/domains/pulse_lab/test_pulse_source_quality.py`
- Test: `tests/unit/test_pulse_candidate_worker.py`
- Test: `tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py`
- Test: `tests/unit/test_pulse_display_status.py`

- [ ] Write failing tests:
  - watched-only row with `rank_score=44` is not enqueued.
  - watched-only row with rank-score boost does not become public trade/watch.
  - matched-only single-author risk reject maps to hidden source quality.
  - multi-author `1h/all` row remains eligible.

- [ ] Implement `PulseSourceQuality`.
  It must read from factor snapshot families:
  - `families.social_heat.facts.unique_authors`
  - `families.social_heat.facts.watched_mentions`
  - `families.social_propagation.facts.independent_authors`
  - `families.social_propagation.facts.source_weighted_effective_authors`
  - `families.social_propagation.facts.effective_authors`
  - `families.social_propagation.facts.top_author_share`
  - `families.social_propagation.facts.duplicate_text_share`

- [ ] Remove watched shortcut from `_is_asset_trigger`.
  New return rule:
  ```python
  return decision in {"high_alert", "watch"} or score >= resolved_thresholds.min_rank_score
  ```

- [ ] Add Pulse-specific source-quality decision before enqueue.
  This does not modify Token Radar factor scoring.

- [ ] Add hidden display mapping for source-quality blocked rows.

- [ ] Run:
  ```bash
  uv run pytest tests/unit/domains/pulse_lab/test_pulse_source_quality.py tests/unit/test_pulse_candidate_worker.py tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py tests/unit/test_pulse_display_status.py -q
  ```

- [ ] Commit:
  ```bash
  git add src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_source_quality.py src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_gate.py src/gmgn_twitter_intel/domains/pulse_lab/services/write_gate.py src/gmgn_twitter_intel/domains/pulse_lab/types/pulse_state.py tests/unit/domains/pulse_lab/test_pulse_source_quality.py tests/unit/test_pulse_candidate_worker.py tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py tests/unit/test_pulse_display_status.py
  git commit -m "feat: require pulse source quality for public display"
  ```

### Task 4: Make material evidence changes wake admission

**Files:**

- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_edge_events.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_admission_policy.py`
- Test: `tests/unit/test_pulse_edge_events.py`
- Test: `tests/unit/test_pulse_admission_policy.py`
- Test: `tests/unit/test_pulse_candidate_worker.py`

- [ ] Write failing tests:
  - timeline signature change emits `timeline_evidence_changed`.
  - trigger signature change emits `trigger_evidence_changed`.
  - unchanged signatures still produce no edge events.
  - candidate worker no longer suppresses changed timeline as generic `unchanged`.

- [ ] Implement new edge events.

- [ ] Update admission policy so evidence-change events enqueue unless active job, retryable failed job, budget, or failure circuit blocks them.

- [ ] Keep score-band-only confirmation behavior intact.

- [ ] Run:
  ```bash
  uv run pytest tests/unit/test_pulse_edge_events.py tests/unit/test_pulse_admission_policy.py tests/unit/test_pulse_candidate_worker.py -q
  ```

- [ ] Commit:
  ```bash
  git add src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_edge_events.py src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_admission_policy.py tests/unit/test_pulse_edge_events.py tests/unit/test_pulse_admission_policy.py tests/unit/test_pulse_candidate_worker.py
  git commit -m "feat: enqueue pulse on material evidence changes"
  ```

### Task 5: Replace two-stage agent with packet-only research committee

**Files:**

- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/types/agent_decision.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/providers.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/services/agent_runtime.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/services/prompt_loader.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_decision_runtime.py`
- Modify: `src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_job_service.py`
- Delete: `src/gmgn_twitter_intel/domains/pulse_lab/prompts/evidence_debate.md`
- Delete: `src/gmgn_twitter_intel/domains/pulse_lab/prompts/decision_maker.md`
- Create: `src/gmgn_twitter_intel/domains/pulse_lab/prompts/signal_analyst.md`
- Create: `src/gmgn_twitter_intel/domains/pulse_lab/prompts/bear_case.md`
- Create: `src/gmgn_twitter_intel/domains/pulse_lab/prompts/risk_portfolio_judge.md`
- Test: `tests/unit/test_pulse_decision_agent_client.py`
- Test: `tests/unit/domains/pulse_lab/test_agent_decision_v2_schema.py`
- Test: `tests/unit/domains/pulse_lab/test_prompt_loader.py`
- Test: `tests/unit/test_pulse_candidate_worker.py`
- Test: `tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py`

- [ ] Write failing tests:
  - runtime contract stages equal `("signal_analyst", "bear_case", "risk_portfolio_judge")`.
  - all stage tool lists are empty.
  - runtime manifest has no `evidence_debate` or `decision_maker`.
  - client executes exactly three stages in order.
  - unknown refs in signal, bear, or final stage produce abstain/hide.
  - prompt loader cannot load old prompt names because old loaders are removed.

- [ ] Add `SignalAnalystMemo` and `BearCaseMemo` schemas.
  Both must use `EvidenceClaim`-style cited refs and execution-language rejection.

- [ ] Replace prompt files and loaders.

- [ ] Replace runtime stage specs and ref validators.

- [ ] Replace OpenAI client pipeline.
  The output of `risk_portfolio_judge` is still `FinalDecision`.

- [ ] Update fake gateways and fake clients in tests to emit the three new stage outputs.

- [ ] Run:
  ```bash
  uv run pytest tests/unit/test_pulse_decision_agent_client.py tests/unit/domains/pulse_lab/test_agent_decision_v2_schema.py tests/unit/domains/pulse_lab/test_prompt_loader.py tests/unit/test_pulse_candidate_worker.py tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py -q
  ```

- [ ] Commit:
  ```bash
  git add src/gmgn_twitter_intel/domains/pulse_lab/types/agent_decision.py src/gmgn_twitter_intel/domains/pulse_lab/providers.py src/gmgn_twitter_intel/domains/pulse_lab/services/agent_runtime.py src/gmgn_twitter_intel/domains/pulse_lab/services/prompt_loader.py src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_decision_runtime.py src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_job_service.py src/gmgn_twitter_intel/domains/pulse_lab/prompts/ tests/unit/test_pulse_decision_agent_client.py tests/unit/domains/pulse_lab/test_agent_decision_v2_schema.py tests/unit/domains/pulse_lab/test_prompt_loader.py tests/unit/test_pulse_candidate_worker.py tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py
  git commit -m "feat: replace pulse agent with research committee"
  ```

### Task 6: Update Signal Pulse read model service and API contract

**Files:**

- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/read_models/signal_pulse_service.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_read_repository.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/schemas.py`
- Test: `tests/unit/test_signal_pulse_service.py`
- Test: `tests/integration/test_signal_pulse_service_decision_v2.py`
- Test: `tests/unit/test_api_signal_pulse_contract.py`

- [ ] Write failing tests:
  - service query includes `lane="discovery"` for all scope.
  - service query includes `lane="watchlist_alert"` for matched scope.
  - default result excludes source-quality-hidden risk rejects.
  - item payload exposes source quality fields.

- [ ] Update repository public SQL and summary SQL.

- [ ] Update service payload transformation and health passthrough.

- [ ] Update API schemas for new fields.

- [ ] Run:
  ```bash
  uv run pytest tests/unit/test_signal_pulse_service.py tests/integration/test_signal_pulse_service_decision_v2.py tests/unit/test_api_signal_pulse_contract.py -q
  ```

- [ ] Commit:
  ```bash
  git add src/gmgn_twitter_intel/domains/pulse_lab/read_models/signal_pulse_service.py src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_read_repository.py src/gmgn_twitter_intel/app/surfaces/api/schemas.py tests/unit/test_signal_pulse_service.py tests/integration/test_signal_pulse_service_decision_v2.py tests/unit/test_api_signal_pulse_contract.py
  git commit -m "feat: expose pulse discovery and alert lanes"
  ```

### Task 7: Update frontend defaults and source-quality badges

**Files:**

- Modify: `web/src/features/signal-lab/api/useSignalLabCompactQuery.ts`
- Modify: `web/src/features/signal-lab/state/signalLabRouteState.ts`
- Modify: `web/src/features/signal-lab/model/signalPulseQueue.ts`
- Modify: `web/src/features/signal-lab/ui/SignalLabPulse.tsx`
- Modify: `web/src/features/signal-lab/ui/SignalPulseQueue.tsx`
- Modify: `web/src/lib/types/frontend-contracts.ts`
- Modify: `web/src/lib/types/openapi.ts`
- Create: `web/src/features/signal-lab/tests/signalLabRouteState.test.ts`
- Create: `web/src/features/signal-lab/tests/signalPulseQueue.test.ts`

- [ ] Write failing frontend tests:
  - default route state window is `4h`.
  - parsing `window=5m` normalizes to `4h`.
  - queue item model adds independent-author and concentration chips.
  - matched lane item is modeled as alert/context, not discovery.

- [ ] Update compact query default to `4h/all`.

- [ ] Update route parser to accept only `1h` and `4h` for Signal Lab Pulse.

- [ ] Update queue model and rendering.

- [ ] Regenerate OpenAPI-derived types after backend schema changes.

- [ ] Run:
  ```bash
  cd web
  npm run test -- signalLabRouteState signalPulseQueue
  npm run build
  ```

- [ ] Commit:
  ```bash
  git add web/src/features/signal-lab/api/useSignalLabCompactQuery.ts web/src/features/signal-lab/state/signalLabRouteState.ts web/src/features/signal-lab/model/signalPulseQueue.ts web/src/features/signal-lab/ui/SignalLabPulse.tsx web/src/features/signal-lab/ui/SignalPulseQueue.tsx web/src/lib/types/frontend-contracts.ts web/src/lib/types/openapi.ts web/src/features/signal-lab/tests/
  git commit -m "feat: default signal lab pulse to 4h discovery"
  ```

### Task 8: Update docs, generated contracts, and architecture assertions

**Files:**

- Modify: `docs/CONTRACTS.md`
- Modify: `docs/WORKERS.md`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/ARCHITECTURE.md`
- Modify: `docs/generated/openapi.json`
- Create or modify: `tests/architecture/test_pulse_no_compat.py`

- [ ] Add architecture tests that assert:
  - no runtime source references `evidence_debate` or `decision_maker` as stage names;
  - `pulse_candidate.windows` default text does not include `5m`;
  - prompt markdown files for old stages do not exist;
  - Signal Pulse API validator rejects `5m`.

- [ ] Update docs to describe 1h/4h primary horizons and matched alert semantics.

- [ ] Regenerate OpenAPI:
  ```bash
  uv run python scripts/regen_openapi.py
  cd web && npm run generate:types
  ```

- [ ] Run:
  ```bash
  uv run pytest tests/architecture/test_pulse_no_compat.py tests/contract/test_openapi_drift.py -q
  ```

- [ ] Commit:
  ```bash
  git add docs/CONTRACTS.md docs/WORKERS.md src/gmgn_twitter_intel/domains/pulse_lab/ARCHITECTURE.md docs/generated/openapi.json web/src/lib/types/openapi.ts tests/architecture/test_pulse_no_compat.py
  git commit -m "docs: document pulse 1h 4h hard cut"
  ```

## PR Breakdown

1. **PR 1 — Evaluation and policy measurement**: Task 1 only. Mergeable on its own because it is read-only and writes a generated report.
2. **PR 2 — Horizon and source-quality hard cut**: Tasks 2, 3, and 4. This changes admission behavior without changing the LLM committee yet.
3. **PR 3 — Research committee runtime**: Task 5. This is the agent runtime break and should not mix with frontend work.
4. **PR 4 — API/frontend surface**: Tasks 6 and 7. This makes the product default match the backend policy.
5. **PR 5 — Docs, contracts, architecture guardrails**: Task 8 plus final generated contract checks.

## Rollout Order

1. Run Task 1 evaluator on live DB and review report. Stop if the report says “stop”.
2. Update operator-owned `/Users/qinghuan/.gmgn-twitter-intel/workers.yaml` to set:
   ```yaml
   pulse_candidate:
     windows: ["1h", "4h"]
     scopes: ["all", "matched"]
     stale_job_ttl_by_window_seconds: {}
   ```
3. Deploy backend hard-cut policy.
4. Verify config with:
   ```bash
   uv run gmgn-twitter-intel config
   ```
5. Start workers and verify no new 5m Pulse jobs are created after deployment timestamp.
6. Deploy frontend default change.
7. Run live API smoke checks for `4h/all`, `1h/all`, and `5m` rejection.

## Rollback

This plan intentionally does not support runtime compatibility rollback. Rollback is a git/deploy rollback to the previous release plus restoration of the previous operator-owned `workers.yaml`.

Compensating actions:

- If backend rejects current operator config at startup, fix `workers.yaml` to `["1h", "4h"]`; do not patch code to accept `5m`.
- If committee runtime fails at high rate, rollback the deployed commit and restore previous prompt/runtime files from git.
- If frontend shows an empty default queue, keep backend hard cut and adjust source-quality thresholds in a new spec/plan after reviewing the evaluator report.

## Acceptance Test Commands

- AC1:
  ```bash
  uv run pytest tests/unit/test_pulse_candidate_worker.py::test_pulse_worker_defaults_to_1h_4h_only -q
  ```
  Expected: worker scans `1h` and `4h`, and never calls Token Radar with `5m` or `24h`.

- AC2:
  ```bash
  uv run pytest tests/unit/test_api_signal_pulse_contract.py::test_signal_pulse_api_rejects_5m_window -q
  ```
  Expected: response status `400`, JSON error `invalid_window`.

- AC3:
  ```bash
  cd web && npm run test -- signalLabRouteState
  ```
  Expected: default Signal Lab route state is `4h/all`; `5m` normalizes to `4h`.

- AC4 and AC5:
  ```bash
  uv run pytest tests/unit/domains/pulse_lab/test_pulse_source_quality.py tests/unit/test_pulse_display_status.py -q
  ```
  Expected: watched-only and matched-only single-author rows do not become public trade/watch candidates.

- AC6:
  ```bash
  uv run pytest tests/unit/test_pulse_edge_events.py tests/unit/test_pulse_admission_policy.py -q
  ```
  Expected: material evidence changes emit explicit edge events and are not generic `unchanged`.

- AC7 and AC8:
  ```bash
  uv run pytest tests/unit/test_pulse_decision_agent_client.py tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py -q
  ```
  Expected: three committee stages are audited; unknown refs hide/abstain.

- AC9:
  ```bash
  uv run python scripts/evaluate_pulse_1h_4h_policy.py --lookback-hours 24
  ```
  Expected: generated markdown report under `docs/generated/`.

- AC10:
  ```bash
  uv run python - <<'PY'
  from gmgn_twitter_intel.platform.config.settings import load_settings
  from gmgn_twitter_intel.platform.db.postgres_client import connect_postgres, with_password_from_file

  settings = load_settings(require_ws_token=False)
  dsn = with_password_from_file(settings.postgres_dsn, settings.postgres_password_file)
  deployment_ms = 1779230000000
  with connect_postgres(dsn, connect_timeout_seconds=settings.postgres_connect_timeout_seconds) as conn:
      row = conn.execute(
          'select count(*) as n from pulse_agent_jobs where "window" = %s and created_at_ms >= %s',
          ("5m", deployment_ms),
      ).fetchone()
      print(row["n"])
  PY
  ```
  Expected: `0`. Replace `deployment_ms` with the actual deployment timestamp recorded in verification.

## Final Verification

Before declaring completion, create `docs/superpowers/plans/active/2026-05-20-pulse-1h-4h-research-committee-verification.md` with:

- full `make check-all` output;
- `uv run pytest` focused command outputs from the acceptance tests;
- frontend `npm run build` output;
- evaluator report path and recommendation;
- live DB query proving zero new 5m Pulse jobs after deployment timestamp;
- coverage, skipped tests, E2E golden path, and residual risks per `docs/WORKFLOW.md`.
