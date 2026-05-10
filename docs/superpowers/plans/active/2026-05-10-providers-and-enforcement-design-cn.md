# Providers Boundary And Enforcement Implementation Plan

> **For agentic workers:** Use this plan task-by-task. Keep the hard KISS rule from the owning spec: no compatibility facade, no deprecated constructor arguments, no dual wiring path.

**Goal:** Move existing Service / Runtime cross-cutting imports behind minimal domain Providers or repository Unit of Work boundaries, then make the boundary mechanically enforceable with agent-friendly remediation messages.

**Architecture:** Keep the four-root layout (`app`, `domains`, `integrations`, `platform`). Add `providers.py` only for domains with real inbound cross-cutting needs, add one service-process composition module at `app/runtime/providers_wiring.py`, and keep database transaction ownership in repositories / repository sessions rather than pretending storage is an external Provider.

**Tech Stack:** Python 3.13, `typing.Protocol`, frozen dataclasses, pytest, ruff, existing AST architecture tests.

---

**Status**: Draft  
**Date**: 2026-05-10  
**Owning spec**: `docs/superpowers/specs/active/2026-05-10-providers-and-enforcement-design-cn.md`  
**Worktree**: `.worktrees/providers-enforcement/`  
**Branch**: `codex/providers-enforcement`

## Pre-flight

- [ ] Confirm the owning spec is approved for implementation.
- [ ] Create the worktree:
  ```bash
  git worktree add .worktrees/providers-enforcement -b codex/providers-enforcement main
  cd .worktrees/providers-enforcement
  ```
- [ ] Confirm worktree state:
  ```bash
  git worktree list
  git branch --show-current
  git status --short
  ```
- [ ] Record clean baseline:
  ```bash
  uv run ruff check .
  uv run pytest
  uv run python -m compileall src tests
  ```

Known-failing baseline tests: none expected. If baseline is not clean, stop and record exact failures before editing.

## File-level edits

### Architecture enforcement

- `tests/test_src_domain_architecture.py`
  - Add a shared remediation assertion helper that formats every failure with `违规`, `原因`, and `修复`.
  - Convert all existing architecture assertions to use the helper.
  - Add `PROVIDER_DOMAINS = {"ingestion", "asset_market", "social_enrichment", "pulse_lab"}`.
  - Add a test that only Provider allowlist domains may contain `providers.py`.
  - Add a test that every `domains/<d>/providers.py` is pure: no `integrations.*`, no `platform.db.*`, no `platform.paths.*`.
  - Add a test that domain `services/`, `scoring/`, and `runtime/` do not import `integrations.*`, `platform.db.*`, or `platform.paths.*`.
  - Add a test that `app/runtime/app.py` does not import `integrations.*` or `domains/*/providers`.
  - Add a test that only `app/runtime/providers_wiring.py` simultaneously imports `integrations.*` and `domains/*/providers`.

### Unit of Work boundary

- `src/gmgn_twitter_intel/app/runtime/repository_session.py`
  - Add a minimal `unit_of_work()` method on `RepositorySession` returning the existing Postgres transaction context for `conn`.
  - Keep transaction implementation here, not in domain runtime files.

- `src/gmgn_twitter_intel/domains/evidence/repositories/evidence_repository.py`
  - Add `unit_of_work()` as the repository-owned transaction context for ingest's existing pinned connection.

- `src/gmgn_twitter_intel/domains/evidence/services/ingest_service.py`
  - Remove direct import of `platform.db.postgres_client.transaction`.
  - Replace `with transaction(self.evidence.conn):` with the repository-owned Unit of Work.
  - Preserve the current atomic span covering event insert, entity insert, token evidence, intents, resolutions, lookup keys, price observations, alerts, and enrichment enqueue.

- `src/gmgn_twitter_intel/domains/social_enrichment/runtime/enrichment_worker.py`
  - Remove direct import of `platform.db.postgres_client.transaction`.
  - Replace the completion/materialization transaction with `repos.unit_of_work()`.
  - Preserve the atomic span covering model-run completion and harness snapshot materialization.

### Domain Provider files

- `src/gmgn_twitter_intel/domains/ingestion/providers.py`
  - Move `IngestStoreProtocol`, `EventPublisherProtocol`, and `UpstreamClientProtocol` out of `runtime/collector_service.py`.
  - Keep only domain-facing method signatures; no GMGN class names.

