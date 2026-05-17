# Token Profile Facts Read Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** persist GMGN exact-token profile facts for resolved DEX assets and expose the same official links/profile block in Token Radar, Search Inspect, and the selected-token drawer.

**Architecture:** `asset_market` owns GMGN profile provider calls, refresh selection, persistence, and profile fact status. Token Radar/Search read models consume a provider-free `TokenProfileReadModel`, and the frontend renders one shared `TokenProfileCard`. No API handler, projection, or React component calls GMGN.

**Tech Stack:** Python 3.13, PostgreSQL/Alembic, psycopg JSONB, existing GMGN OpenAPI provider, FastAPI, React 19, TypeScript, Vitest, `uv run pytest`, `npm run build`, `make check-all`.

---

## Status

**Status**: Superseded
**Date**: 2026-05-13
**Owning spec**: `docs/superpowers/specs/active/2026-05-13-token-profile-facts-read-model-cn.md`
**Worktree**: `.worktrees/token-profile-facts-read-model/`
**Branch**: `codex/token-profile-facts-read-model`

## Pre-flight

- [ ] Verify the main checkout is not used for code edits:
  ```bash
  git worktree list
  git status --short
  git branch --show-current
  ```
  Expected: current checkout may be dirty, but implementation happens in `.worktrees/token-profile-facts-read-model/`.

- [ ] Create isolated worktree:
  ```bash
  git worktree add .worktrees/token-profile-facts-read-model -b codex/token-profile-facts-read-model main
  cd .worktrees/token-profile-facts-read-model
  ```
  Expected: new branch `codex/token-profile-facts-read-model`.

- [ ] Record baseline checks in the worktree:
  ```bash
  uv run ruff check src tests
  uv run pytest tests/unit/test_gmgn_openapi_client.py tests/unit/test_search_inspect_service.py tests/unit/test_token_radar_repository.py -q
  cd web && npm run typecheck && cd ..
  ```
  Expected: pass, or record any unrelated baseline failures before editing.

Known process note:

- User explicitly asked to write spec and plan together after approving the architecture. This plan treats the spec lane as approved and does not implement code until the user chooses an execution mode.
- Superseded on 2026-05-17 by
  `docs/superpowers/plans/active/2026-05-17-token-profile-current-facts-hard-cut-plan-cn.md`.
  Do not implement the GMGN-only public read model from this plan.

## File-Level Edits

### Storage / migrations

- Create `src/gmgn_twitter_intel/platform/db/alembic/versions/20260513_0035_asset_profiles.py`.
- Down revision: `20260512_0034`.
- Add table and indexes:

```sql
CREATE TABLE IF NOT EXISTS asset_profiles (
  asset_id TEXT NOT NULL REFERENCES registry_assets(asset_id) ON DELETE CASCADE,
  provider TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('ready', 'missing', 'unsupported', 'error')),
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
  raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  observed_at_ms BIGINT,
  next_refresh_at_ms BIGINT NOT NULL,
  last_error TEXT,
  created_at_ms BIGINT NOT NULL,
  updated_at_ms BIGINT NOT NULL,
  PRIMARY KEY (asset_id, provider)
);

CREATE INDEX IF NOT EXISTS idx_asset_profiles_due
  ON asset_profiles(provider, next_refresh_at_ms, status);

CREATE INDEX IF NOT EXISTS idx_asset_profiles_status
  ON asset_profiles(status, updated_at_ms DESC);
```

### `src/gmgn_twitter_intel/domains/asset_market/repositories/asset_profile_repository.py`

- Create repository with one clear responsibility: persist and read current asset profile facts.
- Constants:

```python
GMGN_DEX_PROFILE_PROVIDER = "gmgn_dex_profile"
READY_REFRESH_MS = 6 * 60 * 60 * 1000
MISSING_REFRESH_MS = 15 * 60 * 1000
ERROR_REFRESH_MS = 15 * 60 * 1000
```

- Add methods:

```python
class AssetProfileRepository:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def upsert_ready_profile(
        self,
        *,
        asset_id: str,
        provider: str,
        symbol: str | None,
        name: str | None,
        logo_url: str | None,
        banner_url: str | None,
        website_url: str | None,
        twitter_username: str | None,
        twitter_url: str | None,
        telegram_url: str | None,
        gmgn_url: str | None,
        geckoterminal_url: str | None,
        description: str | None,
        raw_payload: dict[str, Any],
        observed_at_ms: int,
        next_refresh_at_ms: int,
        commit: bool = True,
    ) -> None:
        """Insert or replace a ready profile row."""

    def upsert_status(
        self,
        *,
        asset_id: str,
        provider: str,
        status: str,
        observed_at_ms: int | None,
        next_refresh_at_ms: int,
        last_error: str | None,
        raw_payload: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> None:
        """Insert or replace a non-ready profile row."""

    def profiles_for_asset_ids(
        self,
        asset_ids: list[str],
        *,
        provider: str = GMGN_DEX_PROFILE_PROVIDER,
    ) -> dict[str, dict[str, Any]]:
        """Return rows keyed by asset_id."""
```

