# Pulse Signal Evidence-First Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `superpowers:subagent-driven-development` to execute this plan task by task. Keep the checkboxes current while implementing.

**Goal:** 将 Signal Pulse 从“LLM 运行时取关键事实 + 事后校验”的链路，硬切到“worker 先构建 sealed `PulseEvidencePacket` + LLM 只能在证据包内综合/反驳 + 确定性发布门”的链路。

**Architecture:** `pulse_candidate` worker 仍然是生命周期 owner。worker 负责 admission、证据包构建、完整性门、claim verifier、recommendation clipper、eval、write gate 和公开读模型写入。LLM 只承担两个受限角色：`evidence_debate` 和 `decision_maker`。不新增宽图多 agent，不保留 v1/v2 运行时兼容代码。

**Tech Stack:** Python 3.13, Pydantic v2, psycopg, PostgreSQL, Alembic, FastAPI, OpenAI Agents SDK, pytest, ruff, React/TypeScript.

---

## Owning Spec

**Spec:** `docs/superpowers/specs/active/2026-05-18-pulse-signal-evidence-architecture-recovery-cn.md`

本计划以该 spec 为唯一设计来源。执行时如果代码事实和本计划冲突，先修订计划或 spec，再改代码。

---

## Design Locks

- **证据边界在 worker，不在 LLM。** LLM 不负责调用工具拿关键事实。
- **`factor_snapshot` 只能作为 admission context 和 fingerprint。** 不能作为 Pulse 决策证据的唯一来源。
- **公开 signal 必须有 `PulseEvidencePacket`。** 没有 `evidence_packet_hash` 的历史 `pulse_candidates` 只能 audit，不能被默认公开列表读取。
- **所有非 abstain claim 必须 cite `EvidenceRef.ref_id`。** 只 cite event id 不够。
- **不保留 live compatibility path。** 不做 old decision shape adapter，不做 old stage mapper，不保留 `legacy_skipped` live eval。
- **不引入新的 Pulse worker。** 修复范围是当前 worker 的内部架构边界。
- **TradingAgents 只借思想，不借宽图。** Pulse 采用“sealed packet -> bull/bear evidence memo -> decision maker”，不采用多分析师主动工具图。

---

## Target Data Flow

```text
token_radar_rows
  -> PulseAdmissionPolicy
  -> pulse_agent_jobs
  -> PulseEvidenceBuilder
       reads events / enriched_events
       reads asset identity/profile facts
       reads market_ticks / pricefeed current facts
       fingerprints factor_snapshot as admission context
  -> pulse_evidence_packets
  -> EvidenceCompletenessGate
  -> EvidenceDebateSynthesizer
       packet-only bull/bear/rebuttal memo
  -> ClaimEvidenceVerifier
       memo refs and decision refs must be subset of packet refs
  -> DecisionMaker
       packet + debate memo + gate result only
  -> RecommendationClipper
       pulse gate ceiling + evidence gate ceiling
  -> DeterministicEval
  -> PulseWriteGate / PulsePublishPolicy
  -> pulse_candidates(display_status, evidence_status, evidence_packet_hash)
  -> Signal Pulse read model / status health
  -> API / frontend / notifications
  -> ReplayEvalHarness
```

---

## File Map

### Create

- `src/gmgn_twitter_intel/domains/pulse_lab/types/evidence_packet.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/types/pulse_state.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_evidence_repository.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_evidence_source_repository.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/services/evidence_packet_builder.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/services/evidence_completeness_gate.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/services/claim_evidence_verifier.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_freshness_health.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_replay_eval.py`
- `src/gmgn_twitter_intel/app/surfaces/cli/commands/pulse_replay.py`
- `src/gmgn_twitter_intel/platform/db/alembic/versions/20260518_0062_pulse_evidence_first_recovery.py`
- `tests/architecture/test_pulse_signal_evidence_contracts.py`
- `tests/unit/test_pulse_evidence_packet_builder.py`
- `tests/unit/test_pulse_evidence_completeness_gate.py`
- `tests/unit/test_pulse_claim_evidence_verifier.py`
- `tests/unit/test_pulse_display_status.py`
- `tests/unit/test_pulse_recommendation_clipper.py`
- `tests/integration/test_pulse_evidence_repository.py`
- `tests/integration/test_pulse_signal_evidence_flow.py`
- `tests/integration/test_signal_pulse_freshness_health.py`
- `tests/integration/test_pulse_replay_eval.py`

### Modify

- `src/gmgn_twitter_intel/domains/pulse_lab/types/__init__.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/types/agent_decision.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/types/pulse_candidate_context.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/providers.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/services/agent_runtime.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/services/agent_eval.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_job_service.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_decision_runtime.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/services/recommendation_clipper.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/services/write_gate.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/prompts/evidence_debate.md`
- `src/gmgn_twitter_intel/domains/pulse_lab/prompts/decision_maker.md`
- `src/gmgn_twitter_intel/domains/pulse_lab/repositories/__init__.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_candidates_repository.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_read_repository.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_runs_repository.py`
- `src/gmgn_twitter_intel/app/runtime/provider_wiring/openai.py`
- `src/gmgn_twitter_intel/app/runtime/repository_session.py`
- `src/gmgn_twitter_intel/app/surfaces/api/routes_pulse.py`
- `src/gmgn_twitter_intel/app/surfaces/api/schemas.py`
- `src/gmgn_twitter_intel/app/surfaces/cli/main.py`
- `src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py`
- `web/src/lib/types/frontend-contracts.ts`
- `web/src/lib/api.ts`
- `web/src/routes/pulse/+page.svelte` or current Signal Pulse page component
- `docs/ARCHITECTURE.md`
- `docs/WORKER_FLOW.md`
- `docs/WORKERS.md`
- `docs/CONTRACTS.md`
- `src/gmgn_twitter_intel/domains/pulse_lab/ARCHITECTURE.md`

