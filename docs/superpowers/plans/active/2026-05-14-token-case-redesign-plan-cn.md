# Token Case Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `/token/:targetType/:targetId` 和 Search Intel `token_result` 收敛到同一套 `TokenCaseService` 后端 dossier 与同一套 `TokenCasePanel` 前端 case-file 组件。

**Architecture:** 后端新增 `TokenCaseService.dossier(...)` 作为 token dossier 单一真源，`GET /api/token-case` 和 `SearchInspectService.token_result` 都调用它。前端新增 feature adapter `features/token-case`，把后端 dossier、分页 posts、route state、live market WS 更新映射成纯 `TokenCaseViewModel`，再由 `shared/ui/case-file/TokenCasePanel` 编排 9 个 narrative-first section。实现方式是 hard cut：旧 `/token` radar-top-48 查找路径和 Search token_result 的旧两栏 body 在同一个 PR 删除。

**Tech Stack:** Python 3, FastAPI, psycopg, pytest, React 19, TypeScript strict, TanStack Query, CSS Modules, Vitest/RTL, MSW, Playwright, Vite.

**Owning spec:** `docs/superpowers/specs/active/2026-05-14-token-case-redesign-cn.md`

**Visual baseline:** `docs/generated/token-case-redesign-ui-mockup.html`

**Worktree:** `.worktrees/token-case-redesign/`

**Branch:** `codex/token-case-redesign`

---

## Pre-flight

- [ ] Confirm the spec is approved for plan execution.
- [ ] Create and enter the implementation worktree:

  ```bash
  git worktree add .worktrees/token-case-redesign -b codex/token-case-redesign main
  cd .worktrees/token-case-redesign
  git branch --show-current
  ```

  Expected branch: `codex/token-case-redesign`.

- [ ] Inspect current worktree state:

  ```bash
  git worktree list
  git status --short
  ```

  Expected: the new worktree has no unrelated edits before coding.

- [ ] Run baseline backend and frontend checks:

  ```bash
  uv run ruff check .
  uv run pytest tests/unit/test_search_inspect_service.py tests/unit/test_token_target_posts_service.py tests/unit/test_token_target_social_timeline_service.py -v
  cd web && npm run lint && npm run typecheck && npm test -- --run
  ```

  Expected: all commands exit 0, or each pre-existing failure is copied into the implementation verification artefact before code changes begin.

## Current-State Analysis

### Backend

- `src/parallax/app/surfaces/api/http.py:160-189` owns `/api/search/inspect`, constructs `SearchInspectService`, then calls `_enrich_search_inspect_market_overlay(...)` at `http.py:702-710`.
- `src/parallax/app/surfaces/api/http.py:232-247` already exposes `/api/live-market`, which is the correct source for `market_live` snapshot shape.
- `src/parallax/app/surfaces/api/http.py:249-285` owns `/api/target-posts`, which remains the cursor pagination source for load-more.
- `src/parallax/domains/token_intel/read_models/search_inspect_service.py:82-132` currently builds token_result directly from timeline, posts, radar scan, profile, and agent brief. This is the duplicate path to replace.
- `src/parallax/domains/token_intel/read_models/token_target_social_timeline_service.py:17-75` already builds timeline summary, stages, buckets, authors, posts, and market overlay from `TokenTargetRepository.timeline_rows(...)`.
- `src/parallax/domains/token_intel/read_models/token_target_posts_service.py:28-88` already builds `TargetPostsData` with post quality contribution payloads and cursor semantics.
- `src/parallax/domains/token_intel/repositories/token_target_repository.py:12-158` can fetch target-scoped rows, but it has no target identity lookup that works when the target has zero rows in the current window. The new dossier service needs one.
- `src/parallax/domains/asset_market/read_models/token_profile_read_model.py:12-34` already returns `profile` blocks keyed by target.
- `src/parallax/domains/asset_market/runtime/live_price_gateway.py:174-200` already returns missing and ready live market snapshots with price, market cap, liquidity, holders, provider, and timestamps.

### Frontend

- `web/src/routes/token-target.route.tsx:1-4` renders `TokenTargetPage`; this route should become a thin export to `TokenCaseRoute`.
- `web/src/features/token-target/ui/TokenTargetPage.tsx:65-100` fetches `/api/token-radar?limit=48` and linearly scans rows for the route target. This creates the degraded path that AC8 removes.
- `web/src/features/token-target/ui/TokenTargetPage.tsx:126-209` renders "Not in current radar window" plus old shared timeline/posts components. This branch must disappear.
- `web/src/features/search/ui/SearchTokenIntelPage.tsx:39-121` renders `TokenIntelHeader`, `search-content-grid`, `SearchTimelinePanel`, `SearchTwitterResults`, `SearchAgentBrief`, and `SearchRadarPanel`. That entire token_result body is replaced by `TokenCasePanel`.
- `web/src/shared/model/tokenCase.ts:1-260` is the existing radar-card case mapper. Keep it for radar compact rows; create a separate `tokenCaseViewModel.ts` for dossier detail.
- `web/src/shared/ui/case-file/index.ts:1-22` exports existing Obsidian primitives. New TokenCase components live beside this barrel and should export from it.
- `web/src/shared/socket/IntelSocketProvider.tsx:119-120` only patches token-radar query cache on `live_market_update`. It must also patch token-case dossier query cache.
- `web/src/shared/query/queryKeys.ts:37-46` has keys for timeline and posts, but not the new token-case dossier.

### Design Corrections To Apply

1. **Scope alias.** Existing app contracts use `scope=matched` for watched-only data (`web/src/lib/types/frontend-contracts.ts:8`, `http.py:36-37`). The spec uses public URL `scope=watched`. Implement token-case route parsing so `watched` maps to internal `matched`, and make `/api/token-case` accept both `watched` and `matched` while returning the public `query.scope` value as `watched` when the incoming URL used `watched`. Do not migrate every existing endpoint in this PR.
2. **No new storage.** The plan creates no tables and no Alembic migration. The dossier is a read model composed from existing facts and runtime cache.
3. **No OHLC enrichment inside token-case.** Keep `MarketCandlesService.enrich_overlay(...)` on search inspect only if legacy topic/search code still needs it. `TokenCaseService` returns `market_live` from `LivePriceGateway.snapshot(...)` and leaves OHLC readiness as an explicit empty-market UI field.
4. **Search inspect shape consistency.** `SearchInspectData.token_result` becomes the same `TokenCaseDossier` shape returned by `/api/token-case`. The frontend updates `SearchTokenResult` to that shape and stops relying on `radar_item`.
5. **Case-file grammar, not marketing UI.** The mockup's dense dark workspace, IBM Plex Sans / JetBrains Mono pairing, small uppercase labels, thin borders, and 9-section narrative order are the visual truth. Do not introduce hero marketing patterns, nested cards, gradients, or decorative blobs.

## File Structure

### Backend Create

- `src/parallax/domains/token_intel/read_models/token_case_service.py`
- `tests/unit/test_token_case_service.py`

### Backend Modify

- `src/parallax/domains/token_intel/read_models/search_inspect_service.py`
- `src/parallax/domains/token_intel/repositories/token_target_repository.py`
- `src/parallax/app/surfaces/api/http.py`
- `src/parallax/app/surfaces/api/schemas.py`
- `tests/unit/test_search_inspect_service.py`
- `tests/integration/test_api_http.py`
- `docs/CONTRACTS.md`
- `docs/FRONTEND.md`

### Frontend Create