- `src/gmgn_twitter_intel/domains/ingestion/runtime/collector_service.py`
  - Import provider protocols from same-domain `providers.py`.
  - Remove local Protocol definitions.

- `src/gmgn_twitter_intel/domains/asset_market/providers.py`
  - Add provider-facing value objects: `CexTicker`, `DexTokenCandidate`, `DexTokenPrice`, `DexTokenPriceRequest`.
  - Add `CexMarketProvider` and `DexMarketProvider` Protocols.
  - Methods use business terms (`chain_id`, `address`, `symbol`) and never OKX chain indexes.

- `src/gmgn_twitter_intel/domains/social_enrichment/providers.py`
  - Move `EnrichmentClientProtocol` from `integrations/openai_agents/social_event_agent_client.py`.
  - Include `provider`, `model`, `timeout_seconds`, `request_audit(...)`, and `enrich_event(...)`.

- `src/gmgn_twitter_intel/domains/pulse_lab/providers.py`
  - Move `PulseThesisClientProtocol` semantics from `integrations/openai_agents/pulse_thesis_agent_client.py`.
  - Add a domain-owned `PulseThesisResult` value object if needed so runtime code does not depend on integration result classes.

- `src/gmgn_twitter_intel/integrations/openai_agents/social_event_agent_client.py`
  - Delete the integration-owned Protocol class.
  - Keep the concrete OpenAI client structurally compatible with `SocialEnrichmentProvider`.

- `src/gmgn_twitter_intel/integrations/openai_agents/pulse_thesis_agent_client.py`
  - Delete the integration-owned Protocol class.
  - Keep the concrete OpenAI client and its private result shape; adapt it in wiring if the domain Provider returns `PulseThesisResult`.

### Provider wiring

- `src/gmgn_twitter_intel/app/runtime/providers_wiring.py` (new)
  - Import concrete clients from `integrations.*`.
  - Import domain Provider protocols / value objects from `domains/*/providers`.
  - Add frozen dataclasses for wired provider groups:
    - `IngestionProviders`
    - `AssetMarketProviders`
    - `SocialEnrichmentProviders`
    - `PulseLabProviders`
    - `WiredProviders`
  - Add `wire_providers(settings, *, start_collector: bool) -> WiredProviders`.
  - Build GMGN upstream client factory here, not in `app/runtime/app.py`.
  - Build OKX CEX / DEX adapters here; adapters translate OKX chain indexes and OKX dataclasses into `asset_market.providers` values.
  - Build OpenAI social enrichment and pulse thesis providers here.
  - Do not import domain services, scoring modules, runtime workers, or repositories.

- `src/gmgn_twitter_intel/app/runtime/app.py`
  - Remove direct imports of `DirectGmgnWebSocketClient`, `OkxCexClient`, `OkxDexClient`, `OpenAIAgentsPulseThesisClient`, and `OpenAIAgentsSocialEventClient`.
  - Import only `wire_providers` / `WiredProviders` from `providers_wiring.py`.
  - Add a `providers: WiredProviders` field to `CliRuntime`.
  - In `_build_runtime`, call `wire_providers(...)` after DB health check and before worker construction.
  - Construct workers with provider fields, not raw integration clients.
  - Assign `collector.upstream_client` from the ingestion provider factory.
  - Preserve readiness payload keys and worker lifecycle behavior.

### Asset market provider refactor

- `src/gmgn_twitter_intel/domains/asset_market/services/asset_market_sync.py`
  - Remove direct import of `integrations.okx.chains`.
  - Rename internal sync functions to supplier-neutral names:
    - `sync_okx_cex_universe` -> `sync_cex_universe`
    - `sync_okx_dex_prices` -> `sync_dex_prices`
  - Replace `client` parameters with `cex_market` / `dex_market`.
  - Use `DexTokenPriceRequest(chain_id=..., address=...)`; no `chainIndex` request dictionaries inside the domain.
  - Remove `_okx_chain_index`; any OKX mapping belongs in `providers_wiring.py`.

- `src/gmgn_twitter_intel/domains/asset_market/interfaces.py`
  - Export the renamed supplier-neutral sync functions if still needed by other domains.
  - Do not export OKX-named functions or OKX constants.

