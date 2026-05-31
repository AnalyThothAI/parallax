# Token Image Local Mirror Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** DEX/CEX token images must be mirrored, verified, persisted, and served from this service; public API and frontend must never expose or render provider image URLs such as `https://gmgn.ai/external-res/...`.

**Architecture:** Introduce `token_image_assets` as the only product-facing image asset read model, backed by files under `settings.app_home/cache/token-images`. A new `token_image_mirror` asset-market worker mirrors candidate provider URLs from persisted profile/evidence facts, and `token_profile_current.logo_url` becomes a same-origin public URL (`/api/token-images/{image_id}`) or `NULL`; provider URLs remain source/audit facts only. Delete the request-time URL proxy and frontend proxy helper completely.

**Tech Stack:** Python 3.13, FastAPI, PostgreSQL/Alembic, `curl_cffi`/HTTP client wrappers, React/Vite/TypeScript, Vitest, pytest, Docker Compose.

---

**Status**: Draft
**Date**: 2026-05-21
**Owning spec**: User-approved hard-cut request in this thread; no separate spec file.
**Worktree**: `.worktrees/token-image-local-mirror-hard-cut/`
**Branch**: `codex/token-image-local-mirror-hard-cut`

## Hard-Cut Rules

- Do not keep `/api/token-image?url=...`.
- Do not keep `web/src/shared/model/tokenImageUrl.ts`.
- Do not return `http://` or `https://` image URLs from `profile.identity.logo_url`.
- Do not add a feature flag or compatibility path for remote image rendering.
- Do not fall back to GMGN/Binance/OKX image URLs when mirroring fails; return `NULL` and let UI render the existing token mark.
- Keep provider image URLs only in source tables (`asset_profiles`, `asset_identity_evidence`, `cex_token_profiles`) and mirror audit rows.

## Pre-flight

- [ ] Confirm runtime config paths with `uv run parallax config`; report only paths and redacted booleans.
- [ ] Create worktree:
  ```bash
  git worktree add .worktrees/token-image-local-mirror-hard-cut -b codex/token-image-local-mirror-hard-cut main
  ```
- [ ] In the worktree, confirm:
  ```bash
  git branch --show-current
  git status --short
  ```
- [ ] Record baseline:
  ```bash
  uv run ruff check .
  uv run pytest tests/unit/test_token_profile_current_projection.py tests/integration/test_api_http.py
  cd web && npm run test -- --run web/tests/unit/shared/model/tokenImageUrl.test.ts
  ```

Known-failing baseline tests (none expected):

- None.

## File-level edits

### Storage / migrations

- Create `src/parallax/platform/db/alembic/versions/20260521_0078_token_image_assets.py`.
  ```sql
  CREATE TABLE IF NOT EXISTS token_image_assets (
    image_id TEXT PRIMARY KEY,
    source_url TEXT NOT NULL,
    source_url_hash TEXT NOT NULL UNIQUE,
    source_provider TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'ready', 'error', 'unsupported')),
    media_type TEXT,
    file_extension TEXT,
    content_sha256 TEXT,
    byte_size BIGINT,
    storage_path TEXT,
    public_url TEXT,
    raw_ref_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    failure_count BIGINT NOT NULL DEFAULT 0,
    last_error TEXT,
    observed_at_ms BIGINT,
    next_refresh_at_ms BIGINT NOT NULL,
    created_at_ms BIGINT NOT NULL,
    updated_at_ms BIGINT NOT NULL,
    CHECK (
      status <> 'ready'
      OR (
        media_type IN ('image/gif', 'image/jpeg', 'image/png', 'image/webp')
        AND file_extension IN ('.gif', '.jpg', '.png', '.webp')
        AND content_sha256 IS NOT NULL
        AND byte_size IS NOT NULL
        AND byte_size > 0
        AND storage_path IS NOT NULL
        AND public_url IS NOT NULL
        AND public_url LIKE '/api/token-images/%'
      )
    )
  );

  CREATE INDEX IF NOT EXISTS idx_token_image_assets_due
    ON token_image_assets(status, next_refresh_at_ms, updated_at_ms);

  CREATE INDEX IF NOT EXISTS idx_token_image_assets_ready_source
    ON token_image_assets(source_url_hash)
    WHERE status = 'ready';

  ALTER TABLE token_profile_current
    ADD COLUMN IF NOT EXISTS logo_image_id TEXT,
    ADD COLUMN IF NOT EXISTS logo_source_provider TEXT,
    ADD COLUMN IF NOT EXISTS logo_source_url_hash TEXT;

  CREATE INDEX IF NOT EXISTS idx_token_profile_current_logo_image
    ON token_profile_current(logo_image_id)
    WHERE logo_image_id IS NOT NULL;
  ```