- Use `psycopg.types.json.Jsonb` for raw payload.
- Normalize empty strings to `None` before writing.

### `src/gmgn_twitter_intel/domains/asset_market/queries/pending_asset_profile_query.py`

- Create query class selecting recent resolved DEX assets that have no profile row or are due for refresh.
- Mirror `PendingAnchorPriceQuery` style and resolver policy constant.
- Use `token_intent_resolutions` and `registry_assets`; do not read `token_radar_rows`.

```python
class PendingAssetProfileQuery:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def pending_rows(
        self,
        *,
        provider: str,
        now_ms: int,
        limit: int,
        hot_lookback_ms: int = 24 * 60 * 60 * 1000,
    ) -> list[dict[str, Any]]:
        """Return due resolved DEX assets ordered by recent event activity."""
```

- SQL shape:

```sql
SELECT DISTINCT ON (tir.target_id)
  tir.target_id AS asset_id,
  registry_assets.chain_id,
  registry_assets.address,
  asset_identity_current.canonical_symbol AS symbol,
  events.received_at_ms AS latest_event_received_at_ms,
  asset_profiles.status AS profile_status,
  asset_profiles.next_refresh_at_ms
FROM token_intent_resolutions tir
JOIN events ON events.event_id = tir.event_id
JOIN registry_assets
  ON tir.target_type = 'Asset'
 AND registry_assets.asset_id = tir.target_id
LEFT JOIN asset_identity_current
  ON asset_identity_current.asset_id = tir.target_id
LEFT JOIN asset_profiles
  ON asset_profiles.asset_id = tir.target_id
 AND asset_profiles.provider = %s
WHERE tir.is_current = true
  AND tir.resolver_policy_version = %s
  AND tir.target_type = 'Asset'
  AND tir.target_id IS NOT NULL
  AND registry_assets.chain_id IS NOT NULL
  AND registry_assets.address IS NOT NULL
  AND events.received_at_ms >= %s
  AND (
    asset_profiles.asset_id IS NULL
    OR asset_profiles.next_refresh_at_ms <= %s
  )
ORDER BY tir.target_id, events.received_at_ms DESC
LIMIT %s;
```

### `src/gmgn_twitter_intel/domains/asset_market/services/asset_profile_refresh.py`

- Create pure service function so worker and CLI share one path.

```python
def refresh_asset_profiles_once(
    *,
    repos: Any,
    dex_profile_market: Any,
    now_ms: int,
    limit: int = 50,
) -> dict[str, Any]:
    """Refresh due asset profiles and return per-status counts."""
```

- Behavior:
  - Return skipped result if `dex_profile_market is None`.
  - Select due rows with `PendingAssetProfileQuery`.
  - For each row, call `dex_profile_market.token_profile(chain_id=row["chain_id"], address=row["address"])`.
  - If provider returns profile, write `ready` with `next_refresh_at_ms = now_ms + READY_REFRESH_MS`.
  - If provider returns `None`, write `missing` with `next_refresh_at_ms = now_ms + MISSING_REFRESH_MS`.
  - If provider raises, write `error` with `last_error = str(exc)[:500]` and `next_refresh_at_ms = now_ms + ERROR_REFRESH_MS`.
  - Continue after per-asset errors.
  - Commit per asset or at the end of each loop; do not leave partial uncommitted transactions across provider calls.

- Result shape:

```python
{
    "provider": "gmgn_dex_profile",
    "selected": 0,
    "ready": 0,
    "missing": 0,
    "error": 0,
    "skipped": 0,
    "started_at_ms": now_ms,
    "finished_at_ms": finished_at_ms,
}
```

### `src/gmgn_twitter_intel/domains/asset_market/runtime/asset_profile_refresh_worker.py`

- Create async worker following `AnchorPriceWorker` style.

```python
class AssetProfileRefreshWorker:
    def __init__(
        self,
        *,
        repository_session: Callable[[], AbstractContextManager[Any]],
        dex_profile_market: Any = None,
        interval_seconds: float = 60.0,
        limit: int = 50,
    ) -> None:
        """Create a periodic profile refresh worker."""

    async def run(self) -> None:
        """Run until stopped."""

    def run_once(self, *, now_ms: int | None = None) -> dict[str, Any]:
        """Run one refresh loop."""

    def stop(self) -> None:
        """Request shutdown."""

    def close(self) -> None:
        """Close the configured provider when needed."""
```

