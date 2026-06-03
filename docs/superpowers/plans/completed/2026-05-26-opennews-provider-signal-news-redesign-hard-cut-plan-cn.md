# OpenNews Provider Signal News Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `/news` 从“分类/agent 调试台”重构成以 6551/OpenNews provider fact 为主的紧凑新闻磁带，并硬切掉旧兼容路径、重复 agent 分析和前端别名 fallback。

**Architecture:** 继续保持 Kappa/CQRS：OpenNews WebSocket/REST payload 是输入，PostgreSQL material facts 是唯一业务真相，`news_page_rows` 是可重建 read model。新增 item 级 `provider_signal_json` 和 `provider_token_impacts_json` 作为 provider 原生事实；`news_fetch` 是唯一 writer，`news_item_process` 只做 token identity 补全和页面投影触发，`news_item_brief` 对 OpenNews provider signal 不再执行 LLM。API 对前端只暴露新的硬切 contract：`signal`、`token_impacts`、`token_lanes`、`fact_lanes`，不再暴露 `_json` 兼容字段或 unprojected fallback。

**Tech Stack:** Python 3.13, PostgreSQL/Alembic, psycopg3 repositories, existing News Intel workers, FastAPI, React 19, TypeScript, TanStack Query, owner CSS under `web/src/features/news`, pytest, Vitest, Playwright/browser verification.

---

## Product Contract

- `/news` 主视图是 compact tape + inspector。
- 一级导航只有 `有 Token` / `无 Token`。
- 二级筛选只有 `全部` / `利好` / `利空` / `中性` / `≥70` / search。
- 一条新闻永远只占一行；多个 token 不拆成多行。
- 列表行结构：`time | sentiment pill | readable headline/summary | token chips`。
- 列表不再重复右侧 score；总分只在 sentiment pill 出现，per-token 分数只在 token chip 和 inspector 出现。
- 6551/OpenNews 的 `aiRating` 和 `coins[]` 是 provider fact。OpenNews item 默认不跑 `news_item_brief` agent。
- 没有 `aiRating` 的 OpenNews WS 初始 push 显示为 `partial`/`中性`/`waiting aiRating`，等待后续 `news.ai_update` 或下一轮 fetch 更新。
- 非 OpenNews 来源如果未来重新启用，可以通过同一个 `signal.source = "agent"` contract 显示 agent fallback；这不是兼容 alias，而是统一新 contract。

## Hard-Cut Removals

- Remove API `include_unprojected` parameter and repository `_list_news_page_rows_with_unprojected_fallback`.
- Remove frontend fallback reads from `token_lanes_json`, `fact_lanes_json`, `agent_brief_json`, `agent_status`, and `agent_brief_status`.
- Remove `CONTENT_DOMAIN_OPTIONS`, `CONTENT_TAG_OPTIONS`, `SOURCE_OPTIONS`, `DECISION_OPTIONS`, `NewsFilterGroup`, and `NewsDirectionTabs` from `web/src/features/news/NewsPage.tsx`.
- Remove queue summary metrics based on `agent_brief` readiness/drivers/gaps.
- Remove queue copy that calls provider/agent pending states `Agent brief` for OpenNews provider-sourced rows.
- Remove old CSS selectors that only support the retired wide five-column debug table: `.news-filter-panel`, `.news-filter-group`, `.news-feed-head`, `.news-instrument-cell`, `.news-route-cell`, `.news-next-cell` if no detail view still uses them.

## File Structure

### Create

- `src/parallax/platform/db/alembic/versions/20260526_0090_opennews_provider_signal.py`
  Adds provider signal material facts to `news_items` and indexes needed by token/sentiment filters.
- `src/parallax/domains/news_intel/services/opennews_provider_signal.py`
  Pure normalization from OpenNews raw payload to provider signal and token impact facts.
- `tests/unit/domains/news_intel/test_opennews_provider_signal.py`
  Unit coverage for `aiRating`, `coins[]`, partial WS pushes, timestamp-preserving raw payloads.
- `web/src/features/news/model/newsSignalViewModel.ts`
  Frontend pure helpers for labels, tone classes, score formatting, token count, and tab counts.
- `web/src/features/news/ui/NewsTape.tsx`
  Compact list/tape component.
- `web/src/features/news/ui/NewsInspector.tsx`
  Selected item inspector.
- `web/src/features/news/ui/newsTape.css`
  Owner CSS for compact tape and inspector, namespace `.news-tape-*`.
- `web/tests/unit/features/news/newsSignalViewModel.test.ts`
  Pure frontend model tests.
- `web/tests/component/features/news/NewsTape.test.tsx`
  Component tests for compact rows, token chips, and no duplicate score column.

### Modify

- `src/parallax/domains/news_intel/types/source_provider.py`
- `src/parallax/integrations/news_feeds/opennews_client.py`
- `src/parallax/domains/news_intel/runtime/news_fetch_worker.py`
- `src/parallax/domains/news_intel/runtime/news_item_process_worker.py`
- `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py`
- `src/parallax/domains/news_intel/repositories/news_repository.py`
- `src/parallax/domains/news_intel/services/news_page_projection.py`
- `src/parallax/domains/news_intel/queries/news_page_query.py`
- `src/parallax/app/surfaces/api/routes_news.py`
- `web/src/shared/model/newsIntel.ts`
- `web/src/lib/api/client.ts`
- `web/src/shared/query/queryKeys.ts`
- `web/src/features/news/useNewsPage.ts`
- `web/src/features/news/NewsPage.tsx`
- `web/src/features/news/news.css`
- `web/src/features/news/newsRows.css`
- `docs/FRONTEND.md`
- `docs/CONTRACTS.md`
- `docs/WORKERS.md`

