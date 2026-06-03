# News Intel Root Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Implemented on `codex/news-intel-root-fix`; live verification recorded in `2026-05-23-news-intel-root-fix-verification-cn.md`
**Date:** 2026-05-23  
**Owning diagnosis:** Live `/news` route inspection, `/readyz` worker snapshot, DB row counts, and News Intel code review on `main`  
**Recommended branch:** `codex/news-intel-root-fix`

**Goal:** Make the News chain production-usable end to end: stable read path, explicit source/content/decision classification, visible source-quality controls, and a redesigned `/news` page that reflects what workers can actually ingest.

**Architecture:** Keep the existing Kappa/CQRS spine: provider frames and RSS entries are inputs, PostgreSQL material facts remain the only truth, and `news_page_rows` remains a rebuildable read model. Root-fix the read path by removing the expensive unbounded fallback query from normal `/api/news`, add item-level content classification as materialized facts/projection fields, and expose source/content/decision filters through the API and frontend. Provider expansion is staged after the read path and classification model are stable.

**Tech Stack:** Python 3.13, PostgreSQL/Alembic, psycopg3 repositories, existing News Intel workers, FastAPI, React/TypeScript, TanStack Query, owner CSS under `web/src/features/news`, pytest, Vitest, Playwright/browser verification, Docker Compose.

---

## Root-Fix Verdict

This is a root-fix plan only if implemented as the full sequence below.

- Root fix: split source classification, item content classification, and agent decision lanes into separate first-class axes.
- Root fix: make `/api/news` read only from bounded indexed read models in the normal path; do not rely on a full `news_items` fallback scan during every page load.
- Root fix: make the UI reflect the actual data shape: source authority/quality, content category, decision class, token/fact lanes, and pending/attention states.
- Root fix: add provider capability diagnostics so unsupported configured provider types fail visibly before operators expect data from them.
- Not root fix: only increasing PostgreSQL statement timeout.
- Not root fix: only adding frontend tabs while `content_class` is not materialized.
- Not root fix: only filling `coverage_tags` on sources; source tags describe who/where, not what happened in each item.

## Current Evidence

- `/news` static page can render, but `/api/news?limit=100` intermittently fails under runtime load with `psycopg.errors.QueryCanceled: canceling statement due to statement timeout`.
- The hot query is `NewsRepository.list_news_page_rows()` in `src/parallax/domains/news_intel/repositories/news_repository.py`, currently using `news_page_rows UNION ALL fallback news_items`.
- DB has live News data: about 4.5k `news_items` and matching `news_page_rows`, 319 `news_fact_candidates`, 4.5k `news_item_agent_briefs`, and 20 source-quality rows.
- Current runtime sources are 10 enabled RSS sources only. Roles are `specialist_media` and `aggregator`; all `coverage_tags_json` are empty.
- Provider type literals already include `openbb`, `telegram_public`, `twitter_profile`, `reddit`, `hackernews`, `github`, `ossinsight`, and `manual_api`, but the live provider registry only implements `rss`, `atom`, `json_feed`, and `cryptopanic`.
- Current facts are all `attention`, not `accepted`, because current sources are not official authority roles and do not carry authority scope.
- The frontend `NewsPage.tsx` currently exposes only direction tabs: `All`, `Bullish`, `Bear`. It does not expose provider type, source role, trust tier, source quality, coverage tag, content class, or decision class.

## Classification Model

Use three independent axes.

1. **Source Class: who said it**
   - Existing fields: `provider_type`, `source_role`, `trust_tier`, `coverage_tags`, `source_quality_status`.
   - Examples: `rss/specialist_media/high`, `rss/aggregator/standard`, future `manual_api/official_regulator/official`.

2. **Content Class: what happened**
   - New item-level classification, materialized into facts/projection.
   - Initial classes:
     - `crypto_market`
     - `macro_policy`
     - `rates_fed`
     - `regulation`
     - `etf_fund_flow`
     - `exchange_listing`
     - `security_hack`
     - `protocol_development`
     - `equity_earnings`
     - `analyst_rating`
     - `ai_semiconductors`
     - `energy_geopolitics`
     - `consumer_macro`
     - `market_structure`
     - `low_signal`

