# Provider Rank Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 保存 OKX search 的真实候选顺序，并在 market dominance 无法决策时用 fresh provider rank 做 KISS fallback。

**Architecture:** 不加表、不加 migration、不兼容旧 evidence。`TokenDiscoveryWorker` 在 symbol search 写入 `raw_payload_json.provider_rank`；`RegistryRepository` 只读取这个 exact key；`DeterministicTokenResolver` 只在 dominance 返回 None 后选择 fresh provider rank 最小的候选。

**Tech Stack:** Python 3.13, pytest, PostgreSQL JSONB identity evidence.

---

### Task 1: Provider Rank Tests

**Files:**
- Modify: `tests/unit/test_token_discovery_worker.py`
- Modify: `tests/integration/test_registry_repository.py`
- Modify: `tests/unit/test_deterministic_token_resolver.py`

- [ ] **Step 1: Add worker raw payload test**

Add a unit test that calls `_process_dex_symbol_lookup()` with two fake candidates returned in provider order, then asserts the fake identity evidence receives `provider_rank: 0` and `provider_rank: 1`.

Run:

```bash
uv run pytest tests/unit/test_token_discovery_worker.py::test_symbol_lookup_writes_provider_rank_to_identity_payload -q
```

Expected before implementation: FAIL because `provider_rank` is missing.

- [ ] **Step 2: Add registry projection test**

In `test_symbol_lookup_reads_market_metadata_from_okx_identity_evidence`, include `provider_rank` in raw payload and assert `find_assets_by_symbol_with_identity_metadata()` returns `provider_rank` and `provider_rank_observed_at_ms`.

Run:

```bash
uv run pytest tests/integration/test_registry_repository.py::test_symbol_lookup_reads_market_metadata_from_okx_identity_evidence -q
```

Expected before implementation: FAIL because rows do not expose provider rank.

- [ ] **Step 3: Add resolver fallback tests**

Add two resolver tests:
- fresh provider rank resolves to `UNIQUE_BY_CONTEXT / RESOLVED_BY_PROVIDER_RANK` when market fields are absent.
- stale provider rank remains `AMBIGUOUS / NO_MARKET_DOMINANT_CHAIN_ASSET`.

Run:

```bash
uv run pytest tests/unit/test_deterministic_token_resolver.py::test_symbol_without_dominance_falls_back_to_fresh_provider_rank tests/unit/test_deterministic_token_resolver.py::test_symbol_provider_rank_fallback_requires_fresh_identity_evidence -q
```

Expected before implementation: FAIL.

### Task 2: Minimal Implementation

**Files:**
- Modify: `src/parallax/domains/asset_market/runtime/token_discovery_worker.py`
- Modify: `src/parallax/domains/asset_market/repositories/registry_repository.py`
- Modify: `src/parallax/domains/token_intel/services/deterministic_token_resolver.py`

- [ ] **Step 1: Save true provider rank**

In `_process_dex_symbol_lookup()`, build a rank map from the original `candidates` list before exact-symbol filtering:

```python
provider_ranks = _provider_ranks(candidates)
```

Pass `provider_rank=provider_ranks.get(_candidate_identity_key(candidate))` into `_write_dex_candidate()` for retained symbol candidates only.

- [ ] **Step 2: Write exact raw payload key**

Extend `_write_dex_candidate(..., provider_rank: int | None = None)` and add `"provider_rank": provider_rank` to `raw_payload` only when rank is not None.

- [ ] **Step 3: Read exact raw payload key**

In `_with_identity_metadata()`, read only `payload.get("provider_rank")`; no aliases. Return:

```python
"provider_rank": provider_rank,
"provider_rank_observed_at_ms": observed_at_ms if provider_rank is not None else None,
```

- [ ] **Step 4: Resolve by fresh provider rank**

After `_market_dominant_asset(assets)` returns None, call `_provider_rank_asset(assets)`. It should:
- keep only rows with integer `provider_rank`
- require `decision_time_ms - provider_rank_observed_at_ms <= RESOLUTION_MARKET_FRESH_MS`
- sort by `(provider_rank, asset_id)`
- return the first row

Resolution reason: `["RESOLVED_BY_PROVIDER_RANK"]`.

### Task 3: Spec And Verification

**Files:**
- Modify: `docs/superpowers/specs/active/2026-05-12-symbol-only-resolution-gap-cn.md`

- [ ] **Step 1: Update spec**

Move provider-rank fallback from deferred to selected refactor. Keep the warning that no old evidence is guessed or backfilled.

- [ ] **Step 2: Run focused verification**

```bash
uv run pytest tests/unit/test_token_discovery_worker.py tests/unit/test_deterministic_token_resolver.py tests/integration/test_registry_repository.py::test_symbol_lookup_reads_market_metadata_from_okx_identity_evidence -q
uv run pytest tests/integration/test_discovery_and_lookup_repositories.py::test_due_lookup_keys_includes_error_count_for_backoff -q
uv run ruff check src/parallax/domains/asset_market/runtime/token_discovery_worker.py src/parallax/domains/asset_market/repositories/registry_repository.py src/parallax/domains/token_intel/services/deterministic_token_resolver.py tests/unit/test_token_discovery_worker.py tests/unit/test_deterministic_token_resolver.py tests/integration/test_registry_repository.py tests/integration/test_discovery_and_lookup_repositories.py
make check
```

Expected: all commands exit 0. `make check-all` may still be blocked by local docs-generated DB schema drift unrelated to this plan.
