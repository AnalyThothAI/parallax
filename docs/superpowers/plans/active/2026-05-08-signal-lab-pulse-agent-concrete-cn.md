# Signal Lab Pulse Agent Concrete Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. This is the Chinese execution plan derived from `docs/superpowers/specs/2026-05-08-signal-lab-pulse-agent-hard-cut-cn.md`. The exhaustive test-code handoff remains in `docs/superpowers/plans/2026-05-08-signal-lab-pulse-agent-hard-cut.md`.

**Goal:** Hard-cut the old `TradingAttentionService` Signal Lab Pulse and replace it with a materialized Signal Pulse v2 system: deterministic trigger/gate/notification layers plus a bounded `PulseThesisAgent` for timeline thesis summarization.

**Architecture:** The new system has one production read model: `pulse_candidates`. Watched-account tweet extraction remains upstream; token radar remains the deterministic scoring source; `PulseThesisAgent` only summarizes compressed 5m/1h/4h/24h context and never owns ranking, score, or execution. Notifications are generated from materialized candidates only, with status-specific dedupe and cooldown.

**Tech Stack:** Python 3.13, FastAPI, PostgreSQL/Psycopg, Alembic, Pydantic, OpenAI Agents SDK, React, TypeScript, TanStack Query, Zustand, pytest, Vitest.

---

## Scope

### In Scope

- Delete `TradingAttentionService` and old `TradingAttention*` contracts.
- Add Pulse v2 tables: jobs, agent runs, candidates, playbook snapshots, outcomes.
- Add `PulseTimelineContextBuilder` for 5m/1h/4h/24h token timeline summarization.
- Add `PulseThesisAgent` with typed output and audit trace.
- Add deterministic `PulseCandidateGate`.
- Add `PulseCandidateWorker` with trigger dedupe and cooldown.
- Replace `/api/signal-lab/pulse` implementation with `SignalPulseService`.
- Add `signal_pulse_candidate` notification rule from `pulse_candidates`.
- Rewrite frontend Signal Lab Pulse types/components to use `SignalPulseData`.

### Out Of Scope

- No order execution.
- No live MCP event stream.
- No compatibility shim for `TradingAttentionData`.
- No fallback query from old event/social extraction tables for Pulse.
- No agent-owned score, target price, stop loss, leverage, or position sizing.

---

## Phase 0: Ground Rules And Branch Safety

- [ ] Confirm current branch and dirty files.

  Run:

  ```bash
  git status --short
  git branch --show-current
  ```

  Expected:

  - User-created unrelated files are left untouched.
  - New work only touches files listed in this plan.

- [ ] Keep the existing hard-cut plan as the detailed implementation reference.

  Reference:

  ```text
  docs/superpowers/plans/2026-05-08-signal-lab-pulse-agent-hard-cut.md
  ```

---

## Phase 1: Remove Old Pulse Backend

**Purpose:** Make it impossible for `/api/signal-lab/pulse` to silently fall back to old on-demand logic.

**Files:**

- Delete: `src/parallax/retrieval/trading_attention_service.py`
- Delete: `tests/test_trading_attention_service.py`
- Modify: `src/parallax/api/http.py`
- Modify: `tests/test_project_structure.py`

- [ ] Add a project-structure test proving both old files are absent.

  Test name:

  ```python
  test_trading_attention_service_has_been_hard_deleted
  ```

- [ ] Remove the `TradingAttentionService` import from `src/parallax/api/http.py`.

- [ ] Delete the old backend service and its tests.

- [ ] Run:

  ```bash
  uv run pytest tests/test_project_structure.py::test_trading_attention_service_has_been_hard_deleted -q
  ```

  Expected: pass.

---

## Phase 2: Add Pulse Storage Model

**Purpose:** Create materialized storage for Pulse v2 before adding any agent or API behavior.

**Files:**

- Create: `src/parallax/storage/alembic/versions/20260508_0015_signal_pulse_agent_hard_cut.py`
- Create: `src/parallax/storage/pulse_repository.py`
- Modify: `src/parallax/storage/repository_session.py`
- Modify: `tests/test_postgres_schema.py`
- Modify: `tests/test_postgres_schema_runtime.py`
- Create: `tests/test_pulse_repository.py`