3. **Decision Lane: what to do with it**
   - Existing agent brief fields: `direction`, `decision_class`, `bull_strength`, `bear_strength`, `evidence_refs`, `data_gaps`.
   - Examples: `bullish/driver`, `bearish/watch`, `neutral/context`, `neutral/discard`.

Do not overload `source_role` with content semantics. A Yahoo Finance source can publish `equity_earnings`, `analyst_rating`, `energy_geopolitics`, and `low_signal` items in the same hour.

## Release Shape

Ship in four small branches if possible. Each branch must keep existing RSS ingestion working.

1. **Read-path branch:** make `/api/news` fast and bounded.
2. **Classification branch:** add item-level content classification and projection.
3. **Frontend branch:** redesign `/news` around source/content/decision filters.
4. **Provider diagnostics branch:** expose configured-vs-supported provider capability and prepare provider waves.

If the team wants one branch, use separate commits matching the tasks below.

## Pre-Flight

- [ ] Confirm branch and untracked files before editing:
  ```bash
  git status --short
  git branch --show-current
  ```
  Expected: current branch is intentional; unrelated untracked plan files are left untouched.

- [ ] For implementation, create an isolated worktree:
  ```bash
  git worktree add .worktrees/news-intel-root-fix -b codex/news-intel-root-fix main
  cd .worktrees/news-intel-root-fix
  git status --short
  ```
  Expected: clean worktree on `codex/news-intel-root-fix`.

- [ ] Confirm real runtime config paths before live-data debugging:
  ```bash
  uv run parallax config
  ```
  Expected: `config_path` and `workers_config_path` point at `~/.parallax/`. Do not print secret values.

- [ ] Capture the current `/api/news` failure or baseline latency:
  ```bash
  curl -sS -w '\nstatus=%{http_code} time=%{time_total}\n' \
    -H "Authorization: Bearer $GMGN_API_TOKEN" \
    'http://127.0.0.1:8765/api/news?limit=100' >/tmp/news-api-before.json
  ```
  Expected before fix: either intermittent 500/timeout under full runtime load, or latency high enough to record as baseline.

## File Structure

### Create

- `src/parallax/domains/news_intel/types/content_classification.py`
  Canonical `content_class` and `content_tags` literals plus deterministic normalization helpers.
- `src/parallax/domains/news_intel/services/news_content_classification.py`
  Pure deterministic classifier from headline/summary/source/fact lanes to content class and tags.
- `src/parallax/platform/db/alembic/versions/20260523_0087_news_content_classification.py`
  Adds item-level classification storage and read-model indexes.
- `tests/unit/domains/news_intel/test_news_content_classification.py`
  Unit tests for deterministic class assignment.
- `tests/integration/domains/news_intel/test_news_page_rows_read_path.py`
  Integration tests proving `/api/news` does not require scanning fallback rows in the normal path.
- `web/tests/component/features/news/NewsPageClassificationFilters.test.tsx`
  Component tests for source/content/decision filters.

### Modify

- `src/parallax/domains/news_intel/repositories/news_repository.py`
- `src/parallax/domains/news_intel/queries/news_page_query.py`
- `src/parallax/domains/news_intel/runtime/news_item_process_worker.py`
- `src/parallax/domains/news_intel/runtime/news_page_projection_worker.py`
- `src/parallax/domains/news_intel/services/news_page_projection.py`
- `src/parallax/app/surfaces/api/routes_news.py`
- `src/parallax/app/surfaces/api/schemas.py`
- `src/parallax/integrations/news_feeds/provider_registry.py`
- `src/parallax/app/runtime/provider_wiring/news.py`
- `src/parallax/domains/news_intel/ARCHITECTURE.md`
- `docs/ARCHITECTURE.md`
- `docs/CONTRACTS.md`
- `docs/WORKERS.md`
- `web/src/lib/api/client.ts`
- `web/src/features/news/useNewsPage.ts`
- `web/src/features/news/NewsPage.tsx`
- `web/src/features/news/newsViewModel.ts`
- `web/src/features/news/news.css`
- `web/src/features/news/newsRows.css`
- `web/src/shared/model/newsIntel.ts`

### Do Not Modify

- `src/parallax/domains/token_intel/runtime/token_radar_projection_worker.py`
- `src/parallax/domains/pulse_lab/*`
- `src/parallax/domains/asset_market/runtime/market_tick_*`

If implementation appears to require these files, stop and split that work into a separate plan.

## Task 1: Make `/api/news` Read Path Bounded