### Do Not Modify

- Do not touch Token Radar, Pulse Lab, or asset market projection behavior.
- Do not store OpenNews API tokens in repo files.
- Do not re-enable RSS/news sources in `~/.parallax/config.yaml` as part of this implementation.

## Task 1: Add Provider Signal Normalization

**Files:**
- Create: `src/parallax/domains/news_intel/services/opennews_provider_signal.py`
- Modify: `src/parallax/domains/news_intel/types/source_provider.py`
- Modify: `src/parallax/integrations/news_feeds/opennews_client.py`
- Test: `tests/unit/domains/news_intel/test_opennews_provider_signal.py`
- Test: `tests/unit/integrations/news_feeds/test_opennews_client.py`

- [ ] **Step 1: Write failing provider-signal unit tests**

  Add tests covering ready `aiRating`, per-token `coins[]`, and partial pushes:

  ```python
  from parallax.domains.news_intel.services.opennews_provider_signal import (
      provider_signal_from_opennews_payload,
      provider_token_impacts_from_opennews_payload,
  )


  def test_opennews_provider_signal_reads_ai_rating() -> None:
      payload = {
          "id": 2367422,
          "newsType": "6551News",
          "engineType": "news",
          "aiRating": {
              "status": "done",
              "signal": "short",
              "score": 75,
              "grade": "A",
              "summary": "中文摘要",
              "enSummary": "English summary",
          },
      }

      assert provider_signal_from_opennews_payload(payload) == {
          "source": "provider",
          "provider": "opennews",
          "status": "ready",
          "direction": "bearish",
          "label_zh": "利空",
          "signal": "short",
          "score": 75,
          "grade": "A",
          "summary_zh": "中文摘要",
          "summary_en": "English summary",
          "method": "opennews.aiRating",
      }


  def test_opennews_provider_token_impacts_preserve_coin_scores() -> None:
      payload = {
          "coins": [
              {"symbol": "BTC", "market_type": "cex", "score": 75, "signal": "short", "grade": "A"},
              {"symbol": "ETH", "market_type": "cex", "score": 70, "signal": "long", "grade": "B+"},
          ]
      }

      assert provider_token_impacts_from_opennews_payload(payload) == [
          {"symbol": "BTC", "market_type": "cex", "score": 75, "signal": "short", "grade": "A"},
          {"symbol": "ETH", "market_type": "cex", "score": 70, "signal": "long", "grade": "B+"},
      ]


  def test_opennews_provider_signal_marks_missing_ai_rating_as_partial() -> None:
      payload = {"newsType": "6551News", "engineType": "news", "coins": [{"symbol": "EX"}]}

      assert provider_signal_from_opennews_payload(payload) == {
          "source": "provider",
          "provider": "opennews",
          "status": "partial",
          "direction": "neutral",
          "label_zh": "中性",
          "signal": None,
          "score": None,
          "grade": None,
          "summary_zh": None,
          "summary_en": None,
          "method": "opennews.partial",
      }
  ```

- [ ] **Step 2: Run tests to verify RED**

  ```bash
  uv run pytest tests/unit/domains/news_intel/test_opennews_provider_signal.py -q
  ```

  Expected: fails because `opennews_provider_signal.py` does not exist.

- [ ] **Step 3: Implement pure normalizer**

  Implement:

  ```python
  from __future__ import annotations

  from collections.abc import Mapping
  from typing import Any


  def provider_signal_from_opennews_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
      ai_rating = payload.get("aiRating") if isinstance(payload.get("aiRating"), Mapping) else {}
      signal = _optional_text(ai_rating.get("signal"))
      score = _optional_int(ai_rating.get("score"))
      grade = _optional_text(ai_rating.get("grade"))
      status = _optional_text(ai_rating.get("status"))
      if signal or score is not None or grade:
          return {
              "source": "provider",
              "provider": "opennews",
              "status": "ready" if status == "done" or score is not None else "partial",
              "direction": _direction(signal),
              "label_zh": _label_zh(signal),
              "signal": signal,
              "score": score,
              "grade": grade,
              "summary_zh": _optional_text(ai_rating.get("summary")),
              "summary_en": _optional_text(ai_rating.get("enSummary")),
              "method": "opennews.aiRating",
          }
      return {
          "source": "provider",
          "provider": "opennews",
          "status": "partial",
          "direction": "neutral",
          "label_zh": "中性",
          "signal": None,
          "score": None,
          "grade": None,
          "summary_zh": None,
          "summary_en": None,
          "method": "opennews.partial",
      }


  def provider_token_impacts_from_opennews_payload(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
      coins = payload.get("coins")
      if not isinstance(coins, list):
          return []
      impacts: list[dict[str, Any]] = []
      for coin in coins:
          if not isinstance(coin, Mapping):
              continue
          symbol = _optional_text(coin.get("symbol"))
          if not symbol:
              continue
          impacts.append(
              {
                  "symbol": symbol.upper(),
                  "market_type": _optional_text(coin.get("market_type")),
                  "score": _optional_int(coin.get("score")),
                  "signal": _optional_text(coin.get("signal")),
                  "grade": _optional_text(coin.get("grade")),
              }
          )
      return impacts


  def _direction(signal: str | None) -> str:
      if signal == "long":
          return "bullish"
      if signal == "short":
          return "bearish"
      return "neutral"


  def _label_zh(signal: str | None) -> str:
      if signal == "long":
          return "利好"
      if signal == "short":
          return "利空"
      return "中性"


  def _optional_text(value: Any) -> str | None:
      text = str(value or "").strip()
      return text or None


  def _optional_int(value: Any) -> int | None:
      if value is None:
          return None
      try:
          return int(value)
      except (TypeError, ValueError):
          return None
  ```

