# Token Profile Current Facts Hard Cut Plan

> **For agentic workers:** execute with `superpowers:executing-plans` or `superpowers:subagent-driven-development`. Track every checkbox. This is a hard cut: do not add feature flags, compatibility branches, or Binance provider code.

**Goal:** replace the GMGN-only public token profile read path with a canonical `token_profile_current` projection sourced from persisted GMGN OpenAPI, GMGN stream, and OKX DEX exact evidence.

**Owning spec:** `docs/superpowers/specs/active/2026-05-17-token-profile-current-facts-hard-cut-cn.md`

**Key current-code facts:**

- `asset_profiles` and `asset_profile_refresh` already exist as a GMGN OpenAPI source cache.
- `TokenProfileReadModel` is the bad public hardcode: it imports `GMGN_DEX_PROFILE_PROVIDER` and reads only `asset_profiles`.
- GMGN stream icons already exist in `TokenSnapshot.icon_url` and `asset_identity_evidence.raw_payload_json.i`.
- OKX DEX logos already exist in `asset_identity_evidence.raw_payload_json.tokenLogoUrl`.
- OKX/Binance CEX sources do not provide trusted CEX icons in the current architecture.

---

## Status

- [ ] Not started
- [ ] Implementing
- [ ] Verified

## Phase 0 - Baseline and Guardrails

- [ ] Capture dirty worktree before editing:

  ```bash
  git status --short
  ```

- [ ] Confirm current profile hardcode and source facts:

  ```bash
  rg -n "GMGN_DEX_PROFILE_PROVIDER|profiles_for_asset_ids|TokenProfileReadModel" src tests
  rg -n "tokenLogoUrl|raw_payload_json.*i|TokenSnapshot\\(.*icon_url" src tests
  ```

- [ ] Run targeted baseline tests:

  ```bash
  uv run pytest tests/unit/test_token_profile_read_model.py tests/unit/test_asset_profile_repository.py tests/unit/test_asset_profile_refresh.py -q
  ```

- [ ] Record current live DEX coverage for later comparison:

  ```bash
  uv run parallax asset-flow --window 1h --scope all --limit 100 > /tmp/before-token-profile-current.json
  ```

## Phase 1 - Schema: Canonical Current Profile Table

- [ ] Add Alembic migration after the current head:

  `src/parallax/platform/db/alembic/versions/<next>_token_profile_current.py`

- [ ] Create `token_profile_current`:

  ```sql
  CREATE TABLE IF NOT EXISTS token_profile_current (
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ready', 'missing', 'unsupported', 'error')),
    profile_provider TEXT,
    source_kind TEXT NOT NULL,
    source_ref TEXT,
    symbol TEXT,
    name TEXT,
    logo_url TEXT,
    banner_url TEXT,
    website_url TEXT,
    twitter_username TEXT,
    twitter_url TEXT,
    telegram_url TEXT,
    gmgn_url TEXT,
    geckoterminal_url TEXT,
    description TEXT,
    quality_flags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    observed_at_ms BIGINT,
    computed_at_ms BIGINT NOT NULL,
    updated_at_ms BIGINT NOT NULL,
    PRIMARY KEY(target_type, target_id)
  );
  ```

- [ ] Add indexes:

  ```sql
  CREATE INDEX IF NOT EXISTS idx_token_profile_current_status
    ON token_profile_current(status, updated_at_ms DESC);

  CREATE INDEX IF NOT EXISTS idx_token_profile_current_provider
    ON token_profile_current(profile_provider, updated_at_ms DESC);

  CREATE INDEX IF NOT EXISTS idx_token_profile_current_logo
    ON token_profile_current(updated_at_ms DESC)
    WHERE logo_url IS NOT NULL;
  ```

- [ ] Update generated DB schema only if the project workflow requires it. Do not overwrite unrelated existing changes in `docs/generated/db-schema.md`.

## Phase 2 - Repository and Session Wiring

- [ ] Add `src/parallax/domains/asset_market/repositories/token_profile_current_repository.py`.

- [ ] Implement repository methods:

  ```python
  class TokenProfileCurrentRepository:
      def upsert_current(self, row: TokenProfileCurrentRow, *, commit: bool = True) -> None: ...
      def upsert_status(self, *, target_type: str, target_id: str, status: str, source_kind: str, computed_at_ms: int, commit: bool = True) -> None: ...
      def current_for_targets(self, targets: list[tuple[str, str]]) -> dict[tuple[str, str], dict[str, Any]]: ...
      def delete_not_in_batch(self, *, target_type: str, target_ids: list[str], computed_at_ms: int, commit: bool = True) -> None: ...
  ```

