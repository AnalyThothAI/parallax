# Token Narrative Intelligence Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Draft
**Date:** 2026-05-18
**Owning spec:** `docs/superpowers/specs/active/2026-05-18-token-narrative-intelligence-hard-cut-cn.md`
**Worktree:** `.worktrees/token-narrative-intelligence-hard-cut/`
**Branch:** `codex/token-narrative-intelligence-hard-cut`

**Goal:** 一次性把 Token Radar / Token Case 的解释层从数量、phase、deterministic `agent_brief` 升级为持久化的 token-window 叙事读模：per-mention 语义、token discussion digest、Mention Timeline 语义标签，以及只读 public Pulse overlay。

**Architecture:** 新增 `domains/narrative_intel`，位于 `token_intel` 和 `pulse_lab` 之间。`token_intel` 继续拥有 Radar ranking 和 target views；`narrative_intel` 读取 facts/Radar rows 并写自己的 read models；`pulse_lab` 可以读取 digest 作为 evidence，但不能反向触发 narrative 或写 Radar/Digest。API surface 只组合 read services，不跑 provider、不写叙事、不做 raw SQL。

**Tech Stack:** Python 3.13, Pydantic v2, openai-agents, psycopg, Alembic, FastAPI, React, TypeScript, Vitest, pytest, ruff, PostgreSQL.

---

## Pre-flight

- [ ] Spec `docs/superpowers/specs/active/2026-05-18-token-narrative-intelligence-hard-cut-cn.md` approved.
- [ ] Create isolated worktree:
  ```bash
  git worktree add .worktrees/token-narrative-intelligence-hard-cut -b codex/token-narrative-intelligence-hard-cut main
  ```
- [ ] Verify worktree:
  ```bash
  cd .worktrees/token-narrative-intelligence-hard-cut
  git branch --show-current
  git status --short
  ```
  Expected branch: `codex/token-narrative-intelligence-hard-cut`; expected status: clean.
- [ ] Confirm runtime config paths before live-data verification:
  ```bash
  uv run gmgn-twitter-intel config
  ```
  Expected: `config_path` and `workers_config_path` point at `~/.gmgn-twitter-intel/`; do not print secrets.
- [ ] Baseline checks:
  ```bash
  uv run ruff check .
  uv run pytest tests/architecture -q
  uv run pytest tests/unit/test_worker_settings.py tests/unit/test_bootstrap_worker_runtime_wiring.py -q
  cd web && npm test -- --run web/tests/unit/shared/model/tokenCase.test.ts web/tests/unit/features/token-case/model/buildTokenCaseViewModel.test.ts
  ```

Known-failing baseline tests: none expected. If PostgreSQL-dependent integration tests cannot run locally, record the environment gap and run them where Postgres is available before merge.

---

## Release Shape

One hard-cut branch and one PR. Do not merge partial PRs that expose mixed API contracts. Internal commits should be reviewable in this order:

1. Architecture guardrails and failing tests.
2. Storage migration and repository/query layer.
3. Core narrative domain types/services.
4. OpenAI provider adapter and prompts.
5. Workers, config, wake, repository session, runtime wiring.
6. API read composition and canonical Token Case hard cut.
7. Pulse evidence source enrichment.
8. Frontend contracts, view models, UI states, fixtures.
9. Docs, generated OpenAPI/types, verification.

Reason: if backend removes `agent_brief` before web consumes `discussion_digest`, Token Case breaks. If web expects `discussion_digest` before workers/read services exist, Radar lies with empty states. Production should receive one coherent API plus UI cut.

---

## Core Design Decisions

- [ ] `narrative_intel` is a new domain. It is not a submodule of `token_intel` because ranking and narrative interpretation have different compute budgets and failure modes. It is not inside `pulse_lab` because Pulse is downstream decisioning, not the universal token discussion source.
- [ ] `token_mention_semantics` and `token_discussion_digests` are rebuildable read models with single runtime writers:
  - `MentionSemanticsWorker` writes `token_mention_semantics`.
  - `TokenDiscussionDigestWorker` writes `token_discussion_digests`.
- [ ] `narrative_admissions` is control-plane scheduling state, not public truth. `MentionSemanticsWorker` owns admission reconciliation from Radar rows; `TokenDiscussionDigestWorker` reads it.
- [ ] Create `narrative_model_runs` instead of reusing `model_runs`. The existing `model_runs` table is enrichment-specific: `job_id` and `event_id` are non-null and reference `enrichment_jobs/events`. Narrative calls are batch-level and token-window-level, so overloading `model_runs` would create fake event/job ids.
- [ ] No GET request writes. Token Case direct visits outside Radar can show `semantic_unavailable` or `insufficient`; the first cut does not create request-path admission hints because `/api/token-case` must remain a read surface.
- [ ] Store worker scopes as `all | matched`. Token Case can accept/return UI scope `watched`, but repository lookups canonicalize it to `matched`.
- [ ] Keep `build_topic_agent_brief` for topic and ambiguous search results. Remove canonical token usage of `build_token_agent_brief`; do not add compatibility aliases that map digest back to `agent_brief`.

---

## File Structure

### Create

- `src/gmgn_twitter_intel/domains/narrative_intel/__init__.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/ARCHITECTURE.md`
- `src/gmgn_twitter_intel/domains/narrative_intel/_constants.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/providers.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/interfaces.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/types/__init__.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/types/mention_semantics.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/types/discussion_digest.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/types/evidence_refs.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/queries/__init__.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/queries/narrative_source_query.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/repositories/__init__.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/repositories/narrative_repository.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/services/__init__.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/services/fingerprints.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/services/narrative_admission.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/services/mention_semantics_service.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/services/discussion_digest_service.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/services/evidence_ref_validator.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/read_models/__init__.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/read_models/narrative_read_model.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/runtime/__init__.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/runtime/mention_semantics_worker.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/runtime/token_discussion_digest_worker.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/prompts/__init__.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/prompts/mention_semantics.md`
- `src/gmgn_twitter_intel/domains/narrative_intel/prompts/discussion_digest.md`
- `src/gmgn_twitter_intel/integrations/openai_agents/narrative_intel_agent_client.py`
- `src/gmgn_twitter_intel/app/runtime/worker_factories/narrative_intel.py`
- `src/gmgn_twitter_intel/platform/db/alembic/versions/20260518_0063_narrative_intel_read_models.py`
- `tests/architecture/test_narrative_intel_boundaries.py`
- `tests/unit/domains/narrative_intel/test_narrative_admission.py`
- `tests/unit/domains/narrative_intel/test_mention_semantics_service.py`
- `tests/unit/domains/narrative_intel/test_discussion_digest_service.py`
- `tests/unit/domains/narrative_intel/test_narrative_read_model.py`
- `tests/unit/domains/narrative_intel/test_narrative_workers.py`
- `tests/integration/test_narrative_repository.py`
- `tests/unit/test_api_narrative_contract.py`
- `web/tests/unit/features/token-case/model/buildTokenCaseNarrativeViewModel.test.ts`
- `web/tests/unit/shared/model/tokenRadarCompactCaseNarrative.test.ts`

### Modify

