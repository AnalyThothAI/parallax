# Search V2 Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Implemented in worktree `codex/search-v2-hard-cut` from local `main` commit `1e0fa9013a1675fbac68b863f433451cc7a9f603`.

**Goal:** Replace legacy `/api/search` with target-first, lexical/trigram, cursor-paginated search over current production identity tables, with no legacy compatibility path.

**Architecture:** Add focused token-intel query modules for target resolution and search route retrieval, then add a read-model service that fuses route hits and owns cursor paging. API, CLI, and frontend switch to the new `q + cursor` contract in one hard cut; old `AssetSearchService`, old search params, old evidence FTS helpers, and old frontend result cap are removed.

**Tech Stack:** Python 3, FastAPI, psycopg/PostgreSQL, Alembic, PostgreSQL FTS, `pg_trgm`, React, TanStack Query, TypeScript, Vitest, pytest.

---

## Pre-flight

- [x] Spec exists: `docs/superpowers/specs/active/2026-05-11-search-v2-hard-cut-cn.md`.
- [x] Worktree exists at `.worktrees/search-v2-hard-cut/` and `git branch --show-current` returns `codex/search-v2-hard-cut`.
- [x] Baseline `uv run ruff check .` passed in the worktree.
- [x] Baseline backend was measured before code changes.
- [x] Baseline frontend `cd web && npm test -- --run` passed after installing local `web/node_modules`.
- [x] Existing untracked main-checkout file `docs/superpowers/plans/active/2026-05-11-social-heat-propagation-hard-cut-plan-cn.md` was not edited from the search worktree.

Known-failing baseline tests:

- `uv run pytest` on latest main had one pre-existing generated-doc failure: `tests/integration/test_docs_generated.py::test_make_docs_generated_clean_diff`. `make docs-generated` changed `docs/generated/db-schema.md` by flipping `factor_version` from `token_factor_snapshot_v3_social_attention` to `token_factor_snapshot_v1`. This search branch does not include that unrelated db-schema drift.

## Latest Main Reconciliation

- [x] Latest local `main` was newer than `origin/main`; implementation branched from local `main` commit `1e0fa9013a1675fbac68b863f433451cc7a9f603`.
- [x] Original plan migration number was stale. Latest main already had `20260511_0030`, and merge-time main also had `20260512_0031_prune_legacy_pulse_factor_contracts.py`; search v2 migration is therefore `20260512_0032_search_v2_hard_cut.py` with `down_revision = "20260512_0031"`.
- [x] Registry chain ids on latest main are normalized. CA search maps user-facing aliases (`eth`, `base`, `bsc`, `sol`, `ton`) to registry ids (`eip155:1`, `eip155:8453`, `eip155:56`, `solana`, `ton`).
- [x] Core plan remained current: latest main still had legacy `/api/search` params, `AssetSearchService`, old evidence FTS helpers, no cursor pagination, and frontend result truncation.

## File-level Edits

### `src/gmgn_twitter_intel/domains/token_intel/read_models/asset_search_service.py`

- Delete this file after the new service is wired and tests are migrated.
- Runtime must no longer import `AssetSearchService`.
- The delete is intentional hard cut; do not keep an adapter class named `AssetSearchService`.

### `src/gmgn_twitter_intel/domains/token_intel/read_models/search_service.py`

- Create this file. It owns parse/orchestration/fusion/page shaping only. It must not contain raw SQL.
- Public dataclasses and signatures:
  ```python
  from __future__ import annotations

  from dataclasses import dataclass, field
  from typing import Any

  @dataclass(frozen=True, slots=True)
  class SearchPage:
      ok: bool
      query: dict[str, Any]
      items: list[dict[str, Any]] = field(default_factory=list)
      target_candidates: list[dict[str, Any]] = field(default_factory=list)
      page: dict[str, Any] = field(default_factory=dict)
      error: str | None = None

  class SearchCursorError(Exception):
      pass

  class SearchService:
      def __init__(self, *, search_query: Any) -> None:
          self.search_query = search_query
  ```
- Public method signature: `def search(self, query: str, *, limit: int = 20, scope: str = "all", cursor: str | None = None) -> SearchPage`.
- Fusion contract:
  ```python
  RRF_K = 60.0
  ROUTE_WEIGHTS = {
      "target": 1.0,
      "handle": 0.85,
      "lexical": 0.65,
      "trigram": 0.35,
  }

  def _fused_score(route_hits: list[dict[str, Any]]) -> float:
      return sum(
          ROUTE_WEIGHTS[str(hit["route"])] / (RRF_K + max(1, int(hit["route_rank"])))
          for hit in route_hits
      )
  ```