- Store `last_started_at_ms`, `last_run_at_ms`, `last_result`, `last_error`.
- Close only the provider object it owns if it exposes `close`.

### `src/gmgn_twitter_intel/app/runtime/repository_session.py`

- Import and add `AssetProfileRepository`.
- Add `asset_profiles: AssetProfileRepository` to `RepositorySession`.
- Instantiate `asset_profiles=AssetProfileRepository(conn)` in `repositories_for_connection`.

### `src/gmgn_twitter_intel/domains/asset_market/interfaces.py`

- Export `AssetProfileRepository`.

### `src/gmgn_twitter_intel/domains/asset_market/read_models/token_profile_read_model.py`

- Create provider-free read model.

```python
class TokenProfileReadModel:
    def __init__(self, *, asset_profiles: Any) -> None:
        self.asset_profiles = asset_profiles

    def profile_for_target(self, *, target_type: str | None, target_id: str | None) -> dict[str, Any] | None:
        """Return one public profile block for a target."""

    def profiles_for_targets(self, targets: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any] | None]:
        """Return public profile blocks keyed by (target_type, target_id)."""
```

- Public behavior:
  - `target_type != "Asset"` or empty `target_id`: return `None`.
  - no persisted row: return `pending` block with provider `gmgn_dex_profile`.
  - `status = ready`: return identity, links, source, observed time.
  - `status = missing`: return `missing` block with source and observed time.
  - `status = error`: return `error` block with source and `last_error`.

- URL normalization helpers:

```python
def _twitter_url(username_or_url: str | None) -> str | None:
    value = _clean(username_or_url)
    if not value:
        return None
    if value.startswith(("http://", "https://")):
        return value
    handle = value.lstrip("@").strip("/")
    return f"https://x.com/{handle}" if handle else None
```

### `src/gmgn_twitter_intel/domains/token_intel/read_models/asset_flow_service.py`

- Hard-cut constructor:

```python
class AssetFlowService:
    def __init__(self, *, token_radar: Any, profiles: Any, live_market_gateway: Any | None = None) -> None:
        self.token_radar = token_radar
        self.profiles = profiles
        self.live_market_gateway = live_market_gateway
```

- After `_public_row` and live overlay, hydrate profile blocks in one batch:

```python
public_rows = [
    _overlay_live_market(_public_row(row), gateway=self.live_market_gateway, now_ms=now_ms)
    for row in rows
]
profiles = self.profiles.profiles_for_targets([row.get("target") or {} for row in public_rows])
for row in public_rows:
    target = _mapping(row.get("target"))
    key = (str(target.get("target_type") or ""), str(target.get("target_id") or ""))
    if key in profiles:
        row["profile"] = profiles[key]
```

- Do not read/write `factor_snapshot_json` for profile.

### `src/gmgn_twitter_intel/domains/token_intel/read_models/search_inspect_service.py`

- Hard-cut constructor:

```python
class SearchInspectService:
    def __init__(self, *, search_query: Any, token_radar: Any, targets: Any, profiles: Any) -> None:
        self.search_query = search_query
        self.token_radar = token_radar
        self.targets = targets
        self.profiles = profiles
```

- Build `profile` from selected target:

```python
profile = self.profiles.profile_for_target(
    target_type=target_type,
    target_id=target_id,
)
```

- Pass `profiles=self.profiles` into nested `AssetFlowService`.
- Add `"profile": profile` to `token_result`.

### `src/gmgn_twitter_intel/app/surfaces/api/http.py`

- Import `TokenProfileReadModel`.
- Construct one read model per repository session:

```python
profiles = TokenProfileReadModel(asset_profiles=repos.asset_profiles)
```

- Pass `profiles=profiles` into `AssetFlowService` and `SearchInspectService`.

### `src/gmgn_twitter_intel/app/surfaces/cli/main.py`

- Import `TokenProfileReadModel`, `refresh_asset_profiles_once`, and worker/service constants.
- Update `asset-flow` command to pass `profiles`.
- Add ops command:

```text
gmgn-twitter-intel ops refresh-asset-profiles --limit 50
```

- Handler behavior:

```python
result = refresh_asset_profiles_once(
    repos=repos,
    dex_profile_market=providers.asset_market.dex_profile_market,
    now_ms=_now_ms(),
    limit=args.limit,
)
_emit({"ok": True, "data": result}, stdout)
```

### `src/gmgn_twitter_intel/app/runtime/app.py`