- `src/gmgn_twitter_intel/app/runtime/provider_wiring/types.py`
- `src/gmgn_twitter_intel/app/runtime/provider_wiring/openai.py`
- `src/gmgn_twitter_intel/app/runtime/providers_wiring.py`
- `src/gmgn_twitter_intel/app/runtime/repository_session.py`
- `src/gmgn_twitter_intel/app/runtime/wake_bus.py`
- `src/gmgn_twitter_intel/app/runtime/worker_registry.py`
- `src/gmgn_twitter_intel/app/runtime/worker_factories/__init__.py`
- `src/gmgn_twitter_intel/app/surfaces/api/routes_radar.py`
- `src/gmgn_twitter_intel/app/surfaces/api/routes_search.py`
- `src/gmgn_twitter_intel/app/surfaces/api/schemas.py`
- `src/gmgn_twitter_intel/platform/config/settings.py`
- `src/gmgn_twitter_intel/domains/token_intel/read_models/token_case_service.py`
- `src/gmgn_twitter_intel/domains/token_intel/read_models/search_agent_brief.py`
- `src/gmgn_twitter_intel/domains/token_intel/read_models/search_inspect_service.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_evidence_source_repository.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/services/evidence_packet_builder.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/ARCHITECTURE.md`
- `tests/architecture/test_src_domain_architecture.py`
- `tests/architecture/test_worker_runtime_contracts.py`
- `tests/unit/test_worker_settings.py`
- `tests/unit/test_bootstrap_worker_runtime_wiring.py`
- `tests/integration/test_api_http.py`
- `tests/contract/test_openapi_drift.py` only if stricter contract assertions are needed
- `docs/ARCHITECTURE.md`
- `docs/WORKERS.md`
- `docs/WORKER_FLOW.md`
- `docs/CONTRACTS.md`
- `docs/FRONTEND.md`
- `docs/generated/openapi.json`
- `web/src/lib/types/openapi.ts`
- `web/src/lib/types/frontend-contracts.ts`
- `web/src/lib/types/index.ts`
- `web/src/shared/model/tokenRadarCompactCase.ts`
- `web/src/shared/model/tokenCase.ts`
- `web/src/shared/model/tokenCaseViewModel.ts`
- `web/src/features/token-case/model/buildTokenCaseViewModel.ts`
- `web/src/features/search/model/searchCase.ts`
- `web/src/features/search/ui/SearchTokenIntelPage.tsx`
- `web/src/shared/ui/case-file/*`
- `web/tests/fixtures/tokenCaseFixture.ts`
- `web/tests/routes/token-target.route.test.tsx`
- `web/tests/component/features/token-case/ui/TokenCaseRoute.routing.test.tsx`
- `web/tests/component/features/search/ui/SearchIntelPage.routing.test.tsx`
- `web/tests/unit/shared/query/patchMarketUpdate.test.ts`

### Delete Or Hard-Remove Runtime Usage

- Remove `build_token_agent_brief` import and use from canonical token dossier.
- Remove `agent_brief` from `TokenCaseData`, `TokenCaseDossier`, token search result payload, token fixtures, and Token Case UI view model.
- Keep topic/ambiguous search `agent_brief` as a search-topic contract, not as Token Case compatibility.

---

## Storage / Migrations

Create Alembic revision `20260518_0063_narrative_intel_read_models.py` with `down_revision = "20260518_0062"`.

### `narrative_admissions`

Control-plane scheduling state. Only `MentionSemanticsWorker` writes it.

```sql
CREATE TABLE IF NOT EXISTS narrative_admissions (
  admission_id TEXT PRIMARY KEY,
  target_type TEXT NOT NULL,
  target_id TEXT NOT NULL,
  window TEXT NOT NULL,
  scope TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  status TEXT NOT NULL,
  reason TEXT NOT NULL,
  priority BIGINT NOT NULL DEFAULT 0,
  last_radar_rank BIGINT,
  last_rank_score DOUBLE PRECISION,
  source_event_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  source_fingerprint TEXT,
  source_max_received_at_ms BIGINT,
  admitted_at_ms BIGINT NOT NULL,
  last_seen_at_ms BIGINT NOT NULL,
  next_semantics_due_at_ms BIGINT NOT NULL DEFAULT 0,
  next_digest_due_at_ms BIGINT NOT NULL DEFAULT 0,
  suppressed_at_ms BIGINT,
  updated_at_ms BIGINT NOT NULL,
  CHECK (window IN ('5m', '1h', '4h', '24h')),
  CHECK (scope IN ('all', 'matched')),
  CHECK (status IN ('admitted', 'suppressed'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_narrative_admissions_target
  ON narrative_admissions(target_type, target_id, window, scope, schema_version);

CREATE INDEX IF NOT EXISTS idx_narrative_admissions_due_semantics
  ON narrative_admissions(status, next_semantics_due_at_ms, priority DESC, last_seen_at_ms DESC);

CREATE INDEX IF NOT EXISTS idx_narrative_admissions_due_digest
  ON narrative_admissions(status, next_digest_due_at_ms, priority DESC, last_seen_at_ms DESC);
```

### `narrative_model_runs`

Audit table for narrative LLM calls. It is not a public read model.

```sql
CREATE TABLE IF NOT EXISTS narrative_model_runs (
  run_id TEXT PRIMARY KEY,
  stage TEXT NOT NULL,
  target_type TEXT,
  target_id TEXT,
  window TEXT,
  scope TEXT,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  artifact_version_hash TEXT,
  input_hash TEXT NOT NULL,
  output_hash TEXT,
  evidence_event_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  request_json JSONB NOT NULL,
  response_json JSONB,
  usage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  trace_metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL,
  error TEXT,
  started_at_ms BIGINT NOT NULL,
  finished_at_ms BIGINT NOT NULL,
  latency_ms BIGINT NOT NULL DEFAULT 0,
  CHECK (stage IN ('mention_semantics', 'discussion_digest')),
  CHECK (status IN ('done', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_narrative_model_runs_target
  ON narrative_model_runs(target_type, target_id, window, scope, finished_at_ms DESC);

CREATE INDEX IF NOT EXISTS idx_narrative_model_runs_stage_finished
  ON narrative_model_runs(stage, finished_at_ms DESC);
```

### `token_mention_semantics`

Per event-target semantic read model. Only `MentionSemanticsWorker` writes it.

```sql
CREATE TABLE IF NOT EXISTS token_mention_semantics (
  semantic_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  target_type TEXT NOT NULL,
  target_id TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  model_version TEXT NOT NULL,
  text_fingerprint TEXT NOT NULL,
  language TEXT,
  status TEXT NOT NULL,
  trade_stance TEXT NOT NULL DEFAULT 'unknown',
  attention_valence TEXT NOT NULL DEFAULT 'unknown',
  narrative_cluster_key TEXT,
  claim_type TEXT NOT NULL DEFAULT 'other',
  evidence_type TEXT NOT NULL DEFAULT 'unknown',
  semantic_confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
  co_mentioned_targets_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  evidence_refs_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  raw_label_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  model_run_id TEXT REFERENCES narrative_model_runs(run_id) ON DELETE SET NULL,
  source_received_at_ms BIGINT NOT NULL,
  queued_at_ms BIGINT,
  computed_at_ms BIGINT,
  retry_count BIGINT NOT NULL DEFAULT 0,
  next_retry_at_ms BIGINT NOT NULL DEFAULT 0,
  error TEXT,
  CHECK (status IN ('queued', 'labeled', 'retryable_error', 'semantic_unavailable', 'stale')),
  CHECK (trade_stance IN ('bullish', 'bearish', 'neutral', 'skeptical', 'exit-risk', 'research-only', 'unknown')),
  CHECK (attention_valence IN ('positive', 'negative', 'mixed', 'ironic', 'hostile', 'panic', 'celebratory', 'informational', 'unknown'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_token_mention_semantics_identity
  ON token_mention_semantics(event_id, target_type, target_id, schema_version, text_fingerprint);

CREATE INDEX IF NOT EXISTS idx_token_mention_semantics_due
  ON token_mention_semantics(status, next_retry_at_ms, source_received_at_ms DESC);

CREATE INDEX IF NOT EXISTS idx_token_mention_semantics_target_time
  ON token_mention_semantics(target_type, target_id, source_received_at_ms DESC);

CREATE INDEX IF NOT EXISTS idx_token_mention_semantics_cluster
  ON token_mention_semantics(target_type, target_id, narrative_cluster_key, source_received_at_ms DESC);
```

### `token_discussion_digests`

Token-window discussion read model. Only `TokenDiscussionDigestWorker` writes it.