- [ ] Create migration tables:

  ```text
  pulse_agent_jobs
  pulse_agent_runs
  pulse_candidates
  pulse_playbook_snapshots
  pulse_playbook_outcomes
  ```

- [ ] Add candidate indexes:

  ```text
  idx_pulse_candidates_latest
  idx_pulse_candidates_target
  idx_pulse_candidates_subject
  ```

- [ ] Include dedupe/cooldown fields in `pulse_agent_jobs`:

  ```text
  trigger_signature
  timeline_signature
  cooldown_until_ms
  UNIQUE(candidate_id)
  ```

- [ ] Include production read-model fields in `pulse_candidates`:

  ```text
  pulse_status
  verdict
  social_phase
  narrative_type
  candidate_score
  score_band
  trigger_signature
  timeline_signature
  thesis_json
  radar_score_json
  market_context_json
  gate_reasons_json
  risk_reasons_json
  evidence_event_ids_json
  source_event_ids_json
  pulse_version
  gate_version
  prompt_version
  schema_version
  ```

- [ ] Implement `PulseRepository` methods:

  ```text
  enqueue_job
  claim_due_job
  mark_job_succeeded
  mark_job_failed
  insert_agent_run
  finish_agent_run
  upsert_candidate
  list_candidates
  get_health
  upsert_playbook_snapshot
  upsert_playbook_outcome
  ```

- [ ] Wire `RepositorySession.pulse`.

- [ ] Run:

  ```bash
  uv run pytest tests/test_postgres_schema.py tests/test_postgres_schema_runtime.py tests/test_pulse_repository.py -q
  ```

---

## Phase 3: Add Shared Pulse Contract

**Purpose:** Centralize version constants, statuses, score bands, and text guardrails so backend/API/frontend behavior cannot drift.

**Files:**

- Create: `src/parallax/pipeline/pulse_contract.py`
- Create: `src/parallax/pipeline/pulse_thesis.py`
- Create: `tests/test_pulse_thesis.py`

- [ ] Define constants:

  ```python
  PULSE_VERSION = "signal-pulse-v2-agent-thesis"
  PULSE_THESIS_SCHEMA_VERSION = "pulse_thesis_v1"
  PULSE_THESIS_PROMPT_VERSION = "pulse-thesis-agents-sdk-v1"
  PULSE_GATE_VERSION = "pulse-candidate-gate-v1"
  PULSE_PLAYBOOK_VERSION = "shadow-playbook-v1"
  ```

- [ ] Define statuses:

  ```text
  trade_candidate
  token_watch
  theme_watch
  risk_rejected_high_info
  blocked_low_information
  ```

- [ ] Define `PulseThesisPayload` exactly as the spec requires.

- [ ] Add validation:

  ```text
  trade_candidate requires target_type and target_id
  theme_watch cannot force a target
  evidence_event_ids must be input-backed
  blocked_low_information is allowed for health but not normal Pulse rows
  output text must not contain buy/sell/position/leverage/target/stop instructions
  ```

- [ ] Run:

  ```bash
  uv run pytest tests/test_pulse_thesis.py -q
  ```

---

## Phase 4: Build Token Timeline Context

**Purpose:** Make `PulseThesisAgent` summarize a deterministic, bounded token timeline instead of a single tweet or unlimited raw feed.

**Files:**

- Create: `src/parallax/pipeline/pulse_timeline_context.py`
- Create: `tests/test_pulse_timeline_context.py`

- [ ] Implement fixed windows:

  ```text
  trigger_window = 5m
  primary_context_window = 1h
  extended_context_window = 4h
  baseline_window = 24h
  ```

- [ ] Implement deterministic text dedupe:

  ```text
  normalized_text_hash = lowercase + strip urls + normalize whitespace + strip common punctuation/emoji
  semantic_cluster_key = normalized_text + primary_url_domain + cashtags + target_id
  same author + same text = keep first/latest
  multiple authors + same text = one cluster with duplicate_text_share
  ```

- [ ] Implement post selection budget:

  ```text
  max_selected_posts = 24
  max_post_clusters = 16
  max_raw_text_chars_per_post = 280
  ```

- [ ] Ensure selected posts always include:

  ```text
  first seed post
  latest post
  watched-author posts
  representative posts per stage
  direct CA/ticker evidence posts
  price inflection nearby posts
  new independent author posts
  duplicate/concentration risk representative posts
  ```