**Files:**
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py`
- Modify: `src/parallax/domains/news_intel/queries/news_page_query.py`
- Test: `tests/integration/domains/news_intel/test_news_page_rows_read_path.py`
- Test: `tests/unit/test_api_news_contract.py`

- [ ] **Step 1: Add failing integration test for normal projected read path**
  ```python
  def test_list_news_page_rows_uses_projected_rows_without_fallback_scan(news_repo):
      for index in range(3):
          news_repo.replace_page_rows_for_items(
              news_item_ids=[f"news-{index}"],
              rows=[
                  {
                      "row_id": f"news-{index}",
                      "news_item_id": f"news-{index}",
                      "story_id": None,
                      "latest_at_ms": 1_779_500_000_000 - index,
                      "lifecycle_status": "processed",
                      "headline": f"headline {index}",
                      "summary": "",
                      "source_domain": "example.com",
                      "canonical_url": f"https://example.com/{index}",
                      "token_lanes_json": [],
                      "fact_lanes_json": [],
                      "story_json": {},
                      "source_json": {"source_role": "specialist_media", "trust_tier": "standard"},
                      "agent_brief_json": {"status": "ready", "direction": "neutral"},
                      "agent_status": "ready",
                      "agent_brief_computed_at_ms": 1_779_500_000_000,
                      "computed_at_ms": 1_779_500_000_000,
                      "projection_version": "news_page_rows_v2",
                  }
              ],
          )

      rows = news_repo.list_news_page_rows(limit=2, include_unprojected=False)

      assert [row["news_item_id"] for row in rows] == ["news-0", "news-1"]
  ```

- [ ] **Step 2: Run the focused test and confirm it fails**
  ```bash
  uv run pytest tests/integration/domains/news_intel/test_news_page_rows_read_path.py::test_list_news_page_rows_uses_projected_rows_without_fallback_scan -q
  ```
  Expected: fails because `include_unprojected` does not exist.

- [ ] **Step 3: Add `include_unprojected` to repository/query call**
  ```python
  def list_news_page_rows(
      self,
      *,
      limit: int,
      cursor: str | None = None,
      status: str | None = None,
      direction: str | None = None,
      lane: str | None = None,
      source: str | None = None,
      provider_type: str | None = None,
      source_role: str | None = None,
      trust_tier: str | None = None,
      coverage_tag: str | None = None,
      content_class: str | None = None,
      decision_class: str | None = None,
      q: str | None = None,
      include_unprojected: bool = False,
  ) -> list[dict[str, Any]]:
      if include_unprojected:
          return self._list_news_page_rows_with_unprojected_fallback(...)
      return self._list_projected_news_page_rows(...)
  ```

- [ ] **Step 4: Implement `_list_projected_news_page_rows` as a direct indexed query**
  ```sql
  SELECT
    row_id,
    news_item_id,
    story_id,
    latest_at_ms,
    lifecycle_status,
    headline,
    summary,
    source_domain,
    canonical_url,
    token_lanes_json,
    fact_lanes_json,
    story_json,
    source_json,
    agent_brief_json,
    agent_status,
    agent_status AS agent_brief_status,
    agent_brief_json AS agent_brief,
    agent_brief_computed_at_ms,
    computed_at_ms,
    projection_version
  FROM news_page_rows
  WHERE (
    %s::bigint IS NULL
    OR (latest_at_ms, row_id) < (%s::bigint, %s::text)
  )
  ORDER BY latest_at_ms DESC, row_id DESC
  LIMIT %s
  ```

- [ ] **Step 5: Keep fallback available only for explicit early-rollout/debug use**
  ```python
  def list_news(..., include_unprojected: bool = False) -> dict[str, Any]:
      rows = self.repository.list_news_page_rows(
          limit=max(1, int(limit)),
          cursor=cursor,
          ...,
          include_unprojected=include_unprojected,
      )
  ```

- [ ] **Step 6: Add API parameter but default it to false**
  ```python
  include_unprojected: Annotated[bool, Query()] = False
  ```
  Expected behavior: normal `/api/news` reads only `news_page_rows`.

- [ ] **Step 7: Run tests**
  ```bash
  uv run pytest tests/integration/domains/news_intel/test_news_page_rows_read_path.py -q
  uv run pytest tests/unit/test_api_news_contract.py -q
  ```
  Expected: pass.

- [ ] **Step 8: Live verify latency after Docker rebuild**
  ```bash
  docker compose up -d --build
  curl -sS -w '\nstatus=%{http_code} time=%{time_total}\n' \
    -H "Authorization: Bearer $GMGN_API_TOKEN" \
    'http://127.0.0.1:8765/api/news?limit=100' >/tmp/news-api-after.json
  ```
  Expected: `status=200`; target latency under 1 second on warm DB and no `QueryCanceled` in app logs.

## Task 2: Materialize Item-Level Content Classification

**Files:**
- Create: `src/parallax/domains/news_intel/types/content_classification.py`
- Create: `src/parallax/domains/news_intel/services/news_content_classification.py`
- Create: `src/parallax/platform/db/alembic/versions/20260523_0087_news_content_classification.py`
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py`
- Modify: `src/parallax/domains/news_intel/runtime/news_item_process_worker.py`
- Test: `tests/unit/domains/news_intel/test_news_content_classification.py`
- Test: `tests/integration/domains/news_intel/test_news_repository.py`

