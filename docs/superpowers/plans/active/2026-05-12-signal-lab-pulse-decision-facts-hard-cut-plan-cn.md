# Signal Lab Pulse Decision Facts Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Signal Lab Pulse decisions point-in-time auditable, fail-closed on unknown DEX market structure, and explainable without legacy fallback or compatibility code.

**Architecture:** Hard-cut Token Radar/Pulse from `token_factor_snapshot_v3_social_attention` to a new decision-facts contract. The UI live market path stays a live transport, while Pulse and Token Radar decisions consume persisted `decision_market_snapshots` only. Cohort percentile becomes explanation context, not the score that triggers Pulse.

**Tech Stack:** Python 3.13, FastAPI, psycopg/PostgreSQL, Alembic migrations, OpenAI Agents SDK provider adapter, React/TypeScript frontend, `uv run pytest`, `npm test`, `make check-all`.

---

## Pre-flight

- [ ] Current spec is approved with this plan's first-principles amendment: decision-grade market facts are persisted and replayable; `LivePriceGateway` memory is not a Pulse decision source.
- [ ] Worktree exists at `.worktrees/signal-lab-pulse-decision-facts-hard-cut/`.
- [ ] Branch is `codex/signal-lab-pulse-decision-facts-hard-cut`.
- [ ] Baseline `uv run ruff check .` passes.
- [ ] Baseline `uv run pytest tests/unit/test_factor_snapshot.py tests/unit/test_token_radar_apply_cross_section.py tests/unit/test_pulse_candidate_gate.py tests/unit/test_pulse_candidate_worker.py tests/test_pulse_recommendation.py tests/test_pulse_recommendation_agent_client.py -q` passes or known failures are recorded before editing.
- [ ] Frontend baseline `cd web && npm test -- --run` passes or known failures are recorded before editing.

Known-failing baseline tests: none expected.

## Hard-cut contract decisions

- No compatibility reader accepts `token_factor_snapshot_v1`, `token_factor_snapshot_v2`, or `token_factor_snapshot_v3_social_attention` after this work.
- No runtime fallback reads legacy `score_json`, `market_json`, `price_json`, `current_market_field_facts`, or old Pulse thesis fields.
- Old Pulse rows are not migrated into the new schema. They are truncated in the hard-cut migration so the Signal Lab UI does not mix pre-cut candidates with post-cut decision facts.
- Historical `token_radar_rows` for older projection versions may remain in storage, but current runtime constants point only at the new projection/factor versions and readers do not attempt compatibility fallback.

## Target data flow

```text
GMGN public stream
  -> events/entities
  -> token_intents
  -> token_intent_resolutions + asset_identity_current
  -> anchor price observations
  -> decision_market_snapshots (persisted point-in-time market facts)
  -> TokenRadarSourceQuery
  -> build_token_factor_snapshot(v4)
  -> DEX fail-closed gate
  -> cohort ranks as normalization context only
  -> Pulse trigger on raw absolute score + gate result
  -> full pulse_agent_runs.request_json
  -> recommendation/playbook/notification
```

## File-level edits

### Storage / migrations

- Create: `src/parallax/platform/db/alembic/versions/20260512_0035_decision_market_snapshots.py`
  - Add `decision_market_snapshots`.
  - Hard truncate Pulse runtime tables that cannot be read under the new factor contract.
  - Do not recreate `current_market_field_facts`.

```sql
CREATE TABLE IF NOT EXISTS decision_market_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  target_type TEXT NOT NULL,
  target_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  observed_at_ms BIGINT NOT NULL,
  received_at_ms BIGINT NOT NULL,
  expires_at_ms BIGINT NOT NULL,
  price_usd NUMERIC,
  price_quote NUMERIC,
  quote_symbol TEXT,
  price_basis TEXT NOT NULL DEFAULT 'unavailable',
  market_cap_usd NUMERIC,
  liquidity_usd NUMERIC,
  holders BIGINT,
  volume_24h_usd NUMERIC,
  open_interest_usd NUMERIC,
  field_statuses_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at_ms BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_decision_market_snapshots_latest
  ON decision_market_snapshots(target_type, target_id, observed_at_ms DESC, snapshot_id DESC);

CREATE INDEX IF NOT EXISTS idx_decision_market_snapshots_fresh
  ON decision_market_snapshots(target_type, target_id, expires_at_ms DESC)
  WHERE expires_at_ms > 0;

TRUNCATE TABLE
  pulse_playbook_outcomes,
  pulse_playbook_snapshots,
  pulse_candidates,
  pulse_agent_runs,
  pulse_agent_jobs;
```