- `image_id` is `sha256(source_url)` so `/api/token-images/{image_id}` is stable across rebuilds. `content_sha256` validates the downloaded bytes. Store only a relative cache filename in `storage_path`; the API resolves it below `settings.app_home/cache/token-images`.
- Downgrade may drop the new table and columns. This is destructive and only acceptable when rolling back to an older deployment that cannot read the hard-cut schema.

### Asset Market Domain

- Create `src/parallax/domains/asset_market/repositories/token_image_asset_repository.py`.
  - `upsert_pending_sources(rows: list[dict[str, Any]], now_ms: int, commit: bool = True) -> int`
  - `claim_due_sources(now_ms: int, limit: int) -> list[dict[str, Any]]`
  - `mark_ready(source_url: str, media_type: str, file_extension: str, content_sha256: str, byte_size: int, storage_path: str, now_ms: int, commit: bool = True) -> dict[str, Any]`
  - `mark_error(source_url: str, error: str, now_ms: int, retry_ms: int, commit: bool = True) -> None`
  - `ready_by_source_urls(source_urls: list[str]) -> dict[str, dict[str, Any]]`
  - `ready_by_image_id(image_id: str) -> dict[str, Any] | None`
- Create `src/parallax/domains/asset_market/queries/token_image_source_query.py`.
  - Select bounded candidate URLs from current/recent targets only:
    - `asset_profiles.logo_url` for `gmgn_dex_profile` and `binance_web3_profile`.
    - `asset_identity_evidence.raw_payload_json->>'i'` for exact GMGN stream evidence.
    - `asset_identity_evidence.raw_payload_json->>'tokenLogoUrl'` for exact OKX evidence.
    - `cex_token_profiles.logo_url` for current routed CEX tokens.
  - Return `source_url`, `source_provider`, `source_kind`, and `raw_ref_json`.
- Create `src/parallax/domains/asset_market/services/token_image_mirror.py`.
  - Validate URL scheme/host/path against a server-side allowlist.
  - Fetch with existing HTTP stack and browser-like headers.
  - Verify media type and magic bytes:
    - PNG: `89 50 4E 47`
    - JPEG: `FF D8 FF`
    - GIF: `GIF87a` or `GIF89a`
    - WEBP: `RIFF....WEBP`
  - Enforce `TOKEN_IMAGE_MAX_BYTES = 3 * 1024 * 1024`.
  - Write atomically under `Path(settings.app_home) / "cache" / "token-images" / f"{content_sha256}{ext}"`.
  - Mark provider/TLS/404 failures as `error` with retry backoff.
- Create `src/parallax/domains/asset_market/runtime/token_image_mirror_worker.py`.
  - First upsert source candidates from `TokenImageSourceQuery`.
  - Then mirror due rows with `TokenImageMirrorService`.
  - Return counts: `selected`, `pending_upserted`, `mirrored`, `error`, `unsupported`, `ready_existing`.
- Modify `src/parallax/domains/asset_market/runtime/token_profile_current_worker.py`.
  - Load ready image assets for all profile candidate remote URLs before projection.
  - Pass a `ready_images_by_source_url` map into the projection.