- [ ] Compute `timeline_signature` from:

  ```text
  target_id
  window
  phase
  selected_event_ids
  cluster_ids
  author_count_bucket
  duplicate_share_bucket
  price_change_bucket
  risk_flags
  ```

- [ ] Run:

  ```bash
  uv run pytest tests/test_pulse_timeline_context.py -q
  ```

---

## Phase 5: Add Deterministic Candidate Gate

**Purpose:** Keep trade eligibility deterministic and auditable; agent summary cannot upgrade a weak setup into a trade candidate by itself.

**Files:**

- Create: `src/parallax/pipeline/pulse_candidate_gate.py`
- Create: `tests/test_pulse_candidate_gate.py`

- [ ] Implement `trade_candidate` gate:

  ```text
  candidate_type == token_target
  target_type in Asset/CexToken
  target_id present
  radar.decision == driver
  heat >= 75
  quality >= 62
  propagation >= 62
  tradeability >= 70
  timing >= 50
  phase in ignition/expansion
  market_status == fresh
  no hard_risks
  not chase_risk
  agent confidence >= 0.65
  ```

- [ ] Implement downgrade rules:

  ```text
  token_watch = useful information but trade gate incomplete
  theme_watch = source-led or unresolved theme with observable relevance
  risk_rejected_high_info = strong info but hard risk
  blocked_low_information = weak/repetitive/unconfirmed evidence
  ```

- [ ] Implement score band:

  ```text
  high_conviction
  watch
  speculative
  blocked
  ```

- [ ] Run:

  ```bash
  uv run pytest tests/test_pulse_candidate_gate.py -q
  ```

---

## Phase 6: Add PulseThesisAgent

**Purpose:** Use OpenAI Agents SDK only for bounded thesis summarization, with typed output and trace metadata.

**Files:**

- Create: `src/parallax/pipeline/pulse_thesis_agent_client.py`
- Modify: `src/parallax/settings.py`
- Modify: `tests/test_settings.py`
- Create/extend: `tests/test_pulse_thesis.py`

- [ ] Add settings under `llm`:

  ```text
  pulse_agent_enabled
  pulse_agent_interval_seconds
  pulse_agent_batch_size
  pulse_agent_max_attempts
  pulse_agent_model
  ```

- [ ] Implement `PulseThesisAgent`:

  ```text
  Agent(name="PulseThesisAgent")
  output_type=PulseThesisPayload
  max_turns=3
  workflow_name="parallax.pulse_thesis"
  prompt_version="pulse-thesis-agents-sdk-v1"
  schema_version="pulse_thesis_v1"
  ```

- [ ] Agent input must include:

  ```text
  candidate metadata
  PulseTimelineContext
  radar score JSON
  market context
  harness history
  source event IDs
  evidence event IDs
  ```

- [ ] Agent output must be validated before writing `pulse_candidates`.

- [ ] Run:

  ```bash
  uv run pytest tests/test_pulse_thesis.py tests/test_settings.py -q
  ```

---

## Phase 7: Add Worker Trigger, Dedupe, And Cooldown

**Purpose:** Trigger agent jobs from radar/social events without repeated agent runs or repeated user-facing candidates.

**Files:**

- Create: `src/parallax/pipeline/pulse_candidate_worker.py`
- Create: `tests/test_pulse_candidate_worker.py`
- Modify: `src/parallax/api/app.py`

- [ ] Implement asset-led triggers:

  ```text
  radar.decision in driver/watch
  or heat >= 80
  or propagation >= 70
  or watched_confirmation present
  ```

- [ ] Implement source-led triggers from watched social extractions:

  ```text
  high-weight watched account
  meaningful social event
  no forced token target
  default status can only become theme_watch/risk_rejected/blocked until deterministic token binding exists
  ```

- [ ] Compute `trigger_signature`:

  ```text
  pulse_version
  candidate_type
  target_type/target_id or source_event_id
  window/scope
  latest source event bucket
  heat bucket
  decision
  social phase
  watched confirmation flag
  chase risk flag
  ```

- [ ] Apply enqueue rule:

  ```text
  same candidate_id + same trigger_signature + same timeline_signature -> skip
  same candidate_id + materially changed timeline -> enqueue/update job
  same candidate_id + no material change + cooldown active -> skip
  ```