- `web/src/features/token-case/index.ts`
- `web/src/features/token-case/api/useTokenCase.ts`
- `web/src/features/token-case/model/buildTokenCaseViewModel.ts`
- `web/src/features/token-case/state/tokenCaseRouteState.ts`
- `web/src/features/token-case/ui/TokenCaseRoute.tsx`
- `web/src/shared/model/tokenCaseViewModel.ts`
- `web/src/shared/ui/case-file/TokenCasePanel.tsx`
- `web/src/shared/ui/case-file/TokenCasePanel.module.css`
- `web/src/shared/ui/case-file/TokenCaseHero.tsx`
- `web/src/shared/ui/case-file/TokenCaseHero.module.css`
- `web/src/shared/ui/case-file/TokenCaseMetricStrip.tsx`
- `web/src/shared/ui/case-file/TokenCaseMetricStrip.module.css`
- `web/src/shared/ui/case-file/TokenCasePropagationSummary.tsx`
- `web/src/shared/ui/case-file/TokenCasePropagationSummary.module.css`
- `web/src/shared/ui/case-file/TokenCaseTimeline.tsx`
- `web/src/shared/ui/case-file/TokenCaseTimeline.module.css`
- `web/src/shared/ui/case-file/TokenCasePostEventCard.tsx`
- `web/src/shared/ui/case-file/TokenCasePostEventCard.module.css`
- `web/src/shared/ui/case-file/TokenCaseMarketRail.tsx`
- `web/src/shared/ui/case-file/TokenCaseMarketRail.module.css`
- `web/src/shared/ui/case-file/TokenCaseBullBearRail.tsx`
- `web/src/shared/ui/case-file/TokenCaseBullBearRail.module.css`
- `web/src/shared/ui/case-file/TokenCaseAmplifiersRail.tsx`
- `web/src/shared/ui/case-file/TokenCaseAmplifiersRail.module.css`
- `web/src/shared/ui/case-file/TokenCaseDataGapsRail.tsx`
- `web/src/shared/ui/case-file/TokenCaseDataGapsRail.module.css`
- `web/tests/fixtures/tokenCaseFixture.ts`
- `web/tests/unit/features/token-case/model/buildTokenCaseViewModel.test.ts`
- `web/tests/unit/features/token-case/state/tokenCaseRouteState.test.ts`
- `web/tests/component/shared/ui/case-file/TokenCasePanel.test.tsx`
- `web/tests/component/shared/ui/case-file/TokenCaseMarketRail.test.tsx`
- `web/tests/component/shared/ui/case-file/TokenCaseBullBearRail.test.tsx`
- `web/tests/component/features/token-case/ui/TokenCaseRoute.routing.test.tsx`
- `web/tests/e2e/golden-paths/token-case-redesign.spec.ts`

### Frontend Modify

- `web/src/routes/token-target.route.tsx`
- `web/src/features/search/ui/SearchTokenIntelPage.tsx`
- `web/src/features/search/ui/SearchIntelPage.tsx`
- `web/src/features/search/state/searchRouteState.ts`
- `web/src/features/search/api/useSearchInspectQuery.ts`
- `web/src/lib/types/frontend-contracts.ts`
- `web/src/lib/types/openapi.ts`
- `web/src/lib/types/index.ts`
- `web/src/shared/query/queryKeys.ts`
- `web/src/shared/query/patchMarketUpdate.ts`
- `web/src/shared/socket/IntelSocketProvider.tsx`
- `web/src/shared/ui/case-file/index.ts`
- `web/tests/msw/scenarios.ts`
- `web/tests/e2e/support/mockApi.ts`
- `web/tests/component/features/search/ui/SearchIntelPage.routing.test.tsx`
- `web/tests/routes/token-target.route.test.tsx`
- `web/tests/routes/search.route.test.tsx`
- `web/tests/architecture/obsidianArchitectureCleanout.test.ts`

### Frontend Delete

- `web/src/features/token-target/index.ts`
- `web/src/features/token-target/api/useTokenTargetQueries.ts`
- `web/src/features/token-target/state/tokenTargetRouteState.ts`
- `web/src/features/token-target/ui/TokenTargetCaseSummary.tsx`
- `web/src/features/token-target/ui/TokenTargetPage.tsx`
- `web/src/features/token-target/ui/tokenTarget.css`
- `web/tests/component/features/token-target/ui/TokenTargetPage.routing.test.tsx`
- `web/tests/unit/features/token-target/state/tokenTargetRouteState.test.ts`
- `web/src/shared/ui/TokenSocialMarketTimeline.tsx`
- `web/src/shared/ui/TokenPostsPanel.tsx`
- `web/src/shared/ui/ScoreLedger.tsx`
- `web/tests/component/shared/ui/ScoreLedger.test.tsx`
- `web/src/features/search/ui/SearchIntelSidebar.tsx` if present in the implementation branch

### Conditional Frontend Delete After `rg`

Run this after the route refactor:

```bash
rg "SearchRadarPanel|SearchTimelinePanel|SearchTwitterResults|SearchAgentBrief|TokenIntelHeader|search-content-grid|search-primary-stack|search-insight-stack" web/src web/tests
```

Delete a file from the list below only when the command proves it has zero non-test consumers or its remaining tests are for dead UI:

- `web/src/features/search/ui/SearchRadarPanel.tsx`
- `web/src/features/search/ui/SearchTimelinePanel.tsx`
- `web/src/features/search/ui/SearchTwitterResults.tsx`
- `web/src/features/search/model/searchCase.ts`
- `web/src/features/search/model/searchRadar.ts`
- `web/tests/unit/features/search/model/searchCase.test.ts`
- `web/src/shared/ui/TokenIntelHeader.tsx`
- `web/tests/component/shared/ui/TokenIntelHeader.test.tsx`

Keep `SearchAgentBrief.tsx` when `SearchTopicCase.tsx` or `SearchAmbiguousCase.tsx` still imports it.

## Backend Contract

### Public Endpoint

```http
GET /api/token-case?target_type=Asset&target_id=asset:solana:token:FhoxjfsuStvRQKRXSuB9ZDB7WRGjqhUPxa3NztWspump&window=24h&scope=all&posts_limit=24
Authorization: Bearer <ws_token>
```

Successful response:

```json
{
  "ok": true,
  "data": {
    "target": {
      "target_type": "Asset",
      "target_id": "asset:solana:token:FhoxjfsuStvRQKRXSuB9ZDB7WRGjqhUPxa3NztWspump",
      "symbol": "HANSA",
      "chain_id": "solana",
      "address": "FhoxjfsuStvRQKRXSuB9ZDB7WRGjqhUPxa3NztWspump",
      "status": "resolved",
      "source": "registry_assets",
      "reason": "TARGET_ID"
    },
    "profile": {},
    "timeline": {},
    "posts": {},
    "agent_brief": {},
    "market_live": {}
  }
}
```

Error responses:

```json
{ "ok": false, "error": "unauthorized" }
{ "ok": false, "error": "target_not_found" }
{ "ok": false, "error": "invalid_window", "field": "window" }
{ "ok": false, "error": "invalid_scope", "field": "scope" }
{ "ok": false, "error": "invalid_target", "field": "target_type" }
```

### Service Signature

Add to `src/parallax/domains/token_intel/read_models/token_case_service.py`:

```python
class TokenCaseTargetNotFound(Exception):
    pass


class TokenCaseInvalidScope(Exception):
    pass


class TokenCaseService:
    def __init__(self, *, targets: Any, profiles: Any, live_price_gateway: Any | None) -> None:
        self.targets = targets
        self.profiles = profiles
        self.live_price_gateway = live_price_gateway

    def dossier(
        self,
        *,
        target_type: str,
        target_id: str,
        window: str,
        scope: str,
        posts_limit: int,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        target = self.targets.target_identity(target_type=target_type, target_id=target_id)
        if target is None:
            raise TokenCaseTargetNotFound(target_id)
        internal_scope, public_scope = normalize_token_case_scope(scope)
        timeline = TokenTargetSocialTimelineService(targets=self.targets).timeline(
            target_type=target_type,
            target_id=target_id,
            window=window,
            scope=internal_scope,
            limit=max(24, int(posts_limit)),
            now_ms=now_ms,
        )
        posts = TokenTargetPostsService(targets=self.targets).target_posts(
            target_type=target_type,
            target_id=target_id,
            window=window,
            scope=internal_scope,
            post_range="current_window",
            sort="recent",
            limit=int(posts_limit),
            now_ms=now_ms,
        )
        timeline["query"]["scope"] = public_scope
        posts["query"]["scope"] = public_scope
        return {
            "target": target,
            "profile": self.profiles.profile_for_target(target_type=target_type, target_id=target_id),
            "timeline": timeline,
            "posts": posts,
            "agent_brief": build_token_agent_brief(
                target=target,
                timeline=timeline,
                posts=posts,
                radar_item=None,
            ),
            "market_live": token_case_market_snapshot(
                self.live_price_gateway,
                target_type=target_type,
                target_id=target_id,
                now_ms=now_ms,
            ),
        }
```