- [ ] Keep serialization in the repository:

  - sanitize text with existing `postgres_safe_text`;
  - sanitize JSON with existing `postgres_safe_json`;
  - use `Jsonb` for `quality_flags_json` and `source_payload_json`;
  - normalize empty strings to `None`;
  - truncate oversized source payloads only if an existing project helper already does so.

- [ ] Add repository to `RepositorySession`:

  `src/parallax/app/runtime/repository_session.py`

- [ ] Export it from `src/parallax/domains/asset_market/interfaces.py`.

- [ ] Add unit tests:

  `tests/unit/test_token_profile_current_repository.py`

## Phase 3 - Source Query and Projection Policy

- [ ] Add a narrow source-query module:

  `src/parallax/domains/asset_market/queries/token_profile_source_query.py`

- [ ] Implement `recent_profile_targets(now_ms, limit, lookback_ms)`:

  - use current `token_radar_rows` and bounded recent `token_intent_resolutions`;
  - include `target_type='Asset'` rows with exact `asset_id`;
  - include observed `CexToken` rows only to return explicit unsupported status;
  - do not scan unbounded events.

- [ ] Implement source loaders keyed by exact `asset_id`:

  - `gmgn_openapi_profiles(asset_ids)` from `asset_profiles` ready rows;
  - `gmgn_stream_profiles(asset_ids)` from `asset_identity_evidence` provider `gmgn` rows with `raw_payload_json.i`;
  - `okx_dex_profiles(asset_ids)` from `asset_identity_evidence` provider `okx`, evidence kind `okx_dex_exact_address`, and `raw_payload_json.tokenLogoUrl`.

- [ ] Keep source loaders read-only. They must not call GMGN, OKX, Binance, or any network client.

- [ ] Add policy module:

  `src/parallax/domains/asset_market/services/token_profile_current_projection.py`

- [ ] Implement deterministic priority:

  ```text
  gmgn_dex_profile ready row
    > gmgn_stream_snapshot icon
    > okx_dex_evidence non-placeholder tokenLogoUrl
    > missing for DEX Asset
    > unsupported for CexToken
  ```

- [ ] Filter placeholder logos:

  - URLs containing `/default-logo/`;
  - empty strings;
  - non-http/non-https strings.

- [ ] Preserve flags:

  - `okx_placeholder_logo`;
  - `invalid_logo_url`;
  - `source_without_logo`;
  - `cex_profile_unsupported`.

- [ ] Add unit tests:

  `tests/unit/test_token_profile_current_projection.py`

  Required cases:

  - GMGN OpenAPI ready wins over stream and OKX.
  - GMGN stream icon wins when GMGN OpenAPI is missing or error.
  - OKX exact `tokenLogoUrl` fills when GMGN sources are absent.
  - OKX `okx_dex_symbol_candidate` rows are ignored for logos.
  - OKX default-logo is not exposed.
  - `CexToken` becomes unsupported.
  - GMGN OpenAPI `error/missing` does not block lower-priority valid sources.

## Phase 4 - Worker and One-shot Rebuild

- [ ] Add runtime worker:

  `src/parallax/domains/asset_market/runtime/token_profile_current_worker.py`

- [ ] Worker behavior:

  - opens one worker DB session per run;
  - reads bounded profile targets;
  - projects current rows;
  - upserts `token_profile_current`;
  - returns counts by `ready`, `missing`, `unsupported`, `error`, `with_logo`, and `source_provider`.

- [ ] Register worker in:

  - `src/parallax/app/runtime/worker_registry.py`;
  - `src/parallax/app/runtime/bootstrap.py`;
  - `src/parallax/platform/config/settings.py`;
  - `docs/WORKERS.md`;
  - `docs/CONTRACTS.md` if CLI/config surface changes.

- [ ] Add worker setting key:

  ```yaml
  token_profile_current:
    enabled: true
    interval_seconds: 60
    batch_size: 500
  ```

- [ ] Add CLI command:

  ```bash
  uv run parallax ops rebuild-token-profiles --limit 500
  ```

- [ ] Keep `ops refresh-asset-profiles` only as GMGN OpenAPI source refresh. Do not use it in public reads.

- [ ] Add tests:

  - `tests/unit/test_token_profile_current_worker.py`;
  - CLI parser/integration case for `ops rebuild-token-profiles`;
  - worker registry architecture test.

## Phase 5 - Public Read Path Hard Cut

- [ ] Rewrite `src/parallax/domains/asset_market/read_models/token_profile_read_model.py`.

- [ ] Constructor changes:

  ```python
  class TokenProfileReadModel:
      def __init__(self, *, token_profiles: TokenProfileCurrentRepository) -> None:
          self.token_profiles = token_profiles
  ```