- Modify: `src/parallax/platform/db/postgres_migrations.py`
  - Ensure latest migration revision resolves to `20260512_0035`.

### Asset market persistence

- Create: `src/parallax/domains/asset_market/repositories/decision_market_snapshot_repository.py`
  - Owns insert/read SQL for point-in-time market facts.
  - Public methods:
    - `upsert_snapshot(snapshot_id, target_type, target_id, provider, source_kind, observed_at_ms, received_at_ms, expires_at_ms, price_usd, price_quote, quote_symbol, price_basis, market_cap_usd, liquidity_usd, holders, volume_24h_usd, open_interest_usd, field_statuses_json, raw_payload_json, commit=True)`.
    - `latest_for_targets(targets, as_of_ms, max_stale_ms)`.
    - `coverage_summary(since_ms)`.

```python
def snapshot_id(*, target_type: str, target_id: str, provider: str, observed_at_ms: int, source_kind: str) -> str:
    payload = f"{target_type}|{target_id}|{provider}|{source_kind}|{observed_at_ms}"
    return "decision-market:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

- Modify: `src/parallax/domains/asset_market/interfaces.py`
  - Export `DecisionMarketSnapshotRepository`.

- Modify: `src/parallax/app/runtime/repository_session.py`
  - Add `decision_market_snapshots: DecisionMarketSnapshotRepository` to `RepositorySession`.
  - Instantiate it in `repositories_for_connection`.

- Modify: `src/parallax/domains/asset_market/runtime/live_price_gateway.py`
  - Keep `snapshot()` and `live_market_update` behavior for API/WebSocket.
  - Add optional `decision_snapshot_sink` callback, called from `_store_payload()` after cache update.
  - Sink receives the full `LiveMarketSnapshot` plus `source_kind`.
  - No Token Radar or Pulse imports in this file.

```python
def _store_payload(self, snapshot: LiveMarketSnapshot, *, observed_now_ms: int, source_kind: str) -> dict[str, Any]:
    self._cache[(snapshot.target_type, snapshot.target_id)] = snapshot
    self._persist_decision_snapshot(snapshot, received_at_ms=observed_now_ms, source_kind=source_kind)
    return {
        "type": "live_market_update",
        "provider": snapshot.provider,
        "target_type": snapshot.target_type,
        "target_id": snapshot.target_id,
        "observed_at_ms": snapshot.observed_at_ms,
        "live_market": snapshot.to_payload(now_ms=observed_now_ms, stale_after_ms=self.live_stale_after_ms),
    }