Implementation rules:

- Call `self.targets.target_identity(target_type=target_type, target_id=target_id)` first.
- Raise `TokenCaseTargetNotFound` when identity lookup returns `None`.
- Normalize public scope with:

  ```python
  def normalize_token_case_scope(scope: str) -> tuple[str, str]:
      if scope == "all":
          return ("all", "all")
      if scope in {"matched", "watched"}:
          return ("matched", "watched")
      raise TokenCaseInvalidScope(scope)
  ```

  First tuple item is internal service scope; second item is public response scope.

- Build `timeline` through `TokenTargetSocialTimelineService.timeline(...)` with `limit=max(posts_limit, 24)` and internal scope.
- Build `posts` through `TokenTargetPostsService.target_posts(...)` with `post_range="current_window"`, `sort="recent"`, `limit=posts_limit`, and internal scope.
- Build `profile` through `TokenProfileReadModel.profile_for_target(...)`.
- Build `agent_brief` through `build_token_agent_brief(target=target, timeline=timeline, posts=posts, radar_item=None)`.
- Build `market_live` through `live_price_gateway.snapshot(...)` when gateway exists; otherwise return:

  ```python
  {
      "target_type": target_type,
      "target_id": target_id,
      "status": "unsupported",
      "price_usd": None,
      "market_cap_usd": None,
      "liquidity_usd": None,
      "holders": None,
      "observed_at_ms": None,
      "provider": None,
  }
  ```

- Patch `timeline["query"]["scope"]` and `posts["query"]["scope"]` to public scope before returning the dossier.

### Repository Signature

Add to `src/parallax/domains/token_intel/repositories/token_target_repository.py`:

Method signature: `def target_identity(self, *, target_type: str, target_id: str) -> dict[str, Any] | None`.

For `Asset`, SQL selects from `registry_assets` left joined to `asset_identity_current` and the preferred `price_feeds` row:

```sql
SELECT
  'Asset' AS target_type,
  registry_assets.asset_id AS target_id,
  COALESCE(asset_identity_current.canonical_symbol, price_feeds.base_symbol) AS symbol,
  asset_identity_current.canonical_name AS name,
  registry_assets.chain_id,
  registry_assets.address,
  registry_assets.status,
  price_feeds.pricefeed_id,
  price_feeds.provider,
  price_feeds.native_market_id,
  price_feeds.quote_symbol,
  price_feeds.feed_type
FROM registry_assets
LEFT JOIN asset_identity_current
  ON asset_identity_current.asset_id = registry_assets.asset_id
LEFT JOIN LATERAL (
  SELECT *
  FROM price_feeds
  WHERE price_feeds.subject_type = 'Asset'
    AND price_feeds.subject_id = registry_assets.asset_id
    AND price_feeds.status IN ('candidate', 'canonical')
  ORDER BY
    CASE WHEN price_feeds.status = 'canonical' THEN 0 ELSE 1 END,
    price_feeds.updated_at_ms DESC,
    price_feeds.pricefeed_id ASC
  LIMIT 1
) price_feeds ON true
WHERE registry_assets.asset_id = %s
```

For `CexToken`, SQL selects from `cex_tokens` and preferred cex feed:

```sql
SELECT
  'CexToken' AS target_type,
  cex_tokens.cex_token_id AS target_id,
  cex_tokens.base_symbol AS symbol,
  cex_tokens.status,
  price_feeds.pricefeed_id,
  price_feeds.provider,
  price_feeds.native_market_id,
  price_feeds.quote_symbol,
  price_feeds.feed_type
FROM cex_tokens
LEFT JOIN LATERAL (
  SELECT *
  FROM price_feeds
  WHERE price_feeds.subject_type = 'CexToken'
    AND price_feeds.subject_id = cex_tokens.cex_token_id
    AND price_feeds.feed_type LIKE 'cex_%'
    AND price_feeds.status IN ('candidate', 'canonical')
  ORDER BY
    CASE WHEN price_feeds.feed_type = 'cex_spot' THEN 0 WHEN price_feeds.feed_type = 'cex_swap' THEN 1 ELSE 2 END,
    CASE WHEN price_feeds.quote_symbol = 'USDT' THEN 0 WHEN price_feeds.quote_symbol = 'USD' THEN 1 WHEN price_feeds.quote_symbol = 'USDC' THEN 2 ELSE 9 END,
    price_feeds.updated_at_ms DESC,
    price_feeds.native_market_id ASC
  LIMIT 1
) price_feeds ON true
WHERE cex_tokens.cex_token_id = %s
```

Returned `target` dict fields:

```python
{
    "target_type": target_type,
    "target_id": target_id,
    "symbol": row.get("symbol"),
    "name": row.get("name"),
    "chain_id": row.get("chain_id"),
    "address": row.get("address"),
    "status": row.get("status") or "resolved",
    "source": "registry_assets" if target_type == "Asset" else "cex_tokens",
    "reason": "TARGET_ID",
    "pricefeed_id": row.get("pricefeed_id"),
    "provider": row.get("provider"),
    "native_market_id": row.get("native_market_id"),
    "quote_symbol": row.get("quote_symbol"),
    "feed_type": row.get("feed_type"),
}
```

## Frontend ViewModel Contract

Create `web/src/shared/model/tokenCaseViewModel.ts` with plain types only. No React Query imports, no fetch calls, no route imports.

```ts
export type TokenCaseScope = "all" | "watched";
export type TokenCaseSort = "catalyst" | "recent" | "watched";
export type TokenCaseTone = "neutral" | "health" | "info" | "warn" | "risk" | "agent" | "opportunity";

export type TokenCaseViewModel = {
  target: {
    targetType: "Asset" | "CexToken" | string;
    targetId: string;
    symbol: string | null;
    name: string | null;
    chainId: string | null;
    address: string | null;
    displayTitle: string;
    shortId: string;
  };
  route: {
    window: "5m" | "1h" | "4h" | "24h";
    scope: TokenCaseScope;
    searchHref: string;
  };
  hero: {
    logoUrl: string | null;
    title: string;
    subtitle: string;
    contractLabel: string | null;
    actions: Array<{ label: string; href: string; tone: TokenCaseTone }>;
  };
  metrics: Array<{ key: string; label: string; value: string; detail: string; tone: TokenCaseTone }>;
  propagation: {
    summaryZh: string;
    statusPills: Array<{ label: string; tone: TokenCaseTone }>;
    stages: Array<{
      id: string;
      phase: string;
      count: number;
      authors: number;
      leadAccount: string | null;
      readZh: string;
      tone: TokenCaseTone;
    }>;
  };
  timeline: {
    sort: TokenCaseSort;
    items: TokenCasePostEvent[];
    hasMore: boolean;
    isLoading: boolean;
    isFetchingNextPage: boolean;
    emptyLabel: string | null;
  };
  market: TokenCaseMarketView;
  bullBear: {
    stance: string;
    bull: TokenCaseThesisView;
    bear: TokenCaseThesisView;
  };
  amplifiers: Array<{ handle: string; role: string; posts: number; firstSeenLabel: string | null }>;
  dataGaps: string[];
};
```

