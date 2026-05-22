# Spec — News Source Chain Classification And Multi-Source Intake

**Status**: Draft
**Date**: 2026-05-22
**Owner**: Qinghuan / Codex
**Related**:
- `docs/ARCHITECTURE.md`
- `docs/WORKERS.md`
- `docs/CONTRACTS.md`
- `src/gmgn_twitter_intel/domains/news_intel/ARCHITECTURE.md`
- `docs/superpowers/specs/active/2026-05-19-news-intel-kappa-cqrs-cn.md`
- `docs/superpowers/specs/active/2026-05-20-news-item-agent-brief-cn.md`
- `/Users/qinghuan/Documents/code/Horizon/README_zh.md`
- `/Users/qinghuan/Documents/code/Horizon/docs/scrapers.md`
- `/Users/qinghuan/Documents/code/Horizon/docs/scoring.md`
- `/Users/qinghuan/Documents/code/Horizon/docs/horizon-hub-design.md`

## 一句话

把当前 News Intel 从“RSS/CryptoPanic 新闻页”升级成可运营的信息源链路：参考 Horizon 的多源接入、源分类、源质量画像和社区上下文思路，但保持本项目 Kappa/CQRS 的 facts-first 边界，让不同来源先进入统一新闻事实层，再经过 deterministic 身份/事件分类、story grouping、agent brief、source quality 和页面投影，形成可用、可审计、可扩展的 `/news` 工作台。

## 背景

当前项目已经有独立 `news_intel` 域。架构明确规定 News Intel 拥有配置源抓取、原始新闻事实、实体/Token mention、fact candidate、story read model、item brief 和 News 页面读模；它不拥有 Token Radar、Pulse 或 market tick，API 也不能执行 provider calls、实体抽取、Token 解析或 agent。当前 worker 链路为 `news_fetch -> news_item_process -> news_story_projection -> news_item_brief -> news_page_projection`。

当前代码默认支持 11 个新闻源配置，其中 provider type 主要是 `rss` 和 `cryptopanic`；真实运行配置位于 `~/.gmgn-twitter-intel/config.yaml` 和 `~/.gmgn-twitter-intel/workers.yaml`，当前真实 News 源为 10 个 RSS 媒体/金融源。调试真实数据时必须先使用 `uv run gmgn-twitter-intel config` 确认路径，且只报告路径、布尔、数量和诊断结果，不打印 secret 或私有 URL。

Horizon 的启发在信息源层，而不是执行拓扑。Horizon 把 GitHub、Hacker News、RSS、Reddit、Telegram、Twitter/X、OpenBB、OSSInsight 等来源统一到 `ContentItem`，通过 `fetch(since)` 并发抓取、URL 去重、AI scoring、topic dedup、评论/背景 enrichment、双语日报和 webhook/email/MCP 分发。它证明了一个好用信息雷达需要的不只是新闻 API，还需要 source 配置、源类型、用户兴趣、社区上下文、源质量和分发。但 Horizon 的单次批处理、AI-score-first 过滤和日报生成不适合本项目的生产链路：我们的新闻必须先可见、可追溯、可重建，不能在 AI 过滤前丢失低分但关键的监管、上所、黑客或项目官方事件。

## 问题

当前 `/news` 已经可以承载 raw item、deterministic facts 和 item brief，但信息源体系仍偏窄：

- Provider 接口主要围绕 RSS-like `feed_url`，还没有一套明确的 source/provider registry 来接纳 Telegram、Twitter/X、Reddit、GitHub、OpenBB、官方公告、监管源等非 RSS 源。
- `source_role` 和 `trust_tier` 已存在，但还没有成体系地规定什么来源能产生 accepted fact，什么来源只能作为 attention/context。
- 社区讨论、回复、转述、聚合器 item 和官方公告在数据模型上容易混成同一种 `news_item`，后续 agent brief 会有证据强度不清的问题。
- 缺少 source quality read model，操作员无法知道哪些源高噪声、重复、低解析率、低 brief ready 率或抓取不稳定。
- Horizon 风格的“多源 + 人工品味 + 质量画像”还没有落到当前项目的 Kappa/CQRS 表和 worker 边界里。

这份 spec 解决的是：如何分类 news、如何接入不同数据源、如何让链路可用，并明确哪些 Horizon 方案应参考、哪些不能照搬。

## 第一性原则