- Import `AssetProfileRefreshWorker` and `TokenProfileReadModel`.
- Add fields to `CliRuntime`:

```python
asset_profile_refresh_worker: AssetProfileRefreshWorker | None = None
asset_profile_refresh_task: asyncio.Task | None = None
```

- Wire worker when collector is started and `providers.asset_market.dex_profile_market` exists:

```python
runtime.asset_profile_refresh_worker = AssetProfileRefreshWorker(
    dex_profile_market=providers.asset_market.dex_profile_market,
    repository_session=lambda: repository_session(db_pool),
    interval_seconds=60.0,
    limit=50,
)
```

- Start/stop/close task in the same lifecycle sections as anchor/resolution workers.
- Pass profile read model into `_notification_rule_engine` `AssetFlowService`.
- Add health payload:

```python
"asset_profile_refresh": {
    "worker_running": _task_running(runtime.asset_profile_refresh_task),
    "last_started_at_ms": runtime.asset_profile_refresh_worker.last_started_at_ms
    if runtime.asset_profile_refresh_worker
    else None,
    "last_run_at_ms": runtime.asset_profile_refresh_worker.last_run_at_ms
    if runtime.asset_profile_refresh_worker
    else None,
    "last_result": runtime.asset_profile_refresh_worker.last_result
    if runtime.asset_profile_refresh_worker
    else None,
    "last_error": runtime.asset_profile_refresh_worker.last_error
    if runtime.asset_profile_refresh_worker
    else None,
}
```

### `web/src/api/types.ts`

- Add shared type:

```ts
export type TokenProfileBlock = {
  status: "ready" | "pending" | "missing" | "unsupported" | "error" | string;
  provider?: string | null;
  observed_at_ms?: number | null;
  identity?: {
    symbol?: string | null;
    name?: string | null;
    logo_url?: string | null;
    banner_url?: string | null;
    description?: string | null;
  } | null;
  links?: {
    website_url?: string | null;
    twitter_url?: string | null;
    twitter_username?: string | null;
    telegram_url?: string | null;
    gmgn_url?: string | null;
    geckoterminal_url?: string | null;
  } | null;
  source?: {
    provider?: string | null;
    raw_available?: boolean;
    last_error?: string | null;
  } | null;
};
```

- Add `profile?: TokenProfileBlock | null` to `AssetFlowRow`, `SearchTokenResult`, and `TokenFlowItem`.

### `web/src/lib/tokenRadar.ts`

- Preserve API profile block when mapping rows:

```ts
return {
  identity: tokenIdentity,
  profile: row.profile ?? null,
  market: tokenMarket,
  flow: tokenFlow,
  social_heat: socialHeat,
  discussion_quality: discussionQuality,
  propagation,
  tradeability,
  timing,
  opportunity,
  watch,
};
```

- No sorting/scoring behavior changes.

### `web/src/components/TokenProfileCard.tsx`

- Create shared presentational component.
- Props:

```ts
type TokenProfileCardProps = {
  profile?: TokenProfileBlock | null;
  compact?: boolean;
};
```

- Render rules:
  - `null` or `unsupported`: compact muted state or no-op depending caller.
  - `pending`: "profile pending".
  - `missing`: "profile not found".
  - `error`: "profile refresh error".
  - `ready`: logo, name/symbol, description, and icon/text links for Website, X, Telegram, GMGN, GeckoTerminal.
- Use `ExternalLink`, `Globe`, `MessageCircle`, and `Search` icons from `lucide-react` where appropriate.
- Do not parse raw provider payload.

### `web/src/components/TokenDetailDrawer.tsx`

- Import `TokenProfileCard`.
- Render profile card below `DetailDrawerHeader` and above tabs:

```tsx
<TokenProfileCard profile={token.profile} compact />
```

- Do not add a new tab. Profile should be visible before users choose Timeline/Posts/Score.

### `web/src/components/SearchIntelPage.tsx`

- Import `TokenProfileCard`.
- Render profile card at the top of `search-insight-stack`, above `SearchAgentBrief`:

```tsx
<TokenProfileCard profile={result.profile} />
<SearchAgentBrief brief={result.agent_brief} />
```

### `web/src/styles.css`

- Add styles for `.token-profile-card`, `.token-profile-head`, `.token-profile-logo`, `.token-profile-links`, `.token-profile-link`, `.token-profile-description`, `.token-profile-state`.
- Keep dimensions stable so missing/pending/ready states do not resize the drawer unpredictably.

### Tests