- [ ] Implement default agent cooldown:

  ```text
  trade_candidate eligible token target: 5m
  token_watch: 15m
  theme_watch source seed: 60m
  risk_rejected_high_info: 30m
  blocked_low_information: 120m
  ```

- [ ] Allow cooldown bypass for:

  ```text
  status upgrade
  phase change
  heat bucket change
  new watched confirmation
  independent author count +2
  chase risk false -> true
  market pending/stale -> fresh
  new hard risk
  ```

- [ ] Worker execution order:

  ```text
  scan triggers
  build timeline context
  compute signatures
  enqueue/skip by dedupe/cooldown
  claim job
  run agent
  validate output
  run gate
  insert agent run audit
  upsert candidate
  upsert playbook snapshots
  mark job succeeded/failed
  ```

- [ ] Start worker from `api/app.py` only when configured and LLM credentials exist.

- [ ] Run:

  ```bash
  uv run pytest tests/test_pulse_candidate_worker.py -q
  ```

---

## Phase 8: Replace Pulse API

**Purpose:** Keep the public route path but hard-cut response contract to `SignalPulseData`.

**Files:**

- Create: `src/parallax/retrieval/signal_pulse_service.py`
- Modify: `src/parallax/api/http.py`
- Modify: `tests/test_signal_pulse_service.py`
- Modify: `tests/test_api_http.py`

- [ ] Implement `SignalPulseService` over `pulse_candidates` only.

- [ ] Support query params:

  ```text
  window=5m|1h|4h|24h
  scope=all|matched
  status=trade_candidate|token_watch|theme_watch|risk_rejected_high_info
  handle
  q
  limit
  cursor
  ```

- [ ] Return health:

  ```text
  pulse_ready
  agent_worker_running
  candidate_count
  blocked_low_information_count
  dead_job_count
  market_ready_rate
  settlement_coverage
  ```

- [ ] Exclude `blocked_low_information` from normal `items`.

- [ ] Ensure empty state does not query old tables.

- [ ] Run:

  ```bash
  uv run pytest tests/test_signal_pulse_service.py tests/test_api_http.py -q
  ```

---

## Phase 9: Add Signal Pulse Notifications

**Purpose:** Push meaningful Pulse state changes once, from materialized candidates, with notification-specific dedupe.

**Files:**

- Modify: `src/parallax/pipeline/notification_rules.py`
- Modify: `src/parallax/settings.py`
- Modify: `src/parallax/api/app.py`
- Modify: `tests/test_notification_rules.py`

- [ ] Add rule id:

  ```text
  signal_pulse_candidate
  ```

- [ ] Inject `SignalPulseService` or `PulseRepository` into `NotificationRuleEngine`.

- [ ] Generate notification candidates from `pulse_candidates`, not jobs/raw triggers.

- [ ] Map severity:

  ```text
  trade_candidate -> critical
  token_watch -> high
  theme_watch -> warning
  risk_rejected_high_info -> high
  blocked_low_information -> no notification
  ```

- [ ] Compute notification signature:

  ```text
  pulse_version
  candidate_id
  pulse_status
  score_band
  social_phase
  top_risk_keys
  confirmation_trigger_keys
  latest_evidence_event_id_bucket
  ```

- [ ] Compute notification cooldown:

  ```text
  trade_candidate: 15m
  token_watch: 30m
  theme_watch: 2h
  risk_rejected_high_info: 1h
  blocked_low_information: never
  ```

- [ ] Dedup key:

  ```text
  signal_pulse_candidate:{candidate_id}:{notification_signature}:{bucket}
  ```

- [ ] Allow immediate notification on:

  ```text
  token_watch -> trade_candidate
  theme_watch -> token_watch
  token_watch -> risk_rejected_high_info for chase/market stale/identity ambiguous
  new watched source joins same candidate
  score_band -> high_conviction
  ```

- [ ] Run:

  ```bash
  uv run pytest tests/test_notification_rules.py -q
  ```

---

## Phase 10: Rewrite Frontend Contract And Views

**Purpose:** Remove old `TradingAttention*` UI semantics and expose the new trader-facing Pulse candidate model.

**Files:**