```sql
CREATE TABLE IF NOT EXISTS token_discussion_digests (
  digest_id TEXT PRIMARY KEY,
  target_type TEXT NOT NULL,
  target_id TEXT NOT NULL,
  window TEXT NOT NULL,
  scope TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  model_version TEXT NOT NULL,
  status TEXT NOT NULL,
  is_current BOOLEAN NOT NULL DEFAULT true,
  source_fingerprint TEXT,
  label_fingerprint TEXT,
  headline_zh TEXT,
  dominant_narratives_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  bull_view_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  bear_view_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  stance_mix_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  attention_valence_mix_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  propagation_read_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  reflexivity_read_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  watch_triggers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  invalidation_conditions_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  data_gaps_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  semantic_coverage DOUBLE PRECISION NOT NULL DEFAULT 0,
  source_event_count BIGINT NOT NULL DEFAULT 0,
  labeled_event_count BIGINT NOT NULL DEFAULT 0,
  independent_author_count BIGINT NOT NULL DEFAULT 0,
  evidence_refs_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  model_run_id TEXT REFERENCES narrative_model_runs(run_id) ON DELETE SET NULL,
  computed_at_ms BIGINT NOT NULL,
  expires_at_ms BIGINT,
  superseded_at_ms BIGINT,
  CHECK (window IN ('5m', '1h', '4h', '24h')),
  CHECK (scope IN ('all', 'matched')),
  CHECK (status IN ('ready', 'pending', 'insufficient', 'semantic_unavailable', 'stale'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_token_discussion_digests_current
  ON token_discussion_digests(target_type, target_id, window, scope, schema_version)
  WHERE is_current;

CREATE INDEX IF NOT EXISTS idx_token_discussion_digests_target_history
  ON token_discussion_digests(target_type, target_id, window, scope, computed_at_ms DESC);

CREATE INDEX IF NOT EXISTS idx_token_discussion_digests_status
  ON token_discussion_digests(status, computed_at_ms DESC);
```

Downgrade may drop only the four new narrative tables and their indexes. Production rollback should usually leave them inert and roll application code back, because the old code ignores these tables.

---

## Backend Implementation

### 1. Architecture Tests First

#### `tests/architecture/test_src_domain_architecture.py`

- [ ] Add `narrative_intel` to `DOMAINS`.
- [ ] Add `narrative_intel` to `PROVIDER_DOMAINS` because it has `providers.py`.
- [ ] Add provider wiring facade exports:
  - `NarrativeIntelProviders`
  - `OpenAINarrativeIntelProvider`
  - `openai_narrative_intel_provider`
  if the facade export tests require concrete provider names.

#### `tests/architecture/test_worker_runtime_contracts.py`

- [ ] Add expected workers:
  ```python
  "mention_semantics": (
      "gmgn_twitter_intel.domains.narrative_intel.runtime.mention_semantics_worker.MentionSemanticsWorker"
  ),
  "token_discussion_digest": (
      "gmgn_twitter_intel.domains.narrative_intel.runtime.token_discussion_digest_worker.TokenDiscussionDigestWorker"
  ),
  ```
- [ ] Add both keys to `OLD_READYZ_WORKER_KEYS`.
- [ ] Add `narrative_intel.py` to `EXPECTED_WORKER_FACTORY_FILES`.
- [ ] Add single-writer read model allowlists:
  ```python
  "token_mention_semantics": {
      SRC / "domains/narrative_intel/repositories/narrative_repository.py",
      SRC / "domains/narrative_intel/runtime/mention_semantics_worker.py",
      SRC / "platform/db/alembic/versions/20260518_0063_narrative_intel_read_models.py",
  },
  "token_discussion_digests": {
      SRC / "domains/narrative_intel/repositories/narrative_repository.py",
      SRC / "domains/narrative_intel/runtime/token_discussion_digest_worker.py",
      SRC / "platform/db/alembic/versions/20260518_0063_narrative_intel_read_models.py",
  },
  ```

#### `tests/architecture/test_narrative_intel_boundaries.py`

Create static gates:

- [ ] `narrative_intel` must not import `pulse_lab` concrete modules. Pulse may consume narrative through `gmgn_twitter_intel.domains.narrative_intel.interfaces`.
- [ ] API routes may import `NarrativeReadModel` but must not import narrative repositories or providers directly.
- [ ] `token_intel` must not import `narrative_intel` concrete modules; API composition owns hydration.
- [ ] `narrative_intel/runtime` must not import `integrations/openai_agents` directly; provider is injected.
- [ ] No runtime code emits or consumes Pulse hidden candidate states as narrative triggers.

### 2. Narrative Domain Constants And Types

#### `src/gmgn_twitter_intel/domains/narrative_intel/_constants.py`

- [ ] Define:
  ```python
  NARRATIVE_SCHEMA_VERSION = "narrative_intel_v1"
  MENTION_SEMANTICS_PROMPT_VERSION = "mention_semantics_v1"
  DISCUSSION_DIGEST_PROMPT_VERSION = "discussion_digest_v1"
  NARRATIVE_MODEL_VERSION_UNKNOWN = "unknown"
  NARRATIVE_WINDOWS = ("5m", "1h", "4h", "24h")
  NARRATIVE_SCOPES = ("all", "matched")
  ```

#### `types/mention_semantics.py`

- [ ] Pydantic models:
  ```python
  class MentionSemanticLabel(BaseModel):
      event_id: str
      target_type: str
      target_id: str
      language: str | None = None
      trade_stance: Literal["bullish", "bearish", "neutral", "skeptical", "exit-risk", "research-only", "unknown"]
      attention_valence: Literal["positive", "negative", "mixed", "ironic", "hostile", "panic", "celebratory", "informational", "unknown"]
      narrative_cluster_key: str | None = None
      claim_type: str
      evidence_type: str
      semantic_confidence: float
      co_mentioned_targets: list[dict[str, Any]] = Field(default_factory=list)
      evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
      status: Literal["labeled", "semantic_unavailable"]
      unavailable_reason: str | None = None
  ```
- [ ] `MentionSemanticsBatchRequest` and `MentionSemanticsBatchResult` include `run_id`, `schema_version`, `prompt_version`, `mentions`, `raw_response`, `agent_run_audit`.
- [ ] Validators clamp confidence to `[0, 1]`, normalize empty strings to `unknown`, and require at least one evidence ref for `status="labeled"`.

#### `types/discussion_digest.py`

- [ ] Pydantic models:
  - `NarrativeCluster`
  - `ReflexivityRead`
  - `DigestArgument`
  - `TokenDiscussionDigest`
  - `DiscussionDigestRequest`
  - `DiscussionDigestResult`
- [ ] `TokenDiscussionDigest.status` enum: `ready | pending | insufficient | semantic_unavailable | stale`.
- [ ] `ready` digest validator requires non-empty `evidence_refs`, `dominant_narratives`, `bull_view.evidence_refs` or `bear_view.evidence_refs`, and `semantic_coverage > 0`.
- [ ] `insufficient` digest validator requires non-empty `data_gaps`.

#### `types/evidence_refs.py`

- [ ] Define stable ref shapes:
  ```python
  class EvidenceRef(BaseModel):
      ref_id: str
      kind: Literal["event", "semantic", "market_tick", "profile", "data_gap"]
      source_table: str
      event_id: str | None = None
      semantic_id: str | None = None
      target_type: str | None = None
      target_id: str | None = None
      confidence: float | None = None
  ```
- [ ] `ref_id` format:
  - `event:<event_id>`
  - `semantic:<semantic_id>`
  - `market_tick:<tick_id>`
  - `profile:<target_type>:<target_id>`
  - `gap:<reason>`

### 3. Repository And Query Layer

#### `queries/narrative_source_query.py`

- [ ] Implement source reads over facts/read models, no provider calls:
  ```python
  class NarrativeSourceQuery:
      def admitted_radar_rows(
          self,
          *,
          window: str,
          scope: str,
          limit: int,
          projection_version: str,
      ) -> list[dict[str, Any]]

      def source_mentions_for_admission(
          self,
          *,
          target_type: str,
          target_id: str,
          since_ms: int,
          watched_only: bool,
          limit: int,
      ) -> list[dict[str, Any]]

      def digest_context(
          self,
          *,
          target_type: str,
          target_id: str,
          window: str,
          scope: str,
          since_ms: int,
          max_mentions: int,
      ) -> dict[str, Any]
  ```