**Provider observation 不是产品事实。** RSS entry、CryptoPanic post、tweet、Telegram message、Reddit comment、GitHub event、OpenBB row 都只是外部观察。进入系统后必须先持久化为 `news_provider_items` 和规范化事实/上下文，不能直接变成 accepted fact。

**Source role 决定事实门槛。** 同一句 “XYZ lists ABC” 来自 Coinbase 官方公告、CoinTelegraph、CryptoPanic、Telegram 私人频道和 Reddit comment，产品含义完全不同。角色和权威范围必须进入 validation，而不是只进入 UI 展示。

**分类是多维的，不是一个 enum。** 一个来源同时有 transport/provider type、authority role、coverage tags、asset universe、cost/latency class、context policy。一个 item 同时有 content class、target identity state、fact validation lane 和 story relation。

**AI score 不能决定是否入库。** Horizon 的 AI scoring 适合阅读清单排序；本项目必须先保留 raw item 和处理状态。AI 可以参与 brief、source-quality commentary 或 future candidate recall，但不能在 facts 前过滤新闻。

**社区是上下文，不是默认事实。** HN/Reddit/Twitter replies/Telegram chatter 对解释市场反应很有价值，但默认只能进入 context/attention。只有经过 source authority mapping 的官方账号或官方仓库，才可能作为 accepted fact 来源。

**官方也要有 authority scope。** `official_protocol` 只对自身协议/Token 有权威；`official_exchange` 对上所/下架/维护公告有权威；`official_regulator` 对监管动作有权威。官方来源不能跨域无条件接受。

**事实表不依赖读模。** `news_fact_candidates` 只能引用 `news_items` 或 context facts；story association 通过 `news_story_members` 读模派生。删除并重建 story/page/source quality rows 后，语义应可从 facts 恢复。

**API/UI 永远只读。** HTTP route 和 frontend 只能读 facts/read models，不能抓源、解析 token、分组 story、运行 agent、算 source quality 或临时调用外部 provider。

**配置源是 operator intent，DB source 是控制面。** `~/.gmgn-twitter-intel/config.yaml` 里的 sources 需要由 `news_fetch` reconcile 到 `news_sources`。移除/禁用配置源必须让 DB 行进入 disabled，而不是静默继续抓取。

**网络 IO 不持有 DB session。** Worker snapshot due sources 后释放 DB session，再调用 provider，最后打开新 session 写入 fetch run、provider item、news item 和 cache state。

## Goals

- G1. 建立明确的 News source 分类体系，覆盖 RSS/Atom、CryptoPanic、OpenBB、Telegram、Twitter/X、Reddit/HN、GitHub/OSS、官方监管/交易所/协议源。
- G2. 扩展 source/provider 接入契约，让不同 source adapter 能统一输出 provider observations，同时保留 provider-specific raw payload 和元数据。
- G3. 将 source authority、trust tier、coverage tags、asset universe、context policy 纳入 fact validation 和 UI filters。
- G4. 将社区评论/回复/讨论建模为 context facts，而不是把它们拼进 article body 后冒充主新闻事实。
- G5. 增加 source quality projection，用可重建读模展示源健康、有效率、重复率、解析率、attention/accepted/brief ready 分布。
- G6. 保持 News Intel 独立。V1 不把 news fact 写入 Token Radar、Pulse 或 market ticks；未来跨域传播必须通过新的显式 projection spec。
- G7. 所有新 provider 接入都遵守 missed-wake safe、bounded catch-up、single-writer read model 和 API read-only 规则。

## Non-goals

- 不做自动交易、下单建议、仓位、止损、目标价、杠杆或执行许可。
- 不把 Horizon 的日报生成、AI-score-first 过滤、文件式 run store 或 webhook 分发搬进主链路。
- 不引入 LanceDB、pgvector、Kafka、Redis Stream 或外部 search service 作为 V1 truth boundary。
- 不让 social/community source 直接产生 accepted fact，除非有明确 official account/repo/source authority mapping。
- 不在本 spec 打通 News -> Token Radar/Pulse。只预留将来 `accepted_news_facts` 到独立 token-news read model 的可能性。
- 不做 full-web crawler。正文抓取、readability、robots/copyright 策略需要独立 spec。

## Horizon 对照结论