- Modify: `web/src/api/types.ts`
- Rewrite: `web/src/components/SignalLabPulse.tsx`
- Rewrite: `web/src/components/SignalLabWorkbench.tsx`
- Rewrite: `web/src/components/SignalLabInspector.tsx`
- Modify: `web/src/store/useTraderStore.ts`
- Modify: `web/src/App.tsx`
- Modify: `web/src/components/SignalLabPulse.test.tsx`
- Modify: `web/src/App.test.tsx`

- [ ] Delete all `TradingAttention*` types.

- [ ] Add `SignalPulseData`, `SignalPulseItem`, `SignalPulseHealth`, `SignalPulseSummary`, `SignalPulseQuery`.

- [ ] Replace kind filters with status filters:

  ```text
  trade_candidate
  token_watch
  theme_watch
  risk_rejected_high_info
  ```

- [ ] Row display budget:

  ```text
  status
  symbol/subject
  why_now_zh
  social_phase
  score_band
  top_risks
  confirmation/invalidation preview
  updated time
  ```

- [ ] Inspector displays:

  ```text
  bull_case_zh
  bear_case_zh
  source_event_ids
  evidence_event_ids
  radar_score_json
  market_context_json
  gate_reasons_json
  risk_reasons_json
  playbook/outcome data when available
  ```

- [ ] UI must not show old labels:

  ```text
  Direct token
  Topic heat
  Ecosystem
  Structure
  Risk
  low_signal
  NO_TRADE
  missing_market as ordinary candidate
  ```

- [ ] Run:

  ```bash
  npm test -- --run src/components/SignalLabPulse.test.tsx src/App.test.tsx
  ```

---

## Phase 11: End-To-End Verification

**Purpose:** Prove the hard cut works and no old compatibility path remains.

- [ ] Run backend tests:

  ```bash
  uv run pytest
  ```

- [ ] Run lint:

  ```bash
  uv run ruff check .
  ```

- [ ] Run compile check:

  ```bash
  uv run python -m compileall src tests
  ```

- [ ] Run frontend tests:

  ```bash
  npm test -- --run src/components/SignalLabPulse.test.tsx src/App.test.tsx
  ```

- [ ] Run forbidden symbol scan:

  ```bash
  rg -n "TradingAttention|trading_attention_service|direct_token\\|topic_heat|kind=direct_token|kind=topic_heat" src tests web
  ```

  Expected:

  ```text
  no production references
  ```

- [ ] Verify route behavior:

  ```bash
  uv run parallax serve
  ```

  Then call:

  ```text
  GET /api/signal-lab/pulse?window=1h&scope=all&limit=50
  ```

  Expected:

  - `ok=true`
  - response contract is `SignalPulseData`
  - `items` comes only from `pulse_candidates`
  - empty DB returns empty production state plus health

---

## Implementation Order

Recommended order:

1. Phase 1: delete old backend contract.
2. Phase 2: add storage and repository.
3. Phase 3: add shared contract and thesis schema.
4. Phase 4: add timeline context and signatures.
5. Phase 5: add deterministic gate.
6. Phase 6: add agent client.
7. Phase 7: add worker trigger/dedupe/cooldown.
8. Phase 8: replace API route.
9. Phase 9: add notification rule.
10. Phase 10: rewrite frontend.
11. Phase 11: verify and scan.

Do not start frontend before backend contract and tests are stable. Do not start notifications before `pulse_candidates` upsert and signature fields are implemented.

---

## Acceptance Checklist

- [ ] `TradingAttentionService` file is gone.
- [ ] Old `TradingAttention*` frontend types are gone.
- [ ] `/api/signal-lab/pulse` imports `SignalPulseService`.
- [ ] `/api/signal-lab/pulse` reads only `pulse_candidates`.
- [ ] `PulseThesisAgent` receives `PulseTimelineContext`, not a single trigger tweet.
- [ ] 5m/1h/4h/24h windows are present in agent context.
- [ ] `trigger_signature` and `timeline_signature` are stored and tested.
- [ ] Agent cooldown prevents same-signature repeat jobs.
- [ ] Notification dedupe is separate from agent dedupe.
- [ ] `blocked_low_information` never appears in normal Pulse items or notifications.
- [ ] `trade_candidate` requires deterministic token identity and market freshness.
- [ ] Source-led Musk/CZ/HeYi style tweets can become `theme_watch` but not `trade_candidate` unless later token-bound.
- [ ] `signal_pulse_candidate` notifications come from `pulse_candidates`.
- [ ] Full verification commands pass.