```

- Modify: `src/parallax/app/runtime/app.py`
  - Wire the gateway sink inside asset-market runtime composition.
  - Persist snapshots through `repos.decision_market_snapshots`.
  - `/readyz.live_price_gateway.last_result` keeps current live metrics and adds `decision_snapshots_written`.

### Token Radar source and snapshot contract

- Modify: `src/parallax/domains/token_intel/_constants.py`
  - `TOKEN_RADAR_PROJECTION_VERSION = "token-radar-v14-decision-facts-hard-cut"`.
  - `TOKEN_FACTOR_SNAPSHOT_VERSION = "token_factor_snapshot_v4_decision_facts"`.
  - `TOKEN_RADAR_SOURCE_TABLE = "token_intent_resolutions+asset_identity_current+anchor_price+decision_market_snapshots"`.

- Modify: `src/parallax/domains/token_intel/queries/token_radar_source_query.py`
  - Join latest non-expired decision snapshot by `(target_type, target_id)` as of `now_ms`.
  - Select prefixed fields:
    - `decision_market_provider`
    - `decision_market_source_kind`
    - `decision_market_observed_at_ms`
    - `decision_market_received_at_ms`
    - `decision_market_expires_at_ms`
    - `decision_market_price_usd`
    - `decision_market_price_quote`
    - `decision_market_quote_symbol`
    - `decision_market_price_basis`
    - `decision_market_market_cap_usd`
    - `decision_market_liquidity_usd`
    - `decision_market_holders`
    - `decision_market_volume_24h_usd`
    - `decision_market_open_interest_usd`
    - `decision_market_field_statuses_json`

```sql
LEFT JOIN LATERAL (
  SELECT *
  FROM decision_market_snapshots dms
  WHERE dms.target_type = token_intent_resolutions.target_type
    AND dms.target_id = token_intent_resolutions.target_id
    AND dms.observed_at_ms <= %s
    AND dms.expires_at_ms >= %s
  ORDER BY dms.observed_at_ms DESC, dms.snapshot_id DESC
  LIMIT 1
) decision_market ON true
```

- Modify: `src/parallax/domains/token_intel/services/token_radar_projection.py`
  - `_market()` consumes anchor fields plus `decision_market_*` fields.
  - It sets `market_data_source` to `decision_snapshot` or `anchor_only`.
  - It sets `decision_snapshot_observed_at_ms`, `decision_snapshot_age_ms`, and `field_statuses`.
  - It never calls `LivePriceGateway`.
  - `_apply_cross_section()` no longer overwrites `families[family]["score"]`.
  - It writes percentile into `normalization.factor_ranks` and `composite.family_percentiles`.
  - It keeps `composite.raw_alpha_score` and `composite.rank_score` based on raw absolute family scores.
  - `_decision_from_score_and_gates()` remains gate-capped and reads raw `rank_score`.

```python
factor_snapshot["normalization"] = {
    "status": normalization_status,
    "cohort": {...},
    "factor_ranks": factor_ranks,
    "alpha_rank": alpha_rank,
}
factor_snapshot["composite"]["family_scores"] = {
    family: _family_display_score(families.get(family)) for family in TOKEN_RADAR_FACTOR_FAMILIES
}
factor_snapshot["composite"]["family_percentiles"] = {
    family: None if factor_ranks.get(family) is None else round(float(factor_ranks[family]) * 100.0)
    for family in TOKEN_RADAR_FACTOR_FAMILIES
}
factor_snapshot["composite"]["rank_score"] = _raw_composite_score(factor_snapshot)
```

- Modify: `src/parallax/domains/token_intel/scoring/factor_snapshot.py`
  - DEX missing `holders`, `liquidity_usd`, or `market_cap_usd` appends `market_data_unverified`.
  - Below-floor values keep specific floor reasons.
  - `eligible_for_high_alert` is false when any DEX market floor input is missing.
  - `risk_reasons` still includes `market_metadata_missing` for explanation.
  - `_factor_sum()` includes zero scores in the positive average and preserves negative penalties.

```python
if subject["target_market_type"] == "dex":
    missing_floor_inputs = []
    for key, reason in _DEX_FLOOR_REASONS.items():
        value = _optional_float(market.get(key))
        if value is None:
            missing_floor_inputs.append(key)
            continue
        if _is_below(value, key):
            blocked_reasons.append(reason)
    if missing_floor_inputs:
        blocked_reasons.append("market_data_unverified")
        risk_reasons.append("market_metadata_missing")