`TokenCasePanel` receives:

```ts
type TokenCasePanelProps = {
  vm: TokenCaseViewModel;
  onWindowChange: (window: WindowKey) => void;
  onScopeChange: (scope: TokenCaseScope) => void;
  onTimelineSortChange: (sort: TokenCaseSort) => void;
  onLoadMorePosts: () => void;
};
```

## Task 1: Backend TokenCaseService And Target Identity

**Files:**
- Create: `src/parallax/domains/token_intel/read_models/token_case_service.py`
- Modify: `src/parallax/domains/token_intel/repositories/token_target_repository.py`
- Create: `tests/unit/test_token_case_service.py`

- [ ] **Step 1: Write service unit tests first**

  Add tests:

  ```python
  def test_token_case_dossier_builds_all_sections_for_resolved_asset() -> None:
      service = token_case_service_with_hansa_fixture()
      dossier = service.dossier(
          target_type="Asset",
          target_id="asset:solana:token:hansa",
          window="24h",
          scope="all",
          posts_limit=2,
          now_ms=1_777_746_300_000,
      )
      assert set(dossier) == {"target", "profile", "timeline", "posts", "agent_brief", "market_live"}

  def test_token_case_dossier_raises_not_found_for_unknown_target() -> None:
      service = token_case_service_with_hansa_fixture()
      with pytest.raises(TokenCaseTargetNotFound):
          service.dossier(
              target_type="Asset",
              target_id="asset:solana:token:missing",
              window="24h",
              scope="all",
              posts_limit=2,
              now_ms=1_777_746_300_000,
          )

  def test_token_case_accepts_watched_scope_alias() -> None:
      service = token_case_service_with_hansa_fixture()
      dossier = service.dossier(
          target_type="Asset",
          target_id="asset:solana:token:hansa",
          window="24h",
          scope="watched",
          posts_limit=2,
          now_ms=1_777_746_300_000,
      )
      assert dossier["posts"]["query"]["scope"] == "watched"

  def test_token_case_uses_missing_live_market_when_gateway_has_no_snapshot() -> None:
      service = token_case_service_with_hansa_fixture(live_price_gateway=FakeLivePriceGateway(snapshot=None))
      dossier = service.dossier(
          target_type="Asset",
          target_id="asset:solana:token:hansa",
          window="24h",
          scope="all",
          posts_limit=2,
          now_ms=1_777_746_300_000,
      )
      assert dossier["market_live"]["status"] == "missing"

  def test_token_case_limits_first_posts_page_to_posts_limit() -> None:
      service = token_case_service_with_hansa_fixture()
      dossier = service.dossier(
          target_type="Asset",
          target_id="asset:solana:token:hansa",
          window="24h",
          scope="all",
          posts_limit=1,
          now_ms=1_777_746_300_000,
      )
      assert dossier["posts"]["returned_count"] == 1
  ```

  Assertions for the first test:

  ```python
  assert dossier["target"]["target_id"] == "asset:solana:token:hansa"
  assert dossier["profile"]["status"] == "ready"
  assert dossier["timeline"]["summary"]["posts"] == 2
  assert dossier["posts"]["returned_count"] == 2
  assert dossier["agent_brief"]["schema_version"] == "search_agent_brief_v1"
  assert dossier["market_live"]["status"] in {"missing", "ready"}
  assert set(dossier) == {"target", "profile", "timeline", "posts", "agent_brief", "market_live"}
  ```

- [ ] **Step 2: Run failing tests**

  ```bash
  uv run pytest tests/unit/test_token_case_service.py -v
  ```

  Expected: FAIL because `token_case_service.py` does not exist.

- [ ] **Step 3: Implement `TokenTargetRepository.target_identity(...)`**

  Add the method using the SQL in "Repository Signature". Keep `_public_row(...)` unchanged for timeline rows.

- [ ] **Step 4: Implement `TokenCaseService`**

  Use the service signature and rules above. Do not call `AssetFlowService`; the route must work for targets that are absent from `token_radar_rows`.

- [ ] **Step 5: Run service tests**

  ```bash
  uv run pytest tests/unit/test_token_case_service.py -v
  ```

  Expected: PASS.

- [ ] **Step 6: Commit backend read model slice**

  ```bash
  git add src/parallax/domains/token_intel/read_models/token_case_service.py src/parallax/domains/token_intel/repositories/token_target_repository.py tests/unit/test_token_case_service.py
  git commit -m "feat: add token case dossier service"
  ```

## Task 2: HTTP Endpoint And Search Inspect Reuse

**Files:**
- Modify: `src/parallax/app/surfaces/api/http.py`
- Modify: `src/parallax/app/surfaces/api/schemas.py`
- Modify: `src/parallax/domains/token_intel/read_models/search_inspect_service.py`
- Modify: `tests/unit/test_search_inspect_service.py`
- Modify: `tests/integration/test_api_http.py`

- [ ] **Step 1: Add failing HTTP integration tests**

  Add to `tests/integration/test_api_http.py`:

  ```python
  def test_api_token_case_returns_dossier_for_resolved_asset(tmp_path) -> None:
      app = create_app(settings=make_settings(tmp_path), start_collector=False)
      with TestClient(app) as client:
          seed_resolved_asset_with_event(client, symbol="HANSA")
          response = client.get(
              "/api/token-case",
              params={
                  "target_type": "Asset",
                  "target_id": "asset:solana:token:hansa",
                  "window": "24h",
                  "scope": "all",
                  "posts_limit": 2,
              },
              headers={"Authorization": "Bearer secret"},
          )
      assert response.status_code == 200

  def test_api_token_case_returns_404_when_target_not_found(tmp_path) -> None:
      app = create_app(settings=make_settings(tmp_path), start_collector=False)
      with TestClient(app) as client:
          response = client.get(
              "/api/token-case",
              params={"target_type": "Asset", "target_id": "asset:solana:token:missing"},
              headers={"Authorization": "Bearer secret"},
          )
      assert response.status_code == 404
      assert response.json() == {"ok": False, "error": "target_not_found"}

  def test_api_token_case_requires_auth(tmp_path) -> None:
      app = create_app(settings=make_settings(tmp_path), start_collector=False)
      with TestClient(app) as client:
          response = client.get("/api/token-case", params={"target_type": "Asset", "target_id": "asset:x"})
      assert response.status_code == 401

  def test_api_token_case_rejects_invalid_window_and_scope(tmp_path) -> None:
      app = create_app(settings=make_settings(tmp_path), start_collector=False)
      with TestClient(app) as client:
          bad_window = client.get(
              "/api/token-case",
              params={"target_type": "Asset", "target_id": "asset:x", "window": "7d"},
              headers={"Authorization": "Bearer secret"},
          )
          bad_scope = client.get(
              "/api/token-case",
              params={"target_type": "Asset", "target_id": "asset:x", "scope": "private"},
              headers={"Authorization": "Bearer secret"},
          )
      assert bad_window.status_code == 400
      assert bad_scope.status_code == 400

  def test_api_token_case_matches_search_inspect_token_result_shape(tmp_path) -> None:
      app = create_app(settings=make_settings(tmp_path), start_collector=False)
      with TestClient(app) as client:
          seed_resolved_asset_with_event(client, symbol="HANSA")
          token_case = client.get(
              "/api/token-case",
              params={"target_type": "Asset", "target_id": "asset:solana:token:hansa", "window": "24h"},
              headers={"Authorization": "Bearer secret"},
          )
          inspect = client.get(
              "/api/search/inspect",
              params={"q": "HANSA", "window": "24h", "scope": "all"},
              headers={"Authorization": "Bearer secret"},
          )
  assert inspect.json()["data"]["token_result"] == token_case.json()["data"]
  ```

  Add the helper used above in the same test file. It should follow the existing `test_api_exposes_recent_search_and_signal_read_models` pattern:

  ```python
  def seed_resolved_asset_with_event(client: TestClient, *, symbol: str) -> None:
      event = make_token_event(
          "event-token-case-1",
          symbol=symbol,
          address="FhoxjfsuStvRQKRXSuB9ZDB7WRGjqhUPxa3NztWspump",
          text=f"${symbol} ignition FhoxjfsuStvRQKRXSuB9ZDB7WRGjqhUPxa3NztWspump",
          received_at_ms=int(time.time() * 1000),
      )
      client.app.state.service.ingest.ingest_event(event, is_watched=True)
  ```

  Required assertions:

  ```python
  assert response.status_code == 200
  body = response.json()
  assert body["ok"] is True
  assert body["data"]["target"]["target_type"] == "Asset"
  assert "market_live" in body["data"]
  assert "radar_item" not in body["data"]
  assert body["data"]["posts"]["items"][0]["post_quality"]["contributions"]
  ```

  Shape parity assertion:

  ```python
  assert inspect.json()["data"]["token_result"] == token_case.json()["data"]
  ```