- Python:
  - `tests/unit/test_asset_profile_repository.py`
  - `tests/unit/test_pending_asset_profile_query.py`
  - `tests/unit/test_asset_profile_refresh.py`
  - `tests/unit/test_token_profile_read_model.py`
  - update `tests/unit/test_search_inspect_service.py`
  - update `tests/unit/test_asset_flow_service.py` if present, otherwise add it
  - update API/runtime construction tests that instantiate `AssetFlowService` or `SearchInspectService`
- Frontend:
  - `web/src/components/TokenProfileCard.test.tsx`
  - update `web/src/lib/tokenRadar.test.ts`
  - update relevant `web/src/App.test.tsx` drawer/search tests

## TDD Tasks

### Task 1: Storage and Repository

**Files:**
- Create: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260513_0035_asset_profiles.py`
- Create: `src/gmgn_twitter_intel/domains/asset_market/repositories/asset_profile_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/interfaces.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/repository_session.py`
- Test: `tests/unit/test_asset_profile_repository.py`

- [ ] **Step 1: Write failing repository tests**

```python
def test_upsert_ready_profile_round_trips_links(conn):
    repo = AssetProfileRepository(conn)
    repo.upsert_ready_profile(
        asset_id="asset:eip155:1:erc20:0xabc",
        provider=GMGN_DEX_PROFILE_PROVIDER,
        symbol="ABC",
        name="ABC Token",
        logo_url="https://img.example/abc.png",
        banner_url=None,
        website_url="https://abc.example",
        twitter_username="abc",
        twitter_url="https://x.com/abc",
        telegram_url="https://t.me/abc",
        gmgn_url="https://gmgn.ai/eth/token/0xabc",
        geckoterminal_url=None,
        description="project profile",
        raw_payload={"link": {"website": "https://abc.example"}},
        observed_at_ms=1000,
        next_refresh_at_ms=2000,
    )

    rows = repo.profiles_for_asset_ids(["asset:eip155:1:erc20:0xabc"])

    assert rows["asset:eip155:1:erc20:0xabc"]["status"] == "ready"
    assert rows["asset:eip155:1:erc20:0xabc"]["website_url"] == "https://abc.example"
    assert rows["asset:eip155:1:erc20:0xabc"]["raw_payload_json"]["link"]["website"] == "https://abc.example"
```

- [ ] **Step 2: Run test and verify failure**

Run: `uv run pytest tests/unit/test_asset_profile_repository.py -q`

Expected: FAIL because migration/repository does not exist.

- [ ] **Step 3: Implement migration and repository**

Use the SQL and signatures from File-Level Edits. Add repository to `interfaces.py` and `repository_session.py`.

- [ ] **Step 4: Run focused tests**

Run: `uv run pytest tests/unit/test_asset_profile_repository.py tests/unit/test_postgres_api_health.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/gmgn_twitter_intel/platform/db/alembic/versions/20260513_0035_asset_profiles.py \
  src/gmgn_twitter_intel/domains/asset_market/repositories/asset_profile_repository.py \
  src/gmgn_twitter_intel/domains/asset_market/interfaces.py \
  src/gmgn_twitter_intel/app/runtime/repository_session.py \
  tests/unit/test_asset_profile_repository.py
git commit -m "feat: add asset profile fact storage"
```

### Task 2: Pending Query and Profile Refresh Service

**Files:**
- Create: `src/gmgn_twitter_intel/domains/asset_market/queries/pending_asset_profile_query.py`
- Create: `src/gmgn_twitter_intel/domains/asset_market/services/asset_profile_refresh.py`
- Test: `tests/unit/test_pending_asset_profile_query.py`
- Test: `tests/unit/test_asset_profile_refresh.py`

- [ ] **Step 1: Write failing query/service tests**

```python
class FakeProfileProvider:
    def __init__(self, profile=None, error=None):
        self.profile = profile
        self.error = error
        self.calls = []

    def token_profile(self, *, chain_id: str, address: str):
        self.calls.append((chain_id, address))
        if self.error:
            raise self.error
        return self.profile


def test_refresh_asset_profiles_writes_ready_profile(repos):
    provider = FakeProfileProvider(
        profile=DexTokenProfile(
            chain_id="eip155:1",
            address="0xabc",
            symbol="ABC",
            name="ABC Token",
            logo_url="https://img.example/abc.png",
            banner_url=None,
            website="https://abc.example",
            twitter_username="abc",
            telegram="https://t.me/abc",
            gmgn_url="https://gmgn.ai/eth/token/0xabc",
            geckoterminal_url=None,
            description="project profile",
            raw={"link": {"website": "https://abc.example"}},
        )
    )

    result = refresh_asset_profiles_once(repos=repos, dex_profile_market=provider, now_ms=10_000, limit=5)

    assert result["ready"] == 1
    assert provider.calls == [("eip155:1", "0xabc")]