- [ ] **Step 4: Extend provider observation shape**

  Add optional fields to `NewsProviderObservation`:

  ```python
  provider_signal: dict[str, Any] | None = None
  provider_token_impacts: list[dict[str, Any]] = field(default_factory=list)
  ```

- [ ] **Step 5: Populate OpenNews observation facts**

  In `OpenNewsFeedClient._entry_from_params`, add normalized fields to the entry:

  ```python
  "provider_signal": provider_signal_from_opennews_payload(params),
  "provider_token_impacts": provider_token_impacts_from_opennews_payload(params),
  ```

  In the registry/provider conversion path that builds `NewsProviderObservation`, pass those two fields through from entry/raw payload.

- [ ] **Step 6: Run focused tests**

  ```bash
  uv run pytest tests/unit/domains/news_intel/test_opennews_provider_signal.py tests/unit/integrations/news_feeds/test_opennews_client.py -q
  uv run ruff check src/parallax/domains/news_intel/services/opennews_provider_signal.py src/parallax/integrations/news_feeds/opennews_client.py tests/unit/domains/news_intel/test_opennews_provider_signal.py tests/unit/integrations/news_feeds/test_opennews_client.py
  ```

  Expected: tests pass and ruff is clean.

## Task 2: Persist Provider Signal Facts

**Files:**
- Create: `src/parallax/platform/db/alembic/versions/20260526_0090_opennews_provider_signal.py`
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py`
- Modify: `src/parallax/domains/news_intel/runtime/news_fetch_worker.py`
- Test: `tests/integration/domains/news_intel/test_news_repository.py`
- Test: `tests/unit/domains/news_intel/test_news_workers.py`
- Test: `tests/unit/test_postgres_schema.py`

- [ ] **Step 1: Write failing repository test**

  Add an integration test proving provider signal and token impacts survive ingest:

  ```python
  def test_upsert_news_item_persists_provider_signal_and_token_impacts(tmp_path) -> None:
      conn = make_test_conn(tmp_path)
      repo = NewsRepository(conn)
      source_id = seed_news_source(conn, provider_type="opennews")
      provider = repo.upsert_provider_item(
          source_id=source_id,
          fetch_run_id="run-1",
          source_item_key="2367422",
          canonical_url="https://example.com/news/2367422",
          payload_hash="hash",
          raw_payload={"id": 2367422},
          fetched_at_ms=1_779_000_000_000,
      )

      row = repo.upsert_news_item(
          provider_item_id=provider["provider_item_id"],
          source_id=source_id,
          source_domain="6551.io",
          canonical_url="https://example.com/news/2367422",
          title="BTC headline",
          fetched_at_ms=1_779_000_000_000,
          content_hash="content-hash",
          title_fingerprint="btc-headline",
          now_ms=1_779_000_000_000,
          provider_signal={"source": "provider", "provider": "opennews", "status": "ready", "direction": "bullish"},
          provider_token_impacts=[{"symbol": "BTC", "score": 82, "signal": "long", "grade": "A"}],
      )

      loaded = repo.get_news_item_detail(news_item_id=row["news_item_id"])
      assert loaded["provider_signal"] == {
          "source": "provider",
          "provider": "opennews",
          "status": "ready",
          "direction": "bullish",
      }
      assert loaded["provider_token_impacts"] == [
          {"symbol": "BTC", "score": 82, "signal": "long", "grade": "A"}
      ]
  ```

- [ ] **Step 2: Run test to verify RED**

  ```bash
  uv run pytest tests/integration/domains/news_intel/test_news_repository.py::test_upsert_news_item_persists_provider_signal_and_token_impacts -q
  ```

  Expected: fails on missing columns/arguments.

- [ ] **Step 3: Add Alembic migration**

  Add nullable JSONB columns:

  ```python
  op.add_column("news_items", sa.Column("provider_signal_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")))
  op.add_column("news_items", sa.Column("provider_token_impacts_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")))
  op.create_index(
      "ix_news_items_provider_signal_direction",
      "news_items",
      [sa.text("(provider_signal_json ->> 'direction')")],
      postgresql_where=sa.text("provider_signal_json <> '{}'::jsonb"),
  )
  ```

- [ ] **Step 4: Extend repository upsert/detail**

  Update `NewsRepository.upsert_news_item` signature:

  ```python
  provider_signal: Mapping[str, Any] | None = None,
  provider_token_impacts: Sequence[Mapping[str, Any]] | None = None,
  ```

  Persist the fields in INSERT/UPDATE:

  ```sql
  provider_signal_json = EXCLUDED.provider_signal_json,
  provider_token_impacts_json = EXCLUDED.provider_token_impacts_json,
  ```

  Include fields in `get_news_item_detail` response:

  ```python
  "provider_signal": _json_dict(item.get("provider_signal_json")),
  "provider_token_impacts": _json_list(item.get("provider_token_impacts_json")),
  ```

- [ ] **Step 5: Wire fetch worker persistence**

  In `NewsFetchWorker._persist_entries`, pass observation fields:

  ```python
  provider_signal=observation.provider_signal,
  provider_token_impacts=observation.provider_token_impacts,
  ```

- [ ] **Step 6: Add schema guard**

  In `tests/unit/test_postgres_schema.py`, assert both new columns exist and have JSONB type.

- [ ] **Step 7: Run persistence tests**

  ```bash
  uv run pytest tests/integration/domains/news_intel/test_news_repository.py::test_upsert_news_item_persists_provider_signal_and_token_impacts tests/unit/domains/news_intel/test_news_workers.py tests/unit/test_postgres_schema.py -q
  ```

  Expected: provider signal facts persist and fetch worker tests still pass.

## Task 3: Build Provider Token Lanes And Skip OpenNews Agent Briefs

**Files:**
- Modify: `src/parallax/domains/news_intel/runtime/news_item_process_worker.py`
- Modify: `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py`
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py`
- Modify: `src/parallax/domains/news_intel/services/news_page_projection.py`
- Test: `tests/unit/domains/news_intel/test_news_workers.py`
- Test: `tests/unit/domains/news_intel/test_news_page_projection.py`