- [ ] **Step 2: Run failing HTTP tests**

  ```bash
  uv run pytest tests/integration/test_api_http.py::test_api_token_case_returns_dossier_for_resolved_asset -v
  ```

  Expected: FAIL with 404 route not found.

- [ ] **Step 3: Add API schema**

  Add to `src/parallax/app/surfaces/api/schemas.py`:

  ```python
  class TokenCaseData(ApiSchema):
      target: JsonObject
      profile: JsonObject | None = None
      timeline: JsonObject
      posts: JsonObject
      agent_brief: JsonObject
      market_live: JsonObject
  ```

- [ ] **Step 4: Add `/api/token-case` route**

  In `create_api_router(...)`, add a route near `/search/inspect`:

  ```python
  @router.get("/token-case", response_model=api_schemas.ApiEnvelope[api_schemas.TokenCaseData])
  def token_case(
      request: Request,
      target_type: Annotated[str, Query()] = "",
      target_id: Annotated[str, Query()] = "",
      window: Annotated[str, Query()] = "1h",
      scope: Annotated[str, Query()] = "all",
      posts_limit: Annotated[int, Query()] = 24,
  ) -> JSONResponse:
      runtime = _authenticated_runtime(request)
      parsed_target_type = _target_type(target_type)
      if not parsed_target_type:
          raise ApiBadRequest("invalid_target", field="target_type")
      if not target_id:
          raise ApiBadRequest("invalid_target", field="target_id")
      parsed_window = _window(window)
      parsed_posts_limit = max(1, _limit(posts_limit, maximum=50))
      try:
          with runtime.repositories() as repos:
              data = TokenCaseService(
                  targets=repos.token_targets,
                  profiles=TokenProfileReadModel(asset_profiles=repos.asset_profiles),
                  live_price_gateway=getattr(runtime, "live_price_gateway", None),
              ).dossier(
                  target_type=parsed_target_type,
                  target_id=target_id,
                  window=parsed_window,
                  scope=scope,
                  posts_limit=parsed_posts_limit,
                  now_ms=_now_ms(),
              )
      except TokenCaseInvalidScope:
          raise ApiBadRequest("invalid_scope", field="scope")
      except TokenCaseTargetNotFound:
          return _json({"ok": False, "error": "target_not_found"}, status_code=404)
      return _json({"ok": True, "data": data})
  ```

  Route behavior:

  - `target_type` must be `Asset` or `CexToken`; otherwise raise `ApiBadRequest("invalid_target", field="target_type")`.
  - `target_id` must be non-empty; otherwise raise `ApiBadRequest("invalid_target", field="target_id")`.
  - `window` uses existing strict `_window(...)`.
  - `scope` uses token-case strict scope parsing. Invalid values return `{"ok": false, "error": "invalid_scope", "field": "scope"}` with status 400.
  - `posts_limit` uses `_limit(posts_limit, maximum=50)` and coerces minimum to 1 before passing to the service.
  - `TokenCaseTargetNotFound` returns `{"ok": false, "error": "target_not_found"}` with status 404.

- [ ] **Step 5: Refactor `SearchInspectService` to reuse `TokenCaseService`**

  Modify constructor:

  ```python
  def __init__(
      self,
      *,
      search_query: Any,
      token_radar: Any,
      targets: Any,
      profiles: Any,
      live_price_gateway: Any | None = None,
  ) -> None:
      self.search_query = search_query
      self.token_radar = token_radar
      self.targets = targets
      self.profiles = profiles
      self.live_price_gateway = live_price_gateway
  ```

  Replace `_token_result(...)` body with:

  ```python
  return TokenCaseService(
      targets=self.targets,
      profiles=self.profiles,
      live_price_gateway=self.live_price_gateway,
  ).dossier(
      target_type=target_type,
      target_id=target_id,
      window=window,
      scope=scope,
      posts_limit=min(max(1, int(limit)), 50),
      now_ms=now_ms,
  )
  ```

  Keep `token_radar` parameter only if other code still constructs the service with it; stop using it for token_result.

- [ ] **Step 6: Remove search inspect market overlay mutation for token-case dossiers**

  Delete or narrow `_enrich_search_inspect_market_overlay(...)` so it does not mutate the new `TokenCaseDossier` shape. Search token_result parity test must compare equal after this change.

- [ ] **Step 7: Run backend tests**

  ```bash
  uv run pytest tests/unit/test_search_inspect_service.py tests/unit/test_token_case_service.py tests/integration/test_api_http.py::test_api_token_case_returns_dossier_for_resolved_asset tests/integration/test_api_http.py::test_api_token_case_matches_search_inspect_token_result_shape -v
  ```

  Expected: PASS.

- [ ] **Step 8: Commit backend endpoint slice**

  ```bash
  git add src/parallax/app/surfaces/api/http.py src/parallax/app/surfaces/api/schemas.py src/parallax/domains/token_intel/read_models/search_inspect_service.py tests/unit/test_search_inspect_service.py tests/integration/test_api_http.py
  git commit -m "feat: expose token case dossier endpoint"
  ```

## Task 3: Frontend Types, Query Hooks, Route State, And Cache Patching

**Files:**
- Create: `web/src/features/token-case/index.ts`
- Create: `web/src/features/token-case/api/useTokenCase.ts`
- Create: `web/src/features/token-case/model/buildTokenCaseViewModel.ts`
- Create: `web/src/features/token-case/state/tokenCaseRouteState.ts`
- Create: `web/src/shared/model/tokenCaseViewModel.ts`
- Modify: `web/src/lib/types/frontend-contracts.ts`
- Modify: `web/src/lib/types/index.ts`
- Modify: `web/src/shared/query/queryKeys.ts`
- Modify: `web/src/shared/query/patchMarketUpdate.ts`
- Modify: `web/src/shared/socket/IntelSocketProvider.tsx`
- Create: `web/tests/fixtures/tokenCaseFixture.ts`
- Create: `web/tests/unit/features/token-case/state/tokenCaseRouteState.test.ts`
- Create: `web/tests/unit/features/token-case/model/buildTokenCaseViewModel.test.ts`
- Modify: `web/tests/unit/shared/query/patchMarketUpdate.test.ts`

- [ ] **Step 1: Add failing route-state tests**

  `tokenCaseRouteState.test.ts` assertions:

  ```ts
  expect(parseTokenCaseRouteState(new URLSearchParams()).scope).toBe("all");
  expect(parseTokenCaseRouteState(new URLSearchParams("scope=watched")).scope).toBe("watched");
  expect(parseTokenCaseRouteState(new URLSearchParams("scope=matched")).scope).toBe("watched");
  expect(serializeTokenCaseRouteState({ window: "24h", scope: "watched" }).toString()).toBe("window=24h&scope=watched");
  ```