---

## Task 1: DB Contract And State Enums

**Purpose:** 先把持久化边界和状态机固定下来，避免代码继续写旧 stage/outcome 或公开无证据 candidate。

**Files:**

- Create: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260518_0062_pulse_evidence_first_recovery.py`
- Create: `src/gmgn_twitter_intel/domains/pulse_lab/types/pulse_state.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/types/__init__.py`

**Steps:**

- [ ] Add `pulse_evidence_packets`:
  - `evidence_packet_id TEXT PRIMARY KEY`
  - `run_id TEXT NOT NULL REFERENCES pulse_agent_runs(run_id) ON DELETE CASCADE`
  - `candidate_id TEXT NOT NULL`
  - `target_type TEXT NOT NULL`
  - `target_id TEXT NOT NULL`
  - `window TEXT NOT NULL`
  - `scope TEXT NOT NULL`
  - `schema_version TEXT NOT NULL`
  - `evidence_packet_hash TEXT NOT NULL UNIQUE`
  - `packet_json JSONB NOT NULL`
  - `summary_json JSONB NOT NULL DEFAULT '{}'::jsonb`
  - `source_fingerprints_json JSONB NOT NULL DEFAULT '{}'::jsonb`
  - `created_at_ms BIGINT NOT NULL`
- [ ] Add indexes:
  - `idx_pulse_evidence_packets_run`
  - `idx_pulse_evidence_packets_candidate_created`
  - `idx_pulse_evidence_packets_target_created`
- [ ] Add nullable evidence columns to `pulse_agent_runs`:
  - `evidence_packet_id TEXT`
  - `evidence_packet_hash TEXT`
  - `evidence_status TEXT`
  - `display_status TEXT`
- [ ] Add nullable evidence/display columns to `pulse_candidates`:
  - `evidence_packet_hash TEXT`
  - `evidence_status TEXT NOT NULL DEFAULT 'insufficient'`
  - `decision_status TEXT NOT NULL DEFAULT 'invalid_schema'`
  - `display_status TEXT NOT NULL DEFAULT 'hidden_insufficient_evidence'`
  - `claim_verification_json JSONB NOT NULL DEFAULT '{}'::jsonb`
  - `evidence_gate_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- [ ] Hide all existing `pulse_candidates` from default public reads:
  - Set `display_status = 'hidden_insufficient_evidence'`
  - Set `evidence_status = 'insufficient'`
  - Set `decision_status = 'invalid_schema'`
  - Leave historical rows in place for audit and detail debugging.
- [ ] Add DB checks with `NOT VALID` so historical old rows survive but new writes use the recovered state machine:

```sql
ALTER TABLE pulse_agent_run_steps
  ADD CONSTRAINT chk_pulse_agent_run_steps_stage_evidence_first
  CHECK (stage IN (
    'evidence_pack',
    'evidence_completeness_gate',
    'evidence_debate',
    'claim_verifier',
    'decision_maker',
    'recommendation_clipper',
    'deterministic_eval',
    'write_gate'
  )) NOT VALID;

ALTER TABLE pulse_agent_runs
  ADD CONSTRAINT chk_pulse_agent_runs_outcome_evidence_first
  CHECK (outcome IN (
    'running',
    'completed',
    'abstain_insufficient_evidence',
    'blocked_market_contract',
    'blocked_social_contract',
    'blocked_identity_contract',
    'invalid_schema',
    'invalid_unknown_evidence_ref',
    'invalid_unsupported_claim',
    'timeout',
    'provider_rate_limited',
    'provider_unavailable',
    'unexpected_exception'
  )) NOT VALID;

ALTER TABLE pulse_candidates
  ADD CONSTRAINT chk_pulse_candidates_display_status_evidence_first
  CHECK (display_status IN (
    'display_trade_candidate',
    'display_token_watch',
    'display_risk_rejected_high_info',
    'hidden_abstain',
    'hidden_insufficient_evidence',
    'hidden_blocked_low_information',
    'hidden_invalid_output',
    'hidden_hold_publish'
  )) NOT VALID;

ALTER TABLE pulse_candidates
  ADD CONSTRAINT chk_pulse_candidates_public_requires_packet
  CHECK (
    display_status LIKE 'hidden_%'
    OR evidence_packet_hash IS NOT NULL
  ) NOT VALID;
```

- [ ] In `pulse_state.py`, define `Literal` aliases:
  - `EvidenceStatus = Literal['complete', 'partial', 'insufficient', 'stale', 'invalid']`
  - `DecisionStatus = Literal['trade_candidate', 'token_watch', 'risk_rejected_high_info', 'abstain', 'invalid']`
  - `DisplayStatus = Literal[...]` using the DB values above
  - `AgentRunOutcome = Literal[...]` using the DB outcome values above