- [ ] **Step 1: Add deterministic classifier tests**
  ```python
  from parallax.domains.news_intel.services.news_content_classification import classify_news_item_content

  def test_classifies_sec_tokenized_stock_delay_as_regulation() -> None:
      result = classify_news_item_content(
          headline="SEC Delays Tokenized Stocks Innovation Exemption Amid Concerns",
          summary="The SEC delayed a tokenized stocks exemption framework.",
          source_domain="decrypt.co",
          fact_event_types=["regulatory"],
      )

      assert result.content_class == "regulation"
      assert "tokenized_stocks" in result.content_tags

  def test_classifies_empty_yahoo_price_target_as_analyst_rating_low_signal() -> None:
      result = classify_news_item_content(
          headline="Morgan Stanley resets PANW stock price target on demand trends",
          summary="",
          source_domain="finance.yahoo.com",
          fact_event_types=[],
      )

      assert result.content_class == "analyst_rating"
      assert "low_context" in result.content_tags
  ```

- [ ] **Step 2: Run classifier tests and confirm failure**
  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_content_classification.py -q
  ```
  Expected: import failure.

- [ ] **Step 3: Define content classification types**
  ```python
  from dataclasses import dataclass

  CONTENT_CLASSES = (
      "crypto_market",
      "macro_policy",
      "rates_fed",
      "regulation",
      "etf_fund_flow",
      "exchange_listing",
      "security_hack",
      "protocol_development",
      "equity_earnings",
      "analyst_rating",
      "ai_semiconductors",
      "energy_geopolitics",
      "consumer_macro",
      "market_structure",
      "low_signal",
  )

  @dataclass(frozen=True, slots=True)
  class NewsContentClassification:
      content_class: str
      content_tags: tuple[str, ...]
      confidence: float
      method: str
  ```

- [ ] **Step 4: Implement deterministic classifier**
  ```python
  def classify_news_item_content(
      *,
      headline: str,
      summary: str,
      source_domain: str,
      fact_event_types: list[str],
  ) -> NewsContentClassification:
      text = f"{headline} {summary}".lower()
      event_types = {str(value).lower() for value in fact_event_types}

      if "regulatory" in event_types or "sec" in text or "cftc" in text:
          return NewsContentClassification("regulation", _tags(text, ("sec", "tokenized_stocks")), 0.82, "rules_v1")
      if "etf" in event_types or "etf" in text:
          return NewsContentClassification("etf_fund_flow", _tags(text, ("bitcoin_etf", "ethereum_etf")), 0.78, "rules_v1")
      if "listing" in event_types or "lists " in text or "delisting" in text:
          return NewsContentClassification("exchange_listing", _tags(text, ("listing", "delisting")), 0.78, "rules_v1")
      if "hack" in event_types or "malware" in text or "exploit" in text:
          return NewsContentClassification("security_hack", _tags(text, ("malware", "exploit")), 0.8, "rules_v1")
      if "fed" in text or "rate hike" in text or "rate cut" in text:
          return NewsContentClassification("rates_fed", _tags(text, ("fed", "rates")), 0.74, "rules_v1")
      if "oil" in text or "hormuz" in text or "wti" in text:
          return NewsContentClassification("energy_geopolitics", _tags(text, ("oil", "hormuz")), 0.72, "rules_v1")
      if "price target" in text or "raises its price target" in text or "downgrade" in text:
          return NewsContentClassification("analyst_rating", _tags(text, ("price_target", "low_context")), 0.68, "rules_v1")
      if "earnings" in text or "q1 2026" in text:
          return NewsContentClassification("equity_earnings", _tags(text, ("earnings", "low_context")), 0.66, "rules_v1")
      if "nvidia" in text or "semiconductor" in text or "ai" in text:
          return NewsContentClassification("ai_semiconductors", _tags(text, ("ai", "semis")), 0.64, "rules_v1")
      return NewsContentClassification("low_signal", ("uncategorized",), 0.4, "rules_v1")
  ```

- [ ] **Step 5: Add migration**
  ```sql
  ALTER TABLE news_items ADD COLUMN IF NOT EXISTS content_class TEXT NOT NULL DEFAULT 'low_signal';
  ALTER TABLE news_items ADD COLUMN IF NOT EXISTS content_tags_json JSONB NOT NULL DEFAULT '[]'::jsonb;
  ALTER TABLE news_items ADD COLUMN IF NOT EXISTS content_classification_json JSONB NOT NULL DEFAULT '{}'::jsonb;
  ALTER TABLE news_page_rows ADD COLUMN IF NOT EXISTS content_class TEXT NOT NULL DEFAULT 'low_signal';
  ALTER TABLE news_page_rows ADD COLUMN IF NOT EXISTS content_tags_json JSONB NOT NULL DEFAULT '[]'::jsonb;
  CREATE INDEX IF NOT EXISTS idx_news_items_content_class_time
    ON news_items(content_class, published_at_ms DESC);
  CREATE INDEX IF NOT EXISTS idx_news_page_rows_content_class_time
    ON news_page_rows(content_class, latest_at_ms DESC);
  ```

- [ ] **Step 6: Persist classification during item processing and catch-up**
  ```python
  classification = classify_news_item_content(
      headline=str(item_payload.get("title") or ""),
      summary=str(item_payload.get("summary") or ""),
      source_domain=str(item_payload.get("source_domain") or ""),
      fact_event_types=[candidate.event_type for candidate in fact_candidates],
  )
  repos.news.update_item_content_classification(
      news_item_id=news_item_id,
      content_class=classification.content_class,
      content_tags=classification.content_tags,
      classification_payload={
          "confidence": classification.confidence,
          "method": classification.method,
      },
  )
  ```

  Extend the worker claim query so already-processed items are eligible for a one-time classification catch-up when `content_classification_json = '{}'::jsonb`:
  ```sql
  WHERE lifecycle_status IN ('raw', 'process_failed')
     OR (
       lifecycle_status IN ('processed', 'attention')
       AND content_classification_json = '{}'::jsonb
     )
  ```

- [ ] **Step 7: Backfill existing rows through normal worker catch-up**
  ```bash
  uv run parallax db migrate
  docker compose up -d --build
  sleep 45
  uv run parallax ops worker-status
  docker exec parallax-postgres-1 psql -U parallax_app -d parallax \
    -c "select content_class, count(*) from news_items group by content_class order by count(*) desc;"
  docker exec parallax-postgres-1 psql -U parallax_app -d parallax \
    -c "select content_class, count(*) from news_page_rows group by content_class order by count(*) desc;"
  ```
  Expected: `news_item_process` and `news_page_projection` show successful recent runs, and existing rows are no longer all default `low_signal`.

## Task 3: Project Classification And Extend API Filters

**Files:**
- Modify: `src/parallax/domains/news_intel/services/news_page_projection.py`
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py`
- Modify: `src/parallax/domains/news_intel/queries/news_page_query.py`
- Modify: `src/parallax/app/surfaces/api/routes_news.py`
- Modify: `src/parallax/app/surfaces/api/schemas.py`
- Test: `tests/unit/domains/news_intel/test_news_page_projection.py`
- Test: `tests/unit/test_api_news_contract.py`