- [ ] **Step 2: Add failing view-model tests**

  `buildTokenCaseViewModel.test.ts` assertions:

  ```ts
  expect(vm.hero.title).toContain("$HANSA");
  expect(vm.metrics.map((metric) => metric.key)).toEqual(["mentions", "phase", "watched", "readiness"]);
  expect(vm.propagation.stages).toHaveLength(3);
  expect(vm.timeline.items[0].quality.scoreLabel).toMatch(/PQ/);
  expect(vm.market.status).toBe("missing");
  expect(vm.bullBear.bull.title).toBe("Bull · 多头");
  expect(vm.bullBear.bear.title).toBe("Bear · 空头");
  expect(vm.dataGaps.length).toBeGreaterThan(0);
  ```

- [ ] **Step 3: Implement `TokenCaseDossier` types**

  In `frontend-contracts.ts`, define:

  ```ts
  export type TokenCaseDossier = {
    target: SearchTargetCandidate;
    profile?: TokenProfileBlock | null;
    timeline: TokenSocialTimelineData;
    posts: TokenPostsData;
    agent_brief: SearchAgentBrief;
    market_live: LiveMarketSnapshot;
  };
  ```

  Change `SearchTokenResult` to alias the same shape:

  ```ts
  export type SearchTokenResult = TokenCaseDossier;
  ```

  Keep compatibility fields out of the type unless another live route still imports them.

- [ ] **Step 4: Implement route-state parser**

  `tokenCaseRouteState.ts` exports:

  ```ts
  export type TokenCaseRouteState = {
    window: WindowKey;
    scope: TokenCaseScope;
    postSort: TokenCaseSort;
  };

  export function tokenCaseScopeToApiScope(scope: TokenCaseScope): "all" | "watched" {
    return scope;
  }
  ```

  Valid windows: `5m`, `1h`, `4h`, `24h`. Valid public scopes: `all`, `watched`, with `matched` parsed as `watched` for inbound compatibility. Valid sort values: `catalyst`, `recent`, `watched`.

- [ ] **Step 5: Add query keys**

  Add:

  ```ts
  tokenCaseRoot: () => ["token-case"] as const,
  tokenCase: (targetKey: string | null, window: WindowKey, scope: TokenCaseScope, postsLimit: number) =>
    ["token-case", targetKey, window, scope, postsLimit] as const,
  ```

- [ ] **Step 6: Implement `useTokenCase` and `useTokenCasePosts`**

  `useTokenCase(...)`:

  ```ts
  export function useTokenCase({ token, target, window, scope, postsLimit = 24 }: UseTokenCaseArgs) {
    return useQuery({
      queryKey: queryKeys.tokenCase(target ? targetRefKey(target) : null, window, scope, postsLimit),
      queryFn: () =>
        getApi<TokenCaseDossier>("/api/token-case", {
          token,
          params: {
            target_type: target?.target_type,
            target_id: target?.target_id,
            window,
            scope: tokenCaseScopeToApiScope(scope),
            posts_limit: postsLimit,
          },
        }),
      enabled: Boolean(token && target),
      staleTime: 15_000,
    });
  }
  ```

  `useTokenCasePosts(...)` uses `/api/target-posts`, seeds `initialData` from dossier first page, and only fetches cursor pages when load-more is clicked. For `postSort="watched"`, use server `sort="recent"` and client-side watched filtering in `buildTokenCaseViewModel`.

- [ ] **Step 7: Patch token-case cache on live market updates**

  Add to `patchMarketUpdate.ts`:

  ```ts
  export function patchTokenCaseLiveMarketUpdate(queryClient: QueryClient, update: LiveMarketUpdatePayload) {
    queryClient.setQueriesData<ApiResponse<TokenCaseDossier>>(
      { queryKey: queryKeys.tokenCaseRoot() },
      (response) => {
        if (!response?.data || !tokenCaseMatchesMarketUpdate(response.data, update)) return response;
        return { ...response, data: { ...response.data, market_live: update.market.decision_latest } };
      },
    );
  }
  ```

  Call both `patchTokenRadarLiveMarketUpdate(...)` and `patchTokenCaseLiveMarketUpdate(...)` in `IntelSocketProvider.tsx:119-120`.

- [ ] **Step 8: Run frontend model tests**

  ```bash
  cd web
  npm test -- --run tests/unit/features/token-case/state/tokenCaseRouteState.test.ts tests/unit/features/token-case/model/buildTokenCaseViewModel.test.ts tests/unit/shared/query/patchMarketUpdate.test.ts
  npm run typecheck
  ```

  Expected: PASS.

- [ ] **Step 9: Commit frontend adapter slice**

  ```bash
  git add web/src/features/token-case web/src/shared/model/tokenCaseViewModel.ts web/src/lib/types web/src/shared/query web/src/shared/socket/IntelSocketProvider.tsx web/tests/fixtures/tokenCaseFixture.ts web/tests/unit/features/token-case web/tests/unit/shared/query/patchMarketUpdate.test.ts
  git commit -m "feat: add token case frontend adapter"
  ```

## Task 4: Shared TokenCasePanel Components And CSS Modules

**Files:**
- Create all `web/src/shared/ui/case-file/TokenCase*.tsx`
- Create all `web/src/shared/ui/case-file/TokenCase*.module.css`
- Modify: `web/src/shared/ui/case-file/index.ts`
- Create: `web/tests/component/shared/ui/case-file/TokenCasePanel.test.tsx`
- Create: `web/tests/component/shared/ui/case-file/TokenCaseMarketRail.test.tsx`
- Create: `web/tests/component/shared/ui/case-file/TokenCaseBullBearRail.test.tsx`

- [ ] **Step 1: Add failing component tests**

  `TokenCasePanel.test.tsx` assertions:

  ```ts
  expect(screen.getByRole("region", { name: /Token case/i })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: /\$HANSA/i })).toBeInTheDocument();
  expect(screen.getByText("Propagation Summary")).toBeInTheDocument();
  expect(screen.getByText("Mention Timeline")).toBeInTheDocument();
  expect(screen.getByText("Live Market")).toBeInTheDocument();
  expect(screen.getByText("Bull · 多头")).toBeInTheDocument();
  expect(screen.getByText("Bear · 空头")).toBeInTheDocument();
  expect(screen.getByText("Key Amplifiers")).toBeInTheDocument();
  expect(screen.getByText("Data Gaps")).toBeInTheDocument();
  expect(screen.getByText(/PQ/)).toBeInTheDocument();
  expect(screen.getByText(/原文/)).toBeInTheDocument();
  ```

  `TokenCaseMarketRail.test.tsx` assertions:

  ```ts
  expect(screen.getByText("pricefeed route")).toBeInTheDocument();
  expect(screen.getByText("WS subscription")).toBeInTheDocument();
  expect(screen.getByText("OHLC")).toBeInTheDocument();
  ```

  `TokenCaseBullBearRail.test.tsx` assertions:

  ```ts
  expect(screen.getByText("尚无 bull/bear 评估")).toBeInTheDocument();
  expect(screen.getByText("Bull · 多头")).toBeInTheDocument();
  expect(screen.getByText("Bear · 空头")).toBeInTheDocument();
  ```

- [ ] **Step 2: Implement component orchestration**

  `TokenCasePanel.tsx` renders in this order:

  1. `TokenCaseHero`
  2. `TokenCaseMetricStrip`
  3. `TokenCasePropagationSummary`
  4. workspace grid with `TokenCaseTimeline` in main column
  5. side rail with `TokenCaseMarketRail`, `TokenCaseBullBearRail`, `TokenCaseAmplifiersRail`, `TokenCaseDataGapsRail`

  The root element:

  ```tsx
  <section className={styles.panel} aria-label="Token case">
  ```