- [ ] Add helpers:
  - `display_status_from_decision(decision_status, evidence_status, publish_allowed)`
  - `run_outcome_from_failure(reason)`
  - `is_public_display_status(display_status)`

**Acceptance:**

- [ ] `uv run alembic upgrade head` succeeds on a disposable Postgres DB.
- [ ] `uv run alembic downgrade -1 && uv run alembic upgrade head` succeeds where project migration policy expects downgrade support.
- [ ] New DB checks exist.
- [ ] Existing candidates are not public by default after migration because their `display_status` is hidden.

---

## Task 2: Typed Evidence Packet And Decision Contracts

**Purpose:** 把“证据包”和“LLM 输出”变成硬类型，后续所有服务围绕这些类型工作。

**Files:**

- Create: `src/gmgn_twitter_intel/domains/pulse_lab/types/evidence_packet.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/types/agent_decision.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/types/pulse_candidate_context.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/types/__init__.py`

**Steps:**

- [ ] Add `EvidenceRef`:
  - `ref_id: str`
  - `ref_type: Literal['event', 'metric', 'profile', 'cluster', 'market', 'identity', 'gate']`
  - `source_table: str`
  - `source_id: str`
  - `observed_at_ms: int`
  - `summary_zh: str`
  - `quality: Literal['high', 'medium', 'low']`
- [ ] Add evidence models:
  - `SocialEvidence`
  - `MarketEvidence`
  - `IdentityEvidence`
  - `PulseEvidenceQualityMetrics`
  - `PulseEvidenceDataGap`
  - `PulseEvidencePacket`
- [ ] In `PulseEvidencePacket`, include:
  - `evidence_packet_id`
  - `evidence_packet_hash`
  - `schema_version`
  - `candidate_id`
  - `target_type`
  - `target_id`
  - `symbol`
  - `window`
  - `scope`
  - `snapshot_at_ms`
  - `source_event_ids`
  - `allowed_evidence_refs`
  - `social_evidence`
  - `market_evidence`
  - `identity_evidence`
  - `quality_metrics`
  - `data_gaps`
  - `risk_flags`
  - `source_fingerprints`
  - `admission_context`
- [ ] Add deterministic hash method:
  - `packet_hash = sha256(canonical_json_without_hash).hexdigest()`
  - The hash input must sort keys and normalize list order where the builder can control ordering.
- [ ] Replace old stage literals in `agent_decision.py` with:
  - `evidence_pack`
  - `evidence_completeness_gate`
  - `evidence_debate`
  - `claim_verifier`
  - `decision_maker`
  - `recommendation_clipper`
  - `deterministic_eval`
  - `write_gate`
- [ ] Add `EvidenceClaim`:
  - `claim: str`
  - `evidence_refs: tuple[str, ...]`
  - `stance: Literal['bull', 'bear', 'gap', 'risk']`
- [ ] Add `EvidenceDebateMemo`:
  - `bull_claims: tuple[EvidenceClaim, ...]`
  - `bear_claims: tuple[EvidenceClaim, ...]`
  - `rebuttal_claims: tuple[EvidenceClaim, ...]`
  - `data_gap_claims: tuple[EvidenceClaim, ...]`
  - `summary_zh: str`
  - `allowed_evidence_ref_ids: tuple[str, ...]`
- [ ] Update `FinalDecision`:
  - Add `supporting_evidence_refs: tuple[str, ...]`
  - Add `risk_evidence_refs: tuple[str, ...]`
  - Add `data_gap_refs: tuple[str, ...]`
  - Keep `evidence_event_ids` only as a derived API convenience field.
  - Make non-abstain decisions require at least one `supporting_evidence_refs` entry.
- [ ] Update `PulseAgentDecisionResult` to carry:
  - `evidence_packet`
  - `evidence_gate`
  - `debate_memo`
  - `claim_verification`
  - `stage_audits`

**Acceptance:**

- [ ] `uv run pytest tests/unit/test_pulse_display_status.py tests/unit/test_pulse_claim_evidence_verifier.py -q` can import the new types.
- [ ] Pydantic serialization round-trips `PulseEvidencePacket`, `EvidenceDebateMemo`, and `FinalDecision`.
- [ ] `rg -n "analyst|critic|judge|legacy_skipped" src/gmgn_twitter_intel/domains/pulse_lab` returns no live runtime usage.

---

## Task 3: Evidence Repositories

**Purpose:** 建立 packet builder 的数据访问边界。builder 不能直接散落 SQL，也不能从 OpenAI tool runtime 获取事实。

**Files:**

- Create: `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_evidence_repository.py`
- Create: `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_evidence_source_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/repositories/__init__.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/repository_session.py`
- Create: `tests/integration/test_pulse_evidence_repository.py`

**Steps:**

- [ ] Add `PulseEvidenceRepository`:
  - `upsert_packet(packet: PulseEvidencePacket) -> None`
  - `get_packet_by_hash(hash: str) -> PulseEvidencePacket | None`
  - `get_packet_for_run(run_id: str) -> PulseEvidencePacket | None`
  - `latest_packet_for_candidate(candidate_id: str) -> PulseEvidencePacket | None`