- [ ] `source_mentions_for_admission` should reuse the same fact graph as `TokenTargetRepository.timeline_rows`: `token_intent_resolutions`, `events`, `enriched_events`, `market_ticks`, watched flags, identity/profile fields.
- [ ] Query returns normalized `text_clean`, `author_handle`, `received_at_ms`, `tweet_id`, `canonical_url`, `reference_json`, `is_watched`, `price` context, and resolved target fields.

#### `repositories/narrative_repository.py`

- [ ] Implement control/read-model persistence:
  ```python
  class NarrativeRepository:
      def upsert_admissions_from_radar_rows(
          self,
          rows: Sequence[dict[str, Any]],
          *,
          window: str,
          scope: str,
          schema_version: str,
          now_ms: int,
          source_limit: int,
      ) -> dict[str, int]

      def due_admissions_for_semantics(self, *, now_ms: int, limit: int) -> list[dict[str, Any]]
      def due_mentions_for_labeling(self, *, now_ms: int, limit: int) -> list[dict[str, Any]]
      def enqueue_missing_mention_semantics(
          self,
          source_rows: Sequence[dict[str, Any]],
          *,
          schema_version: str,
          model_version: str,
          now_ms: int,
      ) -> dict[str, int]

      def record_narrative_model_run(self, run: dict[str, Any], *, commit: bool = True) -> dict[str, Any]
      def complete_mention_semantics_batch(
          self,
          *,
          run_id: str,
          labels: Sequence[dict[str, Any]],
          failures: Sequence[dict[str, Any]],
          now_ms: int,
      ) -> dict[str, int]

      def due_digest_targets(self, *, now_ms: int, limit: int) -> list[dict[str, Any]]
      def digest_context(self, *, target_type: str, target_id: str, window: str, scope: str, since_ms: int, max_mentions: int) -> dict[str, Any]
      def replace_current_digest(self, digest: dict[str, Any], *, now_ms: int) -> dict[str, Any]

      def current_digests_for_targets(
          self,
          targets: Sequence[dict[str, str]],
          *,
          window: str,
          scope: str,
          schema_version: str,
      ) -> dict[tuple[str, str], dict[str, Any]]

      def semantics_for_posts(
          self,
          posts: Sequence[dict[str, Any]],
          *,
          schema_version: str,
      ) -> dict[tuple[str, str, str], dict[str, Any]]
  ```
- [ ] `replace_current_digest` must run in one transaction:
  1. Set previous current digest `is_current=false`, `superseded_at_ms=now_ms`.
  2. Insert new digest with `is_current=true`.
- [ ] Use deterministic ids:
  - `admission_id = sha256("narrative_admission"|target_type|target_id|window|scope|schema_version)`.
  - `semantic_id = sha256("mention_semantic"|event_id|target_type|target_id|schema_version|text_fingerprint)`.
  - `digest_id = sha256("discussion_digest"|target_type|target_id|window|scope|schema_version|source_fingerprint|label_fingerprint)`.
  - `run_id = sha256("narrative_model_run"|stage|input_hash|started_at_ms)`.

### 4. Core Services

#### `services/fingerprints.py`

- [ ] `text_fingerprint(text: str) -> str`: normalize whitespace, strip control characters, lowercase only where safe, SHA-256.
- [ ] `source_fingerprint(event_ids: Sequence[str], source_max_received_at_ms: int | None) -> str`.
- [ ] `label_fingerprint(semantic_rows: Sequence[dict[str, Any]]) -> str`: include semantic ids, stance, valence, cluster key, confidence bucket, computed time bucket.
- [ ] Tests prove stable order-insensitive fingerprints.

#### `services/narrative_admission.py`

- [ ] Implement `NarrativeAdmissionService.reconcile_from_radar_rows(...)`.
- [ ] Admission selection:
  - Radar rows with target id.
  - Hot rows by rank: top `hot_rank_limit`.
  - Rows over `min_rank_score`.
  - Carry rows already admitted and seen inside `carry_ttl_ms`.
- [ ] Explicit non-trigger: raw tweets outside admitted rows do not enqueue semantics.
- [ ] Suppression: rows not seen for `suppression_ttl_ms` become `suppressed`; history remains queryable.

#### `services/mention_semantics_service.py`

- [ ] Build provider requests from queued source rows.
- [ ] Verify each returned label maps to an input `event_id + target`.
- [ ] Reject labels that cite unknown `event_id`.
- [ ] Keep stance and attention valence independent; do not derive one from the other.
- [ ] Low confidence labels are persisted as `labeled`; digest confidence later accounts for them.
- [ ] `semantic_unavailable` is terminal until schema or input fingerprint changes.

#### `services/discussion_digest_service.py`

- [ ] Implement state and refresh decisions:
  ```python
  class DigestRefreshDecision(BaseModel):
      should_refresh: bool
      reason: str
      status_if_not_refresh: Literal["pending", "insufficient", "ready", "stale"]
  ```
- [ ] Refresh thresholds from worker settings:
  - `min_new_labeled_mentions`
  - `min_new_authors`
  - `min_semantic_coverage`
  - `min_source_mentions`
  - `min_independent_authors`
  - `stance_mix_change_threshold`
  - `attention_mix_change_threshold`
  - `price_move_refresh_pct`
  - `digest_ttl_by_window_seconds`
- [ ] `build_insufficient_digest(...)` returns a persisted digest with concrete data gaps when volume, authors, coverage, identity, market, or worker freshness is insufficient.
- [ ] `build_digest_request(...)` caps context by `max_mentions_per_digest`, sorted by evidence quality, watched/high-quality authors, recency, and cluster coverage.
- [ ] Verify provider result with `EvidenceRefValidator` before persistence.

#### `services/evidence_ref_validator.py`

- [ ] `validate_digest_refs(result, allowed_refs) -> ValidationResult`.
- [ ] Unknown refs fail the run and do not replace current digest.
- [ ] Missing refs on public claims convert result to `insufficient` only if the provider produced otherwise usable gaps; otherwise mark retryable failure.

### 5. Provider Contracts And OpenAI Adapter

#### `providers.py`

- [ ] Define pure domain protocol:
  ```python
  class NarrativeIntelProvider(Protocol):
      @property
      def provider(self) -> str: ...
      @property
      def model(self) -> str: ...
      @property
      def artifact_version_hash(self) -> str: ...

      async def label_mentions(
          self,
          *,
          run_id: str,
          request: MentionSemanticsBatchRequest,
      ) -> MentionSemanticsBatchResult: ...

      async def summarize_discussion(
          self,
          *,
          run_id: str,
          request: DiscussionDigestRequest,
      ) -> DiscussionDigestResult: ...

      async def aclose(self) -> None: ...
  ```

#### `integrations/openai_agents/narrative_intel_agent_client.py`

- [ ] Follow the current strict-output pattern from existing OpenAI clients.
- [ ] Load prompt text from `domains/narrative_intel/prompts/*.md`; do not put business prompt blocks in `integrations`.
- [ ] Use two stage names: `mention_semantics` and `discussion_digest`.
- [ ] Use JSON schema / Pydantic strict parsing.
- [ ] Return `agent_run_audit` with backend, trace id, prompt version, schema version, input/output hashes, usage, latency, safety-net metadata.
- [ ] The client must not query DB, fetch Twitter, fetch GMGN, or call market providers.

#### Prompts

- [ ] `mention_semantics.md` instructions:
  - Label only from provided text and provided refs.
  - Separate `trade_stance` from `attention_valence`.
  - Mark memes/irony/hostile attention explicitly.
  - Use `off-token`/`unknown` rather than inventing a claim.
  - Cite provided `event:<id>` refs.