- Page sort tuple:
  ```python
  (-rank_score, -received_at_ms, event_id)
  ```
  Public cursor encodes positive values as:
  ```python
  f"{rank_score:.12f}:{received_at_ms}:{event_id}"
  ```
- Service algorithm:
  1. `parse_search_query(q, scope)` returns `SearchIntent`.
  2. Empty query returns `ok=False, error="empty_query"`.
  3. Invalid cursor raises `SearchCursorError`, handled by API/CLI.
  4. `search_query.resolve_targets(intent)` returns target candidates.
  5. `search_query.route_hits` returns route hits from target/handle/lexical/trigram.
  6. Group route hits by `event_id`.
  7. Fetch event payloads via search query row payloads already joined in route SQL; do not call `EvidenceRepository.events_by_ids` unless query rows intentionally only carry event ids.
  8. Build `items` with `event`, `match_type`, `score`, `match_reasons`, `target`, `route_scores`.
  9. Apply cursor after fusion and sorting.
  10. Return `limit + 1` internally, then trim to `limit`; `has_more` and `next_cursor` come from the extra row.
- Match type rules:
  ```python
  if any(hit["route"] == "target" for hit in hits): match_type = "target"
  elif any(hit["route"] == "handle" for hit in hits): match_type = "handle"
  elif any(hit["route"] == "lexical" for hit in hits): match_type = "lexical"
  else: match_type = "trigram"
  ```

### `src/gmgn_twitter_intel/domains/token_intel/services/query_parser.py`

- Replace `ParsedQuery` with `SearchIntent` or keep the file name and hard-rewrite the model. No old parser compatibility helpers.
- New dataclass:
  ```python
  @dataclass(frozen=True, slots=True)
  class SearchIntent:
      kind: str
      text: str
      normalized_text: str
      scope: str
      symbol: str | None = None
      ca: str | None = None
      chain: str | None = None
      handle: str | None = None
      lexical_query: str | None = None
  ```
- New public function signature: `def parse_search_query(text: str, *, scope: str) -> SearchIntent`.
- Required behavior:
  - Empty trim => `kind="empty"`.
  - `@handle` => `kind="handle"`, `handle` lowercased.
  - `$BTC` and `BTC` => `kind="symbol"`, `symbol="BTC"`, `lexical_query` remains original normalized text for lexical route.
  - `chain:<address>` and bare valid CA => `kind="ca"`, checksum/lower normalized through existing `normalize_ca`.
  - Multi-token query, quoted phrase, query with OR/NOT => `kind="text"` and preserve original query string for `websearch_to_tsquery`.
  - Symbol-like token regex:
    ```python
    SYMBOL_QUERY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,20}$")
    ```
  - Do not treat one-character symbols as target probes.

### `src/gmgn_twitter_intel/domains/token_intel/queries/search_events_query.py`

- Create this file. It owns all SQL for search target resolution and route retrieval.
- Constructor:
  ```python
  class SearchEventsQuery:
      def __init__(self, conn: Any) -> None:
          self.conn = conn
  ```
- Public methods:
  - `resolve_targets(self, intent: SearchIntent) -> list[dict[str, Any]]`
  - `route_hits(self, *, intent: SearchIntent, target_candidates: list[dict[str, Any]], watched_only: bool, route_limit: int) -> list[dict[str, Any]]`
- SQL rule: every route row must include:
  ```text
  event_id, event_json, canonical_url, received_at_ms, author_handle,
  text_clean, search_text, is_watched,
  route, route_rank, route_score, match_reasons_json,
  target_type, target_id, target_symbol
  ```
- `resolve_targets` for symbol:
  ```sql
  WITH candidates AS (
    SELECT
      'CexToken' AS target_type,
      cex_token_id AS target_id,
      base_symbol AS symbol,
      NULL::text AS chain_id,
      NULL::text AS address,
      'resolved' AS status,
      'cex_token' AS source,
      'CONFIRMED_CEX_TOKEN' AS reason,
      0 AS sort_group
    FROM cex_tokens
    WHERE base_symbol = %s
      AND status IN ('candidate', 'canonical')
    UNION ALL
    SELECT
      'Asset' AS target_type,
      registry_assets.asset_id AS target_id,
      asset_identity_current.canonical_symbol AS symbol,
      registry_assets.chain_id,
      registry_assets.address,
      CASE
        WHEN COUNT(*) OVER () = 1 THEN 'resolved'
        ELSE 'ambiguous'
      END AS status,
      'asset_identity_current' AS source,
      'CANONICAL_SYMBOL_MATCH' AS reason,
      1 AS sort_group
    FROM registry_assets
    JOIN asset_identity_current
      ON asset_identity_current.asset_id = registry_assets.asset_id
    WHERE asset_identity_current.canonical_symbol = %s
      AND registry_assets.status IN ('candidate', 'canonical')
  )
  SELECT
    target_type, target_id, symbol, chain_id, address, status, source, reason
  FROM candidates
  ORDER BY sort_group, target_id
  ```