- Modify `src/parallax/domains/asset_market/services/token_profile_current_projection.py`.
  - Split metadata source selection from logo source selection.
  - Keep provider metadata priority: GMGN OpenAPI, Binance Web3, GMGN stream, OKX, Binance CEX.
  - Set `logo_url` only to `token_image_assets.public_url`.
  - Set `logo_url = None` when no mirrored image exists.
  - Populate `logo_image_id`, `logo_source_provider`, and `logo_source_url_hash`.
  - Add quality flags such as `logo_mirror_pending`, `logo_mirror_error`, or `source_without_logo`; do not use remote URLs as fallback.
- Modify `src/parallax/domains/asset_market/repositories/token_profile_current_repository.py`.
  - Include the three new logo provenance columns in insert/update/select.
- Modify `src/parallax/app/runtime/repository_session.py`.
  - Add `repos.token_image_assets`.
- Modify `src/parallax/app/runtime/worker_registry.py`.
  - Register `token_image_mirror` with an order after `asset_profile_refresh` and before `token_profile_current`.
- Modify `src/parallax/platform/config/settings.py`.
  - Add `TokenImageMirrorWorkerSettings`.
  - Add default `workers.token_image_mirror` block.
  - Add generated workers YAML default.

### API Surface

- Delete `src/parallax/app/surfaces/api/routes_token_image.py`.
- Create `src/parallax/app/surfaces/api/routes_token_images.py`.
  - Route: `GET /api/token-images/{image_id}`.
  - Accept only 64-character lowercase hex IDs.
  - Look up `token_image_assets.status = 'ready'`.
  - Resolve file path below `settings.app_home/cache/token-images`; reject missing file with 404.
  - Return `FileResponse` with `Cache-Control: public, max-age=86400` and stored `media_type`.
  - No `url` query parameter.
- Modify `src/parallax/app/surfaces/api/http.py`.
  - Remove old router include.
  - Include `routes_token_images.router`.
- Modify `src/parallax/app/surfaces/api/schemas.py` if schema docs need to state local image URL semantics.
- Modify `tests/architecture/test_project_structure.py`.
  - Replace `routes_token_image.py` with `routes_token_images.py`.

### CLI / Ops

- Modify `src/parallax/app/surfaces/cli/parser.py`.
  - Add `ops mirror-token-images --limit 500 --source-limit 5000`.
- Modify `src/parallax/app/surfaces/cli/commands/ops.py`.
  - Run `TokenImageMirrorWorker` once.
  - Emit JSON with mirror counts and no secret/provider payload values.
- Regenerate `docs/generated/cli-help.md` after implementation if this project normally updates CLI snapshots in the same PR.

### Frontend

- Delete `web/src/shared/model/tokenImageUrl.ts`.
- Delete `web/tests/unit/shared/model/tokenImageUrl.test.ts`.
- Modify:
  - `web/src/shared/model/tokenRadarCompactCase.ts`
  - `web/src/shared/ui/TokenProfileCard.tsx`
  - `web/src/features/token-case/model/buildTokenCaseViewModel.ts`
  - Any remaining imports found by `rg "tokenImageUrl|/api/token-image|external-res" web/src web/tests`.
- New frontend rule:
  - Use `profile.identity.logo_url` directly only when it starts with `/api/token-images/`.
  - Otherwise treat it as `null` and render the existing fallback mark.
- Add/update tests so no assertion expects `/api/token-image?url=...`.

### Docs

- Modify `docs/ARCHITECTURE.md`.
  - Add image mirror lane:
    ```text
    provider profile/evidence logo URL
      -> token_image_mirror
      -> token_image_assets + local file
      -> token_profile_current.logo_url (/api/token-images/{image_id})
      -> public API/frontend
    ```