- [ ] **Step 3: Implement visual grammar from mockup**

  CSS module rules:

  - Root max width: `min(1440px, 100%)`.
  - Desktop workspace: `grid-template-columns: minmax(0, 1.46fr) minmax(320px, 0.54fr)`.
  - Hero columns: `56px minmax(0, 1fr) auto`; mobile changes to single flow under `@media (max-width: 820px)`.
  - Metric strip: 4 equal columns desktop; single column mobile.
  - Propagation summary: `minmax(230px, 0.72fr) minmax(0, 1.28fr)` desktop; single column mobile.
  - Use `var(--void)`, `var(--slab)`, `var(--slab-2)`, `var(--line)`, `var(--line-soft)`, `var(--bone)`, `var(--ash)`, `var(--dim)`, `var(--health)`, `var(--info)`, `var(--risk)`, `var(--opportunity)`, and corresponding `*-soft` / `*-line` tokens.
  - Use module-scoped class names. Do not import global CSS from these components.
  - No nested cards inside cards. The side rail sections are sibling sections.
  - Button and tab text must fit at 320px viewport without horizontal scroll.

- [ ] **Step 4: Implement timeline interactions**

  `TokenCaseTimeline` toolbar has three buttons: Catalyst, Recent, Watched. It does not fetch. It calls `onTimelineSortChange`.

  `TokenCasePostEventCard` renders:

  - left desktop time gutter, removed on mobile;
  - `data-phase={item.phase}`;
  - PQ pill from `post_quality.score`;
  - pills for `ca_evidence`, `attribution`, `scanner_pattern`, and duplicate caller when present;
  - truncated title from `text_clean || text`;
  - `<details>` with original text and three contribution rows from `post_quality.contributions`.

- [ ] **Step 5: Export components**

  Add to `web/src/shared/ui/case-file/index.ts`:

  ```ts
  export { TokenCasePanel } from "./TokenCasePanel";
  export type { TokenCasePanelProps } from "./TokenCasePanel";
  ```

- [ ] **Step 6: Run component tests**

  ```bash
  cd web
  npm test -- --run tests/component/shared/ui/case-file/TokenCasePanel.test.tsx tests/component/shared/ui/case-file/TokenCaseMarketRail.test.tsx tests/component/shared/ui/case-file/TokenCaseBullBearRail.test.tsx
  npm run lint
  npm run typecheck
  ```

  Expected: PASS.

- [ ] **Step 7: Commit panel slice**

  ```bash
  git add web/src/shared/ui/case-file web/tests/component/shared/ui/case-file
  git commit -m "feat: render shared token case panel"
  ```

## Task 5: Route Integration And Old UI Deletion

**Files:**
- Create: `web/src/features/token-case/ui/TokenCaseRoute.tsx`
- Modify: `web/src/routes/token-target.route.tsx`
- Modify: `web/src/features/search/ui/SearchTokenIntelPage.tsx`
- Modify: `web/src/features/search/ui/SearchIntelPage.tsx`
- Modify: `web/src/features/search/state/searchRouteState.ts`
- Modify: `web/tests/component/features/search/ui/SearchIntelPage.routing.test.tsx`
- Create: `web/tests/component/features/token-case/ui/TokenCaseRoute.routing.test.tsx`
- Modify: `web/tests/routes/token-target.route.test.tsx`
- Modify: `web/tests/routes/search.route.test.tsx`
- Delete old files listed in "Frontend Delete"

- [ ] **Step 1: Add failing route tests**

  `TokenCaseRoute.routing.test.tsx`:

  ```ts
  expect(apiMock.getApi).toHaveBeenCalledWith(
    "/api/token-case",
    expect.objectContaining({
      params: expect.objectContaining({
        target_type: "Asset",
        target_id: expect.stringContaining("HANSA"),
        window: "24h",
        scope: "watched",
      }),
    }),
  );
  expect(screen.getByRole("region", { name: /Token case/i })).toBeInTheDocument();
  ```

  Search routing test:

  ```ts
  expect(screen.getByRole("region", { name: /Token case/i })).toBeInTheDocument();
  expect(screen.queryByText("search-content-grid")).not.toBeInTheDocument();
  expect(apiMock.getApi.mock.calls.filter(([path]) => path === "/api/token-case")).toHaveLength(0);
  ```

- [ ] **Step 2: Implement `TokenCaseRoute`**

  Responsibilities:

  - parse `useParams<{ targetType: string; targetId: string }>()`;
  - validate only `Asset` and `CexToken`;
  - parse and serialize route state with `tokenCaseRouteState.ts`;
  - call `useTokenCase`;
  - call `useTokenCasePosts` seeded by dossier posts;
  - call `useMarketSubscription([target])`;
  - build ViewModel with route state and post pages;
  - render `RemoteState.Loading`, `RemoteState.Error`, `RemoteState.Empty`, or `<TokenCasePanel />`.

- [ ] **Step 3: Replace `/token` route entry**

  `web/src/routes/token-target.route.tsx` becomes:

  ```tsx
  import { TokenCaseRoute } from "@features/token-case";

  export function TokenTargetRoute() {
    return <TokenCaseRoute />;
  }
  ```

- [ ] **Step 4: Replace Search token_result body**

  `SearchTokenIntelPage.tsx` keeps props but renders:

  ```tsx
  const vm = useMemo(
    () =>
      buildTokenCaseViewModel({
        dossier: result,
        postsPages: [result.posts],
        route: { window: routeState.window, scope: tokenCaseScopeFromSearchScope(routeState.scope), postSort },
        loading: { posts: false, fetchingNextPage: false },
      }),
    [postSort, result, routeState.scope, routeState.window],
  );

  return (
    <TokenCasePanel
      vm={vm}
      onWindowChange={(window) => onRouteChange({ window })}
      onScopeChange={(scope) => onRouteChange({ scope: scope === "watched" ? "matched" : "all" })}
      onTimelineSortChange={setPostSort}
      onLoadMorePosts={() => undefined}
    />
  );
  ```

  Search token_result must not call `/api/token-case`.

- [ ] **Step 5: Delete old token-target feature and shared old components**

  Delete files in "Frontend Delete". Then run:

  ```bash
  rg "TokenTargetPage|TokenTargetCaseSummary|TokenSocialMarketTimeline|TokenPostsPanel|ScoreLedger|useTokenTargetQueries|tokenTargetRouteState" web/src web/tests
  ```

  Expected: no matches outside `obsidianArchitectureCleanout.test.ts` forbidden-name strings.

- [ ] **Step 6: Update architecture cleanout tests**

  In `web/tests/architecture/obsidianArchitectureCleanout.test.ts`:

  - remove the old test that expects `TokenSocialMarketTimeline` to exist and contain chart scroll settings;
  - add a forbidden file existence test for the deleted files;
  - add a forbidden string test for `search-content-grid`, `search-primary-stack`, and `search-insight-stack`;
  - add a test that `routes/token-target.route.tsx` imports from `@features/token-case`.

- [ ] **Step 7: Run route and architecture tests**

  ```bash
  cd web
  npm test -- --run tests/component/features/token-case/ui/TokenCaseRoute.routing.test.tsx tests/component/features/search/ui/SearchIntelPage.routing.test.tsx tests/routes/token-target.route.test.tsx tests/routes/search.route.test.tsx tests/architecture/obsidianArchitectureCleanout.test.ts
  npm run lint
  npm run typecheck
  ```

  Expected: PASS.

- [ ] **Step 8: Commit integration and deletion slice**

  ```bash
  git add -A web/src/features/token-case web/src/routes/token-target.route.tsx web/src/features/search web/src/shared web/tests
  git commit -m "feat: hard cut token detail routes to token case panel"
  ```

## Task 6: Fixtures, MSW, E2E, Docs, And Generated Types