- [ ] `discussion_digest.md` instructions:
  - Summarize 24h/current-window narratives from supplied labeled mentions and market/profile facts only.
  - Always produce bull view, bear view, propagation read, reflexivity read, triggers, invalidation, data gaps.
  - Every claim must cite allowed refs.
  - Abstain with `insufficient` when evidence is thin.

### 6. Runtime Settings, Provider Wiring, Worker Registry

#### `platform/config/settings.py`

- [ ] Add `narrative_intel_model: str | None = None` to `LlmConfig` and include it in the optional string validator.
- [ ] Add `Settings.narrative_intel_model` and `Settings.narrative_intel_configured` properties:
  ```python
  @property
  def narrative_intel_model(self) -> str | None:
      return self.llm.narrative_intel_model or self.llm_model

  @property
  def narrative_intel_configured(self) -> bool:
      return bool(self.llm_api_key and self.narrative_intel_model)
  ```
- [ ] Add:
  ```python
  class MentionSemanticsWorkerSettings(PerWorkerSettings):
      interval_seconds: float = Field(default=60.0, ge=0)
      timeout_seconds: float = Field(default=0.0, ge=0)
      batch_size: int = Field(default=50, ge=1)
      max_attempts: int = Field(default=3, ge=1)
      advisory_lock_key: int = 2026051801
      wakes_on: tuple[str, ...] = ("token_radar_updated", "resolution_updated")
      windows: tuple[str, ...] = ("5m", "1h", "4h", "24h")
      scopes: tuple[str, ...] = ("all", "matched")
      admission_limit: int = Field(default=200, ge=1)
      source_limit: int = Field(default=2000, ge=1)
      min_rank_score: int = Field(default=30, ge=0)
      hot_rank_limit: int = Field(default=50, ge=1)
      carry_ttl_seconds: int = Field(default=3600, ge=1)
      suppression_ttl_seconds: int = Field(default=3600, ge=1)
  ```
- [ ] Add:
  ```python
  class TokenDiscussionDigestWorkerSettings(PerWorkerSettings):
      interval_seconds: float = Field(default=120.0, ge=0)
      timeout_seconds: float = Field(default=0.0, ge=0)
      batch_size: int = Field(default=25, ge=1)
      max_attempts: int = Field(default=3, ge=1)
      advisory_lock_key: int = 2026051802
      wakes_on: tuple[str, ...] = ("token_radar_updated", "narrative_semantics_updated", "market_tick_written")
      windows: tuple[str, ...] = ("5m", "1h", "4h", "24h")
      scopes: tuple[str, ...] = ("all", "matched")
      min_source_mentions: int = Field(default=3, ge=1)
      min_independent_authors: int = Field(default=2, ge=1)
      min_new_labeled_mentions: int = Field(default=3, ge=1)
      min_new_authors: int = Field(default=2, ge=1)
      min_semantic_coverage: float = Field(default=0.35, ge=0, le=1)
      max_mentions_per_digest: int = Field(default=120, ge=1)
      stance_mix_change_threshold: float = Field(default=0.20, ge=0, le=1)
      attention_mix_change_threshold: float = Field(default=0.20, ge=0, le=1)
      price_move_refresh_pct: float = Field(default=12.0, ge=0)
      digest_ttl_by_window_seconds: dict[str, int] = Field(
          default_factory=lambda: {"5m": 120, "1h": 300, "4h": 600, "24h": 900}
      )
  ```
- [ ] Add both fields to `WorkersSettings`.
- [ ] Add both sections to `default_workers_yaml()` after `token_radar_projection` and before `pulse_candidate`.
- [ ] Update `tests/unit/test_worker_settings.py` to assert advisory lock keys, wakes, windows/scopes, thresholds, and no legacy narrative fallback keys.

#### `app/runtime/provider_wiring/types.py`

- [ ] Add:
  ```python
  @dataclass(frozen=True, slots=True)
  class NarrativeIntelProviders:
      narrative_provider: NarrativeIntelProvider | None = None
  ```
- [ ] Add `narrative_intel: NarrativeIntelProviders` to `WiredProviders`.

#### `app/runtime/provider_wiring/openai.py`

- [ ] Add `OpenAINarrativeIntelProvider` wrapper if the client needs a domain adapter.
- [ ] Add:
  ```python
  def openai_narrative_intel_provider(settings: Settings, *, llm_gateway: object | None) -> OpenAINarrativeIntelProvider:
      gateway = _require_llm_gateway(llm_gateway)
      model = settings.narrative_intel_model or settings.llm_model or ""
      return OpenAINarrativeIntelProvider(
          OpenAIAgentsNarrativeIntelClient(
              api_key=settings.llm_api_key or "",
              model=model,
              llm_gateway=gateway,
              base_url=settings.llm_base_url,
              timeout_seconds=settings.llm_timeout_seconds,
              safety_net=_build_safety_net(settings, model=model),
              trace_enabled=settings.llm_trace_enabled,
              trace_include_sensitive_data=settings.llm_trace_include_sensitive_data,
          )
      )
  ```
- [ ] Update `wire_providers(...)` to populate `providers.narrative_intel`.

#### `app/runtime/worker_registry.py`

- [ ] Add classes:
  ```python
  "mention_semantics": (
      "gmgn_twitter_intel.domains.narrative_intel.runtime.mention_semantics_worker.MentionSemanticsWorker"
  ),
  "token_discussion_digest": (
      "gmgn_twitter_intel.domains.narrative_intel.runtime.token_discussion_digest_worker.TokenDiscussionDigestWorker"
  ),
  ```
- [ ] Start priorities:
  ```python
  "mention_semantics": 88,
  "token_discussion_digest": 89,
  "pulse_candidate": 90,
  ```

#### `app/runtime/worker_factories/narrative_intel.py`

- [ ] Construct workers only when settings are enabled, `ctx.settings.narrative_intel_configured` is true, and `ctx.providers.narrative_intel.narrative_provider` is configured.
- [ ] `WORKER_KEYS = frozenset({"mention_semantics", "token_discussion_digest"})`.
- [ ] Wire wake listeners:
  ```python
  ctx.db.wake_listener("mention_semantics", workers.mention_semantics.wakes_on)
  ctx.db.wake_listener("token_discussion_digest", workers.token_discussion_digest.wakes_on)
  ```
- [ ] Pass `wake_bus` to `MentionSemanticsWorker` so it can emit `narrative_semantics_updated`.

#### `app/runtime/worker_factories/__init__.py`

- [ ] Import narrative worker factory and include `WorkerFactorySpec("narrative_intel.py", NARRATIVE_INTEL_KEYS, construct_narrative_intel_workers)` between `token_intel.py` and `pulse.py`.

#### `app/runtime/wake_bus.py`

- [ ] Add:
  ```python
  def notify_narrative_semantics_updated(
      self,
      *,
      window: str,
      scope: str,
      target_count: int,
  ) -> None:
      self._notify(
          "narrative_semantics_updated",
          {"window": str(window), "scope": str(scope), "target_count": int(target_count)},
      )
  ```

#### `app/runtime/repository_session.py`

- [ ] Import `NarrativeRepository`.
- [ ] Add `narratives: NarrativeRepository` to `RepositorySession`.
- [ ] Instantiate `narratives=NarrativeRepository(conn)`.

### 7. Workers

#### `runtime/mention_semantics_worker.py`

- [ ] Inherit `WorkerBase`, `SINGLE_WRITER_KEY = 2026051801`.
- [ ] `run_once_async` shape:
  1. In a short DB session, reconcile admissions from latest Radar rows for configured windows/scopes.
  2. In a short DB session, enqueue missing mention semantic rows for due admissions.
  3. In a short DB session, claim queued/retryable rows up to `batch_size`.
  4. Release DB session.
  5. Call `NarrativeIntelProvider.label_mentions(...)`.
  6. In a short DB session, record `narrative_model_runs` and update `token_mention_semantics`.
  7. Emit `narrative_semantics_updated` wake if at least one label changed.