- Modify `docs/CONTRACTS.md`.
  - State `profile.identity.logo_url` is `NULL` or a same-origin `/api/token-images/{image_id}` path.
  - State provider image URLs are not public contract fields.
- Modify `docs/WORKERS.md` and `docs/WORKER_FLOW.md`.
  - Add `token_image_mirror` ownership, reads, writes, interval, and catch-up semantics.
- Modify `docs/FRONTEND.md`.
  - Add rule: frontend never proxies provider image URLs and never renders external provider URLs for token logos.
- Modify `docs/SETUP.md`.
  - Add live smoke command:
    ```bash
    uv run parallax ops mirror-token-images --limit 50 --source-limit 500
    uv run parallax ops rebuild-token-profiles --limit 500
    ```

## TDD Task Breakdown

### Task 1: Storage and Repository Foundation

**Files:**
- Create: `src/parallax/platform/db/alembic/versions/20260521_0078_token_image_assets.py`
- Create: `src/parallax/domains/asset_market/repositories/token_image_asset_repository.py`
- Modify: `src/parallax/app/runtime/repository_session.py`
- Test: `tests/unit/test_postgres_schema.py`
- Test: `tests/integration/test_token_image_asset_repository.py`

- [ ] Write schema tests asserting `token_image_assets`, indexes, ready-row check constraints, and new `token_profile_current` columns exist in the migration text.
- [ ] Write repository integration tests for pending upsert idempotency, due claims, ready marking, error retry scheduling, and ready lookup by source URL/image ID.
- [ ] Implement migration and repository.
- [ ] Run:
  ```bash
  uv run pytest tests/unit/test_postgres_schema.py tests/integration/test_token_image_asset_repository.py
  ```
- [ ] Commit:
  ```bash
  git add src/parallax/platform/db/alembic/versions/20260521_0078_token_image_assets.py \
    src/parallax/domains/asset_market/repositories/token_image_asset_repository.py \
    src/parallax/app/runtime/repository_session.py \
    tests/unit/test_postgres_schema.py \
    tests/integration/test_token_image_asset_repository.py
  git commit -m "feat: add token image asset storage"
  ```

### Task 2: Mirror Source Query and Mirror Service

**Files:**
- Create: `src/parallax/domains/asset_market/queries/token_image_source_query.py`
- Create: `src/parallax/domains/asset_market/services/token_image_mirror.py`
- Test: `tests/unit/test_token_image_mirror.py`
- Test: `tests/integration/test_token_image_source_query.py`

- [ ] Write unit tests for allowed URLs, rejected hosts, magic-byte mismatch, oversized content, successful atomic file write, and provider fetch failure.
- [ ] Write integration tests proving source query reads current/recent profile/evidence/cex URLs without scanning unrelated old rows.
- [ ] Implement source query and mirror service.
- [ ] Run:
  ```bash
  uv run pytest tests/unit/test_token_image_mirror.py tests/integration/test_token_image_source_query.py
  ```
- [ ] Commit:
  ```bash
  git add src/parallax/domains/asset_market/queries/token_image_source_query.py \
    src/parallax/domains/asset_market/services/token_image_mirror.py \
    tests/unit/test_token_image_mirror.py \
    tests/integration/test_token_image_source_query.py
  git commit -m "feat: mirror token images into local assets"
  ```

### Task 3: Worker and Ops Command

**Files:**
- Create: `src/parallax/domains/asset_market/runtime/token_image_mirror_worker.py`
- Modify: `src/parallax/app/runtime/worker_registry.py`
- Modify: `src/parallax/platform/config/settings.py`
- Modify: `src/parallax/app/surfaces/cli/parser.py`
- Modify: `src/parallax/app/surfaces/cli/commands/ops.py`
- Test: `tests/unit/test_worker_runtime_contracts.py`
- Test: `tests/unit/test_worker_settings.py`
- Test: `tests/unit/test_bootstrap_worker_runtime_wiring.py`
- Test: `tests/unit/test_cli.py`