```

- Modify: `src/parallax/domains/token_intel/scoring/factor_snapshot_contract.py`
  - Require v4 schema.
  - Require `composite.family_percentiles`.
  - Reject `hard_gates`, legacy family names, and v3 schema.

### Pulse gate, trigger, and audit

- Modify: `src/parallax/domains/pulse_lab/interfaces.py`
  - `PULSE_VERSION = "signal-pulse-v4-decision-facts"`.
  - `PULSE_RECOMMENDATION_PROMPT_VERSION = "pulse-recommendation-agents-sdk-v2-decision-facts"`.
  - `PULSE_GATE_VERSION = "pulse-factor-gate-v2-decision-facts"`.
  - `PULSE_PLAYBOOK_VERSION = "shadow-playbook-v2-decision-facts"`.

- Modify: `src/parallax/domains/pulse_lab/services/pulse_candidate_gate.py`
  - Continue using `factor_snapshot.gates.blocked_reasons`.
  - Missing DEX market data now returns `risk_rejected_high_info` when score is high, never `trade_candidate`.
  - `max_recommendation` remains `research` for `risk_rejected_high_info`.

- Modify: `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py`
  - `_is_asset_trigger()` uses raw absolute score and gate max decision, not cohort percentile.
  - It does not enqueue `trade_candidate` work when `gates.max_decision` is below `high_alert`.
  - `insert_agent_run(request_json=...)` stores full sanitized agent input.

```python
request_json={
    "input_hash": str(audit.get("input_hash") or _stable_hash(agent_context)),
    "agent_context": agent_context,
    "available_factor_keys": audit.get("available_factor_keys") or [],
    "prompt_version": str(audit.get("prompt_version") or PULSE_RECOMMENDATION_PROMPT_VERSION),
}
```

- Modify: `src/parallax/domains/pulse_lab/types/pulse_recommendation.py`
  - Prompt explains:
    - `composite.family_scores` are absolute deterministic family scores.
    - `composite.family_percentiles` are cohort-relative context.
    - `normalization.cohort.size` and family `data_health` must be considered before calling a signal strong.
    - `market_data_unverified` and `gate_result.max_recommendation` cap the recommendation.
  - `collect_factor_keys()` includes `composite.family_percentiles.<family>`.
  - It continues rejecting factor keys not present in `available_factor_keys`.

### API and frontend contract

- Modify: `src/parallax/domains/pulse_lab/read_models/signal_pulse_service.py`
  - `fact_card.alpha_family_scores` remains absolute.
  - Add `fact_card.alpha_family_percentiles` from `composite.family_percentiles`.
  - `market_ready_rate` should count decision-fact readiness, not UI live status.

- Modify: `src/parallax/domains/token_intel/read_models/asset_flow_service.py`
  - Keep `live_market` overlay as UI-only.
  - Public row `factor_snapshot.market` now contains decision snapshot metadata.
  - Do not use `live_market` to mutate `factor_snapshot`.

- Modify: `docs/CONTRACTS.md`
  - Token Radar contract: `factor_snapshot.market` is decision-grade persisted context.
  - `/api/token-radar.live_market` remains live UI transport.
  - Signal Pulse contract: `family_scores` absolute, `family_percentiles` relative.

- Modify: `src/parallax/domains/token_intel/ARCHITECTURE.md`
  - Add `decision_market_snapshots` between live/anchor market and projection.
  - State that Pulse decisions never read process-local live cache.

- Modify: `web/src/lib/tokenFactorSnapshot.ts`
  - Require schema `"token_factor_snapshot_v4_decision_facts"`.
  - Require `composite.family_percentiles`.

- Modify: `web/src/api/types.ts`
  - Add `family_percentiles?: Record<string, number | null | undefined>` to `TokenFactorSnapshot.composite`.
  - Keep `live_market` fields unchanged.

- Modify: `web/src/lib/tokenRadar.ts`
  - Score ledger uses absolute `family_scores`.
  - If showing relative context, use `family_percentiles` explicitly labeled as percentile.
  - Continue deriving UI market display from `live_market`, not `factor_snapshot.market`.

- Modify: `web/src/components/SignalLabPulse.tsx` and `web/src/components/SignalLabInspector.tsx`
  - Display market-unverified candidates as capped/research/watch instead of high-conviction trade rows.
  - Show percentile context only where labeled.

### No-fallback tests

- Modify: `tests/architecture/test_no_factor_snapshot_fallback.py`
  - Add assertions that v3 schema string is not accepted by runtime validators.
  - Add assertions that no Python or web runtime imports/uses `token_factor_snapshot_v3_social_attention`.
  - Keep generated docs references out of the runtime scan if they exist for history.

## Task breakdown

### Task 1: Add decision market snapshot storage

**Files:**
- Create: `src/parallax/platform/db/alembic/versions/20260512_0035_decision_market_snapshots.py`
- Create: `src/parallax/domains/asset_market/repositories/decision_market_snapshot_repository.py`
- Modify: `src/parallax/domains/asset_market/interfaces.py`
- Modify: `src/parallax/app/runtime/repository_session.py`
- Test: `tests/integration/test_decision_market_snapshot_repository.py`
- Test: `tests/unit/test_postgres_schema.py`

- [ ] **Step 1: Write repository tests**
  - Assert `upsert_snapshot()` inserts a DEX snapshot with `market_cap_usd`, `liquidity_usd`, and `holders`.
  - Assert duplicate `(target, provider, source_kind, observed_at_ms)` writes are idempotent through stable `snapshot_id`.
  - Assert `latest_for_targets(..., as_of_ms, max_stale_ms)` returns only non-expired snapshots.

- [ ] **Step 2: Add migration and repository**
  - Add DDL exactly under Storage / migrations.
  - Add repository methods without importing token_intel or pulse_lab.

- [ ] **Step 3: Wire repository session**
  - Add `decision_market_snapshots` to `RepositorySession`.
  - Export through `asset_market.interfaces`.

- [ ] **Step 4: Run storage tests**
  - Run: `uv run pytest tests/integration/test_decision_market_snapshot_repository.py tests/unit/test_postgres_schema.py -q`
  - Expected: PASS.

### Task 2: Persist live provider facts as decision snapshots

**Files:**
- Modify: `src/parallax/domains/asset_market/runtime/live_price_gateway.py`
- Modify: `src/parallax/app/runtime/app.py`
- Modify: `tests/test_live_price_gateway.py`
- Modify: `tests/unit/test_postgres_api_health.py`
- Modify: `tests/integration/test_api_health.py`

- [ ] **Step 1: Write failing gateway sink tests**
  - DEX update stores cache, publishes `live_market_update`, and invokes the decision snapshot sink with `source_kind="okx_dex_ws"`.
  - CEX ticker stores cache, publishes `live_market_update`, and invokes the sink with `source_kind="okx_cex_ticker"`.
  - Missing sink keeps existing UI behavior.

- [ ] **Step 2: Implement gateway sink**
  - Add constructor arg `decision_snapshot_sink: Callable[[LiveMarketSnapshot, str, int], Any] | None = None`.
  - Call sink from `_store_payload()`.
  - Increment `decision_snapshots_written` in `last_result` when sink succeeds.

- [ ] **Step 3: Wire runtime persistence**
  - In `_build_runtime()`, pass a sink that opens `repository_session(db_pool)` and calls `repos.decision_market_snapshots.upsert_snapshot(...)`.
  - Keep `hub.publish` unchanged.

- [ ] **Step 4: Run gateway and health tests**
  - Run: `uv run pytest tests/test_live_price_gateway.py tests/unit/test_postgres_api_health.py tests/integration/test_api_health.py -q`
  - Expected: PASS.

### Task 3: Hard-cut Token Factor Snapshot v4

**Files:**
- Modify: `src/parallax/domains/token_intel/_constants.py`
- Modify: `src/parallax/domains/token_intel/scoring/factor_snapshot.py`
- Modify: `src/parallax/domains/token_intel/scoring/factor_snapshot_contract.py`
- Modify: `tests/unit/test_factor_snapshot.py`
- Modify: `tests/architecture/test_no_factor_snapshot_fallback.py`

- [ ] **Step 1: Write fail-closed DEX gate tests**
  - Replace `test_fresh_dex_market_missing_floor_inputs_is_not_market_ready` expectation: `market_data_unverified` appears in `blocked_reasons`, `eligible_for_high_alert is False`, and `max_decision` is not `high_alert`.
  - Replace non-finite market input expectations the same way.

- [ ] **Step 2: Bump factor version and contract**
  - Set `TOKEN_FACTOR_SNAPSHOT_VERSION = "token_factor_snapshot_v4_decision_facts"`.
  - Require `composite.family_percentiles`.
  - Reject v3 snapshots.

- [ ] **Step 3: Implement fail-closed market gates**
  - Missing DEX floor inputs append one stable blocker: `market_data_unverified`.
  - Keep specific below-floor blockers for present values below thresholds.
  - Keep `market_metadata_missing` in `risk_reasons`.

- [ ] **Step 4: Fix `_factor_sum()` zero handling**
  - Average all non-negative finite scores including zero.
  - Add negative penalties after the average.

- [ ] **Step 5: Run factor tests**
  - Run: `uv run pytest tests/unit/test_factor_snapshot.py tests/architecture/test_no_factor_snapshot_fallback.py -q`
  - Expected: PASS.

### Task 4: Feed decision snapshots into Token Radar projection

**Files:**
- Modify: `src/parallax/domains/token_intel/queries/token_radar_source_query.py`
- Modify: `src/parallax/domains/token_intel/services/token_radar_projection.py`
- Modify: `tests/unit/test_token_radar_source_query.py`
- Modify: `tests/unit/test_token_radar_projection.py`

- [ ] **Step 1: Write source query contract tests**
  - Assert SQL contains `decision_market_snapshots`.
  - Assert selected row keys include `decision_market_market_cap_usd`, `decision_market_liquidity_usd`, and `decision_market_holders`.

- [ ] **Step 2: Write projection market tests**
  - With decision snapshot fields present, `_project_group()` writes those values into `factor_snapshot.market`.
  - With no decision snapshot fields, DEX snapshot has `market_data_source="anchor_only"` and gate blocks `market_data_unverified`.
  - CEX rows can remain market-ready with price/volume but no DEX floor blockers.

- [ ] **Step 3: Implement SQL join**
  - Add the lateral join described above.
  - Pass `now_ms` twice for `observed_at_ms <= now_ms` and `expires_at_ms >= now_ms`.

- [ ] **Step 4: Implement `_market()` decision fact merge**
  - Anchor fields stay immutable.
  - Decision snapshot fields populate current decision facts.
  - `snapshot_age_ms = now_ms - decision_market_received_at_ms`.
  - `field_statuses` reflects present/missing for price, market cap, liquidity, holders, volume, open interest.

- [ ] **Step 5: Run projection tests**
  - Run: `uv run pytest tests/unit/test_token_radar_source_query.py tests/unit/test_token_radar_projection.py -q`
  - Expected: PASS.

### Task 5: Make cohort normalization explanatory only

**Files:**
- Modify: `src/parallax/domains/token_intel/services/token_radar_projection.py`
- Modify: `tests/unit/test_token_radar_apply_cross_section.py`
- Modify: `tests/unit/test_cross_section_normalizer.py` only if helper signatures change.

- [ ] **Step 1: Replace cross-section expectations**
  - `families.social_heat.score` remains raw absolute score.
  - `composite.family_scores.social_heat` remains raw absolute score.
  - `composite.family_percentiles.social_heat` receives percentile score.
  - `composite.rank_score` remains raw absolute alpha score.

- [ ] **Step 2: Update `_apply_cross_section()`**
  - Do not overwrite family `score`.
  - Write percentile values under `composite.family_percentiles`.
  - Keep `normalization.factor_ranks` and `normalization.alpha_rank`.
  - Decision uses raw `rank_score` plus gate caps.

- [ ] **Step 3: Run cross-section tests**
  - Run: `uv run pytest tests/unit/test_token_radar_apply_cross_section.py tests/unit/test_cross_section_normalizer.py -q`
  - Expected: PASS.

### Task 6: Recut Pulse trigger, gate, audit, and prompt

**Files:**
- Modify: `src/parallax/domains/pulse_lab/interfaces.py`
- Modify: `src/parallax/domains/pulse_lab/services/pulse_candidate_gate.py`
- Modify: `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py`
- Modify: `src/parallax/domains/pulse_lab/types/pulse_recommendation.py`
- Modify: `src/parallax/integrations/openai_agents/pulse_recommendation_agent_client.py` only if audit payload shape needs centralization.
- Modify: `tests/unit/test_pulse_candidate_gate.py`
- Modify: `tests/unit/test_pulse_candidate_worker.py`
- Modify: `tests/test_pulse_recommendation.py`
- Modify: `tests/test_pulse_recommendation_agent_client.py`

- [ ] **Step 1: Write Pulse gate tests**
  - `market_data_unverified` + high score returns `risk_rejected_high_info`, score band `blocked` or `watch`, and `max_recommendation="research"`.
  - Clean DEX with all market floors present can still become `trade_candidate`.

- [ ] **Step 2: Write trigger tests**
  - Candidate with percentile high but raw `rank_score < min_rank_score` is not enqueued.
  - Candidate with raw score high but `gates.max_decision != "high_alert"` does not enqueue as trade candidate.

- [ ] **Step 3: Write request audit test**
  - `pulse_agent_runs.request_json` contains `agent_context.factor_snapshot`, `agent_context.gate_result`, `agent_context.selected_posts`, `available_factor_keys`, and `prompt_version`.
  - It does not contain only `context_hash`.

- [ ] **Step 4: Implement Pulse version bumps and gate logic**
  - Update constants in `interfaces.py`.
  - Keep no compatibility with old Pulse versions.

- [ ] **Step 5: Implement full request audit**
  - Store complete sanitized agent context in `request_json`.
  - Keep `input_hash` for indexing and trace comparison.

- [ ] **Step 6: Update prompt and factor keys**
  - Add explicit percentile vs absolute-score instructions.
  - Add `composite.family_percentiles.<family>` to `collect_factor_keys()`.

- [ ] **Step 7: Run Pulse tests**
  - Run: `uv run pytest tests/unit/test_pulse_candidate_gate.py tests/unit/test_pulse_candidate_worker.py tests/test_pulse_recommendation.py tests/test_pulse_recommendation_agent_client.py -q`
  - Expected: PASS.

### Task 7: Update API, frontend, and docs contracts

**Files:**
- Modify: `src/parallax/domains/pulse_lab/read_models/signal_pulse_service.py`
- Modify: `src/parallax/domains/token_intel/read_models/asset_flow_service.py` if fact-card/read payload needs field labels.
- Modify: `docs/CONTRACTS.md`
- Modify: `src/parallax/domains/token_intel/ARCHITECTURE.md`
- Modify: `docs/generated/score-versions.md` through the existing docs generation command.
- Modify: `web/src/lib/tokenFactorSnapshot.ts`
- Modify: `web/src/api/types.ts`
- Modify: `web/src/lib/tokenRadar.ts`
- Modify: `web/src/components/SignalLabPulse.tsx`
- Modify: `web/src/components/SignalLabInspector.tsx`
- Modify: `web/src/components/ScoreLedger.test.tsx`
- Modify: `web/src/components/SignalLabPulse.test.tsx`
- Modify: `web/src/components/SignalLabInspector.test.tsx`
- Modify: `web/src/lib/tokenRadar.test.ts`

- [ ] **Step 1: Write frontend contract tests**
  - v3 snapshot is rejected.
  - v4 snapshot requires `family_percentiles`.
  - Score ledger shows absolute family score separately from percentile.
  - Token Radar market display still derives from `live_market`.

- [ ] **Step 2: Update backend read model**
  - Add `alpha_family_percentiles` to Signal Pulse fact cards.
  - Ensure `market_ready_rate` uses factor snapshot decision-fact readiness.

- [ ] **Step 3: Update frontend runtime validators and types**
  - Change schema constant to `token_factor_snapshot_v4_decision_facts`.
  - Add `family_percentiles`.
  - Keep `live_market` type unchanged.

- [ ] **Step 4: Update docs**
  - Document decision facts vs live market.
  - Document Pulse score semantics.

- [ ] **Step 5: Run API/frontend tests**
  - Run: `uv run pytest tests/unit/test_asset_flow_service.py tests/unit/test_signal_pulse_service.py tests/integration/test_api_http.py -q`
  - Run: `cd web && npm test -- --run`
  - Expected: PASS.

### Task 8: End-to-end verification and production probes

**Files:**
- Create after implementation: `docs/superpowers/plans/active/2026-05-12-signal-lab-pulse-decision-facts-hard-cut-verification-cn.md`
- Modify if needed: `docs/TECH_DEBT.md`

- [ ] **Step 1: Run full backend checks**
  - Run: `make check-all`
  - Expected: exit 0.

- [ ] **Step 2: Rebuild projections locally**
  - Run the existing projection worker/CLI path used in this repo for Token Radar rebuild.
  - Expected: new rows use `token-radar-v14-decision-facts-hard-cut` and `token_factor_snapshot_v4_decision_facts`.

- [ ] **Step 3: Probe current DB behavior**
  - Query Pulse candidates in the last hour.
  - Expected before DEX WS is fully configured: DEX market-unknown candidates are `risk_rejected_high_info` or `blocked_low_information`, not `trade_candidate`.

```sql
SELECT pulse_status, target_type, COUNT(*)
FROM pulse_candidates
WHERE updated_at_ms > (EXTRACT(EPOCH FROM NOW()) - 3600) * 1000
GROUP BY pulse_status, target_type
ORDER BY target_type, pulse_status;
```

- [ ] **Step 4: Verify request audit**
  - Expected: `hash_only = 0`.

```sql
SELECT
  COUNT(*) FILTER (WHERE request_json ? 'agent_context') AS with_agent_context,
  COUNT(*) FILTER (WHERE request_json ? 'context_hash' AND NOT request_json ? 'agent_context') AS hash_only