- [ ] Add `PulseEvidenceSourceRepository`:
  - `list_source_events(event_ids: Sequence[str])`
  - `list_enriched_events(event_ids: Sequence[str])`
  - `get_asset_identity(target_type: str, target_id: str)`
  - `get_latest_profile(target_type: str, target_id: str)`
  - `get_latest_market_tick(target_type: str, target_id: str, max_age_ms: int)`
  - `list_market_facts(context: PulseTargetContext, max_age_ms: int)`
- [ ] Use existing canonical tables and repositories where present:
  - `events`
  - `enriched_events`
  - `asset_identity_current` / current identity table in this repo
  - token profile tables already used by Token Radar
  - `market_ticks` as the current live market snapshot source
- [ ] Export both repositories from `repositories/__init__.py` by appending to current exports:
  - `PulseAdmissionRepository`
  - `PulseAgentEvalRepository`
  - `PulseCandidatesRepository`
  - `PulseJobsRepository`
  - `PulsePlaybooksRepository`
  - `PulseReadRepository`
  - `PulseRunsRepository`
  - `PulseEvidenceRepository`
  - `PulseEvidenceSourceRepository`
- [ ] Wire both repositories into `RepositorySession` without replacing existing repository properties.
- [ ] Integration tests must use `tests/postgres_test_utils.py`; do not add SQLite helpers.

**Acceptance:**

- [ ] `uv run pytest tests/integration/test_pulse_evidence_repository.py -q` passes.
- [ ] Packet JSON persists exactly enough to reconstruct `PulseEvidencePacket`.
- [ ] Repository session exposes `repos.pulse_evidence` and `repos.pulse_evidence_sources`.

---

## Task 4: Evidence Packet Builder

**Purpose:** worker 先从事实表构建 sealed packet，使 LLM 输入闭合、可 hash、可 replay。

**Files:**

- Create: `src/gmgn_twitter_intel/domains/pulse_lab/services/evidence_packet_builder.py`
- Create: `tests/unit/test_pulse_evidence_packet_builder.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/types/pulse_candidate_context.py`

**Steps:**

- [ ] Add `PulseEvidenceBuilder.build(context, *, run_id, now_ms) -> PulseEvidencePacket`.
- [ ] Builder inputs:
  - `PulseCandidateContext`
  - `PulseEvidenceSourceRepository`
  - route/window config from existing Pulse worker config
- [ ] Builder must read facts from repositories first:
  - source event ids from candidate context/admission row
  - enriched social/event summaries
  - identity/profile facts
  - normalized market facts
- [ ] Builder may include `factor_snapshot` only in:
  - `admission_context`
  - `source_fingerprints`
  - source event id hints
- [ ] Builder must create refs for every fact that the LLM may cite:
  - social event refs: `event:<event_id>`
  - market metric refs: `metric:market:<metric_name>`
  - identity refs: `identity:<source_id>`
  - profile refs: `profile:<source_id>`
  - cluster refs: `cluster:social:<cluster_id>`
  - gate refs: `gate:pulse:<gate_name>`
- [ ] Builder must normalize CEX market shape:
  - accept `pricefeed_id` as the canonical instrument ref when `venue_id` is absent
  - emit `venue_ref` from provider/exchange identity if present
  - do not leak provider-only keys into downstream readiness checks
- [ ] Builder must sort refs and source ids before hashing.
- [ ] Builder unit tests:
  - complete CEX packet with `pricefeed_id` and no `venue_id`
  - DEX/meme packet with pair/liquidity evidence
  - packet with social but stale market evidence
  - packet hash stable across dict key order changes
  - packet does not treat `factor_snapshot` as source of truth when canonical repo facts disagree

**Acceptance:**

- [ ] `uv run pytest tests/unit/test_pulse_evidence_packet_builder.py -q` passes.
- [ ] For the sampled CEX failure shape, builder emits market evidence as `partial` or `complete`, not a hard `0.5` block due only to missing `venue_id`.

---

## Task 5: Evidence Completeness Gate

**Purpose:** 把“能否公开”和“最多能推荐到什么级别”从 prompt 里移到确定性服务。

**Files:**

- Create: `src/gmgn_twitter_intel/domains/pulse_lab/services/evidence_completeness_gate.py`
- Create: `tests/unit/test_pulse_evidence_completeness_gate.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/services/recommendation_clipper.py`

**Steps:**

- [ ] Add `EvidenceCompletenessGateResult`:
  - `evidence_status`
  - `hard_blocked: bool`
  - `blocked_reason: str | None`
  - `max_decision_status`
  - `required_ref_ids`
  - `missing_ref_types`
  - `data_gaps`
  - `public_allowed: bool`
- [ ] Add route-specific gates:
  - CEX: fresh price or instrument market evidence, source provider, target identity, social event refs
  - DEX/meme: price/liquidity/pair evidence, target identity, social event refs
  - unknown route: social-only packet is `insufficient` and maps to a hidden abstain, not a public candidate