- [ ] **Step 1: Write failing process-worker test**

  Add a test where OpenNews provider token impacts are present and no `brief_input` dirty target is enqueued:

  ```python
  def test_news_item_process_uses_opennews_provider_tokens_and_skips_brief_input() -> None:
      repo = FakeNewsRepo(
          items=[
              {
                  "news_item_id": "news-1",
                  "source_id": "opennews-realtime",
                  "provider_type": "opennews",
                  "source_domain": "6551.io",
                  "title": "BTC headline",
                  "summary": "",
                  "body_text": "",
                  "provider_signal_json": {
                      "source": "provider",
                      "provider": "opennews",
                      "status": "ready",
                      "direction": "bullish",
                  },
                  "provider_token_impacts_json": [
                      {"symbol": "BTC", "score": 82, "signal": "long", "grade": "A"}
                  ],
              }
          ]
      )

      worker = NewsItemProcessWorker(
          name="news_item_process",
          db=FakeDB(repo),
          settings=SimpleNamespace(batch_size=10),
          identity_lookup=FakeIdentityLookup(symbols={"BTC": resolved_identity("BTC")}),
      )

      result = worker.run_once_sync(now_ms=1_779_000_000_000)

      assert result.processed == 1
      assert repo.replaced_token_mentions[0][0].observed_symbol == "BTC"
      assert [target["projection_name"] for target in repo.enqueued_targets] == [
          "story",
          "page",
          "source_quality",
          "source_quality",
      ]
  ```

- [ ] **Step 2: Run test to verify RED**

  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_workers.py::test_news_item_process_uses_opennews_provider_tokens_and_skips_brief_input -q
  ```

  Expected: fails because current worker always enqueues `brief_input`.

- [ ] **Step 3: Include provider fields in unprocessed loader**

  Add these selected fields in `list_unprocessed_items`:

  ```sql
  claimed.provider_signal_json,
  claimed.provider_token_impacts_json,
  sources.provider_type,
  ```

- [ ] **Step 4: Generate token mentions from provider impacts**

  In `NewsItemProcessWorker`, build entities/mentions from provider impacts first:

  ```python
  provider_impacts = _json_list(item_payload.get("provider_token_impacts_json"))
  if provider_impacts:
      entities = _entities_from_provider_impacts(news_item_id=news_item_id, impacts=provider_impacts, now_ms=now)
  else:
      entities = extract_news_entities(
          news_item_id=news_item_id,
          title=_text(item_payload, "title"),
          summary=_text(item_payload, "summary"),
          body_text=_text(item_payload, "body_text"),
          now_ms=now,
      )
  ```

  Keep identity lookup; provider coin symbols are observed symbols, not canonical identity by themselves.

- [ ] **Step 5: Skip `brief_input` for OpenNews provider rows**

  Add helper:

  ```python
  def _needs_agent_brief(item: Mapping[str, Any]) -> bool:
      provider_type = str(item.get("provider_type") or "")
      provider_signal = _json_dict(item.get("provider_signal_json"))
      if provider_type == "opennews" and provider_signal.get("source") == "provider":
          return False
      return True
  ```

  Build dirty targets without `brief_input` when false.

- [ ] **Step 6: Add brief worker queue cleanup guard**

  In `NewsItemBriefWorker.run_once`, before `_process_candidate`, skip candidates whose item has `provider_signal_json.source == "provider"` and mark claimed target done. This handles stale `brief_input` targets already in DB.

  Expected notes increment:

  ```python
  notes["provider_signal_skip"] += 1
  ```

- [ ] **Step 7: Extend page projection token lanes**

  In `build_news_page_row`, pass `provider_token_impacts` from item and merge into token lanes:

  ```python
  token_lanes = _merge_provider_impacts(
      [_token_lane(row) for row in token_mentions],
      _json_list(item.get("provider_token_impacts_json")),
  )
  ```

  Resulting lane includes:

  ```python
  {
      "symbol": "BTC",
      "lane": "resolved",
      "target_id": "token:btc",
      "provider_signal": "long",
      "provider_score": 82,
      "provider_grade": "A",
      "market_type": "cex",
  }
  ```

- [ ] **Step 8: Run worker/projection tests**

  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_workers.py tests/unit/domains/news_intel/test_news_page_projection.py -q
  ```

  Expected: OpenNews rows skip agent brief and page rows expose provider token impact fields.