| Horizon 机制 | 是否参考 | 在本项目里的落点 |
|--------------|----------|------------------|
| 多 source scraper + `fetch(since)` 统一接口 | 深度参考 | 扩展 News provider registry 和 adapter contract，但输出必须进入 Postgres facts。 |
| `ContentItem` 统一模型 | 参考思想 | 映射为 `NewsProviderObservation`/`NormalizedNewsItem`，不直接作为产品事实。 |
| URL 去重、richest content primary | 部分参考 | 当前 story projection 已有 canonical URL/content hash；可补充 cross-source provenance 和 context merge。 |
| AI scoring 0-10 后阈值过滤 | 不照搬 | 可作为 source quality/brief 辅助，不允许过滤入库和页面可见性。 |
| AI topic dedup | 不照搬为 truth | story grouping 继续 deterministic；AI 只可作为未来 candidate recall。 |
| 评论/社区 discussion enrichment | 深度参考 | 建模为 `news_context_items`，进入 brief context，不默认 accepted fact。 |
| OpenBB watchlist financial news | 深度参考 | 作为 `openbb` adapter，映射 equity/macro/company news 和 filings。 |
| Telegram public channel scraper | 参考 | 作为 `telegram_public` adapter；官方频道可配置 authority scope，普通频道为 social/context。 |
| Twitter/X Apify + reply expansion | 参考但受控 | 优先复用已有 GMGN/Twitter事实或配置化 Apify adapter；高成本、低权威，默认 social/context。 |
| HorizonHub source marketplace/quality profile | 深度参考 | 做本地 `news_source_quality_rows` 和未来可选 source recommendation，不做中心化 telemetry。 |

## News 分类体系

News 分类分五层。每层都要可独立查询和审计，不能压成一个模糊标签。

### 1. Provider/Transport Type

`provider_type` 表示怎么抓，不表示来源权威。

| Provider type | 示例 | 输出类型 | 默认风险 |
|---------------|------|----------|----------|
| `rss` / `atom` | CoinDesk、WSJ、SEC RSS、project blog | article/feed entry | HTML 摘要噪声、canonical URL 不稳 |
| `json_feed` | 自定义 JSON feed | article/feed entry | schema 漂移 |
| `cryptopanic` | CryptoPanic posts | aggregator post + currencies | 聚合器转述，原始来源需展开 |
| `openbb` | yfinance/Benzinga/FMP/SEC/Fed via OpenBB | company/macro news, filings | provider 差异、optional dependency |
| `telegram_public` | public channel web preview | social/announcement message | 反爬、转述多、无结构 |
| `twitter_profile` | watched accounts / Apify profile | tweet/post | 成本高、账号身份需验证 |
| `twitter_thread_context` | replies/conversation expansion | context item | 只作社区上下文 |
| `reddit` | subreddit/user posts/comments | community item/context | 高噪声、非事实 |
| `hackernews` | story + top comments | community discussion | 技术社区上下文 |
| `github` | repo releases/user events | developer event | 需要 repo authority mapping |
| `ossinsight` | trending repos | developer trend | trend/context，不是业务事实 |
| `manual_api` | 未来特殊 provider | provider-specific | 必须有 adapter test |

### 2. Source Authority Role

`source_role` 表示来源能否作为事实证据。

| Source role | 默认 trust tier | 可接受事实范围 | 默认 lane |
|-------------|----------------|----------------|----------|
| `official_regulator` | `official` | approval, enforcement, lawsuit, rule, filing, macro policy | accepted if slots complete |
| `official_exchange` | `official` | listing, delisting, maintenance, incident, product launch | accepted if venue/asset slots complete |
| `official_protocol` | `official` | protocol upgrade, exploit disclosure, governance, tokenomics | accepted if target matches authority scope |
| `official_issuer` | `official` | ETF/fund/issuer statement, equity issuer PR | accepted if issuer/security matches |
| `specialist_media` | `high` or `standard` | reported claim, investigation, context | attention unless corroborated |
| `aggregator` | `standard` | discovery/context only | context/attention |
| `social` | `standard` or `low` | sentiment, early signal, official account if mapped | context/attention by default |
| `community` | `low` | discussion, reaction, technical debate | context |
| `developer_signal` | `standard` or `high` | repo release, project activity | accepted only for mapped official repo |
| `observed_source` | `standard` | unknown/general | attention/context |

### 3. Coverage Tags

`coverage_tags` 表示源覆盖什么，不表示可信度。建议从这些稳定标签开始：

- `crypto_market`
- `crypto_policy`
- `crypto_security`
- `crypto_exchange`
- `crypto_protocol`
- `crypto_etf`
- `macro_policy`
- `equity_market`
- `single_stock`
- `developer_release`
- `community_discussion`
- `social_viral`
- `onchain_flow`
- `fund_flow`