- [ ] Remove these from the read model:

  - import of `GMGN_DEX_PROFILE_PROVIDER`;
  - `asset_profiles.profiles_for_asset_ids(...)`;
  - target-type filtering that silently returns `None` for `CexToken`.

- [ ] New behavior:

  - fetch current rows by `(target_type, target_id)`;
  - return `pending` when a DEX `Asset` has no current row;
  - return `unsupported` when `target_type == "CexToken"` and no row exists;
  - preserve the existing public block shape for `identity`, `links`, and `source`;
  - include `source_kind`, `source_ref`, and `quality_flags` in `source`.

- [ ] Update all wiring:

  - `src/parallax/app/surfaces/api/http.py`;
  - `src/parallax/app/surfaces/cli/main.py`;
  - `src/parallax/app/runtime/bootstrap.py`;
  - tests that instantiate `TokenProfileReadModel`.

- [ ] Add architecture guard:

  ```bash
  ! rg -n "GMGN_DEX_PROFILE_PROVIDER|profiles_for_asset_ids" src/parallax/domains/asset_market/read_models/token_profile_read_model.py
  ```

## Phase 6 - Frontend Contract Check

- [ ] Verify web API types already tolerate the enriched source fields. If not, update:

  - `web/src/api/types.ts`;
  - any local profile block type declarations.

- [ ] Keep rendering from `profile.identity.logo_url`.

- [ ] Do not add React-side parsing of:

  - `token_snapshot`;
  - OKX raw payload;
  - GMGN raw payload;
  - Binance payload.

- [ ] Update frontend tests only for explicit statuses if needed:

  - ready with logo;
  - pending/missing/unsupported without logo.

## Phase 7 - Architecture and Regression Tests

- [ ] Add architecture test:

  `tests/architecture/test_token_profile_current_hard_cut.py`

- [ ] Assertions:

  - public read model does not import `GMGN_DEX_PROFILE_PROVIDER`;
  - public read model does not call `asset_profiles`;
  - no source file under `src/parallax` imports a Binance profile client or defines a Binance token profile provider;
  - HTTP/API read paths do not call GMGN/OKX provider methods for profiles.

- [ ] Update existing tests:

  - `tests/unit/test_token_profile_read_model.py`;
  - `tests/unit/test_worker_settings.py`;
  - `tests/architecture/test_worker_runtime_contracts.py`;
  - API/CLI tests that inspect profile output.

- [ ] Run targeted suite:

  ```bash
  uv run pytest \
    tests/unit/test_token_profile_current_repository.py \
    tests/unit/test_token_profile_current_projection.py \
    tests/unit/test_token_profile_read_model.py \
    tests/unit/test_token_profile_current_worker.py \
    tests/architecture/test_token_profile_current_hard_cut.py \
    tests/integration/test_cli.py \
    -q
  ```

## Phase 8 - Live Verification with Real Config

- [ ] Use the real local config path:

  ```bash
  uv run parallax config | jq '.paths, .providers.gmgn, .providers.okx'
  ```

- [ ] Run GMGN source refresh. Provider block is acceptable if it reports no token-level errors:

  ```bash
  uv run parallax ops refresh-asset-profiles --limit 20
  ```

- [ ] Rebuild current profiles:

  ```bash
  uv run parallax ops rebuild-token-profiles --limit 500
  ```

- [ ] Inspect current coverage:

  ```bash
  uv run parallax asset-flow --window 1h --scope all --limit 100 > /tmp/after-token-profile-current.json
  ```

- [ ] Compare:

  - DEX rows with `profile.identity.logo_url` should exceed the GMGN-only baseline.
  - DEX rows with GMGN stream `i` and old GMGN profile error/missing should now show `provider=gmgn_stream_snapshot`.
  - DEX rows with OKX non-placeholder `tokenLogoUrl` and no GMGN source should now show `provider=okx_dex_evidence`.
  - CEX rows should show `unsupported` or no profile by explicit contract; they must not receive DEX-matched logos.

- [ ] Run final quality checks:

  ```bash
  uv run ruff check src tests
  uv run pytest tests/unit/test_token_profile_read_model.py tests/unit/test_token_profile_current_projection.py -q
  git diff --check
  ```

## Completion Criteria

- [ ] `TokenProfileReadModel` reads only `token_profile_current`.
- [ ] `asset_profiles` is only a GMGN OpenAPI source cache.
- [ ] GMGN stream snapshot icons are promoted to current profile facts.
- [ ] OKX DEX exact `tokenLogoUrl` values are promoted when non-placeholder.
- [ ] CEX icons remain explicit unsupported, not symbol-faked.
- [ ] No Binance dependency/config/provider was introduced.
- [ ] Frontend uses the same `profile.identity.logo_url` contract with no raw fallback.
- [ ] Live coverage after rebuild is better than the GMGN-only baseline.