## Task 4: Hard-Cut API Contract

**Files:**
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py`
- Modify: `src/parallax/domains/news_intel/queries/news_page_query.py`
- Modify: `src/parallax/app/surfaces/api/routes_news.py`
- Modify: `src/parallax/domains/news_intel/services/news_page_projection.py`
- Test: `tests/unit/test_api_news_contract.py`
- Test: `tests/unit/domains/news_intel/test_news_page_projection.py`

- [ ] **Step 1: Write failing API contract test**

  Update contract tests so `/api/news` rows use only the new response shape:

  ```python
  def test_news_api_rows_expose_signal_without_compatibility_json_aliases(client, auth_headers) -> None:
      response = client.get("/api/news?limit=1", headers=auth_headers)
      assert response.status_code == 200
      row = response.json()["data"]["items"][0]

      assert "signal" in row
      assert "token_impacts" in row
      assert "token_lanes" in row
      assert "fact_lanes" in row
      assert "token_lanes_json" not in row
      assert "fact_lanes_json" not in row
      assert "agent_brief_json" not in row
      assert "agent_status" not in row
  ```

- [ ] **Step 2: Run test to verify RED**

  ```bash
  uv run pytest tests/unit/test_api_news_contract.py::test_news_api_rows_expose_signal_without_compatibility_json_aliases -q
  ```

  Expected: fails because current repository returns `_json` aliases.

- [ ] **Step 3: Remove unprojected fallback**

  Delete `include_unprojected` from:

  - `routes_news.list_news`
  - `NewsPageQuery.list_news`
  - `NewsRepository.list_news_page_rows`

  Delete `_list_news_page_rows_with_unprojected_fallback`.

- [ ] **Step 4: Project new signal object**

  Add `signal` and `token_impacts` to `build_news_page_row`:

  ```python
  provider_signal = _json_object(item.get("provider_signal_json"))
  agent_signal = _compact_agent_brief(agent_brief)
  signal = _page_signal(provider_signal=provider_signal, agent_signal=agent_signal)
  token_impacts = _json_list(item.get("provider_token_impacts_json"))
  ```

  `signal` shape:

  ```python
  {
      "source": "provider",
      "provider": "opennews",
      "status": "ready",
      "direction": "bullish",
      "label_zh": "利好",
      "score": 82,
      "grade": "A",
      "summary_zh": "资金流入继续增强。",
      "method": "opennews.aiRating",
  }
  ```

- [ ] **Step 5: Return canonical names only**

  In repository row selection, alias DB JSON columns to canonical response names:

  ```sql
  token_lanes_json AS token_lanes,
  fact_lanes_json AS fact_lanes,
  agent_brief_json AS agent_brief,
  ```

  Then compact response dicts to remove:

  ```python
  for key in ("token_lanes_json", "fact_lanes_json", "agent_brief_json", "agent_status", "agent_brief_status"):
      row.pop(key, None)
  ```

- [ ] **Step 6: Filter by token presence and provider signal**

  Replace direction/decision filters with hard-cut filters:

  - `has_token=true|false`
  - `signal=bullish|bearish|neutral`
  - `min_score=<int>`
  - `q=<text>`

  Implement SQL against read-model JSON:

  ```sql
  jsonb_array_length(token_lanes_json) > 0
  signal_json ->> 'direction' = %s
  (signal_json ->> 'score')::int >= %s
  ```

  If `signal_json` is not stored in `news_page_rows` yet, add it to the same migration or compute from `agent_brief_json`/`provider_signal_json` during row replacement.

- [ ] **Step 7: Run API/projection tests**

  ```bash
  uv run pytest tests/unit/test_api_news_contract.py tests/unit/domains/news_intel/test_news_page_projection.py -q
  ```

  Expected: API exposes canonical hard-cut shape only.

## Task 5: Rewrite Frontend Types And Client Without Compatibility Aliases

**Files:**
- Modify: `web/src/shared/model/newsIntel.ts`
- Modify: `web/src/lib/api/client.ts`
- Modify: `web/src/shared/query/queryKeys.ts`
- Modify: `web/src/features/news/useNewsPage.ts`
- Test: `web/tests/unit/features/news/useNewsPage.test.ts`

- [ ] **Step 1: Write failing frontend unit test**

  Add a test proving `_json` aliases are ignored/unsupported:

  ```tsx
  it("normalizes news rows from the hard-cut signal contract only", async () => {
    server.use(
      http.get("/api/news", () =>
        HttpResponse.json({
          ok: true,
          data: {
            items: [
              {
                row_id: "row-1",
                news_item_id: "news-1",
                lifecycle_status: "processed",
                headline: "BTC headline",
                latest_at_ms: 1779000000000,
                signal: { source: "provider", status: "ready", direction: "bullish", label_zh: "利好", score: 82, grade: "A" },
                token_lanes: [{ symbol: "BTC", provider_score: 82, provider_signal: "long", provider_grade: "A" }],
                fact_lanes: [],
              },
            ],
            next_cursor: null,
          },
        }),
      ),
    );

    const { result } = renderHook(() => useNewsPageWithToken("token"), { wrapper });
    await waitFor(() => expect(result.current.data?.items[0].signal.label_zh).toBe("利好"));
    expect(result.current.data?.items[0]).not.toHaveProperty("agent_brief_json");
  });
  ```

- [ ] **Step 2: Run test to verify RED**

  ```bash
  cd web
  npm test -- --run tests/unit/features/news/useNewsPage.test.ts
  ```

  Expected: fails until types/client normalize `signal`.

- [ ] **Step 3: Replace shared model types**

  Add:

  ```ts
  export type NewsSignalSummary = {
    source: "provider" | "agent" | "partial" | string;
    provider?: string | null;
    status: "ready" | "partial" | "pending" | "failed" | string;
    direction: "bullish" | "bearish" | "neutral" | string;
    label_zh?: string | null;
    signal?: "long" | "short" | "neutral" | string | null;
    score?: number | null;
    grade?: string | null;
    summary_zh?: string | null;
    summary_en?: string | null;
    method?: string | null;
  };

  export type NewsTokenLane = {
    lane: "resolved" | "attention" | "ignored" | string;
    resolution_status?: string | null;
    symbol?: string | null;
    target_type?: string | null;
    target_id?: string | null;
    provider_signal?: string | null;
    provider_score?: number | null;
    provider_grade?: string | null;
    market_type?: string | null;
    reason_codes?: string[];
  };
  ```

  Remove optional `token_lanes_json`, `fact_lanes_json`, `agent_brief_json`, `agent_status`, and `agent_brief_status` from `NewsRow`.

- [ ] **Step 4: Simplify API client normalizers**

  `normalizeNewsRow` reads:

  ```ts
  signal: normalizeNewsSignal(payload.signal),
  token_lanes: normalizeTokenLanes(payload.token_lanes),
  fact_lanes: normalizeFactLanes(payload.fact_lanes),
  ```

  Remove fallback reads from `row.token_lanes_json`, `row.fact_lanes_json`, and `payload.agent_brief_json`.

- [ ] **Step 5: Update query params**

  Replace `content_class`, `content_tag`, `coverage_tag`, `decision_class`, `direction`, `provider_type`, `source_role`, `trust_tier` in `NewsPageQueryParams` with:

  ```ts
  has_token?: boolean | null;
  signal?: "bullish" | "bearish" | "neutral" | null;
  min_score?: number | null;
  q?: string | null;
  ```

- [ ] **Step 6: Run client tests/typecheck**

  ```bash
  cd web
  npm test -- --run tests/unit/features/news/useNewsPage.test.ts
  npm run typecheck
  ```

  Expected: hard-cut client contract typechecks.

## Task 6: Implement Compact Tape + Inspector UI

**Files:**
- Create: `web/src/features/news/model/newsSignalViewModel.ts`
- Create: `web/src/features/news/ui/NewsTape.tsx`
- Create: `web/src/features/news/ui/NewsInspector.tsx`
- Create: `web/src/features/news/ui/newsTape.css`
- Modify: `web/src/features/news/NewsPage.tsx`
- Modify: `web/src/features/news/news.css`
- Modify: `web/src/features/news/newsRows.css`
- Test: `web/tests/unit/features/news/newsSignalViewModel.test.ts`
- Test: `web/tests/component/features/news/NewsTape.test.tsx`

- [ ] **Step 1: Write failing view-model tests**

  ```ts
  import { newsSignalLabel, newsSignalTone, newsSignalScoreLabel } from "@features/news/model/newsSignalViewModel";

  it("labels provider bullish/bearish/neutral signals in Chinese", () => {
    expect(newsSignalLabel({ source: "provider", status: "ready", direction: "bullish" })).toBe("利好");
    expect(newsSignalLabel({ source: "provider", status: "ready", direction: "bearish" })).toBe("利空");
    expect(newsSignalLabel({ source: "provider", status: "partial", direction: "neutral" })).toBe("中性");
  });

  it("does not duplicate scores outside the signal pill and token chips", () => {
    expect(newsSignalScoreLabel({ score: 82, grade: "A" })).toBe("A · 82");
    expect(newsSignalScoreLabel({ score: null, grade: null })).toBe("partial");
  });
  ```

- [ ] **Step 2: Run view-model test to verify RED**

  ```bash
  cd web
  npm test -- --run tests/unit/features/news/newsSignalViewModel.test.ts
  ```

  Expected: fails because file does not exist.

- [ ] **Step 3: Implement view-model helpers**

  Include:

  ```ts
  export const newsSignalLabel = (signal: Pick<NewsSignalSummary, "direction" | "label_zh">) =>
    signal.label_zh ?? (signal.direction === "bullish" ? "利好" : signal.direction === "bearish" ? "利空" : "中性");

  export const newsSignalTone = (signal: Pick<NewsSignalSummary, "direction">) =>
    signal.direction === "bullish" ? "is-long" : signal.direction === "bearish" ? "is-short" : "is-neutral";

  export const newsSignalScoreLabel = (signal: Pick<NewsSignalSummary, "score" | "grade">) =>
    signal.score == null ? "partial" : [signal.grade, String(signal.score)].filter(Boolean).join(" · ");
  ```

- [ ] **Step 4: Write failing compact-tape component test**

  ```tsx
  it("renders compact rows without a duplicate score column", () => {
    render(<NewsTape rows={[rowWithBtcEth]} selectedId="news-1" onSelect={vi.fn()} onOpen={vi.fn()} />);

    expect(screen.getByText("利好")).toBeInTheDocument();
    expect(screen.getByText("A · 82")).toBeInTheDocument();
    expect(screen.getByText("BTC")).toBeInTheDocument();
    expect(screen.getByText("82 A")).toBeInTheDocument();
    expect(screen.queryByText("score")).not.toBeInTheDocument();
  });
  ```

- [ ] **Step 5: Implement `NewsTape`**

  Render row columns:

  ```tsx
  <button className={`news-tape-row ${selected ? "is-selected" : ""}`} onClick={() => onSelect(row.news_item_id)}>
    <span className="news-tape-time">
      <b>{row.latest_at_ms ? `${formatRelativeTime(row.latest_at_ms)} ago` : "time missing"}</b>
      <small>{row.source_domain ?? "source unknown"}</small>
    </span>
    <span className={`news-tape-signal ${newsSignalTone(row.signal)}`}>
      <b>{newsSignalLabel(row.signal)}</b>
      <small>{newsSignalScoreLabel(row.signal)}</small>
    </span>
    <span className="news-tape-copy">
      <strong>{row.headline}</strong>
      <small>{row.signal.summary_zh || row.summary || "No summary available."}</small>
    </span>
    <span className="news-tape-token-strip">
      {row.token_lanes.slice(0, 4).map((lane) => (
        <span className={`news-tape-token ${tokenImpactTone(lane)}`} key={`${row.news_item_id}-${lane.symbol ?? lane.target_id}`}>
          <b>{lane.symbol || lane.target_id || "token"}</b>
          <small>{tokenImpactLabel(lane)}</small>
        </span>
      ))}
    </span>
  </button>
  ```

  Do not render a separate score column.

- [ ] **Step 6: Implement `NewsInspector`**

  Inspector shows selected item title, source line, provider summary, per-token impact bars, provider fields, and actions:

  - `Open detail`
  - `Filter <symbol>`
  - `Original`

- [ ] **Step 7: Replace `NewsPage.tsx` queue route**

  Remove old state:

  ```ts
  contentDomainFilter
  contentTagFilter
  decisionFilter
  directionFilter
  sourceFilter
  ```

  Add new state:

  ```ts
  const [tokenMode, setTokenMode] = useState<"with-token" | "no-token">("with-token");
  const [signalFilter, setSignalFilter] = useState<"all" | "bullish" | "bearish" | "neutral">("all");
  const [minScore, setMinScore] = useState<number | null>(null);
  const [selectedNewsItemId, setSelectedNewsItemId] = useState<string | null>(null);
  ```

- [ ] **Step 8: Replace CSS**

  Move compact UI styles into `web/src/features/news/ui/newsTape.css` with `.news-tape-*` namespace. Keep `news.css` for route shell only. Delete unused old row/filter selectors from `newsRows.css` after component replacement.

- [ ] **Step 9: Run frontend tests**

  ```bash
  cd web
  npm test -- --run tests/unit/features/news/newsSignalViewModel.test.ts tests/component/features/news/NewsTape.test.tsx
  npm run typecheck
  npm run lint
  ```

  Expected: tests, typecheck, ESLint, and CSS architecture harness pass.

## Task 7: Detail Page Provider-First Cleanup

**Files:**
- Modify: `web/src/features/news/NewsPage.tsx`
- Modify: `web/src/features/news/NewsDetail.css`
- Test: `web/tests/component/features/news/NewsPage.test.tsx`

- [ ] **Step 1: Write failing detail test**

  ```tsx
  it("renders OpenNews provider fact instead of Agent memo when signal source is provider", async () => {
    renderNewsItemRoute(openNewsProviderItem);

    expect(await screen.findByText("Provider signal")).toBeInTheDocument();
    expect(screen.getByText("利好")).toBeInTheDocument();
    expect(screen.getByText("BTC")).toBeInTheDocument();
    expect(screen.queryByText("Agent memo")).not.toBeInTheDocument();
  });
  ```

- [ ] **Step 2: Run test to verify RED**

  ```bash
  cd web
  npm test -- --run tests/component/features/news/NewsPage.test.tsx
  ```

  Expected: fails because detail still renders `Agent memo`.

- [ ] **Step 3: Update detail hero**

  Replace `Agent memo` hero with:

  - Provider signal summary for `item.signal.source === "provider"`.
  - Agent fallback panel only for `item.signal.source === "agent"`.
  - Partial provider state for OpenNews pushes without `aiRating`.

- [ ] **Step 4: Keep audit data below the fold**

  Provider fields and agent run metadata should live in a detail/audit section, not the hero or row.

- [ ] **Step 5: Run detail tests**

  ```bash
  cd web
  npm test -- --run tests/component/features/news/NewsPage.test.tsx
  npm run typecheck
  ```

  Expected: detail page uses provider-first language and still supports non-provider fallback via `signal.source`.

## Task 8: Config And Runtime Verification

**Files:**
- Operator config only: `/Users/qinghuan/.parallax/config.yaml`
- No source file changes unless tests expose a config schema bug.

- [ ] **Step 1: Confirm runtime config path**

  ```bash
  uv run parallax config
  ```

  Expected: reports `config_path=/Users/qinghuan/.parallax/config.yaml` and `workers_config_path=/Users/qinghuan/.parallax/workers.yaml`. Do not print secret values.

- [ ] **Step 2: Confirm only OpenNews source is enabled**

  Run a redacted config summary script:

  ```bash
  uv run python - <<'PY'
  from pathlib import Path
  import yaml

  path = Path.home() / ".parallax" / "config.yaml"
  data = yaml.safe_load(path.read_text()) or {}
  news = data.get("news_intel") or {}
  opennews = news.get("opennews") or {}
  print("config_path=", path)
  print("opennews_token_present=", bool(str(opennews.get("api_token") or "").strip()))
  print("enabled_sources=", [s.get("source_id") for s in news.get("sources") or [] if s.get("enabled")])
  PY
  ```

  Expected: token present is `True`; enabled sources are `["opennews-realtime"]`.

- [ ] **Step 3: Run a bounded OpenNews fetch against config**

  ```bash
  uv run python scripts/dev_check_opennews_fetch.py
  ```

  Expected output should include only redacted diagnostics: WebSocket status `101`, subscription params, entry count, and field presence booleans for `aiRating` and `coins`.

  If `scripts/dev_check_opennews_fetch.py` does not exist, create it as a repo-local dev script that never prints token values and is excluded from production runtime imports.

## Task 9: Docs And Contract Updates

**Files:**
- Modify: `docs/FRONTEND.md`
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/WORKERS.md`
- Modify: `docs/ARCHITECTURE.md` if News Intel data-flow section references agent-first news reads.