### 4. Content/Event Class

`news_item_process` 和未来 fact extractor 应输出内容分类。V1 可 deterministic，后续可由 agent 提候选但必须 validator 决定。

| Content class | 典型触发 | 事实接受要求 |
|---------------|----------|--------------|
| `exchange_listing` | lists, listing, trading opens | official exchange 或多源 corroboration；asset + venue |
| `exchange_delisting` | delist, suspend trading | official exchange；asset + venue |
| `regulatory_action` | SEC/CFTC/court/approval/lawsuit | official regulator/court 或高可信媒体 attention |
| `security_incident` | hack, exploit, drained | official protocol/security firm/media attention；target + incident |
| `protocol_upgrade` | mainnet, hard fork, upgrade | official protocol/repo；target + version/action |
| `governance_tokenomics` | unlock, vote, emission, proposal | official protocol/issuer；target + schedule |
| `etf_fund_flow` | ETF approval/inflow/outflow | official issuer/fund data/provider; instrument + flow/action |
| `macro_policy` | Fed/CPI/jobs/rates/fiscal | official macro source or high-trust market data |
| `equity_company_event` | earnings, guidance, M&A | issuer/filing/high-trust financial provider |
| `developer_release` | GitHub release, repo event | mapped official repo |
| `market_commentary` | analyst opinion, price recap | context only unless separate accepted fact |
| `social_viral` | Twitter/Telegram/Reddit spread | attention/context |

### 5. Product Lane

Product lane 是 UI 和 operator 看到的处理结果：

- `raw`: 已抓取但未处理。
- `entity_extracted`: 已有 entity/token mentions。
- `fact_candidate`: 有候选事件，但未 accepted。
- `attention`: unknown/ambiguous identity、弱来源、缺 slot、社交噪声或需人工观察。
- `accepted`: 来源权威、identity 生产可用、required slots 完整、realis 合格。
- `context`: 社区/评论/背景材料，不作为事实。
- `discard`: spam、广告、重复或非相关。

## Target Architecture

保留当前五段主链路，新增 source/provider registry、context facts 和 source quality projection。

```text
operator config (~/.gmgn-twitter-intel/config.yaml)
  -> news_fetch source reconciliation
  -> news_sources control state
  -> provider registry selects adapter
  -> provider observation fetch
  -> news_fetch_runs + news_provider_items
  -> news_items + optional news_context_items
  -> news_item_process
  -> news_item_entities + news_token_mentions + news_fact_candidates
  -> news_story_projection
  -> news_story_groups + news_story_members
  -> news_item_brief
  -> news_item_agent_runs + news_item_agent_briefs
  -> news_source_quality_projection
  -> news_source_quality_rows
  -> news_page_projection
  -> news_page_rows
  -> /api/news + /api/news/sources/status
  -> web /news
```

`news_source_quality_projection` 是新增 worker，唯一 runtime writer 为 `news_source_quality_rows`。它只从 `news_sources`、`news_fetch_runs`、`news_items`、`news_token_mentions`、`news_fact_candidates`、`news_item_agent_briefs` 和 story/page read models 读数据，不调用 providers。

## Provider Adapter Contract

现有 `NewsFeedProvider.fetch(url, etag, last_modified, provider_type, source)` 应演进为更显式的 adapter registry。兼容期可以保留 `feed_client`，但新 provider 应实现统一 contract：

```python
class NewsSourceProvider(Protocol):
    provider_type: str

    def fetch(
        self,
        *,
        source: NewsSourceSnapshot,
        since_ms: int | None,
        cursor: dict[str, object],
        cache: NewsSourceHttpCache,
        limit: int,
    ) -> NewsProviderFetchResult: ...
```

`NewsProviderFetchResult` 包含：

- `status_code`
- `observations`: list of `NewsProviderObservation`
- `context_observations`: optional list of discussion/comment/reply observations
- `etag`, `last_modified`, `next_cursor`
- `not_modified`
- `provider_diagnostics`

`NewsProviderObservation` 至少包含：

- `source_item_key`
- `canonical_url`
- `title`
- `summary`
- `body_text` or `body_excerpt`
- `author`
- `published_at_ms`
- `language`
- `raw_payload`
- `engagement_json`
- `linked_symbols_json`
- `provider_tags_json`
- `original_source_url` / `original_source_domain` when the provider is an aggregator

Adapter 规则：