- `resolve_targets` for CA:
  ```sql
  SELECT
    'Asset' AS target_type,
    registry_assets.asset_id AS target_id,
    asset_identity_current.canonical_symbol AS symbol,
    registry_assets.chain_id,
    registry_assets.address,
    'resolved' AS status,
    'registry_asset_address' AS source,
    'CHAIN_ADDRESS_EXACT' AS reason
  FROM registry_assets
  LEFT JOIN asset_identity_current
    ON asset_identity_current.asset_id = registry_assets.asset_id
  WHERE lower(registry_assets.address) = %s
    AND (%s IS NULL OR registry_assets.chain_id = %s)
    AND registry_assets.status IN ('candidate', 'canonical')
  ORDER BY registry_assets.updated_at_ms DESC, registry_assets.asset_id
  ```
- Target route SQL. The Python method must build one parameterized `VALUES` row per resolved target candidate; ambiguous candidates stay in `target_candidates` for UI context and do not enter target route unless a later approved rule promotes them to resolved. If the resolved candidate list is empty, skip this route before SQL execution.
  ```sql
  WITH target_candidates(target_type, target_id, target_symbol) AS (
    VALUES
      (%s, %s, %s)
  ),
  ranked AS (
    SELECT
      events.*,
      tir.target_type,
      tir.target_id,
      target_candidates.target_symbol,
      row_number() OVER (
        ORDER BY
          CASE
            WHEN tir.resolution_status = 'EXACT' THEN 0
            WHEN tir.resolution_status = 'UNIQUE_BY_CONTEXT' THEN 1
            WHEN tir.resolution_status = 'AMBIGUOUS' THEN 2
            ELSE 3
          END,
          events.received_at_ms DESC,
          events.event_id DESC
      ) AS route_rank,
      CASE
        WHEN tir.resolution_status = 'EXACT' THEN 1.0
        WHEN tir.resolution_status = 'UNIQUE_BY_CONTEXT' THEN 0.9
        WHEN tir.resolution_status = 'AMBIGUOUS' THEN 0.45
        ELSE 0.1
      END AS route_score
    FROM target_candidates
    JOIN token_intent_resolutions tir
      ON tir.target_type = target_candidates.target_type
     AND tir.target_id = target_candidates.target_id
     AND tir.is_current = true
     AND tir.resolver_policy_version = %s
    JOIN events ON events.event_id = tir.event_id
    WHERE (%s = false OR events.is_watched = true)
  )
  SELECT *, 'target' AS route, jsonb_build_array('target:' || target_type) AS match_reasons_json
  FROM ranked
  ORDER BY route_rank
  LIMIT %s
  ```
- Handle route SQL:
  ```sql
  SELECT
    events.*,
    NULL::text AS target_type,
    NULL::text AS target_id,
    NULL::text AS target_symbol,
    row_number() OVER (ORDER BY events.received_at_ms DESC, events.event_id DESC) AS route_rank,
    1.0 AS route_score,
    'handle' AS route,
    jsonb_build_array('author_handle') AS match_reasons_json
  FROM events
  WHERE events.author_handle = %s
    AND (%s = false OR events.is_watched = true)
  ORDER BY events.received_at_ms DESC, events.event_id DESC
  LIMIT %s
  ```
- Lexical route SQL:
  ```sql
  WITH query AS (
    SELECT
      websearch_to_tsquery('simple', %s) AS simple_q,
      websearch_to_tsquery('english', %s) AS english_q
  ),
  ranked AS (
    SELECT
      events.*,
      NULL::text AS target_type,
      NULL::text AS target_id,
      NULL::text AS target_symbol,
      (
        ts_rank_cd(events.search_tsv, query.simple_q)
        + ts_rank_cd(events.search_tsv, query.english_q)
      ) AS route_score
    FROM events, query
    WHERE (
        events.search_tsv @@ query.simple_q
        OR events.search_tsv @@ query.english_q
      )
      AND (%s = false OR events.is_watched = true)
  )
  SELECT
    *,
    row_number() OVER (ORDER BY route_score DESC, received_at_ms DESC, event_id DESC) AS route_rank,
    'lexical' AS route,
    jsonb_build_array('fts') AS match_reasons_json
  FROM ranked
  ORDER BY route_score DESC, received_at_ms DESC, event_id DESC
  LIMIT %s
  ```