- [ ] Gate result rules:
  - `complete`: public candidate may reach `trade_candidate`
  - `partial`: public candidate may reach `token_watch` or `risk_rejected_high_info`
  - `insufficient`: non-public abstain
  - `stale`: non-public abstain or hidden hold depending freshness health
  - `invalid`: non-public invalid output
- [ ] Update `recommendation_clipper.py`:
  - input: `decision`, existing pulse gate, evidence gate
  - output cannot exceed `evidence_gate.max_decision_status`
  - when clipped, append a gate ref to `data_gap_refs` or `risk_evidence_refs`
- [ ] Unit tests:
  - CEX with `pricefeed_id` passes market contract
  - CEX with no fresh price is `blocked_market_contract`
  - packet with no social refs is `blocked_social_contract`
  - `trade_candidate` clipped to `token_watch` when gate is `partial`
  - `hidden_abstain` for insufficient evidence

**Acceptance:**

- [ ] `uv run pytest tests/unit/test_pulse_evidence_completeness_gate.py tests/unit/test_pulse_recommendation_clipper.py -q` passes.
- [ ] No readiness check in Pulse decision path depends on raw `venue_id` or `pair_symbol`.

---

## Task 6: Packet-Only OpenAI Runtime

**Purpose:** 移除 Pulse agent 的 critical tool calling，把 OpenAI client 改成 packet-only structured synthesis。

**Files:**

- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/providers.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/services/agent_runtime.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_decision_runtime.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/provider_wiring/openai.py`
- Modify: `src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/prompts/evidence_debate.md`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/prompts/decision_maker.md`
- Modify: `tests/unit/test_pulse_decision_agent_client.py`

**Steps:**

- [ ] Hard-cut prompt role concept:
  - `evidence_debate.md` is the packet-only evidence debate prompt.
  - Delete the legacy `investigator.md`; do not keep a compatibility filename.
  - Runtime stage name is `evidence_debate`.
- [ ] Update `PulseAgentRuntimeContract`:
  - `stage_names = ('evidence_debate', 'decision_maker')`
  - `tool_names_by_stage = {'evidence_debate': (), 'decision_maker': ()}`
  - runtime manifest includes `evidence_packet_schema_version`
  - remove route max tool-call budgets from Pulse public runtime
- [ ] In `provider_wiring/openai.py`, remove:
  - `tool_runtime_factory=lambda ... AgentToolRuntime(...)`
  - all Pulse route max tool-call budget wiring
  - any Pulse decision provider requirement for tool runtime
- [ ] In `pulse_decision_agent_client.py`, remove imports and tool registration for:
  - `get_target_recent_tweets`
  - `get_target_price_action`
  - `get_official_token_profile`
- [ ] Client input for `evidence_debate`:
  - sealed `PulseEvidencePacket`
  - `EvidenceCompletenessGateResult`
  - allowed ref ids
- [ ] Client output for `evidence_debate`:
  - `EvidenceDebateMemo`
- [ ] Client input for `decision_maker`:
  - sealed `PulseEvidencePacket`
  - `EvidenceDebateMemo`
  - gate result
  - recommendation constraints
- [ ] Client output for `decision_maker`:
  - `FinalDecision`
- [ ] Prompts must explicitly say:
  - Use only evidence refs in `allowed_evidence_refs`.
  - If a fact is absent, state a data gap and abstain or lower confidence.
  - Do not invent exchange, volume, price, identity, or social evidence.
  - Every claim must cite refs.
- [ ] Unit tests:
  - client constructs no tools
  - request JSON contains `evidence_packet_hash`
  - `evidence_debate` rejects refs not in packet at schema or verifier layer
  - no `tool_calls_present` eval requirement remains

**Acceptance:**

- [ ] `uv run pytest tests/unit/test_pulse_decision_agent_client.py -q` passes.
- [ ] `rg -n "get_target_recent_tweets|get_target_price_action|get_official_token_profile|tool_runtime_factory|investigator_max_tool_calls|investigator.md" src/gmgn_twitter_intel/domains/pulse_lab src/gmgn_twitter_intel/integrations/openai_agents src/gmgn_twitter_intel/app/runtime/provider_wiring/openai.py` shows no Pulse decision runtime usage or legacy prompt path.

---

## Task 7: Claim Verifier, Eval, And Write Gate

**Purpose:** 让 LLM 输出通过确定性 ref 校验和发布门，而不是靠“看起来合理”的 JSON。

**Files:**

- Create: `src/gmgn_twitter_intel/domains/pulse_lab/services/claim_evidence_verifier.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/services/agent_eval.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/services/write_gate.py`
- Create: `tests/unit/test_pulse_claim_evidence_verifier.py`

**Steps:**

- [ ] Add `ClaimEvidenceVerificationResult`:
  - `valid: bool`
  - `unknown_ref_ids`
  - `unsupported_claims`
  - `missing_required_ref_claims`
  - `decision_status`
  - `display_status_if_failed`
- [ ] Verifier input:
  - `PulseEvidencePacket`
  - `EvidenceDebateMemo`
  - `FinalDecision`
- [ ] Verifier rules:
  - every memo claim ref must be in packet allowed refs
  - every final decision ref must be in packet allowed refs
  - non-abstain decision needs supporting refs
  - `evidence_event_ids` cannot substitute for refs
  - data-gap claims can cite gate refs and missing ref descriptors