```

- [ ] **Step 2: Run tests and verify failure**

Run: `uv run pytest tests/unit/test_pending_asset_profile_query.py tests/unit/test_asset_profile_refresh.py -q`

Expected: FAIL because query/service do not exist.

- [ ] **Step 3: Implement query and service**

Use `PendingAnchorPriceQuery` as the shape reference. Keep provider exceptions per asset and write explicit `error` states.

- [ ] **Step 4: Run focused tests**

Run: `uv run pytest tests/unit/test_pending_asset_profile_query.py tests/unit/test_asset_profile_refresh.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/gmgn_twitter_intel/domains/asset_market/queries/pending_asset_profile_query.py \
  src/gmgn_twitter_intel/domains/asset_market/services/asset_profile_refresh.py \
  tests/unit/test_pending_asset_profile_query.py \
  tests/unit/test_asset_profile_refresh.py
git commit -m "feat: refresh resolved asset profiles"
```

### Task 3: Runtime Worker and CLI

**Files:**
- Create: `src/gmgn_twitter_intel/domains/asset_market/runtime/asset_profile_refresh_worker.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/app.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/cli/main.py`
- Test: `tests/unit/test_asset_profile_refresh_worker.py`
- Test: `tests/integration/test_api_health.py`
- Test: CLI test if existing harness supports ops commands

- [ ] **Step 1: Write failing worker and CLI tests**

```python
def test_asset_profile_refresh_worker_records_result(repository_session, fake_profile_provider):
    worker = AssetProfileRefreshWorker(
        repository_session=repository_session,
        dex_profile_market=fake_profile_provider,
        interval_seconds=60,
        limit=5,
    )

    result = worker.run_once(now_ms=10_000)

    assert worker.last_started_at_ms == 10_000
    assert worker.last_result == result
    assert "selected" in result
```

- [ ] **Step 2: Run tests and verify failure**

Run: `uv run pytest tests/unit/test_asset_profile_refresh_worker.py tests/integration/test_api_health.py -q`

Expected: FAIL because worker/health wiring does not exist.

- [ ] **Step 3: Implement worker, runtime lifecycle, and CLI command**

Wire worker only when `providers.asset_market.dex_profile_market` exists. Add start/stop/close lifecycle and health state.

- [ ] **Step 4: Run focused tests**

Run: `uv run pytest tests/unit/test_asset_profile_refresh_worker.py tests/integration/test_api_health.py tests/integration/test_cli.py -q`

Expected: PASS or skip unavailable CLI integration if the repo has no matching test harness; record exact result.

- [ ] **Step 5: Commit**

```bash
git add src/gmgn_twitter_intel/domains/asset_market/runtime/asset_profile_refresh_worker.py \
  src/gmgn_twitter_intel/app/runtime/app.py \
  src/gmgn_twitter_intel/app/surfaces/cli/main.py \
  tests/unit/test_asset_profile_refresh_worker.py \
  tests/integration/test_api_health.py \
  tests/integration/test_cli.py
git commit -m "feat: wire asset profile refresh worker"
```

### Task 4: Provider-Free Read Model and API Surfaces

**Files:**
- Create: `src/gmgn_twitter_intel/domains/asset_market/read_models/token_profile_read_model.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/read_models/asset_flow_service.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/read_models/search_inspect_service.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/http.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/cli/main.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/app.py`
- Test: `tests/unit/test_token_profile_read_model.py`
- Test: `tests/unit/test_search_inspect_service.py`
- Test: `tests/integration/test_api_http.py`

- [ ] **Step 1: Write failing read-model/API tests**

```python
def test_profile_read_model_returns_ready_block(asset_profiles):
    asset_profiles.upsert_ready_profile(
        asset_id="asset:eip155:1:erc20:0xabc",
        provider=GMGN_DEX_PROFILE_PROVIDER,
        symbol="ABC",
        name="ABC Token",
        logo_url=None,
        banner_url=None,
        website_url="https://abc.example",
        twitter_username="abc",
        twitter_url=None,
        telegram_url=None,
        gmgn_url="https://gmgn.ai/eth/token/0xabc",
        geckoterminal_url=None,
        description="project profile",
        raw_payload={"ok": True},
        observed_at_ms=1000,
        next_refresh_at_ms=2000,
    )

    model = TokenProfileReadModel(asset_profiles=asset_profiles)
    profile = model.profile_for_target(target_type="Asset", target_id="asset:eip155:1:erc20:0xabc")

    assert profile["status"] == "ready"
    assert profile["links"]["twitter_url"] == "https://x.com/abc"
    assert profile["links"]["website_url"] == "https://abc.example"