- Trigram route SQL:
  ```sql
  SELECT
    events.*,
    NULL::text AS target_type,
    NULL::text AS target_id,
    NULL::text AS target_symbol,
    similarity(events.search_text, %s) AS route_score,
    row_number() OVER (
      ORDER BY similarity(events.search_text, %s) DESC, events.received_at_ms DESC, events.event_id DESC
    ) AS route_rank,
    'trigram' AS route,
    jsonb_build_array('trigram') AS match_reasons_json
  FROM events
  WHERE events.search_text %% %s
    AND similarity(events.search_text, %s) >= 0.18
    AND (%s = false OR events.is_watched = true)
  ORDER BY route_score DESC, events.received_at_ms DESC, events.event_id DESC
  LIMIT %s
  ```
- Route admission:
  - Target route runs for non-empty resolved target candidates.
  - Handle route runs only for `kind="handle"`.
  - Lexical route runs for `kind in {"symbol", "text", "ca"}` when lexical query is non-empty; CA lexical uses the normalized address string.
  - Trigram route runs only when lexical query normalized length is at least 4 and target+lexical hits are fewer than `limit + 1`.
- Decode event rows using a small local function or reuse `decode_event_row` from `EvidenceRepository`; do not call removed FTS methods.

### `src/gmgn_twitter_intel/domains/token_intel/services/search_aliases.py`

- Create this file for high-confidence query expansion. Keep it deterministic and small.
- Initial constants:
  ```python
  from collections.abc import Mapping, Sequence

  TOKEN_QUERY_ALIASES: Mapping[str, Sequence[str]] = {
      "BTC": ("btc", "bitcoin", "bitcoins", "比特币", "xbt"),
      "ETH": ("eth", "ethereum", "ether", "以太坊"),
      "SOL": ("sol", "solana"),
      "DOGE": ("doge", "dogecoin", "狗狗币"),
  }
  ```
- Public function signature: `def expanded_lexical_query(intent: SearchIntent, target_candidates: list[dict[str, Any]]) -> str`.
- Expansion rules:
  - Preserve quoted phrases and explicit `OR`/`NOT` queries by returning original lexical query.
  - For simple symbol intent with aliases, return `"btc OR bitcoin OR bitcoins OR 比特币 OR xbt"` style websearch string.
  - For text intent, do not inject aliases unless the entire query is one known alias.

### `src/gmgn_twitter_intel/domains/evidence/repositories/evidence_repository.py`

- Remove methods named `search_fts`, `count_fts`, and `_fts_query`.
- Keep `recent_events`, `events_by_ids`, `event_to_row`, and `decode_event_row`.
- Update imports to remove unused `re`.
- Run `rg "search_fts|count_fts|_fts_query" src tests` and delete or migrate every usage.

### `src/gmgn_twitter_intel/app/surfaces/api/http.py`

- Replace import:
  ```python
  from gmgn_twitter_intel.domains.token_intel.read_models.search_service import (
      SearchCursorError,
      SearchService,
  )
  from gmgn_twitter_intel.domains.token_intel.queries.search_events_query import SearchEventsQuery
  ```
- Replace `/api/search` signature:
  ```python
  @router.get("/search")
  async def search(
      request: Request,
      q: Annotated[str, Query()] = "",
      limit: Annotated[int, Query()] = 20,
      scope: Annotated[str, Query()] = "all",
      cursor: Annotated[str, Query()] = "",
  ) -> JSONResponse:
      for removed in ("symbol", "ca", "chain", "handle"):
          if removed in request.query_params:
              raise ApiBadRequest("unsupported_query_param", field=removed)
      try:
          with runtime.repositories() as repos:
              results = SearchService(
                  search_query=SearchEventsQuery(repos.conn),
              ).search(
                  q,
                  limit=_limit(limit, maximum=200),
                  scope=_scope(scope),
                  cursor=cursor or None,
              )
      except SearchCursorError:
          return _json({"ok": False, "error": "invalid_cursor"}, status_code=400)
      return _json(
          {
              "ok": results.ok,
              "data": {
                  "query": results.query,
                  "page": results.page,
                  "target_candidates": results.target_candidates,
                  "items": results.items,
              },
              "error": results.error,
          }
      )
  ```
- Reject removed params with FastAPI by removing them from the function signature. If clients pass them, they are ignored by FastAPI by default; to make hard cut observable, add this explicit guard at the start:
  ```python
  for removed in ("symbol", "ca", "chain", "handle"):
      if removed in request.query_params:
          raise ApiBadRequest("unsupported_query_param", field=removed)
  ```