- [ ] **Step 1: Add projection test**
  ```python
  def test_page_projection_copies_content_class_and_source_classification():
      row = build_news_page_row(
          item={
              "news_item_id": "n1",
              "title": "SEC delays tokenized stock exemption",
              "summary": "",
              "published_at_ms": 1,
              "source_domain": "decrypt.co",
              "provider_type": "rss",
              "source_role": "specialist_media",
              "trust_tier": "standard",
              "coverage_tags_json": ["crypto_policy"],
              "source_quality_status": "watch",
              "content_class": "regulation",
              "content_tags_json": ["sec", "tokenized_stocks"],
          },
          token_mentions=[],
          fact_candidates=[],
          story=None,
          agent_brief=None,
          computed_at_ms=2,
      )

      assert row["content_class"] == "regulation"
      assert row["content_tags_json"] == ["sec", "tokenized_stocks"]
      assert row["source_json"]["source_quality_status"] == "watch"
  ```

- [ ] **Step 2: Extend page projection payload**
  ```python
  row["content_class"] = str(item.get("content_class") or "low_signal")
  row["content_tags_json"] = _json_list(item.get("content_tags_json"))
  row["source_json"] = {
      "source_id": item.get("source_id"),
      "provider_type": item.get("provider_type"),
      "source_role": item.get("source_role"),
      "trust_tier": item.get("trust_tier"),
      "coverage_tags": _json_list(item.get("coverage_tags_json")),
      "source_quality_status": item.get("source_quality_status"),
  }
  ```