- [ ] Write worker tests proving `token_image_mirror` is canonical, ordered before `token_profile_current`, and wired into bootstrap.
- [ ] Write CLI tests for `ops mirror-token-images`.
- [ ] Implement worker, settings, registry, parser, and ops handler.
- [ ] Run:
  ```bash
  uv run pytest tests/unit/test_worker_runtime_contracts.py tests/unit/test_worker_settings.py tests/unit/test_bootstrap_worker_runtime_wiring.py tests/unit/test_cli.py
  ```
- [ ] Commit:
  ```bash
  git add src/parallax/domains/asset_market/runtime/token_image_mirror_worker.py \
    src/parallax/app/runtime/worker_registry.py \
    src/parallax/platform/config/settings.py \
    src/parallax/app/surfaces/cli/parser.py \
    src/parallax/app/surfaces/cli/commands/ops.py \
    tests/unit/test_worker_runtime_contracts.py \
    tests/unit/test_worker_settings.py \
    tests/unit/test_bootstrap_worker_runtime_wiring.py \
    tests/unit/test_cli.py
  git commit -m "feat: run token image mirror worker"
  ```

### Task 4: Token Profile Current Hard Cut

**Files:**
- Modify: `src/parallax/domains/asset_market/runtime/token_profile_current_worker.py`
- Modify: `src/parallax/domains/asset_market/services/token_profile_current_projection.py`
- Modify: `src/parallax/domains/asset_market/repositories/token_profile_current_repository.py`
- Modify: `src/parallax/domains/asset_market/queries/token_profile_source_query.py`
- Test: `tests/unit/test_token_profile_current_projection.py`
- Test: `tests/unit/test_token_profile_current_repository.py`
- Test: `tests/unit/test_token_profile_source_query.py`
- Test: `tests/unit/test_token_profile_read_model.py`

- [ ] Update projection tests so remote GMGN/Binance/OKX URLs never appear in output.
- [ ] Add projection tests for mirrored logo selection, mirror-pending `NULL` logo, and logo source provenance fields.
- [ ] Implement local-logo-only projection and repository persistence.
- [ ] Run:
  ```bash
  uv run pytest tests/unit/test_token_profile_current_projection.py tests/unit/test_token_profile_current_repository.py tests/unit/test_token_profile_source_query.py tests/unit/test_token_profile_read_model.py
  ```
- [ ] Commit:
  ```bash
  git add src/parallax/domains/asset_market/runtime/token_profile_current_worker.py \
    src/parallax/domains/asset_market/services/token_profile_current_projection.py \
    src/parallax/domains/asset_market/repositories/token_profile_current_repository.py \
    src/parallax/domains/asset_market/queries/token_profile_source_query.py \
    tests/unit/test_token_profile_current_projection.py \
    tests/unit/test_token_profile_current_repository.py \
    tests/unit/test_token_profile_source_query.py \
    tests/unit/test_token_profile_read_model.py
  git commit -m "feat: expose only mirrored token profile logos"
  ```

### Task 5: API Route Replacement

**Files:**
- Delete: `src/parallax/app/surfaces/api/routes_token_image.py`
- Create: `src/parallax/app/surfaces/api/routes_token_images.py`
- Modify: `src/parallax/app/surfaces/api/http.py`
- Modify: `tests/architecture/test_project_structure.py`
- Modify: `tests/integration/test_api_http.py`

- [ ] Delete old proxy tests that call `/api/token-image?url=...`.
- [ ] Add route tests proving `/api/token-images/{image_id}` serves ready local files, rejects invalid IDs, returns 404 for missing/error rows, and old `/api/token-image` is absent.
- [ ] Implement new route and remove old route include.
- [ ] Run:
  ```bash
  uv run pytest tests/integration/test_api_http.py tests/architecture/test_project_structure.py
  ```