- Handler body must match the signature block above: reject removed params, map `SearchCursorError` to `400 {"ok": false, "error": "invalid_cursor"}`, and return the Search V2 response shape below.
- Delete `_search_query` at `http.py:619` after CLI no longer uses a matching helper.
- Response shape:
  ```python
  {
      "ok": results.ok,
      "data": {
          "query": results.query,
          "page": results.page,
          "target_candidates": results.target_candidates,
          "items": results.items,
      },
      "error": results.error,
  }
  ```

### `src/gmgn_twitter_intel/app/surfaces/cli/main.py`

- Replace `AssetSearchService` import with `SearchService` and `SearchEventsQuery`.
- Search parser edits:
  - Remove `--symbol`.
  - Remove `--ca`.
  - Remove `--chain`.
  - Remove `--handle`.
  - Add:
    ```python
    search.add_argument("--cursor", default="", help="opaque cursor returned by a prior search page")
    ```
- Runtime search block:
  ```python
  if command == "search":
      try:
          results = SearchService(search_query=SearchEventsQuery(repos.conn)).search(
              args.query,
              limit=args.limit,
              scope=args.scope,
              cursor=args.cursor or None,
          )
      except SearchCursorError:
          _emit({"ok": False, "error": "invalid_cursor"}, stdout)
          return 1
      _emit(
          {
              "ok": results.ok,
              "data": {
                  "query": results.query,
                  "page": results.page,
                  "target_candidates": results.target_candidates,
                  "items": results.items,
              },
              "error": results.error,
          },
          stdout,
      )
      return 0 if results.ok else 1
  ```
- Delete CLI `_search_query(args)` helper at `main.py:943` after removing old flags.

### `src/gmgn_twitter_intel/platform/db/alembic/versions/20260512_0032_search_v2_hard_cut.py`

- Create migration with revision id `20260512_0032` and `down_revision = "20260512_0031"`.
- Upgrade SQL:
  ```sql
  CREATE EXTENSION IF NOT EXISTS pg_trgm;

  DROP INDEX IF EXISTS idx_events_search_tsv;
  ALTER TABLE events DROP COLUMN IF EXISTS search_tsv;
  ALTER TABLE events
    ADD COLUMN search_tsv tsvector GENERATED ALWAYS AS (
      setweight(to_tsvector('simple', coalesce(search_text, '')), 'A') ||
      setweight(to_tsvector('english', coalesce(search_text, '')), 'B') ||
      setweight(to_tsvector('simple', coalesce(author_handle, '')), 'D')
    ) STORED;

  CREATE INDEX IF NOT EXISTS idx_events_search_tsv ON events USING GIN(search_tsv);
  CREATE INDEX IF NOT EXISTS idx_events_search_text_trgm
    ON events USING GIN(search_text gin_trgm_ops)
    WHERE search_text IS NOT NULL;
  ```
- Downgrade SQL:
  ```sql
  DROP INDEX IF EXISTS idx_events_search_text_trgm;
  DROP INDEX IF EXISTS idx_events_search_tsv;
  ALTER TABLE events DROP COLUMN IF EXISTS search_tsv;
  ALTER TABLE events
    ADD COLUMN search_tsv tsvector GENERATED ALWAYS AS (
      setweight(to_tsvector('simple', coalesce(author_handle, '')), 'A') ||
      setweight(to_tsvector('simple', coalesce(search_text, '')), 'B') ||
      setweight(to_tsvector('simple', coalesce(text_clean, '')), 'C')
    ) STORED;
  CREATE INDEX IF NOT EXISTS idx_events_search_tsv ON events USING GIN(search_tsv);
  ```
- Do not create duplicate generated columns or dual-read compatibility indexes.

### `src/gmgn_twitter_intel/app/surfaces/api/http.py` generated docs dependencies

- After API change, regenerate:
  ```bash
  uv run python scripts/regen_openapi.py
  uv run python scripts/regen_cli_help.py
  uv run python scripts/regen_db_schema.py
  ```
- Expected files modified:
  - `docs/generated/openapi.json`
  - `docs/generated/cli-help.md`
  - `docs/generated/db-schema.md`

### `web/src/api/types.ts`