```

- [ ] **Step 2: Run tests and verify failure**

Run: `uv run pytest tests/unit/test_token_profile_read_model.py tests/unit/test_search_inspect_service.py tests/integration/test_api_http.py -q`

Expected: FAIL because constructors/contracts do not include profile.

- [ ] **Step 3: Implement read model and hard-cut constructors**

Update every `AssetFlowService` and `SearchInspectService` construction site to pass `profiles=TokenProfileReadModel(asset_profiles=repos.asset_profiles)`.

- [ ] **Step 4: Run focused tests**

Run: `uv run pytest tests/unit/test_token_profile_read_model.py tests/unit/test_search_inspect_service.py tests/integration/test_api_http.py tests/integration/test_cli.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/gmgn_twitter_intel/domains/asset_market/read_models/token_profile_read_model.py \
  src/gmgn_twitter_intel/domains/token_intel/read_models/asset_flow_service.py \
  src/gmgn_twitter_intel/domains/token_intel/read_models/search_inspect_service.py \
  src/gmgn_twitter_intel/app/surfaces/api/http.py \
  src/gmgn_twitter_intel/app/surfaces/cli/main.py \
  src/gmgn_twitter_intel/app/runtime/app.py \
  tests/unit/test_token_profile_read_model.py \
  tests/unit/test_search_inspect_service.py \
  tests/integration/test_api_http.py
git commit -m "feat: expose token profile read model"
```

### Task 5: Frontend Shared Profile Card

**Files:**
- Modify: `web/src/api/types.ts`
- Modify: `web/src/lib/tokenRadar.ts`
- Create: `web/src/components/TokenProfileCard.tsx`
- Modify: `web/src/components/TokenDetailDrawer.tsx`
- Modify: `web/src/components/SearchIntelPage.tsx`
- Modify: `web/src/styles.css`
- Test: `web/src/components/TokenProfileCard.test.tsx`
- Test: `web/src/lib/tokenRadar.test.ts`
- Test: `web/src/App.test.tsx`

- [ ] **Step 1: Write failing frontend tests**

```tsx
it("renders ready token profile links", () => {
  render(
    <TokenProfileCard
      profile={{
        status: "ready",
        provider: "gmgn_dex_profile",
        identity: { symbol: "ABC", name: "ABC Token", description: "project profile" },
        links: {
          website_url: "https://abc.example",
          twitter_url: "https://x.com/abc",
          gmgn_url: "https://gmgn.ai/eth/token/0xabc",
        },
        source: { provider: "gmgn_dex_profile", raw_available: true },
      }}
    />,
  );

  expect(screen.getByText("ABC Token")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /website/i })).toHaveAttribute("href", "https://abc.example");
  expect(screen.getByRole("link", { name: /x/i })).toHaveAttribute("href", "https://x.com/abc");
});
```

- [ ] **Step 2: Run tests and verify failure**

Run: `cd web && npm run test -- TokenProfileCard && cd ..`

Expected: FAIL because component/types do not exist.

- [ ] **Step 3: Implement types, mapping, component, drawer/search rendering, and CSS**

Add `profile: row.profile ?? null` in `tokenRadarRowToTokenItem`. Render `TokenProfileCard` under drawer header and above Search Agent Brief.

- [ ] **Step 4: Run frontend checks**

Run:

```bash
cd web
npm run test -- TokenProfileCard tokenRadar
npm run typecheck
npm run lint
npm run build
cd ..
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/api/types.ts \
  web/src/lib/tokenRadar.ts \
  web/src/components/TokenProfileCard.tsx \
  web/src/components/TokenDetailDrawer.tsx \
  web/src/components/SearchIntelPage.tsx \
  web/src/styles.css \
  web/src/components/TokenProfileCard.test.tsx \
  web/src/lib/tokenRadar.test.ts \
  web/src/App.test.tsx
git commit -m "feat: render shared token profile card"
```

### Task 6: Contract Docs, Real Data Smoke, and Full Gate

**Files:**
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md`
- Modify: `docs/generated/db-schema.md` if schema generation is part of `make check-all` or repo workflow
- Create verification note after implementation if needed

- [ ] **Step 1: Update docs**

Document:
  - `asset_profiles` ownership under `asset_market`.
  - `/api/token-radar` row `profile`.
  - `/api/search/inspect` `token_result.profile`.
  - provider-free read-model invariant.
  - narrative agent remains a future lane.

- [ ] **Step 2: Run real data one-shot where GMGN credentials exist**

Run:

```bash
uv run gmgn-twitter-intel ops refresh-asset-profiles --limit 10
uv run gmgn-twitter-intel asset-flow --window 24h --scope all --limit 10
```