- [ ] Return `WorkerResult` notes:
  ```python
  {
      "admissions_seen": int,
      "admissions_upserted": int,
      "mentions_enqueued": int,
      "claimed": int,
      "labeled": int,
      "semantic_unavailable": int,
      "failed": int,
      "windows": {...},
  }
  ```
- [ ] No provider call while a DB transaction/session is open. Existing architecture test should catch this pattern; add a unit test with a fake provider that asserts no fake connection is active.
- [ ] Do not scan raw tweets directly. Source mentions come only from due admitted target/window rows.

#### `runtime/token_discussion_digest_worker.py`

- [ ] Inherit `WorkerBase`, `SINGLE_WRITER_KEY = 2026051802`.
- [ ] `run_once_async` shape:
  1. In a short DB session, find due digest targets from `narrative_admissions`.
  2. In a short DB session, gather digest context and semantic rows for each target.
  3. Release DB session.
  4. For insufficient contexts, build/persist `insufficient` digest without provider call.
  5. For ready contexts needing refresh, call `NarrativeIntelProvider.summarize_discussion(...)`.
  6. Validate evidence refs.
  7. In a short DB session, record run and replace current digest.
- [ ] Return `WorkerResult` notes:
  ```python
  {
      "claimed": int,
      "ready": int,
      "insufficient": int,
      "pending": int,
      "failed": int,
      "refresh_reasons": {...},
  }
  ```
- [ ] `market_tick_written` may refresh digest/reflexivity but never per-mention semantics.
- [ ] Pulse hidden states are not inputs.

---

## API And Read Models

### `read_models/narrative_read_model.py`

- [ ] Create `NarrativeReadModel`:
  ```python
  class NarrativeReadModel:
      def hydrate_token_radar(
          self,
          data: dict[str, Any],
          *,
          window: str,
          scope: str,
          now_ms: int,
      ) -> dict[str, Any]

      def hydrate_token_case(
          self,
          dossier: dict[str, Any],
          *,
          window: str,
          scope: str,
          now_ms: int,
      ) -> dict[str, Any]

      def hydrate_target_posts(
          self,
          posts_data: dict[str, Any],
          *,
          window: str,
          scope: str,
          now_ms: int,
      ) -> dict[str, Any]
  ```
- [ ] `hydrate_token_radar` adds `discussion_digest` and `pulse_overlay` to both `targets` and `attention` rows.
- [ ] `hydrate_token_case` adds `discussion_digest`, `narrative_clusters`, and `pulse_overlay`.
- [ ] `hydrate_target_posts` adds per-post `semantic`.
- [ ] Missing current digest returns:
  ```python
  {
      "status": "pending" | "semantic_unavailable",
      "data_gaps": [{"reason": "digest_not_ready" | "target_not_admitted"}],
      "semantic_coverage": 0,
      "evidence_refs": [],
  }
  ```
- [ ] Public Pulse overlay is read-only and display-gated. The read model should call `repos.pulse_read` or an existing public read service, not Pulse job internals.

### `routes_radar.py`

- [ ] Lines around `_token_radar_data`: after `AssetFlowService.asset_flow(...)`, call `NarrativeReadModel(...).hydrate_token_radar(...)`.
- [ ] Keep route pure: no provider, no SQL, no scoring.

### `routes_search.py`

- [ ] `/api/token-case`: build deterministic target dossier with `TokenCaseService`, then hydrate through `NarrativeReadModel`.
- [ ] `/api/target-posts`: build current posts page with `TokenTargetPostsService`, then hydrate through `NarrativeReadModel`.
- [ ] `/api/search/inspect`: after `SearchInspectService.inspect(...)`, if `data["token_result"]` exists, hydrate it through `NarrativeReadModel`. Do not hydrate topic or ambiguous result `agent_brief`.

### `schemas.py`

- [ ] Replace:
  ```python
  agent_brief: JsonObject
  ```
  with:
  ```python
  discussion_digest: JsonObject
  narrative_clusters: list[JsonObject] = Field(default_factory=list)
  pulse_overlay: JsonObject | None = None
  ```
- [ ] `TokenRadarData` and `TargetPostsData` remain list/dict payloads, but contract tests should assert narrative keys exist.

### `token_case_service.py`

- [ ] Remove `build_token_agent_brief` import.
- [ ] `dossier()` return keys become:
  ```python
  ["target", "profile", "timeline", "posts", "market_live"]
  ```
- [ ] Keep `normalize_token_case_scope`.
- [ ] Existing token service tests should be rewritten to assert deterministic target/timeline/posts/market only. Narrative assertions move to API/read model tests.

### `search_agent_brief.py`

- [ ] Delete `build_token_agent_brief` or leave it unexported only if tests prove no runtime import remains.
- [ ] Keep `build_topic_agent_brief` and `SCHEMA_VERSION = "search_agent_brief_v1"` for topic/ambiguous search.
- [ ] Add architecture/static test to fail if `build_token_agent_brief` is imported by API or Token Case code.

### `search_inspect_service.py`

- [ ] Keep returning token dossier from `TokenCaseService`.
- [ ] Do not import `narrative_intel` in this token domain service. Route-layer hydration owns cross-domain composition.
- [ ] Topic/ambiguous result still uses `build_topic_agent_brief`.

---

## Pulse Integration

### `pulse_evidence_source_repository.py`

- [ ] Add methods that read current digest and semantic refs:
  ```python
  def get_current_discussion_digest(
      self,
      *,
      target_type: str,
      target_id: str,
      window: str,
      scope: str,
      schema_version: str,
  ) -> dict[str, Any] | None

  def list_semantic_refs(self, semantic_ids: Sequence[str]) -> list[dict[str, Any]]
  ```
- [ ] These are read-only. Pulse does not write narrative tables.

### `evidence_packet_builder.py`

- [ ] Add optional `discussion_digest` block to sealed Pulse evidence packet when a ready digest exists.
- [ ] Include digest `digest_id`, `schema_version`, `computed_at_ms`, `semantic_coverage`, `evidence_refs`, and compact narrative fields.
- [ ] If digest is absent, Pulse can still run with existing evidence. Absence of narrative digest must not block Pulse candidate scanning unless Pulse completeness policy chooses to abstain.
- [ ] Add tests proving Pulse hidden/internal state does not trigger narrative workers.

---

## Frontend Implementation

### Contract Types

#### `web/src/lib/types/frontend-contracts.ts`

- [ ] Add:
  ```ts
  export type NarrativeStatus = "ready" | "pending" | "insufficient" | "semantic_unavailable" | "stale";

  export type TokenMentionSemantic = {
    status: "labeled" | "pending" | "semantic_unavailable" | "retryable_error" | "stale";
    trade_stance: "bullish" | "bearish" | "neutral" | "skeptical" | "exit-risk" | "research-only" | "unknown";
    attention_valence: "positive" | "negative" | "mixed" | "ironic" | "hostile" | "panic" | "celebratory" | "informational" | "unknown";
    narrative_cluster_key?: string | null;
    claim_type?: string | null;
    evidence_type?: string | null;
    semantic_confidence?: number | null;
    data_gaps?: Array<{ reason: string; detail?: string | null }>;
  };

  export type TokenDiscussionDigest = {
    status: NarrativeStatus;
    headline_zh?: string | null;
    dominant_narratives: NarrativeCluster[];
    bull_view?: NarrativeArgument | null;
    bear_view?: NarrativeArgument | null;
    stance_mix: Record<string, number>;
    attention_valence_mix: Record<string, number>;
    propagation_read?: Record<string, unknown> | null;
    reflexivity_read?: Record<string, unknown> | null;
    watch_triggers: string[];
    invalidation_conditions: string[];
    data_gaps: Array<{ reason: string; detail?: string | null }>;
    semantic_coverage: number;
    source_event_count: number;
    labeled_event_count: number;
    evidence_refs: EvidenceRef[];
    computed_at_ms?: number | null;
  };

  export type PulseOverlay = {
    status: "absent" | "public_candidate" | "public_watch" | "public_risk_rejected";
    candidate_id?: string | null;
    recommendation?: string | null;
    display_status?: string | null;
    evidence_packet_hash?: string | null;
    summary_zh?: string | null;
    risk_labels?: string[];
    computed_at_ms?: number | null;
  };
  ```