- [ ] **Step 1: Update frontend route contract**

  In `docs/FRONTEND.md`, replace current News route wording with:

  - `/news` renders deterministic provider/agent `signal` facts from `/api/news`.
  - Frontend must not infer sentiment from headline/summary.
  - Primary navigation is token presence and provider sentiment.
  - No `content_class`/`content_tag` control surface unless reintroduced by product spec.

- [ ] **Step 2: Update API contract**

  In `docs/CONTRACTS.md`, document:

  - `/api/news` row fields: `signal`, `token_lanes`, `token_impacts`, `fact_lanes`.
  - Removed fields: `token_lanes_json`, `fact_lanes_json`, `agent_brief_json`, `agent_status`.
  - Removed query param: `include_unprojected`.

- [ ] **Step 3: Update workers doc**

  In `docs/WORKERS.md`, document:

  - `news_fetch` writes OpenNews provider signal facts.
  - `news_item_process` resolves provider token impacts but does not enqueue OpenNews rows for agent brief.
  - `news_item_brief` marks stale OpenNews provider-signal targets done without executing LLM.

## Task 10: Final Verification

**Files:** no source edits.

- [ ] **Step 1: Backend targeted verification**

  ```bash
  uv run pytest \
    tests/unit/domains/news_intel/test_opennews_provider_signal.py \
    tests/unit/integrations/news_feeds/test_opennews_client.py \
    tests/unit/domains/news_intel/test_news_workers.py \
    tests/unit/domains/news_intel/test_news_page_projection.py \
    tests/unit/test_api_news_contract.py \
    tests/unit/test_postgres_schema.py \
    -q
  ```

  Expected: all selected tests pass.