- Replace `SearchData`:
  ```ts
  export type SearchRouteScores = Record<string, number>;

  export type SearchTargetCandidate = {
    target_type: "Asset" | "CexToken" | string;
    target_id: string;
    symbol?: string | null;
    chain_id?: string | null;
    address?: string | null;
    status: "resolved" | "ambiguous" | "unresolved" | string;
    source: string;
    reason: string;
  };

  export type SearchItem = {
    event: EventRecord;
    match_type: "target" | "handle" | "lexical" | "trigram" | string;
    score: number;
    match_reasons: string[];
    target?: SearchTargetCandidate | null;
    route_scores: SearchRouteScores;
  };

  export type SearchData = {
    query: Record<string, unknown>;
    page: {
      returned_count: number;
      has_more: boolean;
      next_cursor?: string | null;
    };
    target_candidates: SearchTargetCandidate[];
    items: SearchItem[];
  };
  ```
- Remove old `total_count`, top-level `returned_count`, top-level `has_more`, `candidates`.

### `web/src/features/live/useLiveData.ts`

- Replace `useQuery` search call with `useInfiniteQuery`.
- New query key:
  ```ts
  ["search", submittedSearch, "v2"]
  ```
- Query function:
  ```ts
  ({ pageParam }) =>
    getApi<SearchData>("/api/search", {
      token,
      params: { q: submittedSearch, limit: 36, scope: "all", cursor: pageParam ?? "" },
    })
  ```
- `getNextPageParam`:
  ```ts
  (lastPage) => lastPage.data.page.next_cursor ?? undefined
  ```
- Expose from hook:
  ```ts
  currentSearchData,
  fetchNextSearchPage: searchQuery.fetchNextPage,
  searchHasNextPage: Boolean(searchQuery.hasNextPage),
  searchFetchingNextPage: searchQuery.isFetchingNextPage,
  ```
- Merge pages:
  ```ts
  const searchData = useMemo(() => {
    const pages = searchQuery.data?.pages ?? [];
    if (!pages.length) return null;
    const first = pages[0].data;
    return {
      query: first.query,
      target_candidates: first.target_candidates,
      page: pages[pages.length - 1].data.page,
      items: pages.flatMap((page) => page.data.items),
    };
  }, [searchQuery.data?.pages]);
  ```

### `web/src/app/CockpitApp.tsx`

- Pass new search paging controls into `EvidenceDetailDrawer`:
  ```tsx
  fetchNextSearchPage,
  searchHasNextPage,
  searchFetchingNextPage,
  ```
- Update `resolveEvidenceDetails` query mode props to include:
  ```ts
  onLoadMore: () => void;
  hasMore: boolean;
  isFetchingNextPage: boolean;
  ```

### `web/src/components/EvidenceDetailDrawer.tsx`

- Query mode prop changes:
  ```ts
  | {
      mode: "query";
      query: string;
      data: SearchData | null;
      isFetching: boolean;
      error?: Error | null;
      hasMore: boolean;
      isFetchingNextPage: boolean;
      onLoadMore: () => void;
    };
  ```
- Replace metrics:
  - `returned` = `data?.items.length ?? 0`
  - `page` = `data?.page.has_more ? "more" : "end"`
  - remove `total`
- Remove `items.slice(0, 8)` and render all loaded `items`.
- Add load-more button after list:
  ```tsx
  {hasMore ? (
    <button className="secondary-action" disabled={isFetchingNextPage} onClick={onLoadMore} type="button">
      {isFetchingNextPage ? "Loading" : "Load more"}
    </button>
  ) : null}
  ```

### `web/src/components/__tests__/SearchQueryDrawer.test.tsx`

- Create this file if no focused drawer test exists.
- Tests:
  - `renders_all_loaded_search_items_without_eight_item_cap`
  - `calls_on_load_more_when_has_more`
  - `hides_total_count_metric_for_search_v2`

### `tests/unit/test_query_parser.py`

- Rewrite tests for `parse_search_query`.
- Required tests:
  ```python
  def test_parse_search_query_treats_bare_symbol_as_symbol_probe():
      parsed = parse_search_query("btc", scope="all")
      assert parsed.kind == "symbol"
      assert parsed.symbol == "BTC"
      assert parsed.lexical_query == "btc"

  def test_parse_search_query_treats_cashtag_as_same_symbol_probe():
      parsed = parse_search_query("$btc", scope="all")
      assert parsed.kind == "symbol"
      assert parsed.symbol == "BTC"

  def test_parse_search_query_preserves_phrase_text():
      parsed = parse_search_query('"bitcoin price"', scope="all")
      assert parsed.kind == "text"
      assert parsed.lexical_query == '"bitcoin price"'

  def test_parse_search_query_preserves_or_text():
      parsed = parse_search_query("btc OR eth", scope="all")
      assert parsed.kind == "text"
      assert parsed.lexical_query == "btc OR eth"
  ```