- [ ] Commit:
  ```bash
  git add src/parallax/app/surfaces/api/http.py \
    src/parallax/app/surfaces/api/routes_token_images.py \
    tests/architecture/test_project_structure.py \
    tests/integration/test_api_http.py
  git rm src/parallax/app/surfaces/api/routes_token_image.py
  git commit -m "feat: replace token image proxy with local asset serving"
  ```

### Task 6: Frontend Hard Cut

**Files:**
- Delete: `web/src/shared/model/tokenImageUrl.ts`
- Delete: `web/tests/unit/shared/model/tokenImageUrl.test.ts`
- Modify: `web/src/shared/model/tokenRadarCompactCase.ts`
- Modify: `web/src/shared/ui/TokenProfileCard.tsx`
- Modify: `web/src/features/token-case/model/buildTokenCaseViewModel.ts`
- Modify any test files found by `rg "tokenImageUrl|/api/token-image|external-res" web/src web/tests`.

- [ ] Update frontend tests so local `/api/token-images/{image_id}` URLs render and remote `https://...` URLs render fallback marks.
- [ ] Remove all imports of `tokenImageUrl`.
- [ ] Implement direct local URL rendering with remote URL rejection.
- [ ] Run:
  ```bash
  cd web
  npm run test
  npm run typecheck
  npm run lint
  npm run build
  ```
- [ ] Commit:
  ```bash
  git add web/src web/tests
  git rm web/src/shared/model/tokenImageUrl.ts web/tests/unit/shared/model/tokenImageUrl.test.ts
  git commit -m "feat: render only local token image assets"
  ```

### Task 7: Architecture Gates and Docs

**Files:**
- Modify: `tests/architecture/test_token_profile_current_hard_cut.py`
- Modify: `tests/architecture/test_project_structure.py`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/WORKERS.md`
- Modify: `docs/WORKER_FLOW.md`
- Modify: `docs/FRONTEND.md`
- Modify: `docs/SETUP.md`
- Modify: `docs/generated/cli-help.md` if CLI snapshots are updated in this branch.

- [ ] Add architecture tests forbidding `/api/token-image`, `tokenImageUrl`, and public `profile.identity.logo_url` examples with `https://`.
- [ ] Update docs to describe the mirror lane and local-only public contract.
- [ ] Run:
  ```bash
  uv run pytest tests/architecture
  uv run parallax --help > docs/generated/cli-help.md
  git diff -- docs/generated/cli-help.md
  ```
- [ ] Commit:
  ```bash
  git add tests/architecture docs/ARCHITECTURE.md docs/CONTRACTS.md docs/WORKERS.md docs/WORKER_FLOW.md docs/FRONTEND.md docs/SETUP.md docs/generated/cli-help.md
  git commit -m "docs: document local token image hard cut"
  ```

### Task 8: End-to-End Verification and Rollout Notes

**Files:**
- Create: `docs/superpowers/plans/active/2026-05-21-token-image-local-mirror-hard-cut/verification.md`

- [ ] Run full verification:
  ```bash
  make check-all
  ```
- [ ] Run live-data smoke after applying migration in the deployment environment:
  ```bash
  uv run parallax config
  uv run parallax ops mirror-token-images --limit 50 --source-limit 500
  uv run parallax ops rebuild-token-profiles --limit 500
  curl -s 'http://127.0.0.1:8765/api/token-radar?window=1h&scope=all&limit=20' | jq '.. | objects | select(has("logo_url")) | .logo_url'
  curl -i 'http://127.0.0.1:8765/api/token-image?url=https%3A%2F%2Fgmgn.ai%2Fexternal-res%2Ftoken.webp'
  ```
- [ ] Expected smoke evidence:
  - `config_path` and `workers_config_path` point at `~/.parallax/`.
  - `profile.identity.logo_url` values are `null` or `/api/token-images/{image_id}`.
  - No token radar API response contains `https://gmgn.ai/external-res/`.
  - Old `/api/token-image?url=...` returns 404.