- `src/gmgn_twitter_intel/domains/asset_market/services/message_market_observation.py`
  - Replace `cex_client` / `dex_client` parameters with `cex_market` / `dex_market`.
  - Use domain provider value objects for quotes and prices.

- `src/gmgn_twitter_intel/domains/asset_market/runtime/asset_market_sync_worker.py`
  - Rename constructor parameters and fields from `client` / `dex_client` to `cex_market` / `dex_market`.
  - Call `sync_cex_universe` and `sync_dex_prices`.
  - Keep provider state keys `cex` and `dex` unchanged for readiness compatibility.

- `src/gmgn_twitter_intel/domains/asset_market/runtime/message_market_observation_worker.py`
  - Rename constructor parameters and fields to `cex_market` / `dex_market`.
  - Preserve `close()` behavior by calling `close` on provider objects when present.

- `src/gmgn_twitter_intel/domains/asset_market/runtime/token_discovery_worker.py`
  - Rename `dex_client` to `dex_market`.
  - Rename `chain_indexes` to `chain_ids`.
  - Remove `_chain_id_from_okx_index`; candidates already carry domain `chain_id`.
  - Keep lookup behavior, retention limit, demotion, reprocess, and projection triggers unchanged.

- `src/gmgn_twitter_intel/domains/token_intel/runtime/token_radar_projection_worker.py`
  - Rename `dex_client` to `dex_market`.
  - Call supplier-neutral `sync_dex_prices`.
  - Preserve preflight hydration behavior and readiness fields.

- `src/gmgn_twitter_intel/app/surfaces/cli/main.py`
  - Update imports and calls for renamed supplier-neutral asset-market sync functions.
  - Keep command names and CLI public contract unchanged.
  - CLI may keep direct integration imports under this spec's explicit exception.

### Pulse and social workers

- `src/gmgn_twitter_intel/domains/social_enrichment/runtime/enrichment_worker.py`
  - Type `client` as the same-domain enrichment Provider.
  - Keep behavior unchanged for audit, timeout, failure recording, job completion, and publishing.

- `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py`
  - Import `PulseThesisClientProtocol` / `PulseThesisResult` from same-domain `providers.py`.
  - Remove import from `integrations.openai_agents.*`.
  - Keep job scan, gate, model run, persistence, failure handling, and close behavior unchanged.

### Docs

- `docs/ARCHITECTURE.md`
  - Extend dependency direction table with `domains/<d>/providers.py` and `app/runtime/providers_wiring.py`.
  - State that Service / Runtime may not import `integrations.*`, `platform.db.*`, or `platform.paths.*`.
  - State that CLI ops remain a separate surface exception for this spec.

- `docs/superpowers/specs/active/2026-05-10-providers-and-enforcement-design-cn.md`
  - Change `**Status**` to `Approved` only if the user explicitly approves this plan.

## Tasks

### Task 1: Add red architecture tests

- [ ] Update `tests/test_src_domain_architecture.py` with the remediation helper and new Provider / import-boundary tests.
- [ ] Run focused architecture tests and confirm the new tests fail on current leaks:
  ```bash
  uv run pytest tests/test_src_domain_architecture.py -q
  ```
- [ ] Confirm failure output includes `违规`, `原因`, `修复`.

### Task 2: Move transaction ownership behind Unit of Work

- [ ] Add `RepositorySession.unit_of_work()` and `EvidenceRepository.unit_of_work()`.
- [ ] Refactor `IngestService` and `EnrichmentWorker` to use those Unit of Work contexts.
- [ ] Run:
  ```bash
  uv run pytest tests -q -k "ingest or enrichment"
  uv run pytest tests/test_src_domain_architecture.py -q
  ```
- [ ] Confirm there is no `platform.db.*` import under domain `services/` or `runtime/`.

### Task 3: Add domain Provider modules and move existing Protocols

- [ ] Create `ingestion/providers.py`, `asset_market/providers.py`, `social_enrichment/providers.py`, and `pulse_lab/providers.py`.
- [ ] Remove Provider Protocols from runtime and integration files.
- [ ] Update domain runtime classes to import same-domain providers only.
- [ ] Run:
  ```bash
  uv run pytest tests/test_src_domain_architecture.py -q
  uv run python -m compileall src tests
  ```

### Task 4: Add service-process provider wiring