- [ ] Update `TokenCaseDossier`: remove `agent_brief`; add `discussion_digest`, `narrative_clusters`, `pulse_overlay`.
- [ ] Update `TokenPostItem`: add `semantic: TokenMentionSemantic`.
- [ ] Update `TokenFlowItem`: add optional `discussion_digest` and `pulse_overlay`.
- [ ] Update `SearchTokenResult = TokenCaseDossier`; topic/ambiguous result still has `agent_brief`.

### Token Radar

#### `web/src/shared/model/tokenRadarCompactCase.ts`

- [ ] Prefer `item.discussion_digest` over factor snapshot heuristic for WHY NOW narrative.
- [ ] `ready`: show dominant narrative headline/label, stance mix summary, semantic coverage.
- [ ] `pending`: show concise pending state and no generic catalyst prose.
- [ ] `insufficient`: show top data gap reason.
- [ ] `semantic_unavailable`: show worker/analysis unavailable state.
- [ ] Public Pulse overlay appears as a secondary badge and never changes rank/decision text.

#### `web/src/features/live/ui/TokenRadarTable.tsx`

- [ ] Update column/cell rendering to use compact narrative state.
- [ ] Add small coverage/status badge in WHY NOW cell.
- [ ] Ensure row layout stays dense and does not overflow in the table.

### Token Case

#### `web/src/features/token-case/model/buildTokenCaseViewModel.ts`

- [ ] Replace all `dossier.agent_brief.*` reads with `dossier.discussion_digest`.
- [ ] Build:
  - hero subtitle from digest headline or status gap.
  - propagation section from `propagation_read` and digest clusters.
  - bull/bear thesis from `bull_view` / `bear_view`.
  - data gaps from `discussion_digest.data_gaps`.
  - amplifiers from clusters/top authors if present.
  - timeline post pills from `post.semantic.trade_stance`, `attention_valence`, `claim_type`.
- [ ] Keep market live patching behavior unchanged.

#### `web/src/shared/ui/case-file/*`

- [ ] Update props only where necessary. Do not introduce landing-page style explanatory copy.
- [ ] Add visual states for `pending`, `insufficient`, and `semantic_unavailable`.
- [ ] Mention Timeline cards show stance/valence/claim chips from `semantic`, not from `post_quality` or `stage_phase`.

### Search

#### `web/src/features/search/model/searchCase.ts`

- [ ] Token result uses `discussion_digest`.
- [ ] Topic and ambiguous results continue to use `agent_brief`.
- [ ] Tests must assert token result has no `agent_brief`.

### Fixtures And Generated Types

- [ ] Update `web/tests/fixtures/tokenCaseFixture.ts`.
- [ ] Update route/component fixtures to include `discussion_digest`, `narrative_clusters`, `pulse_overlay`, and per-post `semantic`.
- [ ] Run:
  ```bash
  make regen-contract
  ```

---

## Docs

### `docs/ARCHITECTURE.md`

- [ ] Insert `domains/narrative_intel` in the top flow between `token_intel/social_enrichment` and `pulse_lab`.
- [ ] Update one-writer invariant to include:
  - `token_mention_semantics` by `MentionSemanticsWorker`
  - `token_discussion_digests` by `TokenDiscussionDigestWorker`
- [ ] Add domain row:
  ```text
  domains/narrative_intel/ | Per-mention semantics, token-window narrative clusters, discussion digests, narrative coverage, evidence refs.
  ```
- [ ] Add module architecture link to `src/gmgn_twitter_intel/domains/narrative_intel/ARCHITECTURE.md`.

### `src/gmgn_twitter_intel/domains/narrative_intel/ARCHITECTURE.md`

- [ ] Document:
  - Purpose and boundaries.
  - Read dependencies.
  - Tables and single writers.
  - Worker state machines.
  - Trigger/non-trigger table.
  - API composition rule.
  - Pulse consumption rule.

### `docs/WORKERS.md`

- [ ] Add worker inventory keys:
  ```text
  mention_semantics, token_discussion_digest
  ```
- [ ] Add rows:
  - `mention_semantics`: reads `token_radar_rows`, events/resolutions/enriched events, existing semantic rows; writes `narrative_admissions`, `token_mention_semantics`, `narrative_model_runs`; wake-in `token_radar_updated`, `resolution_updated`; wake-out `narrative_semantics_updated`; catch-up `interval_seconds`.
  - `token_discussion_digest`: reads `narrative_admissions`, `token_mention_semantics`, `token_radar_rows`, market/profile facts; writes `token_discussion_digests`, `narrative_model_runs`; wake-in `token_radar_updated`, `narrative_semantics_updated`, `market_tick_written`; wake-out none; catch-up `interval_seconds`.
- [ ] Add wake channel:
  ```text
  narrative_semantics_updated | MentionSemanticsWorker | TokenDiscussionDigestWorker | {window, scope, target_count}
  ```

### `docs/CONTRACTS.md`

- [ ] Search Inspect: `token_result` has Token Case dossier with `discussion_digest`; topic/ambiguous keep `agent_brief`.
- [ ] Token Case: remove `data.agent_brief`, add `data.discussion_digest`, `data.narrative_clusters`, `data.pulse_overlay`.
- [ ] Target Posts: each item has `semantic`.
- [ ] Token Radar: rows have compact `discussion_digest` and optional public `pulse_overlay`.

### `docs/FRONTEND.md`

- [ ] Token Radar convention: scan surface displays persisted narrative digest status; UI never infers stance from score/quality.
- [ ] Token Case convention: canonical token dossier is digest-driven; topic brief remains only for search topic/ambiguous cases.

### `docs/WORKER_FLOW.md`

- [ ] Add a narrative lane after Token Radar projection and before Pulse candidate.
- [ ] Include state-machine debugging notes for admissions, mention semantics, digest refresh, missed wakes.

---

## Tests

### Unit Tests

- [ ] `tests/unit/domains/narrative_intel/test_narrative_admission.py`
  - Raw tweet rows are ignored until target/window is admitted from Radar.
  - Radar top rows create admitted rows with due semantics/digest.
  - Missing target id rows are skipped.
  - Suppressed carry rows do not enqueue new semantics.

- [ ] `tests/unit/domains/narrative_intel/test_mention_semantics_service.py`
  - Stance and attention valence are stored independently.
  - Unknown evidence refs are rejected.
  - Low confidence labels persist as `labeled`.
  - `semantic_unavailable` stores reason and evidence gap.
  - Same `event_id + target + fingerprint + schema` is not relabeled.

- [ ] `tests/unit/domains/narrative_intel/test_discussion_digest_service.py`
  - Insufficient source volume produces `insufficient` digest with gap.
  - Low semantic coverage produces `insufficient` or pending decision.
  - New labeled count below threshold does not refresh current digest.
  - Stance mix/valence mix threshold triggers refresh.
  - Ready digest without evidence refs is rejected.
  - Market move refresh affects digest only, not mention labels.

- [ ] `tests/unit/domains/narrative_intel/test_narrative_read_model.py`
  - Radar rows are hydrated with ready digest.
  - Missing digest yields explicit pending/unavailable block.
  - Token Case adds digest/clusters/overlay and does not add `agent_brief`.
  - Target posts are hydrated with semantic block.
  - Pulse overlay appears only for public displayable rows with packet hash.

- [ ] `tests/unit/domains/narrative_intel/test_narrative_workers.py`
  - Mention worker does not call provider for raw/unadmitted source rows.
  - Mention worker emits `narrative_semantics_updated` only after label changes.
  - Digest worker consumes wake/catch-up by rereading DB.
  - Digest worker ignores Pulse hidden/internal state.
  - Provider calls happen outside DB session.