- [ ] Record full outputs in verification artefact.
- [ ] Commit:
  ```bash
  git add docs/superpowers/plans/active/2026-05-21-token-image-local-mirror-hard-cut/verification.md
  git commit -m "test: verify token image local mirror hard cut"
  ```

## PR Breakdown

1. **PR 1 — image asset storage + mirror worker**: Tasks 1-3. Mergeable behind no public surface change, but worker can start filling `token_image_assets`.
2. **PR 2 — profile/API/frontend hard cut**: Tasks 4-6. Requires PR 1; removes old proxy and remote frontend rendering.
3. **PR 3 — docs, gates, rollout verification**: Tasks 7-8. Can be squashed with PR 2 if release pressure is high.

For a strict hard cut, land all PRs together in one release train and deploy after the migration is applied.

## Rollout Order

1. Build and deploy image containing migration and new worker.
2. Apply migration:
   ```bash
   uv run parallax db migrate
   ```
3. Run mirror warmup:
   ```bash
   uv run parallax ops mirror-token-images --limit 500 --source-limit 5000
   ```
4. Rebuild token profiles so `token_profile_current.logo_url` points at local assets:
   ```bash
   uv run parallax ops rebuild-token-profiles --limit 5000
   ```
5. Restart app workers or wait one worker interval.
6. Verify public API:
   ```sql
   SELECT count(*)
   FROM token_profile_current
   WHERE logo_url LIKE 'http://%' OR logo_url LIKE 'https://%';
   ```
   Expected: `0`.
7. Verify browser UI shows either local images or fallback marks, with no network requests to `gmgn.ai/external-res`.

## Rollback

- There is no compatibility fallback by design.
- Code rollback before migration: deploy the previous image.
- Code rollback after migration: deploy the previous image only after confirming it does not require deleted `/api/token-image` behaviour from the new frontend bundle.
- Schema rollback is destructive:
  ```sql
  DROP TABLE token_image_assets;
  ALTER TABLE token_profile_current
    DROP COLUMN logo_image_id,
    DROP COLUMN logo_source_provider,
    DROP COLUMN logo_source_url_hash;
  ```
- If local image serving is broken after deploy, safest compensating action is to keep the new schema, pause `token_image_mirror`, set affected `token_profile_current.logo_url = NULL`, rebuild profiles, and let UI render fallback marks while fixing the mirror service.

## Acceptance Test Commands

- AC1 storage exists:
  ```bash
  uv run pytest tests/unit/test_postgres_schema.py tests/integration/test_token_image_asset_repository.py
  ```
- AC2 mirror works without live network:
  ```bash
  uv run pytest tests/unit/test_token_image_mirror.py tests/integration/test_token_image_source_query.py
  ```
- AC3 worker and CLI are wired:
  ```bash
  uv run pytest tests/unit/test_worker_runtime_contracts.py tests/unit/test_worker_settings.py tests/unit/test_bootstrap_worker_runtime_wiring.py tests/unit/test_cli.py
  ```
- AC4 public API serves local assets only:
  ```bash
  uv run pytest tests/integration/test_api_http.py
  ```
- AC5 frontend contains no proxy/remote image path:
  ```bash
  cd web
  npm run test
  npm run typecheck
  npm run lint
  npm run build
  ```
- AC6 no old compatibility symbols remain:
  ```bash
  rg "tokenImageUrl|/api/token-image|routes_token_image" src web tests
  rg "external-res" web/src web/tests
  ```
  Expected: no active runtime/frontend/test references.
- AC7 full gate:
  ```bash
  make check-all
  ```

## Verification

Create `docs/superpowers/plans/active/2026-05-21-token-image-local-mirror-hard-cut/verification.md` before declaring completion. It must include:

- Full `make check-all` output.
- Coverage section.
- Skipped tests section.
- E2E golden path section.
- Live smoke SQL/API output proving no remote logo URLs are exposed.
- Remaining risks and follow-ups.