- 必须在 unit test 中覆盖 malformed row、missing URL/title/date、old row、duplicate row、provider error。
- 必须保留 raw payload，但 public API 不直接返回 raw payload。
- 必须显式声明 cost class：`free`, `metered`, `paid`, `browser`, `manual`.
- 不允许在 adapter 内做 product fact acceptance。

## Data Model Changes

### Extend `news_sources`

Add optional operator-owned classification fields:

- `provider_type`: expand allowed values to the provider list above.
- `coverage_tags_json JSONB NOT NULL DEFAULT '[]'::jsonb`
- `asset_universe_json JSONB NOT NULL DEFAULT '[]'::jsonb`
- `authority_scope_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `fetch_policy_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `context_policy_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `cost_policy_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `source_quality_status TEXT NOT NULL DEFAULT 'unknown'`

`authority_scope_json` examples:

```json
{
  "targets": [{"target_type": "CexToken", "target_id": "BTCUSDT"}],
  "domains": ["coinbase.com"],
  "accounts": ["coinbase"],
  "repos": ["ethereum/go-ethereum"],
  "event_types": ["exchange_listing", "exchange_delisting"]
}
```

### Add `news_context_items`

Context items are first-class facts for comments/replies/discussion snippets and secondary observations.

Fields:

- `context_item_id TEXT PRIMARY KEY`
- `source_id TEXT NOT NULL`
- `parent_news_item_id TEXT REFERENCES news_items(news_item_id) ON DELETE CASCADE`
- `provider_item_id TEXT REFERENCES news_provider_items(provider_item_id) ON DELETE SET NULL`
- `context_type TEXT NOT NULL` (`comment`, `reply`, `discussion`, `engagement_snapshot`, `related_post`, `source_quote`)
- `author TEXT`
- `canonical_url TEXT`
- `body_text TEXT NOT NULL`
- `published_at_ms BIGINT`
- `engagement_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at_ms BIGINT NOT NULL`

Context items may be used by `news_item_brief` and source quality, but do not become accepted fact by themselves.

### Add `news_source_quality_rows`

Rebuildable read model, one row per source per rolling window.

Fields:

- `row_id TEXT PRIMARY KEY`
- `source_id TEXT NOT NULL`
- `window TEXT NOT NULL` (`1h`, `4h`, `24h`, `7d`)
- `computed_at_ms BIGINT NOT NULL`
- `fetch_success_rate DOUBLE PRECISION`
- `items_fetched INTEGER`
- `items_inserted INTEGER`
- `duplicate_rate DOUBLE PRECISION`
- `process_success_rate DOUBLE PRECISION`
- `resolved_token_rate DOUBLE PRECISION`
- `attention_rate DOUBLE PRECISION`
- `accepted_fact_rate DOUBLE PRECISION`
- `brief_ready_rate DOUBLE PRECISION`
- `median_lag_ms BIGINT`
- `quality_score DOUBLE PRECISION`
- `diagnostics_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `projection_version TEXT NOT NULL`

`quality_score` is deterministic, not LLM-generated. It is a source-operations score, not item importance.

### Optional Later: `news_source_directory`

HorizonHub 的 marketplace 思路可以作为本地 source catalog：

- curated source presets
- category/coverage tags
- source descriptions
- operator notes
- disabled reason
- suggested configs

V1 不做中心化 telemetry，不上传用户使用数据。

## Worker Design

### `news_fetch`

Responsibilities:

- Reconcile `news_intel.sources` into `news_sources`.
- Validate source classification fields.
- Claim due sources.
- Pick adapter via provider registry.
- Fetch provider observations outside DB sessions.
- Persist `news_fetch_runs`, `news_provider_items`, `news_items`, and `news_context_items`.
- Update provider cache/cursor only in the same successful persistence path.
- Emit `news_item_written` when primary items are inserted or updated.

Rules:

- `source_role` and `trust_tier` must be persisted with item/source join metadata for downstream processing.
- Aggregator providers must preserve original source URL/domain when available.
- Browser/costly providers such as CryptoPanic browser transport or Apify must have lower fetch frequency and clear diagnostics.

### `news_item_process`

Responsibilities:

- Extract deterministic entities from title, summary, body, and selected context snippets.
- Resolve token identity only through domain interfaces.
- Produce `news_token_mentions` with `exact_address`, `known_symbol`, `unique_by_context`, `ambiguous_symbol`, `unknown_attention`, `non_crypto`, or `nil`.
- Classify content/event class using deterministic high-precision rules first.
- Build `news_fact_candidates` with source role, authority scope, required slots, realis, evidence quote/span, affected target status, and rejection reasons.

Rules:

- Unknown symbols remain attention-visible.
- Context items can support brief evidence but cannot alone make a fact accepted.
- Official source acceptance must check authority scope.

### `news_story_projection`

Responsibilities:

- Group items by deterministic signals:
  - same provider item
  - same canonical URL
  - same content hash
  - same original source URL from aggregator
  - title fingerprint + token/source/time overlap
- Write `news_story_groups` and `news_story_members`.

Rules:

- No embedding as V1 truth boundary.
- AI semantic dedup can only be future candidate recall with deterministic validation.
- Rolling updates that change content hash must force stale membership/page rows to refresh.

### `news_item_brief`

Responsibilities:

- Build bounded item/story/token/fact/context packet.
- Reserve `news.item_brief` lane through `AgentExecutionGateway`.
- Produce Chinese market read, bull/bear view, decision class, evidence refs, data gaps.
- Validate output against evidence refs and no-execution-language guardrails.
- Write `news_item_agent_runs` and `news_item_agent_briefs`.

Rules:

- It may summarize impact; it may not issue trades.
- It must render degraded states instead of frontend heuristics.
- It must cite only packet evidence refs.

### `news_source_quality_projection`

Responsibilities:

- Read fetch runs and downstream facts/read models.
- Compute rolling source-quality rows.
- Surface source health and quality diagnostics to `/api/news/sources/status`.

Quality score suggestion:

```text
quality_score =
  25 * fetch_success_rate
  + 15 * process_success_rate
  + 15 * resolved_token_rate
  + 15 * brief_ready_rate
  + 10 * (1 - duplicate_rate)
  + 10 * normalized_freshness
  + 10 * useful_fact_or_context_rate