FROM pulse_agent_runs
WHERE started_at_ms > (EXTRACT(EPOCH FROM NOW()) - 3600) * 1000;
```

- [ ] **Step 5: Verify decision fact fill rate**
  - Expected with DEX WS disabled: CEX snapshots fill, DEX remains low but fail-closed.
  - Expected after DEX WS enabled: hot DEX targets begin filling `decision_market_snapshots`.

```sql
SELECT target_type, COUNT(*) AS snapshots
FROM decision_market_snapshots
WHERE created_at_ms > (EXTRACT(EPOCH FROM NOW()) - 3600) * 1000
GROUP BY target_type;
```

## Impact and coupling assessment

| Chain | Impact | Coupling | Mitigation |
|---|---|---|---|
| GMGN ingestion | No behavioral change | None | No files under `domains/ingestion` or evidence extraction need changes. |
| Token identity / resolution | No resolver logic change | Low | `TokenRadarSourceQuery` still consumes current resolutions; only market fact join is added. |
| Anchor price worker | No semantic change | Low | Anchor price remains immutable event-time price; do not add market fields to anchor observations. |
| LivePriceGateway / WebSocket | Add persistence side effect | Medium | Keep public `live_market_update` payload unchanged; persistence sink is asset-market only and tested separately. |
| Token Radar projection | Major contract change | High | Bump projection/factor versions; no compatibility fallback; tests cover v4-only shape. |
| Cohort normalizer | Semantic change | High | Math helper can stay; projection changes where percentiles are stored and how they are consumed. |
| Pulse candidate worker | Major trigger/audit change | High | Version bump Pulse constants; truncate old Pulse rows; tests cover full request audit and raw-score trigger. |
| OpenAI agent client | Prompt/audit semantics change | Medium | Keep output schema `pulse_recommendation_v1`; change prompt version and input instructions. |
| Notifications | Indirect volume drop | Medium | Signal Pulse notification rule reads Pulse statuses; expect fewer `trade_candidate` notifications and more risk-rejected/blocked rows. No rule compatibility fallback. |
| Harness/playbook settlement | Old pending Pulse playbooks removed | Medium | Hard truncate Pulse playbook tables; new playbooks use v2 decision-facts version. Historical outcome comparisons across hard cut are intentionally not mixed. |
| `/api/token-radar` | Public payload additive for factor snapshot | Medium | `live_market` unchanged; factor snapshot schema bumped and frontend validator updated. |
| `/api/signal-lab/pulse` | Public payload schema bump through nested factor snapshot | High | Frontend and tests update in the same PR; old candidates are truncated so UI does not see mixed schemas. |
| Search inspect market overlay | No direct change | Low | Search overlay uses candle service and matched radar row; verify no factor snapshot fallback breaks it. |
| Stocks radar | No direct change | Low | Stocks use separate `MarketInstrument` path; run stocks tests to catch accidental constants coupling. |
| Frontend Token Radar | Moderate | Medium | Keep UI market from `live_market`; update score labels to avoid percentile ambiguity. |
| Frontend Signal Lab | Moderate | Medium | v4 validator and fact cards show absolute scores plus explicit percentile context. |

## Rollout order

1. Create worktree and branch.
2. Apply migration creating `decision_market_snapshots` and truncating old Pulse runtime tables.
3. Deploy code with v14/v4 constants and fail-closed gates.
4. Restart the single ASGI worker so runtime constants, worker state, and in-memory live cache reset together.
5. Keep `dex_ws_enabled=false` acceptable during first deploy; expected behavior is fewer/no DEX `trade_candidate` rows.
6. Enable `dex_ws_enabled=true` only after snapshot persistence is verified for CEX and the OKX DEX WS smoke test passes.
7. Monitor `/readyz.live_price_gateway.last_result.decision_snapshots_written`, Pulse status distribution, and `decision_market_snapshots` fill rate.

## Rollback

- Code rollback is a normal deploy rollback to the previous commit.
- Database rollback is not fully reversible because Pulse runtime tables are truncated by design. The compensating action is to rebuild Token Radar projections and let Pulse repopulate from current facts.
- If DEX WS causes provider quota or stability issues, set `providers.okx.dex_ws_enabled=false` and restart. Pulse remains fail-closed for DEX market unknowns.
- Do not restore v3 readers or old Pulse candidates as a rollback path; that would reintroduce the bug.

## Acceptance test commands

- AC1 fail-closed DEX gates:
  - `uv run pytest tests/unit/test_factor_snapshot.py::test_fresh_dex_market_missing_floor_inputs_is_not_market_ready tests/unit/test_pulse_candidate_gate.py -q`
- AC2 decision snapshot source:
  - `uv run pytest tests/integration/test_decision_market_snapshot_repository.py tests/unit/test_token_radar_source_query.py tests/unit/test_token_radar_projection.py -q`
- AC3 no percentile-as-score:
  - `uv run pytest tests/unit/test_token_radar_apply_cross_section.py -q`
- AC4 full Pulse request audit:
  - `uv run pytest tests/unit/test_pulse_candidate_worker.py tests/integration/test_pulse_repository.py -q`
- AC5 no compatibility fallback:
  - `uv run pytest tests/architecture/test_no_factor_snapshot_fallback.py web/src/lib/tokenFactorSnapshot.test.ts -q`
  - Frontend test command is `cd web && npm test -- --run`.
- AC6 end-to-end:
  - `make check-all`
  - Production probe SQL listed in Task 8.

## Verification artifact

Create `docs/superpowers/plans/active/2026-05-12-signal-lab-pulse-decision-facts-hard-cut-verification-cn.md` before declaring implementation complete. It must include:

- Full `make check-all` output.
- Backend targeted test outputs.
- Frontend test output.
- Migration revision applied.
- `/readyz` excerpt for `live_price_gateway`, `token_radar_projection`, and `pulse_agent`.
- SQL evidence for Pulse status distribution, request audit fill rate, and decision snapshot fill rate.
- Remaining risks and any `docs/TECH_DEBT.md` additions.