### `tests/unit/test_search_service.py`

- Create this file to replace `tests/unit/test_asset_search_service.py`.
- Fake query object records calls and returns deterministic route hits.
- Required tests:
  - `test_search_merges_target_and_lexical_hits_by_event_id`
  - `test_search_paginates_with_next_cursor`
  - `test_search_rejects_invalid_cursor`
  - `test_search_routes_symbol_and_cashtag_to_same_target_candidates`
  - `test_search_does_not_call_legacy_asset_candidate_methods`
- Delete `tests/unit/test_asset_search_service.py` after equivalent coverage exists.

### `tests/integration/test_api_http.py`

- Update existing search assertion around `test_api_http` line 455 to new response shape:
  ```python
  search = client.get("/api/search", params={"q": "$PEPE", "limit": 5}, headers=headers)
  assert search.status_code == 200
  payload = search.json()["data"]
  assert payload["items"][0]["event"]["event_id"] == "event-1"
  assert payload["page"]["returned_count"] == 1
  assert "total_count" not in payload
  ```
- Add hard-cut param rejection test:
  ```python
  def test_search_rejects_removed_filter_params(client, headers):
      response = client.get("/api/search", params={"symbol": "PEPE"}, headers=headers)
      assert response.status_code == 400
      assert response.json()["error"] == "unsupported_query_param"
      assert response.json()["field"] == "symbol"
  ```
- Add cursor test with two seeded events for the same target:
  ```python
  first = client.get("/api/search", params={"q": "$PEPE", "limit": 1}, headers=headers)
  cursor = first.json()["data"]["page"]["next_cursor"]
  second = client.get("/api/search", params={"q": "$PEPE", "limit": 1, "cursor": cursor}, headers=headers)
  assert first.json()["data"]["items"][0]["event"]["event_id"] != second.json()["data"]["items"][0]["event"]["event_id"]
  ```

### `tests/integration/test_postgres_schema_runtime.py`

- Add assertions:
  - `pg_trgm` extension exists.
  - `idx_events_search_text_trgm` exists.
  - `events.search_tsv` exists after migration.

### `tests/unit/test_cli_search_query.py`

- Rewrite for new CLI args:
  - Positional `btc` is accepted.
  - `--cursor` is accepted.
  - `--symbol`, `--ca`, `--chain`, `--handle` are not present in help.

### `web/src/App.test.tsx`

- Update mocked `/api/search` response shape:
  ```ts
  {
    query: { kind: "text", text: "PEPE", scope: "all" },
    page: { returned_count: 1, has_more: false, next_cursor: null },
    target_candidates: [],
    items: [
      {
        event: searchEvent,
        match_type: "lexical",
        score: 0.5,
        match_reasons: ["fts"],
        target: null,
        route_scores: { lexical: 0.5 },
      },
    ],
  }
  ```
- Update expectations that rely on `total_count`, `returned_count`, or `has_more` top-level fields.

### `docs/CONTRACTS.md`

- Add a short Search V2 HTTP contract under HTTP:
  - `/api/search` accepts `q`, `limit`, `scope`, `cursor`.
  - Removed `symbol/ca/chain/handle`.
  - Cursor pages, no exact total count.
  - Search uses current token targets before lexical/trigram retrieval.

### `docs/ARCHITECTURE.md` and `src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md`

- Update Token Intel local architecture with a short “Search read model” row or paragraph:
  - Search reads current `token_intent_resolutions`, `cex_tokens`, `registry_assets`, `asset_identity_current`.
  - Search does not perform provider calls, extraction, or resolution mutation.
  - Search does not read legacy `assets / asset_aliases / asset_venues`.

## PR Breakdown

1. **PR 1 — Backend Search V2 Core**: add parser, alias expansion, query module, search service, remove `AssetSearchService`, remove `EvidenceRepository.search_fts/count_fts`, update API/CLI, add backend unit tests.
2. **PR 2 — Storage Hard Cut**: add Alembic migration for `pg_trgm`, rewrite `search_tsv`, add runtime schema assertions, regenerate db schema docs.
3. **PR 3 — Frontend Search Pagination**: update `SearchData`, switch to infinite query, render all loaded search rows, add load-more UI, update frontend tests.
4. **PR 4 — Contracts and Generated Artifacts**: update `docs/CONTRACTS.md`, Token Intel architecture docs, regenerate OpenAPI and CLI help, update contract tests.

These PRs may be landed as one branch if review bandwidth is small, but each slice must be internally testable. The final branch must not leave mixed old/new search contracts.

## Rollout Order