- [ ] **Step 3: Extend repository filters**
  ```sql
  -- content class
  content_class = %s

  -- content tag
  content_tags_json ? %s

  -- decision class
  agent_brief_json ->> 'decision_class' = %s
  ```

- [ ] **Step 4: Extend API query params**
  ```python
  content_class: Annotated[str, Query()] = ""
  content_tag: Annotated[str, Query()] = ""
  decision_class: Annotated[str, Query()] = ""
  provider_type: Annotated[str, Query()] = ""
  source_role: Annotated[str, Query()] = ""
  trust_tier: Annotated[str, Query()] = ""
  coverage_tag: Annotated[str, Query()] = ""
  ```

- [ ] **Step 5: Run API/projection tests**
  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py -q
  uv run pytest tests/unit/test_api_news_contract.py -q
  ```
  Expected: pass.

## Task 4: Redesign `/news` Around Source, Content, And Decision

**Files:**
- Modify: `web/src/shared/model/newsIntel.ts`
- Modify: `web/src/lib/api/client.ts`
- Modify: `web/src/features/news/useNewsPage.ts`
- Modify: `web/src/features/news/newsViewModel.ts`
- Modify: `web/src/features/news/NewsPage.tsx`
- Modify: `web/src/features/news/news.css`
- Modify: `web/src/features/news/newsRows.css`
- Test: `web/tests/component/features/news/NewsPageClassificationFilters.test.tsx`

- [ ] **Step 1: Read frontend guardrails before UI edits**
  ```bash
  sed -n '1,220p' docs/FRONTEND.md
  ```
  Expected: confirm owner CSS remains under `web/src/features/news`.

- [ ] **Step 2: Extend client params**
  ```ts
  export async function fetchNewsRows(params: {
    limit?: number;
    cursor?: string | null;
    direction?: string | null;
    decision_class?: string | null;
    content_class?: string | null;
    content_tag?: string | null;
    provider_type?: string | null;
    source_role?: string | null;
    trust_tier?: string | null;
    coverage_tag?: string | null;
    source?: string | null;
    status?: string | null;
    target?: string | null;
    token?: string | null;
  } = {}): Promise<NewsRowsData> {
    const response = await getApi<NewsRowsData>("/api/news", {
      params: {
        cursor: params.cursor,
        direction: params.direction,
        decision_class: params.decision_class,
        content_class: params.content_class,
        content_tag: params.content_tag,
        provider_type: params.provider_type,
        source_role: params.source_role,
        trust_tier: params.trust_tier,
        coverage_tag: params.coverage_tag,
        limit: params.limit ?? 100,
        source: params.source,
        status: params.status,
        target: params.target,
      },
      token: params.token ?? undefined,
    });
    return { ...response.data, items: response.data.items.map(normalizeNewsRow) };
  }
  ```

- [ ] **Step 3: Add News filter state**
  ```ts
  type NewsFilters = {
    direction: "all" | "bullish" | "bearish" | "mixed" | "neutral";
    decisionClass: "all" | "driver" | "watch" | "context" | "discard";
    contentClass: "all" | "regulation" | "rates_fed" | "energy_geopolitics" | "analyst_rating" | "security_hack" | "low_signal";
    sourceRole: "all" | "official_exchange" | "official_regulator" | "official_protocol" | "specialist_media" | "aggregator" | "social" | "developer_signal";
    trustTier: "all" | "official" | "high" | "standard" | "low";
  };
  ```

- [ ] **Step 4: Replace direction-only controls with three compact control groups**
  - Content tabs: `All`, `Macro/Rates`, `Regulation`, `Crypto`, `Equity`, `Security`, `Low Signal`.
  - Source segmented control: `All`, `Official`, `High`, `Media`, `Aggregator`, `Watch/Degraded`.
  - Decision segmented control: `All`, `Driver`, `Watch`, `Context`, `Discard`.

- [ ] **Step 5: Add row chips**
  Each row must show:
  - `content_class`
  - `source_role`
  - `trust_tier`
  - `source_quality_status`
  - `decision_class`
  - existing `direction`

- [ ] **Step 6: Component test the query params**
  ```ts
  it("passes content and source filters to fetchNewsRows", async () => {
    render(<NewsPage token="token" />);
    await user.click(screen.getByRole("tab", { name: /Regulation/i }));
    await user.click(screen.getByRole("button", { name: /High/i }));
    await user.click(screen.getByRole("button", { name: /Driver/i }));

    expect(fetchNewsRows).toHaveBeenLastCalledWith(
      expect.objectContaining({
        content_class: "regulation",
        trust_tier: "high",
        decision_class: "driver",
      }),
    );
  });
  ```

- [ ] **Step 7: Run frontend checks**
  ```bash
  cd web
  npm run lint
  npm test -- --run NewsPageClassificationFilters
  ```
  Expected: pass.

- [ ] **Step 8: Browser verify**
  ```bash
  docker compose up -d --build
  ```
  Then open `http://127.0.0.1:8765/news` and verify:
  - page exits loading state;
  - filters do not overlap on desktop or mobile;
  - row chips are visible;
  - changing filters updates rows without console errors.