- [ ] Create `app/runtime/providers_wiring.py`.
- [ ] Move GMGN / OKX / OpenAI concrete client construction out of `app/runtime/app.py`.
- [ ] Add OKX adapters that translate OKX chain indexes and integration dataclasses into domain provider values.
- [ ] Update `_build_runtime` to use `wire_providers(...)`.
- [ ] Run:
  ```bash
  uv run pytest tests -q -k "runtime or readiness or app"
  uv run pytest tests/test_src_domain_architecture.py -q
  ```

### Task 5: Refactor asset-market callers to supplier-neutral Providers

- [ ] Rename asset-market sync functions to supplier-neutral names and update all imports.
- [ ] Refactor asset-market workers, message observation, token discovery, and token radar projection to use provider objects.
- [ ] Update CLI imports/calls without changing command names.
- [ ] Run:
  ```bash
  uv run pytest tests -q -k "asset_market or token_discovery or token_radar_projection or message_market"
  uv run gmgn-twitter-intel --help >/tmp/gmgn-help.txt
  ```

### Task 6: Refactor social enrichment and pulse workers

- [ ] Update `EnrichmentWorker` to type against `social_enrichment.providers`.
- [ ] Update `PulseCandidateWorker` to type against `pulse_lab.providers`.
- [ ] Adapt OpenAI pulse result to domain `PulseThesisResult` in `providers_wiring.py` if needed.
- [ ] Run:
  ```bash
  uv run pytest tests -q -k "social_enrichment or pulse"
  uv run pytest tests/test_src_domain_architecture.py -q
  ```

### Task 7: Update architecture docs and remove naming drift

- [ ] Update `docs/ARCHITECTURE.md` with Provider and Unit of Work rules.
- [ ] Search for prohibited internal names:
  ```bash
  rg -n "sync_okx_|dex_client|cex_client|OKX_CHAIN|PulseThesisClientProtocol|EnrichmentClientProtocol|platform\\.db\\.postgres_client import transaction" src/gmgn_twitter_intel/domains src/gmgn_twitter_intel/app/runtime
  ```
- [ ] Fix any remaining hits unless they are in `app/runtime/providers_wiring.py` and intentionally part of adapter wiring.

### Task 8: Final verification

- [ ] Run full gates:
  ```bash
  uv run ruff check .
  uv run pytest
  uv run python -m compileall src tests
  ```
- [ ] Run explicit architecture proof:
  ```bash
  uv run pytest tests/test_src_domain_architecture.py -q
  rg -n "from gmgn_twitter_intel\\.(integrations|platform\\.db|platform\\.paths)" src/gmgn_twitter_intel/domains -g '*.py'
  rg -n "from gmgn_twitter_intel\\.integrations|from gmgn_twitter_intel\\.domains\\..*\\.providers" src/gmgn_twitter_intel/app/runtime/app.py
  ```
- [ ] Record verification output in the final implementation notes or a sibling verification artifact before moving plan/spec to completed.

## PR breakdown

1. **Single PR — Providers boundary hard cut**: all edits above. This is intentionally one PR because the spec rejects compatibility paths and half-providerized runtime states.

## Rollout order

1. Merge code and docs together.
2. Deploy normally; no database migration or config change is required.
3. Watch startup / readiness paths because integration client construction moved from `app/runtime/app.py` to `app/runtime/providers_wiring.py`.
4. Smoke-check:
   - `gmgn-twitter-intel --help`
   - `/healthz`
   - `/readyz`
   - `/ws` connection if a local config is available

## Rollback

- Revert the PR. There are no schema changes, no config changes, and no public contract changes.
- If rollback is needed after deploy, restart the service on the previous revision; PostgreSQL state remains compatible because persistence behavior is unchanged.

## Acceptance test commands

- AC1, AC2, AC3:
  ```bash
  uv run pytest tests/test_src_domain_architecture.py -q
  ```
- Runtime and CLI integrity:
  ```bash
  uv run pytest
  uv run gmgn-twitter-intel --help >/tmp/gmgn-help.txt
  ```
- Static quality:
  ```bash
  uv run ruff check .
  uv run python -m compileall src tests
  ```

## Non-goals

- No DB schema or Alembic migration.
- No HTTP / WebSocket / CLI contract changes.
- No frontend changes.
- No telemetry, feature flag, or config slicing.
- No empty Provider files.
- No compatibility aliases for renamed internal functions.