- [ ] **Step 2: Backend integration verification**

  ```bash
  uv run pytest tests/integration/domains/news_intel/test_news_repository.py tests/integration/domains/news_intel/test_news_ingest_flow.py -q
  ```

  Expected: ingest flow persists provider signal/token impacts and page rows rebuild.

- [ ] **Step 3: Frontend verification**

  ```bash
  cd web
  npm test -- --run \
    tests/unit/features/news/newsSignalViewModel.test.ts \
    tests/unit/features/news/useNewsPage.test.ts \
    tests/component/features/news/NewsTape.test.tsx \
    tests/component/features/news/NewsPage.test.tsx
  npm run typecheck
  npm run lint
  ```

  Expected: compact tape tests pass; no CSS architecture violations.

- [ ] **Step 4: Browser verification**

  Start the app and inspect:

  ```bash
  cd web
  npm run dev
  ```

  Open `/news` at:

  - desktop `1366x720`
  - wide desktop `1920x1080`
  - mobile `390x844`

  Expected:

  - first viewport shows compact tape, not old filter wall.
  - no duplicate right-side score column in rows.
  - token chips do not overflow.
  - inspector does not overlap list.
  - `有 Token` and `无 Token` views are reachable.
  - no failing `/api/news` requests.

- [ ] **Step 5: Compatibility-code scan**

  ```bash
  rg -n "include_unprojected|token_lanes_json|fact_lanes_json|agent_brief_json|agent_status|CONTENT_DOMAIN_OPTIONS|CONTENT_TAG_OPTIONS|SOURCE_OPTIONS|DECISION_OPTIONS|NewsDirectionTabs|NewsFilterGroup" \
    src/parallax/app/surfaces/api/routes_news.py \
    src/parallax/domains/news_intel/queries/news_page_query.py \
    src/parallax/domains/news_intel/repositories/news_repository.py \
    web/src/features/news \
    web/src/lib/api/client.ts \
    web/src/shared/model/newsIntel.ts
  ```

  Expected: no matches in API/frontend hard-cut surfaces. Matches in DB migration history are acceptable only if they are historical migrations, not active read path or frontend code.

- [ ] **Step 6: Diff hygiene**

  ```bash
  git diff --check
  ```

  Expected: no whitespace errors.

## Self-Review

- Spec coverage: This plan covers OpenNews provider facts, no duplicate agent work, compact tape UI, inspector UI, hard-cut API shape, frontend compatibility removal, docs, and verification.
- Placeholder scan: No placeholder labels or ellipsis snippets remain.
- Type consistency: The canonical frontend/backend names are `signal`, `token_impacts`, `token_lanes`, and `fact_lanes`. Legacy `_json` names are explicitly removed from API/frontend surfaces.
- Risk: Full DB column removal for `agent_brief_json` in `news_page_rows` is not part of this plan because it is an internal read-model storage detail. The hard cut is at API/frontend surfaces plus old fallback query removal. A separate storage-only migration can rename internal columns after this contract is stable and covered by browser/API tests.