## Task 5: Provider Capability Diagnostics And Runtime Source Hygiene

**Files:**
- Modify: `src/parallax/integrations/news_feeds/provider_registry.py`
- Modify: `src/parallax/app/runtime/provider_wiring/news.py`
- Modify: `src/parallax/app/surfaces/api/routes_news.py`
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py`
- Modify: `docs/CONTRACTS.md`
- Test: `tests/unit/integrations/news_feeds/test_provider_registry.py`
- Test: `tests/unit/test_api_news_contract.py`

- [ ] **Step 1: Add provider capability API contract**
  ```json
  {
    "supported_provider_types": ["rss", "atom", "json_feed", "cryptopanic"],
    "configured_provider_types": ["rss"],
    "unsupported_configured_provider_types": [],
    "sources_missing_coverage_tags": ["coindesk", "yahoo-finance"]
  }
  ```

- [ ] **Step 2: Add registry method**
  ```python
  def supported_provider_types(self) -> tuple[str, ...]:
      return tuple(sorted(self._providers.keys()))
  ```

- [ ] **Step 3: Extend `/api/news/sources/status`**
  Add `provider_capabilities` and `source_hygiene` to the response.

- [ ] **Step 4: Add warning-level diagnostics**
  Runtime should report:
  - configured source has unsupported `provider_type`;
  - enabled source has empty `coverage_tags`;
  - official source role has empty `authority_scope`;
  - source quality status is `degraded`.

- [ ] **Step 5: Tests**
  ```bash
  uv run pytest tests/unit/integrations/news_feeds/test_provider_registry.py -q
  uv run pytest tests/unit/test_api_news_contract.py -q
  ```
  Expected: pass.

## Task 6: Source Config And Provider Wave Plan

**Files:**
- Modify: `docs/WORKERS.md`
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/ARCHITECTURE.md`
- Optionally modify operator-owned `~/.parallax/config.yaml` only after explicit operator approval.

- [ ] **Step 1: Document current supported provider set**
  Supported now:
  - `rss`
  - `atom`
  - `json_feed`
  - `cryptopanic`

