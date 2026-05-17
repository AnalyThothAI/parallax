# Binance Profile Source Hard-Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 正式引入 Binance 作为 token profile 数据源，替换 `cex_tokens` 上的 icon 兼容字段，并把 Binance Web3 DEX metadata 接入 profile source 链路。

**Architecture:** `cex_tokens` 继续只表达 CEX token 身份与路由；CEX icon/profile 写入新的 `cex_token_profiles` source cache。DEX Binance Web3 metadata 使用现有 `asset_profiles` 多 provider cache，写入 `provider='binance_web3_profile'`，由唯一 `token_profile_current` writer 投影到公共读模型。

**Tech Stack:** Python, PostgreSQL/Alembic, httpx, pytest, existing worker/provider wiring.

---

### Task 1: Source Cache Schema

**Files:**
- Create: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260517_0058_binance_profile_sources.py`
- Create: `src/gmgn_twitter_intel/domains/asset_market/repositories/cex_token_profile_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/interfaces.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/repository_session.py`

- [x] Add `cex_token_profiles` keyed by `(cex_token_id, provider)`.
- [x] Migrate existing `cex_tokens.logo_*` into `cex_token_profiles(provider='binance_cex_profile')`.
- [x] Drop `cex_tokens.logo_*` and `idx_cex_tokens_logo`.
- [x] Add repository method that upserts only when the CEX token exists.

### Task 2: Binance Clients and Sync

**Files:**
- Replace: `src/gmgn_twitter_intel/integrations/binance/cex_icon_client.py`
- Create: `src/gmgn_twitter_intel/integrations/binance/web3_token_client.py`
- Replace: `src/gmgn_twitter_intel/domains/asset_market/services/cex_token_icon_sync.py`

- [x] Rename CEX client/service language from icon fallback to Binance CEX profile source.
- [x] Implement Binance Web3 token metadata client using `/bapi/defi/v1/public/wallet-direct/buw/wallet/dex/market/token/meta/info/ai`.
- [x] Normalize Web3 relative icon paths with `https://bin.bnbstatic.com`.

### Task 3: Provider and Worker Wiring

**Files:**
- Modify: `src/gmgn_twitter_intel/platform/config/settings.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/providers_wiring.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/services/asset_profile_refresh.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/runtime/asset_profile_refresh_worker.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/bootstrap.py`

- [x] Add Binance config under `providers.binance`.
- [x] Wire Binance Web3 as a `PROFILE_DEX_EXACT` provider source.
- [x] Make `asset_profile_refresh` iterate explicit provider sources instead of one hardcoded GMGN source.

### Task 4: Projection Hard Cut

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/asset_market/queries/token_profile_source_query.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/services/token_profile_current_projection.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/runtime/token_profile_current_worker.py`

- [x] Read `binance_web3_profile` rows from `asset_profiles`.
- [x] Read CEX profiles from `cex_token_profiles`, not `cex_tokens`.
- [x] Project source priority as GMGN OpenAPI, Binance Web3, GMGN stream, OKX exact, then missing.
- [x] Project CEX rows with `profile_provider='binance_cex_profile'`.

### Task 5: CLI, Docs, Verification

**Files:**
- Modify: `src/gmgn_twitter_intel/app/surfaces/cli/main.py`
- Modify: `docs/ARCHITECTURE.md`, `docs/WORKERS.md`, `docs/CONTRACTS.md`, domain architecture docs
- Regenerate: `docs/generated/cli-help.md`, `docs/generated/db-schema.md`

- [x] Replace `ops sync-cex-token-icons` with `ops sync-binance-cex-profiles`.
- [x] Update docs to reflect source caches and real config location.
- [x] Run targeted pytest, migration checks, CLI help generation, and residue grep for old compatibility paths.

### Verification Notes

- [x] `uv run gmgn-twitter-intel db migrate`
- [x] `make docs-generated`
- [x] `uv run gmgn-twitter-intel ops sync-binance-cex-profiles`
- [x] `uv run gmgn-twitter-intel ops refresh-asset-profiles --limit 20`
- [x] `uv run gmgn-twitter-intel ops rebuild-token-profiles --limit 1000`
- [x] `uv run ruff check .`
- [x] `uv run pytest -q --ignore=tests/integration/test_docs_generated.py`