**Files:**
- Modify: `web/tests/msw/scenarios.ts`
- Modify: `web/tests/e2e/support/mockApi.ts`
- Create: `web/tests/e2e/golden-paths/token-case-redesign.spec.ts`
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/FRONTEND.md`
- Modify: `web/src/lib/types/openapi.ts`

- [ ] **Step 1: Add mock API token-case dossier**

  In MSW and Playwright support, add:

  ```ts
  if (path === "/api/token-case") return ok(tokenCaseFixture());
  ```

  For `/api/search/inspect`, return `token_result: tokenCaseFixture()` for token queries.

- [ ] **Step 2: Add Playwright golden path**

  `token-case-redesign.spec.ts` covers:

  ```ts
  test("token route renders token case dossier", async ({ page }) => {
    await installMockApi(page);
    await page.goto("/token/Asset/asset:solana:token:FhoxjfsuStvRQKRXSuB9ZDB7WRGjqhUPxa3NztWspump?window=24h&scope=watched");
    await expect(page.getByRole("region", { name: /Token case/i })).toBeVisible();
    await expect(page.getByText("Propagation Summary")).toBeVisible();
    await expect(page.getByText("Live Market")).toBeVisible();
  });
  ```

  Add a second test for `/search?q=HANSA` and assert it renders the same section headings without requesting `/api/token-case`.

- [ ] **Step 3: Generate OpenAPI types**

  After backend schema route exists:

  ```bash
  cd web
  npm run generate:types
  ```

  Expected: `web/src/lib/types/openapi.ts` includes `/api/token-case` and `TokenCaseData`.

- [ ] **Step 4: Update docs**

  `docs/CONTRACTS.md`:

  - add `/api/token-case` contract, auth requirement, query params, 404, invalid_scope, and dossier shape;
  - document that `scope=watched` is accepted for token-case and maps to watched-only events.

  `docs/FRONTEND.md`:

  - add `features/token-case/` to source layer map as feature-owned API/model/state/ui adapter for shared token case rendering;
  - update Token Radar drilldown note: `/token/:targetType/:targetId` loads `/api/token-case` directly and no longer depends on token-radar top rows;
  - note that Search token_result reuses `TokenCasePanel` from `@shared/ui/case-file`.

- [ ] **Step 5: Run full checks**

  ```bash
  uv run ruff check .
  uv run pytest tests/unit/test_token_case_service.py tests/unit/test_search_inspect_service.py tests/integration/test_api_http.py -v
  cd web && npm run lint
  cd web && npm run typecheck
  cd web && npm test -- --run
  cd web && npm run build
  cd web && npm run test:e2e -- token-case-redesign.spec.ts
  make check-all
  ```

  Expected: all commands exit 0.

- [ ] **Step 6: Browser QA against local app**

  Start the app according to `docs/SETUP.md`, then verify with Browser or Playwright:

  - hard-reload `/token/Asset/asset:solana:token:FhoxjfsuStvRQKRXSuB9ZDB7WRGjqhUPxa3NztWspump?window=1h&scope=all`;
  - hard-reload `/token/Asset/asset:solana:token:FhoxjfsuStvRQKRXSuB9ZDB7WRGjqhUPxa3NztWspump?window=24h&scope=watched`;
  - hard-reload `/search?q=HANSA`;
  - check desktop viewport `1440x1100` and mobile viewport `390x844`;
  - confirm no horizontal scroll at mobile width;
  - confirm Live Market dashed empty state appears when `market_live.status !== "ready"`;
  - confirm no console errors;
  - save screenshots to:

    ```text
    docs/generated/token-case-redesign-desktop.png
    docs/generated/token-case-redesign-mobile.png
    docs/generated/token-case-redesign-search.png
    ```

- [ ] **Step 7: Commit docs and QA slice**

  ```bash
  git add docs/CONTRACTS.md docs/FRONTEND.md docs/generated/token-case-redesign-*.png web/src/lib/types/openapi.ts web/tests/msw/scenarios.ts web/tests/e2e/support/mockApi.ts web/tests/e2e/golden-paths/token-case-redesign.spec.ts
  git commit -m "test: cover token case hard cut"
  ```

## PR Breakdown

One hard-cut PR, because the spec explicitly rejects a feature-flagged dual implementation.

1. **PR 1 - Token Case Redesign Hard Cut:** includes backend dossier endpoint, Search inspect reuse, TokenCase frontend adapter, TokenCasePanel, route integration, old UI deletion, tests, docs, generated types, and QA screenshots. Merge only after all acceptance commands pass.

## Rollout Order

1. Land backend endpoint and Search inspect reuse in the same branch as frontend consumers.
2. Land frontend hard cut and deletion in the same PR.
3. Run full `make check-all`.
4. Run browser QA and archive screenshots.
5. Merge PR.
6. Deploy normally. No DB migration or backfill is required.

## Rollback

No storage changes are introduced, so rollback is code-only.

1. Revert the hard-cut PR.
2. Redeploy previous image.
3. Confirm `/api/search/inspect`, `/api/token-radar`, `/api/target-posts`, and old `/token/:targetType/:targetId` route behavior are restored.
4. Leave any generated screenshots in git history; they do not affect runtime.

## Acceptance Test Commands

- **AC1 shared component:**  
  `cd web && npm test -- --run tests/component/features/token-case/ui/TokenCaseRoute.routing.test.tsx tests/component/features/search/ui/SearchIntelPage.routing.test.tsx`  
  Expected: both `/token` and Search token_result render `TokenCasePanel`.

- **AC2 dossier endpoint:**  
  `uv run pytest tests/integration/test_api_http.py::test_api_token_case_returns_dossier_for_resolved_asset tests/integration/test_api_http.py::test_api_token_case_matches_search_inspect_token_result_shape -v`  
  Expected: 200 dossier and exact Search token_result parity.

- **AC3 narrative-first:**  
  `cd web && npm test -- --run tests/component/shared/ui/case-file/TokenCasePanel.test.tsx`  
  Expected: Propagation Summary appears before Mention Timeline and Live Market in DOM order.

- **AC4 missing market state:**  
  `cd web && npm test -- --run tests/component/shared/ui/case-file/TokenCaseMarketRail.test.tsx`  
  Expected: dashed empty-market content includes pricefeed route, WS subscription, and OHLC labels.

- **AC5 deletion:**  
  `cd web && npm test -- --run tests/architecture/obsidianArchitectureCleanout.test.ts`  
  Expected: forbidden legacy file names and old layout selectors are absent.

- **AC6 visual alignment:**  
  `cd web && npm run test:e2e -- token-case-redesign.spec.ts` plus screenshot comparison against `docs/generated/token-case-redesign-ui-mockup.html`.  
  Expected: same section order, dense case-file spacing, Obsidian token colors, IBM Plex Sans / JetBrains Mono rendering.

- **AC7 mobile:**  
  Playwright `token-case-redesign.spec.ts` mobile viewport test.  
  Expected: no horizontal scroll, all 9 sections visible.

- **AC8 not in Radar:**  
  `cd web && npm test -- --run tests/component/features/token-case/ui/TokenCaseRoute.routing.test.tsx`  
  Expected: route requests `/api/token-case`, never `/api/token-radar`, and does not render "Not in current radar window".

- **AC9 tests green:**  
  `make check-all`  
  Expected: exit 0.

- **AC10 browser QA:**  
  Manual Browser or Playwright run on three URLs listed in Task 6 Step 6.  
  Expected: TokenCasePanel renders, console has no errors, market placeholder appears for non-ready market.

## Verification Artefact

Before marking implementation complete, create:

```text
docs/superpowers/plans/active/2026-05-14-token-case-redesign-verification-cn.md
```

It must include:

- full output of `make check-all`;
- `Coverage`;
- `Skipped tests`;
- `E2E golden path`;
- `Other commands run`;
- browser screenshots paths;
- remaining risks and follow-ups.