- [ ] Update `agent_eval.py`:
  - remove live `tool_calls_present` scoring
  - score packet presence, ref coverage, unsupported ref rate, schema validity, gate consistency
  - invalid unknown refs map to `invalid_unknown_evidence_ref`
  - unsupported claims map to `invalid_unsupported_claim`
- [ ] Update `write_gate.py`:
  - accept `final_decision`, `eval_result`, `evidence_gate`, `claim_verification`, `freshness_health`
  - return `PulseWriteGateResult` with `write_allowed`, `publish_allowed`, `display_status`, `reason`
  - `publish_allowed` false when health is degraded beyond threshold
  - no public display when `claim_verification.valid` is false
- [ ] Unit tests:
  - unknown ref blocks publish
  - event-id-only final decision blocks non-abstain publish
  - complete refs and complete gate allows public display
  - health hold maps to `hidden_hold_publish`

**Acceptance:**

- [ ] `uv run pytest tests/unit/test_pulse_claim_evidence_verifier.py -q` passes.
- [ ] `write_gate.py` can explicitly reject publish without throwing worker exceptions.

---

## Task 8: Worker Orchestration Hard Cut

**Purpose:** 把新证据链路接进 `pulse_candidate` worker，确保每个 run 的 audit rows、outcome 和 candidate write 都走新状态机。

**Files:**

- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_job_service.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_runs_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_candidates_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_decision_runtime.py`
- Create: `tests/integration/test_pulse_signal_evidence_flow.py`
- Modify: `tests/unit/test_pulse_candidate_worker.py`
- Modify: `tests/integration/test_pulse_desk_e2e.py`

**Steps:**

- [ ] In job service, create `pulse_agent_runs` row first with outcome `running`.
- [ ] Build and persist `PulseEvidencePacket` before any LLM call.
- [ ] Insert `pulse_agent_run_steps` for `evidence_pack`.
- [ ] Run `EvidenceCompletenessGate`.
- [ ] Insert stage row `evidence_completeness_gate`.
- [ ] If gate hard-blocks:
  - build deterministic abstain `FinalDecision`
  - set outcome to one of:
    - `blocked_market_contract`
    - `blocked_social_contract`
    - `blocked_identity_contract`
    - `abstain_insufficient_evidence`
  - write candidate only if write gate allows audit write
  - do not call OpenAI
- [ ] If gate allows synthesis:
  - call packet-only `evidence_debate`
  - verify debate refs immediately
  - call `decision_maker`
  - run claim verifier over debate and decision
  - clip recommendation
  - run deterministic eval
  - run write gate
- [ ] Persist stage rows with new stage names only.
- [ ] Update `PulseRunsRepository.finish_run` to persist:
  - `evidence_packet_id`
  - `evidence_packet_hash`
  - `evidence_status`
  - `display_status`
  - new outcome values
- [ ] Update `PulseCandidatesRepository.upsert_candidate` to require for new writes:
  - `evidence_packet_hash`
  - `evidence_status`
  - `decision_status`
  - `display_status`
  - `claim_verification_json`
  - `evidence_gate_json`
- [ ] Remove `_investigation_tool_calls_count` from worker outcome logic.
- [ ] Map exceptions:
  - schema validation -> `invalid_schema`
  - unknown ref -> `invalid_unknown_evidence_ref`
  - unsupported claim -> `invalid_unsupported_claim`
  - timeout -> `timeout`
  - provider rate limit -> `provider_rate_limited`
  - provider outage -> `provider_unavailable`
  - other -> `unexpected_exception`

**Acceptance:**

- [ ] `uv run pytest tests/unit/test_pulse_candidate_worker.py tests/integration/test_pulse_signal_evidence_flow.py -q` passes.
- [ ] A hard-blocked market contract run creates packet and gate audit rows, finishes with a typed outcome, and does not call OpenAI.
- [ ] A valid packet run writes a candidate with non-null `evidence_packet_hash`.

---

## Task 9: Read Model, API, CLI, And Frontend Health

**Purpose:** Signal Pulse 不再只展示“有没有 worker running”，而是展示证据链路是否新鲜、是否 hold publish、失败率是什么。

**Files:**

- Create: `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_freshness_health.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_read_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/read_models/signal_pulse_service.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/routes_pulse.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/schemas.py`
- Create: `src/gmgn_twitter_intel/app/surfaces/cli/commands/pulse_replay.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/cli/main.py`
- Modify: `web/src/lib/types/frontend-contracts.ts`
- Modify: `web/src/lib/api.ts`
- Modify: `web/src/routes/pulse/+page.svelte` or current Signal Pulse page component
- Create: `tests/integration/test_signal_pulse_freshness_health.py`
- Modify: `tests/unit/test_signal_pulse_service.py`

**Steps:**

- [ ] `PulseReadRepository` default list filters:
  - `display_status IN ('display_trade_candidate', 'display_token_watch', 'display_risk_rejected_high_info')`
  - `evidence_packet_hash IS NOT NULL`
- [ ] Add explicit debug/admin query path for hidden rows. It must be opt-in and labeled diagnostic, not default public behavior.
- [ ] Add `PulseFreshnessHealth`:
  - `latest_packet_created_at_ms`
  - `latest_agent_run_finished_at_ms`
  - `latest_public_candidate_updated_at_ms`
  - `due_jobs`
  - `claimed_jobs`
  - `failed_jobs_4h`
  - `agent_runs_4h`
  - `agent_failed_4h`
  - `unknown_ref_failures_4h`
  - `unsupported_claim_failures_4h`
  - `hidden_abstain_4h`
  - `hidden_hold_publish_4h`
  - `publish_status: healthy | degraded | hold_publish`
  - `reasons`
- [ ] Add API schema fields:
  - `display_status`
  - `evidence_status`
  - `decision_status`
  - `evidence_packet_hash`
  - `claim_verification`
  - `pulse_health`
- [ ] Update `/api/status` or the existing worker status route to include Pulse health, not only worker process state.
- [ ] Add CLI command through existing `main.py` command dispatch pattern:
  - `uv run gmgn-twitter-intel pulse replay-eval --since-hours 4`
  - `uv run gmgn-twitter-intel pulse health --since-hours 4`
- [ ] Frontend:
  - update generated/manual type contracts in `web/src/lib/types/frontend-contracts.ts`
  - show health banner when `publish_status != healthy`
  - default list remains public display only
  - diagnostic view may show hidden counts but not mix them into public cards

**Acceptance:**

- [ ] `uv run pytest tests/unit/test_signal_pulse_service.py tests/integration/test_signal_pulse_freshness_health.py -q` passes.
- [ ] Frontend typecheck passes with the new fields.
- [ ] API default Pulse list cannot show rows without `evidence_packet_hash`.

---

## Task 10: Replay Eval Harness

**Purpose:** 把这次生产故障变成可复放数据集，避免后续重构再次把 Signal Pulse 变成“运行着但不产出”。

**Files:**

- Create: `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_replay_eval.py`
- Create: `tests/integration/test_pulse_replay_eval.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/cli/commands/pulse_replay.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/cli/main.py`

**Steps:**

- [ ] Add replay case model:
  - `case_id`
  - `candidate_context`
  - `expected_packet_properties`
  - `expected_gate_status`
  - `expected_public_allowed`
  - `expected_failure_class`
- [ ] Seed replay cases from deterministic fixtures:
  - CEX with `pricefeed_id` and no `venue_id`
  - unknown evidence ref from LLM output
  - schema validation failure
  - hidden abstain with fresh packet
  - stale market facts
- [ ] Replay flow:
  - build packet
  - run gate
  - optionally run stubbed LLM outputs
  - run verifier/eval/write gate
  - output pass/fail summary
- [ ] CLI output must include:
  - total cases
  - pass count
  - failure classes
  - newest packet clock
  - public-allowed count
- [ ] Tests must not call external providers.

**Acceptance:**

- [ ] `uv run pytest tests/integration/test_pulse_replay_eval.py -q` passes.
- [ ] `uv run gmgn-twitter-intel pulse replay-eval --fixture smoke` exits non-zero on a deliberately broken fixture and zero on valid fixtures.

---

## Task 11: Architecture Guards

**Purpose:** 用测试防止未来把关键事实重新塞回 LLM tools 或旧状态机。

**Files:**

- Create: `tests/architecture/test_pulse_signal_evidence_contracts.py`

**Steps:**

- [ ] Add guard: Pulse decision runtime does not import or register:
  - `get_target_recent_tweets`
  - `get_target_price_action`
  - `get_official_token_profile`
- [ ] Add guard: live Pulse runtime code does not contain `legacy_skipped`.
- [ ] Add guard: live Pulse stage names do not contain `analyst`, `critic`, `judge`, or `investigator` as stage values.
- [ ] Add guard: `pulse_read_repository.py` default public list filters by `display_status` and `evidence_packet_hash`.
- [ ] Add guard: `pulse_candidate_job_service.py` calls `PulseEvidenceBuilder` before OpenAI provider call.
- [ ] Add guard: `FinalDecision` has `supporting_evidence_refs`, `risk_evidence_refs`, and `data_gap_refs`.

**Acceptance:**

- [ ] `uv run pytest tests/architecture/test_pulse_signal_evidence_contracts.py -q` passes.

---

## Task 12: Documentation Update

**Purpose:** 让后续调试者能从 docs 看懂新链路，而不是回到旧的工具调用模型。

**Files:**

- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/WORKER_FLOW.md`
- Modify: `docs/WORKERS.md`
- Modify: `docs/CONTRACTS.md`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/ARCHITECTURE.md`

**Steps:**

- [ ] Update `docs/ARCHITECTURE.md`:
  - Pulse is evidence-first CQRS read-model pipeline.
  - `pulse_evidence_packets` is the LLM trust boundary.
- [ ] Update `docs/WORKER_FLOW.md`:
  - `pulse_candidate` worker stage order from Task 8.
  - Include outcome taxonomy and recovery actions.
- [ ] Update `docs/WORKERS.md`:
  - worker status must be interpreted with Pulse health clocks.
  - worker running does not imply public Pulse freshness.
- [ ] Update `docs/CONTRACTS.md`:
  - API fields for `display_status`, `evidence_status`, `decision_status`, `pulse_health`.
  - CLI commands for pulse health and replay eval.
- [ ] Update `src/gmgn_twitter_intel/domains/pulse_lab/ARCHITECTURE.md`:
  - include sequence diagram and module ownership.
  - explain TradingAgents-inspired debate shape.

**Acceptance:**

- [ ] Docs mention sealed `PulseEvidencePacket`.
- [ ] Docs do not describe LLM tool calls as required Pulse fact acquisition.
- [ ] Docs state that historical rows without packet hash are audit-only.

---

## Task 13: Full Verification And Rollout

**Purpose:** 验证新链路不会再出现“worker alive, public Signal Pulse stale, failures hidden”的状态。

**Steps:**

- [ ] Run focused tests:

```bash
uv run pytest \
  tests/unit/test_pulse_evidence_packet_builder.py \
  tests/unit/test_pulse_evidence_completeness_gate.py \
  tests/unit/test_pulse_claim_evidence_verifier.py \
  tests/unit/test_pulse_recommendation_clipper.py \
  tests/unit/test_pulse_decision_agent_client.py \
  tests/unit/test_pulse_candidate_worker.py \
  tests/unit/test_signal_pulse_service.py \
  tests/integration/test_pulse_evidence_repository.py \
  tests/integration/test_pulse_signal_evidence_flow.py \
  tests/integration/test_signal_pulse_freshness_health.py \
  tests/integration/test_pulse_replay_eval.py \
  tests/architecture/test_pulse_signal_evidence_contracts.py \
  -q