- [ ] **Step 2: Document staged provider waves**
  Wave 1:
  - Add/enable `cryptopanic` if credential exists.
  - Keep as `aggregator` or `specialist_media`, not authority source.

  Wave 2:
  - Add official RSS/manual API feeds for exchanges, regulators, protocols, and issuers.
  - These are the only feeds eligible for `accepted` fact candidates after authority-scope validation.

  Wave 3:
  - Add OpenBB/macro/equity source adapters if needed.
  - Keep equity event ownership boundaries clear with `equity_event_intel`.

  Wave 4:
  - Add social/community/developer context sources: Telegram, Reddit/HN, GitHub, X/Twitter context.
  - Store replies/comments in `news_context_items`, not `news_items.body_text`.

- [ ] **Step 3: Provide safe operator checklist**
  ```bash
  uv run parallax config
  curl -sS -H "Authorization: Bearer $GMGN_API_TOKEN" \
    http://127.0.0.1:8765/api/news/sources/status | jq '.data.provider_capabilities'
  ```
  Expected: operator sees supported vs configured provider types without secrets.

## Task 7: Verification And Completion Gates

**Files:**
- Modify: `docs/superpowers/plans/active/2026-05-23-news-intel-root-fix-plan-cn.md`
- Optionally create verification file after implementation:
  `docs/superpowers/plans/active/2026-05-23-news-intel-root-fix-verification-cn.md`

- [ ] **Step 1: Backend tests**
  ```bash
  uv run ruff check .
  uv run pytest tests/unit/domains/news_intel -q
  uv run pytest tests/integration/domains/news_intel -q
  uv run pytest tests/unit/test_api_news_contract.py -q
  uv run pytest tests/architecture -q
  ```
  Expected: pass.

- [ ] **Step 2: Frontend tests**
  ```bash
  cd web
  npm run lint
  npm test -- --run
  ```
  Expected: pass.

- [ ] **Step 3: Docker verification**
  ```bash
  docker compose up -d --build
  docker compose ps
  curl -sS http://127.0.0.1:8765/healthz
  curl -sS -H "Authorization: Bearer $GMGN_API_TOKEN" \
    'http://127.0.0.1:8765/api/news?limit=100' \
    -w '\nstatus=%{http_code} time=%{time_total}\n' \
    -o /tmp/news-api-verified.json
  ```
  Expected:
  - app container healthy;
  - `/healthz` returns `ok`;
  - `/api/news` returns `status=200`;
  - warm latency target under 1 second.

- [ ] **Step 4: Browser verification**
  Use the in-app browser or Playwright to verify:
  - `http://127.0.0.1:8765/news` exits loading state;
  - content/source/decision filters work;
  - no console errors;
  - mobile width does not overlap controls or row text.

- [ ] **Step 5: Log scan**
  ```bash
  docker compose logs --tail=500 app | rg -i "api/news|QueryCanceled|statement timeout|Exception in ASGI|unsupported news source provider"
  ```
  Expected: no `/api/news` `QueryCanceled` or ASGI exception.

- [ ] **Step 6: Update docs**
  Ensure `docs/ARCHITECTURE.md`, `docs/CONTRACTS.md`, `docs/WORKERS.md`, and `src/parallax/domains/news_intel/ARCHITECTURE.md` describe:
  - source/content/decision axes;
  - provider capability diagnostics;
  - normal `/api/news` projected-only read path;
  - provider waves and authority constraints.

## Risks And Guardrails

- Source classification is not content classification. Do not make Yahoo or Cointelegraph tags decide item categories.
- `accepted` fact status must remain impossible for specialist media and aggregators unless a separate corroboration spec is approved.
- Do not add full article crawling in this plan. It changes legal, provider-cost, and latency assumptions.
- Do not add social replies into `news_items.body_text`. Use `news_context_items`.
- Do not bypass frontend CSS architecture harness after editing `web/src/features/news`.
- If `/readyz` remains red because of non-News workers, record it separately; do not hide News-specific failures behind global readiness noise.

## Definition Of Done

- `/api/news?limit=100` returns consistently without statement timeout under Docker runtime.
- `/news` exits loading state and renders a classified, filterable desk.
- Every News row has source-class fields and item-level `content_class`.
- API supports filters for `provider_type`, `source_role`, `trust_tier`, `coverage_tag`, `content_class`, `content_tag`, `decision_class`, `direction`, and `status`.
- Source status endpoint shows supported vs configured provider types and source hygiene warnings.
- Existing RSS sources continue ingesting without regression.
- Tests and browser verification are recorded before merge.