- [ ] `tests/unit/test_api_narrative_contract.py`
  - `/api/token-radar` item shape includes `discussion_digest.status`.
  - `/api/token-case` shape excludes `agent_brief`.
  - `/api/target-posts` items include `semantic.status`.
  - `/api/search/inspect` token result excludes `agent_brief`, topic result includes it.

### Integration Tests

- [ ] `tests/integration/test_narrative_repository.py`
  - Migration tables and indexes support insert/upsert/replace current digest.
  - Partial unique current digest index allows one current row and historical superseded rows.
  - `semantics_for_posts` maps post rows to semantic rows.
  - `current_digests_for_targets` returns keyed rows by target.

- [ ] `tests/integration/test_api_http.py`
  - Update existing search/token assertions that currently expect `agent_brief`.
  - Add fixture-backed API assertions for digest and semantic fields.

### Contract / Generated Tests

- [ ] `make regen-contract`
- [ ] `make contract-check`
- [ ] `tests/contract/test_openapi_drift.py` should pass with new schemas.

### Frontend Tests

- [ ] `web/tests/unit/features/token-case/model/buildTokenCaseNarrativeViewModel.test.ts`
  - Ready digest builds hero/propgation/bull/bear/timeline semantic pills.
  - Insufficient digest builds gap state.
  - No fixture or VM path reads `agent_brief` for Token Case.

- [ ] `web/tests/unit/shared/model/tokenRadarCompactCaseNarrative.test.ts`
  - Ready digest drives WHY NOW.
  - Pending/insufficient/unavailable do not use generic catalyst prose.
  - Pulse overlay is secondary.

- [ ] Existing tests to update:
  - `web/tests/fixtures/tokenCaseFixture.ts`
  - `web/tests/routes/token-target.route.test.tsx`
  - `web/tests/component/features/token-case/ui/TokenCaseRoute.routing.test.tsx`
  - `web/tests/component/features/search/ui/SearchIntelPage.routing.test.tsx`
  - `web/tests/unit/shared/query/patchMarketUpdate.test.ts`

---

## Acceptance Test Commands

- [ ] AC1, AC2, AC3, AC4, AC5, AC6, AC7, AC8, AC9:
  ```bash
  uv run pytest tests/unit/test_api_narrative_contract.py -q
  uv run pytest tests/unit/domains/narrative_intel -q
  ```

- [ ] AC10 wake/catch-up:
  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_narrative_workers.py::test_digest_worker_catches_up_without_wake -q
  ```

- [ ] AC11 raw tweet non-trigger:
  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_narrative_admission.py::test_raw_mentions_do_not_enqueue_without_admission -q
  ```

- [ ] AC12 digest refresh threshold:
  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_discussion_digest_service.py::test_single_new_label_does_not_force_digest_refresh -q
  ```

- [ ] AC13 Pulse hidden state non-trigger:
  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_narrative_workers.py::test_pulse_hidden_state_does_not_trigger_narrative_workers -q
  ```

- [ ] Worker architecture:
  ```bash
  uv run pytest tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_worker_inventory_contract.py tests/architecture/test_narrative_intel_boundaries.py -q
  ```

- [ ] Repository integration:
  ```bash
  uv run pytest tests/integration/test_narrative_repository.py -q
  ```

- [ ] Frontend:
  ```bash
  cd web && npm run typecheck
  cd web && npm run lint
  cd web && npm test -- --run
  cd web && npm run build
  ```

- [ ] Full gate:
  ```bash
  make check-all
  ```

---

## Manual Live Verification

Run after local server is on `http://localhost:8765` and workers are enabled with real runtime config.

- [ ] Confirm config paths:
  ```bash
  uv run gmgn-twitter-intel config
  ```
- [ ] Token Radar row has digest status:
  ```bash
  curl -s 'http://localhost:8765/api/token-radar?window=24h&scope=all&limit=5' \
    | jq '.data.targets[0] | {target:.target, digest:.discussion_digest.status, coverage:.discussion_digest.semantic_coverage, pulse:.pulse_overlay.status}'
  ```
  Expected: `digest` exists. `pulse` can be `absent`.
- [ ] SOL Token Case no longer has `agent_brief`:
  ```bash
  curl -s 'http://localhost:8765/api/token-case?target_type=Asset&target_id=asset%3Asolana%3Atoken%3ASo11111111111111111111111111111111111111112&window=24h&scope=all' \
    | jq '.data | {has_agent_brief:has("agent_brief"), digest:.discussion_digest.status, clusters:(.narrative_clusters|length), pulse:.pulse_overlay.status}'
  ```
  Expected: `has_agent_brief=false`; `digest` is `ready`, `pending`, `insufficient`, or `semantic_unavailable`.
- [ ] Mention Timeline has per-post semantics:
  ```bash
  curl -s 'http://localhost:8765/api/target-posts?target_type=Asset&target_id=asset%3Asolana%3Atoken%3ASo11111111111111111111111111111111111111112&window=24h&scope=all&limit=5' \
    | jq '.data.items[] | {event_id, semantic:.semantic.status, stance:.semantic.trade_stance, valence:.semantic.attention_valence}'
  ```
  Expected: every row has `semantic.status`.
- [ ] Browser verification:
  - Open `/` and check Token Radar WHY NOW shows narrative status/coverage without layout overlap.
  - Open `/token/Asset/asset%3Asolana%3Atoken%3ASo11111111111111111111111111111111111111112?window=24h&scope=all`.
  - Confirm Token Case top explanation is digest-driven, Mention Timeline has stance/valence/claim chips, and no visible fallback brief text appears.

---

## Rollout

1. [ ] Merge one hard-cut PR containing backend, frontend, migrations, docs, and generated contracts.
2. [ ] Apply Alembic migration:
   ```bash
   uv run alembic upgrade head
   ```
3. [ ] Deploy service and frontend bundle together.
4. [ ] Ensure active `~/.gmgn-twitter-intel/workers.yaml` either includes new worker sections or relies on defaults. The config loader must accept missing sections through `WorkersSettings` defaults.
5. [ ] Start workers. Narrative catch-up should populate admissions first, then mention semantics, then digests.
6. [ ] Watch worker health:
   ```bash
   uv run gmgn-twitter-intel ops worker-status
   ```
   Expected canonical worker keys include `mention_semantics` and `token_discussion_digest`.
7. [ ] Run live verification curls above.

---

## Rollback

This is a hard-cut API release; rollback means rolling back application code and frontend bundle together.

- Database: keep `narrative_admissions`, `narrative_model_runs`, `token_mention_semantics`, and `token_discussion_digests` in place during rollback unless the release has not processed production data. Old code ignores these tables.
- Workers: disabling `mention_semantics` and `token_discussion_digest` is safe; it stops refresh but does not affect token ingestion, Radar, Pulse, or market capture.
- API/frontend: cannot roll back only one side because `agent_brief` is removed from token dossier and web expects `discussion_digest`.
- Provider: if OpenAI narrative provider is unavailable, workers stay disabled or emit explicit `semantic_unavailable`; API must still serve Radar/Case with data-gap states.
- Downgrade migration drops narrative tables only for pre-production or explicit data-discard rollback:
  ```bash
  uv run alembic downgrade 20260518_0062
  ```

---

## Completion Checklist

- [ ] No runtime canonical token path returns or reads `agent_brief`.
- [ ] `rg "agent_brief" src/gmgn_twitter_intel web/src web/tests tests | rg -v "topic|ambiguous|SearchAgentBrief|search_agent_brief|openapi"` shows no Token Case usage.
- [ ] `token_mention_semantics` and `token_discussion_digests` are documented as single-writer read models.
- [ ] Narrative workers do not call providers inside DB sessions.
- [ ] Pulse can read digest evidence but cannot trigger narrative workers.
- [ ] `make regen-contract`, backend tests, frontend tests, and `make check-all` pass or any environment-only gap is documented with exact command output.