```

- [ ] Run lint/type gates used by this repo:

```bash
uv run ruff check src tests
```

- [ ] Run CLI smoke against local config without printing secrets:

```bash
uv run gmgn-twitter-intel config
uv run gmgn-twitter-intel pulse health --since-hours 4
uv run gmgn-twitter-intel pulse replay-eval --fixture smoke
```

- [ ] Run a local worker smoke on disposable DB:
  - enqueue one CEX candidate with `pricefeed_id`
  - verify packet created
  - verify stage rows use new names
  - verify candidate has `evidence_packet_hash`
  - verify default Pulse API shows only public display statuses
- [ ] Run frontend checks:

```bash
cd web
npm run check
```

- [ ] Production rollout order:
  - deploy migration
  - deploy code
  - run `pulse health --since-hours 4`
  - run `pulse replay-eval --since-hours 4` if connected to production read-only fixtures
  - monitor `publish_status`, `agent_failed_4h`, `unknown_ref_failures_4h`, `hidden_hold_publish_4h`

**Acceptance:**

- [ ] Worker status and Pulse health both report fresh clocks.
- [ ] Public Signal Pulse newest displayable row advances after a successful evidence-first run.
- [ ] Agent failure rate no longer dominated by `schema_validation_failed` or `unknown_evidence_id`.
- [ ] Default public Pulse API cannot become stale silently; health exposes hold/degraded reasons.

---

## Architecture Tradeoffs

### Why Not Add More Agents

More agents would increase cost, latency, and failure surface without fixing the trust boundary. The production failure showed facts were often present but not admissible to the final decision. A three-agent writer setup would still fail if each role reasons over an unsealed or weakly typed context.

### Why Borrow TradingAgents Debate Shape

TradingAgents has a useful separation: analysts produce reports, bull/bear researchers debate from those reports, and a manager synthesizes. Pulse adopts that separation in compact form:

```text
TradingAgents: analyst reports -> bull researcher / bear researcher -> research manager
Pulse: sealed evidence packet -> bull/bear evidence memo -> decision maker
```

The key difference is that Pulse evidence acquisition is deterministic and worker-owned. The LLM debate cannot expand the fact universe.

### Why Keep One Worker

`pulse_candidate` already owns admission, jobs, run audit, candidate writes, and worker status. Splitting packet construction into a separate worker would introduce cross-worker ordering and stale packet races before the current trust boundary is fixed. A later scale-out can split after `pulse_evidence_packets` becomes stable.

### Why Hide Historical Candidates Without Packet Hash

`pulse_candidates` is a rebuildable read model. Translating old rows into displayable evidence-first candidates would create compatibility code and false confidence. Historical rows remain in DB for audit, while default public reads require `display_status` and `evidence_packet_hash`.

### Why Keep Structured Output But Add Verifier

Structured output guarantees shape. It does not guarantee truth, evidence coverage, or citation validity. `ClaimEvidenceVerifier` closes that gap by checking refs against the sealed packet.

### Coupling Impact

- `PulseEvidenceBuilder` couples Pulse to canonical domain repositories, which is intended because facts belong in the data layer.
- OpenAI runtime decouples from provider data acquisition because it receives a sealed packet.
- API/frontend couple to `display_status` and `pulse_health`, not to agent internals.
- The only new persistence coupling is `pulse_candidates.evidence_packet_hash`, which is required to make public rows replayable.

### Complexity Budget

The plan adds several modules, but each module owns one boundary:

- packet builder: admissible facts
- completeness gate: public eligibility ceiling
- debate synthesizer: bounded reasoning
- verifier: ref truth boundary
- write gate: public publish decision
- freshness health: operator visibility

This is more code than a patch, but less complex than broad multi-agent orchestration and easier to replay.