```

This score is for source operations only. It cannot demote raw item visibility.

### `news_page_projection`

Responsibilities:

- Build `news_page_rows` from item, story, token lanes, fact lanes, source quality summary, and current item brief.
- Support filters by provider type, source role, trust tier, coverage tag, content class, lifecycle lane, direction, agent status, target, source, q.

Rules:

- It never executes agents or provider calls.
- It must listen to `news_item_brief_updated` and retain interval catch-up. The real runtime `workers.yaml` should include this wake for timely UI refresh.

## Source Configuration Shape

Operator config stays in `~/.gmgn-twitter-intel/config.yaml`:

```yaml
news_intel:
  enabled: true
  sources:
    - source_id: coinbase-announcements
      provider_type: rss
      feed_url: "https://example.com/feed.xml"
      source_domain: coinbase.com
      source_name: Coinbase Announcements
      source_role: official_exchange
      trust_tier: official
      coverage_tags: ["crypto_exchange", "exchange_listing"]
      authority_scope:
        event_types: ["exchange_listing", "exchange_delisting", "maintenance"]
        domains: ["coinbase.com"]
      fetch_policy:
        refresh_interval_seconds: 120
        max_items: 50
      context_policy:
        fetch_discussion: false
      cost_policy:
        class: free
      enabled: true
```

Provider-specific examples:

```yaml
    - source_id: openbb-megacaps
      provider_type: openbb
      feed_url: "openbb://news/company?provider=yfinance&symbols=AAPL,MSFT,NVDA&limit=30"
      source_domain: openbb.local
      source_name: OpenBB Megacaps
      source_role: specialist_media
      trust_tier: standard
      coverage_tags: ["equity_market", "single_stock"]
      asset_universe: ["AAPL", "MSFT", "NVDA"]
      cost_policy: {class: free}

    - source_id: telegram-binance
      provider_type: telegram_public
      feed_url: "telegram://binance_announcements?fetch_limit=20"
      source_domain: t.me
      source_name: Binance Telegram Announcements
      source_role: official_exchange
      trust_tier: official
      coverage_tags: ["crypto_exchange"]
      authority_scope:
        accounts: ["binance_announcements"]
        event_types: ["exchange_listing", "exchange_delisting", "maintenance"]

    - source_id: reddit-cryptocurrency
      provider_type: reddit
      feed_url: "reddit://r/CryptoCurrency/hot?fetch_limit=25&min_score=50&comments=5"
      source_domain: reddit.com
      source_name: r/CryptoCurrency
      source_role: community
      trust_tier: low
      coverage_tags: ["community_discussion", "social_viral"]
      context_policy:
        fetch_comments: true