Expected:
  - first command returns `ok: true` with `selected`, `ready`, `missing`, or `error` counts;
  - second command includes `profile` for resolved DEX assets, with `ready`, `pending`, `missing`, or `error`.

- [ ] **Step 3: Run API smoke if local server is available**

Run:

```bash
curl -s 'http://127.0.0.1:8000/api/token-radar?window=24h&scope=all&limit=10' | jq '.data.targets[0].profile'
curl -s 'http://127.0.0.1:8000/api/search/inspect?q=0xf280b16ef293d8e534e370794ef26bf312694126&window=24h&scope=all' | jq '.data.token_result.profile'
```

Expected:
  - both shapes use the same `TokenProfileBlock` contract;
  - no request-time provider error appears in API response.

- [ ] **Step 4: Run full verification**

Run:

```bash
uv run ruff check .
uv run pytest tests/unit/test_asset_profile_repository.py \
  tests/unit/test_pending_asset_profile_query.py \
  tests/unit/test_asset_profile_refresh.py \
  tests/unit/test_asset_profile_refresh_worker.py \
  tests/unit/test_token_profile_read_model.py \
  tests/unit/test_search_inspect_service.py \
  tests/integration/test_api_http.py \
  tests/integration/test_api_health.py -q
cd web && npm run test && npm run build && cd ..
make check-all
```

Expected:
  - focused tests pass;
  - frontend tests/build pass;
  - `make check-all` exits 0.

- [ ] **Step 5: Commit docs and verification**

```bash
git add docs/CONTRACTS.md docs/ARCHITECTURE.md \
  src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md \
  docs/generated/db-schema.md
git commit -m "docs: document token profile fact chain"
```

## PR Breakdown

Single PR is recommended.

Reason: storage, worker, API contract, and frontend card are one product-visible chain. Shipping storage without API does not solve the user problem; shipping UI without worker creates a permanent pending state.

Logical commits inside the PR:

1. `feat: add asset profile fact storage`
2. `feat: refresh resolved asset profiles`
3. `feat: wire asset profile refresh worker`
4. `feat: expose token profile read model`
5. `feat: render shared token profile card`
6. `docs: document token profile fact chain`

## Acceptance Mapping

| Spec AC | Plan tasks |
|---------|------------|
| AC1 GMGN profile provider called for due resolved assets | Task 2, Task 3 |
| AC2 Profile fields persisted with raw/freshness | Task 1, Task 2 |
| AC3 Missing profile state persisted | Task 1, Task 2 |
| AC4 Error state persisted without API failure | Task 2, Task 4 |
| AC5 `/api/token-radar` row profile | Task 4 |
| AC6 `/api/search/inspect` token profile | Task 4 |
| AC7 No provider calls from projection/API/read model | Task 2, Task 4 |
| AC8 Shared frontend card visible in drawer/search | Task 5 |
| AC9 Missing/pending UI state | Task 5 |

## Rollout Order

1. Merge migration and code.
2. Apply migration:
   ```bash
   uv run gmgn-twitter-intel db migrate
   ```
3. Run one-shot refresh:
   ```bash
   uv run gmgn-twitter-intel ops refresh-asset-profiles --limit 50
   ```
4. Rebuild/restart service so `AssetProfileRefreshWorker` runs.
5. Verify `/api/token-radar` and `/api/search/inspect` include profile blocks.
6. Verify UI selected-token drawer and Search Intel show `TokenProfileCard`.

## Rollback

- Code rollback is safe while `asset_profiles` remains in the database; old code ignores the table.
- Do not drop `asset_profiles` during emergency rollback. The table is current-state read-model data and can be refreshed.
- If bad profile rows are written, pause the worker by disabling GMGN profile provider wiring or rolling back code, then clear rows for provider:
  ```sql
  DELETE FROM asset_profiles WHERE provider = 'gmgn_dex_profile';
  ```
  Run the one-shot refresh after the fix.
- If API contract rollout causes frontend issues, revert Tasks 4 and 5 together. Do not leave frontend expecting `profile` while API lacks it.

## Verification

Before declaring implementation complete, record:

- `uv run ruff check .`
- focused Python tests listed in Task 6
- `cd web && npm run test && npm run build`
- `make check-all`
- real data result from `ops refresh-asset-profiles`
- sample `/api/token-radar` profile block
- sample `/api/search/inspect` profile block
- a browser check or screenshot showing profile card in selected-token drawer and Search Intel

If GMGN credentials are unavailable in the implementation environment, record that explicitly and use fake-provider tests plus API contract tests as the completed verification, then leave real-data verification for the credentialed environment.