1. Create worktree:
   ```bash
   git worktree add .worktrees/search-v2-hard-cut -b codex/search-v2-hard-cut main
   cd .worktrees/search-v2-hard-cut
   ```
2. Run baseline:
   ```bash
   uv run ruff check .
   uv run pytest
   cd web && npm test -- --run && cd ..
   ```
3. Implement PR 1 backend core.
4. Implement PR 2 migration.
5. Run migration locally:
   ```bash
   uv run alembic upgrade head
   ```
6. Implement PR 3 frontend.
7. Implement PR 4 docs/generated artifacts.
8. Run focused checks:
   ```bash
   uv run pytest tests/unit/test_query_parser.py tests/unit/test_search_service.py tests/integration/test_api_http.py -q
   cd web && npm test -- --run SearchQueryDrawer App && cd ..
   ```
9. Run full completion gate:
   ```bash
   make check-all
   ```
10. Record full output in verification artifact before declaring completion.

## Rollback

1. If code has not shipped, revert the search branch commits and remove `.worktrees/search-v2-hard-cut/`.
2. If migration has been applied locally before merge, run:
   ```bash
  uv run alembic downgrade 20260512_0031
   ```
3. If migration shipped and index rebuild caused production issues, rollback app deploy and run downgrade during maintenance. The downgrade restores old `search_tsv` expression and drops the trigram index.
4. If API hard cut shipped and external callers still use removed params, do not add compatibility code in-place. Either communicate the new `q` contract or create a separate approved spec for a compatibility gateway outside this service.
5. If frontend pagination fails after deploy, rollback frontend bundle with backend together because response shape is intentionally hard-cut and not dual-compatible.

## Acceptance Test Commands

- AC1 / AC2 target symbol parity:
  ```bash
  uv run pytest tests/integration/test_api_http.py::test_search_v2_symbol_and_cashtag_share_target_results -q
  ```
  Expected: PASS; assertions show `/api/search?q=btc` and `/api/search?q=$btc` return the same target candidate and target-route event.

- AC3 alias expansion:
  ```bash
  uv run pytest tests/unit/test_search_service.py::test_search_expands_known_symbol_aliases_for_lexical_route -q
  ```
  Expected: PASS; fake query receives `btc OR bitcoin OR bitcoins OR 比特币 OR xbt` for BTC lexical route.

- AC4 phrase preservation:
  ```bash
  uv run pytest tests/unit/test_query_parser.py::test_parse_search_query_preserves_phrase_text -q
  ```
  Expected: PASS; parser keeps `"bitcoin price"`.

- AC5 OR preservation:
  ```bash
  uv run pytest tests/unit/test_query_parser.py::test_parse_search_query_preserves_or_text -q
  ```
  Expected: PASS; parser keeps `btc OR eth`.

- AC6 trigram fallback:
  ```bash
  uv run pytest tests/unit/test_search_service.py::test_search_runs_trigram_when_lexical_page_is_short -q
  ```
  Expected: PASS; fake query records trigram route after target/lexical return fewer than `limit + 1` rows.

- AC7 cursor pagination:
  ```bash
  uv run pytest tests/integration/test_api_http.py::test_search_v2_cursor_returns_next_non_overlapping_page -q
  ```
  Expected: PASS; first and second page event ids differ.

- AC8 author handle demotion:
  ```bash
  uv run pytest tests/integration/test_api_http.py::test_search_v2_body_and_target_hits_rank_above_author_handle_text_matches -q
  ```
  Expected: PASS; event with body/target BTC outranks unrelated event from author handle containing btc.

- AC9 frontend load more:
  ```bash
  cd web && npm test -- --run SearchQueryDrawer && cd ..
  ```
  Expected: PASS; tests render all loaded items and click Load more.

- AC10 CLI help hard cut:
  ```bash
  uv run pytest tests/unit/test_cli_search_query.py -q
  ```
  Expected: PASS; help includes `--cursor` and excludes removed flags.

- AC11 no legacy runtime:
  ```bash
  rg "AssetSearchService|search_fts|count_fts|candidates_for_symbol\\(|candidates_for_ca\\(" src tests
  ```
  Expected: no runtime matches except test names that explicitly assert absence are also removed before final verification; if this command prints anything, inspect and remove/migrate the match.

## Verification

Create `docs/superpowers/plans/active/2026-05-11-search-v2-hard-cut-verification.md` from `docs/superpowers/_templates/verification-template.md` before completion.

Required final command:

```bash
make check-all
```

The verification artifact must include the full `make check-all` output plus the required `Coverage`, `Skipped tests`, `E2E golden path`, `Other commands run`, and `Remaining risks` sections.