```

Secrets must be referenced through environment/config indirection and redacted in diagnostics.

## Source Classes To Add First

Phase 1 should prioritize sources that improve trading/news usefulness without exploding complexity:

1. **Official exchange/protocol/regulator RSS/Atom**
   Highest fact quality. Add configs and tests before social expansion.

2. **OpenBB watchlist provider**
   Useful for equity/macro/company event surface. Adapter should lazy-import OpenBB, no-op with warning when optional dependency missing, and keep provider credentials inside OpenBB environment/settings.

3. **Telegram public official/social channels**
   Useful for crypto announcements and early social flow. Official channels require explicit authority mapping; ordinary channels are context/attention only.

4. **Twitter/X watched profile context**
   Prefer existing watched-account/social facts where possible. Apify-style adapter is optional, high-cost, and should be disabled by default.

5. **Reddit/HN discussion context**
   Useful for context and source quality, not for accepted fact. Fetch comments/replies into `news_context_items`.

6. **GitHub repo releases/events**
   Useful for protocol upgrades, developer release and OSS trend. Accepted only when repo is mapped as official for the target/project.

CryptoPanic should remain an aggregator provider, not an authoritative source. It is valuable for discovery and original-source hints.

## Fact Acceptance Policy

Accepted fact requires all of:

- source role is authoritative for the event type;
- authority scope matches target/account/domain/repo/venue;
- affected target identity is production-eligible;
- required slots are complete;
- realis is `actual`, `scheduled`, or `official_proposed`; `reported_claim` defaults to `attention` unless a future corroboration policy explicitly upgrades it;
- evidence quote/span points to the source item or accepted context ref;
- no contradiction from stronger source in the same story group.

Specialist media default:

- `specialist_media` can create `attention` fact candidates and `ready` item briefs.
- It does not create `accepted` listing/regulatory/security facts by itself unless a future corroboration policy is implemented.

Aggregator default:

- `aggregator` creates discovery/context only.
- If it exposes original source URL/domain, story grouping can link to original-source items.

Social/community default:

- `social` and `community` create context/attention.
- Official mapped accounts can be upgraded by authority scope, not by follower count or engagement.

Developer source default:

- GitHub releases/events are accepted only for mapped official repos and event classes such as `developer_release` or `protocol_upgrade`.

## API And UI Contract

Extend `/api/news` filters:

- `provider_type`
- `source_role`
- `trust_tier`
- `coverage_tag`
- `content_class`
- `lane`
- `agent_status`
- `direction`
- `target`
- `source`
- `q`

Extend row payload compactly:

- `source.provider_type`
- `source.source_role`
- `source.trust_tier`
- `source.coverage_tags`
- `source.quality`
- `content_classes`
- `context_counts`
- `authority_summary`

Extend `/api/news/items/{news_item_id}`:

- context items summary;
- source classification;
- authority-scope validation details;
- source quality snapshot;
- fact candidate rejection reasons.

Extend `/api/news/sources/status`:

- source classification fields;
- fetch health;
- rolling quality rows;
- last diagnostics;
- disabled/removed status.

Frontend `/news` should show:

- source role/trust tier/provider badge;
- lane (`raw`, `attention`, `accepted`, `context`);
- content class;
- token identity state;
- story continuity;
- agent brief state;
- source quality warning when a source is noisy or failing.

The frontend must not infer Chinese summaries, bull/bear theses, source authority, or fact acceptance locally.

## Migration / Implementation Shape

Recommended implementation in small hard-cut PRs:

### PR1 — Source Classification Schema

- Extend `NewsSourceSettings`.
- Extend `news_sources`.
- Reconcile new config fields into DB.
- Update `/api/news/sources/status`.
- Add config/unit tests and redaction tests.

### PR2 — Provider Registry

- Introduce `NewsSourceProvider` contract and registry.
- Port existing RSS and CryptoPanic behind the registry.
- Preserve existing public API.
- Add architecture tests ensuring API does not import provider adapters.

### PR3 — Context Items

- Add `news_context_items`.
- Extend packet builder for item brief.
- Add deterministic context limits and evidence refs.
- Add tests for comments/replies not becoming accepted facts.

### PR4 — First New Providers

- Add `openbb` adapter.
- Add `telegram_public` adapter.
- Add GitHub release adapter if target/repo mapping is ready.
- Keep Reddit/HN/Twitter disabled by default until source quality and cost controls are proven.

### PR5 — Source Quality Projection

- Add `news_source_quality_rows`.
- Add `news_source_quality_projection` worker and wake/catch-up config.
- Extend source status API and UI.

### PR6 — Authority-Scope Validation

- Upgrade fact candidate validator to use `authority_scope_json`.
- Add event-class-specific acceptance tests.
- Keep specialist/aggregator/social default as attention/context.

### PR7 — Optional Cross-Domain Proposal

- Write a separate spec for `accepted_news_facts -> token_news_read_model`.
- Do not write Token Radar/Pulse in this source-chain work.

## Testing Gates

- `uv run ruff check .`
- `uv run pytest tests/architecture -q`
- `uv run pytest tests/unit/domains/news_intel -q`
- `uv run pytest tests/unit/test_worker_settings.py tests/unit/test_bootstrap_worker_runtime_wiring.py -q`
- Provider adapter tests for RSS, CryptoPanic, OpenBB, Telegram, and any added social/community source.
- Integration tests for source reconciliation and provider item/news item persistence.
- Missed-wake tests where practical: downstream workers progress by interval catch-up after rows are inserted without NOTIFY.
- API tests proving `/api/news` and `/api/news/sources/status` are read-only.
- Search/architecture tests proving News Intel does not write `token_radar_rows`, Pulse tables, or market tick facts.
- Frontend tests after UI changes: `cd web && npm run lint && npm test -- --run`.

## Acceptance Criteria

- AC1. When operator config contains enabled sources across multiple provider types, `news_fetch` reconciles them into `news_sources` with classification fields and does not print secrets.
- AC2. When an RSS/CryptoPanic/OpenBB/Telegram adapter fetches valid observations, the system persists provider items and normalized news items without provider IO inside DB transactions.
- AC3. When a source produces comments/replies/discussion context, those rows are persisted as context and cannot by themselves create accepted facts.
- AC4. When a specialist media or aggregator item reports an exchange listing, the fact candidate remains `attention` unless an authority/corroboration policy accepts it.
- AC5. When an official exchange/protocol/regulator source emits an in-scope event with resolved target and complete slots, the fact candidate can become `accepted`.
- AC6. When a social account is not mapped in authority scope, high engagement does not upgrade it to accepted fact.
- AC7. When `news_source_quality_rows` are truncated, the source quality worker rebuilds them from facts/control rows.
- AC8. When `news_item_brief_updated` is emitted or missed, `news_page_projection` eventually updates page rows via wake or interval catch-up.
- AC9. `/api/news` can filter by source role, trust tier, provider type, content class, lane, direction, source, target and q without executing providers or agents.
- AC10. Repository search finds no runtime writes from News Intel to Token Radar, Pulse, or market tick tables.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Source expansion turns News into noisy social firehose | High | Add providers disabled-by-default; source quality rows; context/attention lanes; strict fetch limits. |
| Social/aggregator sources contaminate accepted facts | High | Authority scope validation; default non-official sources to attention/context. |
| Provider-specific code leaks into API or domain decisions | High | Adapter registry in integrations; domain consumes normalized observations; architecture tests. |
| OpenBB optional dependency breaks runtime | Medium | Lazy import; no-op with warning; adapter tests with fake SDK payloads. |
| Browser/Apify sources add cost and flakiness | Medium | Cost policy, disabled default, longer intervals, diagnostics, source quality. |
| Context items bloat item brief packets | Medium | Hard limits by context type, engagement, recency, and source quality. |
| Source quality score becomes hidden ranking truth | Medium | Label as operational score only; never filter raw visibility by quality score. |
| Config shape becomes too complex | Medium | Keep required fields small; advanced fields optional JSON; provide examples and status diagnostics. |

## Open Questions

- Which official crypto sources should be the first curated authority set: exchanges, protocols, regulators, or ETF/issuer feeds?
- Should Twitter/X official account mapping reuse existing watched handles, or have a separate `news_authority_accounts` config?
- Should `news_context_items` be visible on `/news` detail immediately, or only feed item brief first?
- Should source quality be computed by fixed formula only, or expose formula components and let UI sort by individual metrics?
- Should OpenBB filings be included in the first OpenBB adapter PR, or only company news first?

## Decision

Proceed with the source-chain design as an extension of existing News Intel, not a replacement. Use Horizon as a reference for broad source coverage, source discovery, source quality and community context. Do not copy Horizon's AI-score-first filtering, topic-dedup truth boundary or daily-summary runtime. Keep `/news` independent and auditable first; cross-domain propagation belongs in a separate explicit spec.
