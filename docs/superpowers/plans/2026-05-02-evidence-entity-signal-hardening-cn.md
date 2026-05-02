# Evidence / Entity / Signal 硬化中文总结与实施计划

> **执行原则：** 这是一次 breaking cutover，不做兼容层，不双写，不保留 LanceDB 作为“未来可能有用”的代码、依赖、配置或文档入口。当前产品只保留对交易员当下有确定价值的能力。

## 一句话结论

当前系统应该从“把推文存进一个带向量能力的库，之后再慢慢补处理”改成“先把证据、实体、信号三层做成稳定的交易情报内核”。

最终架构是：

```text
GMGN public Twitter WebSocket
  -> Collector
  -> Evidence 写入 SQLite WAL
  -> Entity 确定性抽取
  -> Signal 物化窗口和账户提醒
  -> WebSocket / CLI / API 查询
```

SQLite WAL 是 operational source of truth。SQLite FTS5 负责当前需要的全文检索。LanceDB、embedding、LLM enrichment 不属于当前产品，全部移除。

## 第一性原理总结

### 1. 交易员首先需要的是可审计证据，不是搜索 demo

交易动作不能建立在“也许检索到了相关内容”上，而要能回答：

- 这条信号来自哪条原始推文？
- 是谁发的？
- 什么时间进入系统？
- 系统有没有漏处理、积压、重复？
- 这个 token / keyword 是从原文里确定抽出来的，还是模型猜的？

所以第一层必须是 evidence：raw frame、normalized event、文本、作者、时间、去重 key、原始 JSON 都要稳定落库。

### 2. Entity 必须确定性、便宜、可重放

第一版实体不靠 LLM 猜。只抽能从文本中确定拿到的东西：

- EVM CA
- Solana CA
- cashtag，例如 `$PEPE`
- hashtag
- mention
- URL / domain
- 配置的关键词，例如 `listing`, `airdrop`, `mainnet`

cashtag 没有 CA 时就是 unresolved symbol，不硬解析成某个 token。这样短期少一点“聪明”，长期少很多脏数据。

### 3. Signal 不是摘要，而是物化指标

signal 应该是可查询、可排序、可复现的记录：

- 监控账号首次提到某 CA / cashtag。
- 监控账号首次提到某关键词。
- token 在 1m / 5m / 1h / 24h 的 mention count、unique authors、weighted reach、mindshare、velocity。
- keyword 在窗口里的提及热度、关注账号参与度、top events。

每个 signal 都必须能回到 event_id，再回到原文证据。

### 4. 检索是服务于交易问题，不是架构中心

当前真正需要的是：

- 按 CA 精确查。
- 按 cashtag / symbol 查。
- 按 handle 查。
- 按 keyword / 全文查。
- 按时间窗口查。
- 按 watched account 查。

SQLite 普通索引 + FTS5 可以覆盖这些需求，并且和写入事务一致。LanceDB 的向量能力不是当前关键路径，也不该因为“未来可能有用”留在系统里。

## 为什么彻底移除 LanceDB

### 保留 LanceDB 的问题

如果 LanceDB 只是未来可能会用，它会带来确定成本：

- 多一套存储 mental model。
- 多一组 Docker/env/path 配置。
- 多一批依赖和构建体积。
- 多一类锁、线程池、文件快照、容器运行时问题。
- 让后续代码继续写适配层、兼容层和分叉路径。

这些成本现在发生，但收益不确定。

### 移除 LanceDB 后保留什么能力

移除 LanceDB 不等于放弃检索。当前检索由 SQLite 承担：

- `events` 表用普通索引支持按时间、作者、watched scope、tweet_id 查询。
- `event_entities` 表支持 CA / symbol / keyword / hashtag / mention 精确查询。
- `event_fts` 使用 SQLite FTS5 支持 keyword / full-text / BM25。
- `token_windows` 和 `keyword_windows` 支持交易员最关心的排名、mindshare、velocity。

如果未来真的证明需要 semantic search，那是新的产品需求和新的架构决策。到那时重新写 spec、重新选型，而不是现在保留 LanceDB。

## 实现之后的效果

### 数据链路效果

实现后，每条 GMGN Twitter frame 会走一条确定链路：

```text
raw frame
  -> normalized event
  -> FTS row
  -> extracted entities
  -> account alerts
  -> token / keyword windows
  -> live publish
```

同一个事务里完成 evidence、FTS 和 entity 写入。signal 可以同步计算最关键提醒，窗口指标可以同步 upsert 或通过受控 rebuild 命令重建。

### 稳定性效果

预期改善：

- 不再受 LanceDB 写入 hang、线程池、文件锁、Docker snapshot 影响。
- 单文件 SQLite WAL，写路径更容易定位和备份。
- `/readyz` 不只看进程活着，还看 collector、DB 写探针、最近 frame、最近 event、错误计数。
- 容器重启后不需要手动重建索引，FTS5 和表数据一起持久化。
- 没有 `while true` 这种外层假保活逻辑，失败由 app readiness 和 Docker restart policy 接管。

### 交易员能看到的效果

实现后应该能直接回答这些问题：

1. **过去 5 分钟哪些 token 被最多提到？**

   `gmgn-twitter-intel token-flow --window 5m --limit 20`

   返回 mention count、watched mention count、unique authors、weighted reach、market mindshare、watched mindshare、velocity、top authors、top events。

2. **我监控的账号刚刚提到了哪些 token？**

   `gmgn-twitter-intel account-alerts --window 24h --limit 50`

   返回 author、CA / cashtag、是否该作者首次提到、是否全局首次出现、原推文 evidence。

3. **我监控的账号刚刚提到了哪些关键词或 narrative？**

   `gmgn-twitter-intel account-alerts --window 24h --alert-type keyword`

   返回 keyword、author、原文、时间、first_seen 状态。

4. **某个 CA / symbol 过去有哪些推文证据？**

   `gmgn-twitter-intel search --symbol PEPE --limit 20`

   或：

   `gmgn-twitter-intel search 0x... --limit 20`

5. **关键词是否正在升温？**

   `gmgn-twitter-intel keyword-flow --window 1h --limit 20`

   返回窗口计数、关注账号参与度、velocity、top evidence。

### WebSocket 效果

live payload 不再只是推文事件，而是带上实体和提醒：

```json
{
  "type": "event",
  "event": {
    "event_id": "...",
    "author_handle": "toly",
    "text_clean": "...",
    "received_at_ms": 1770000000000
  },
  "entities": [
    {
      "entity_type": "symbol",
      "normalized_value": "PEPE",
      "token_resolution_status": "unresolved"
    }
  ],
  "alerts": [
    {
      "alert_type": "account_token",
      "author_handle": "toly",
      "entity_key": "symbol:PEPE",
      "is_first_seen_by_author": true
    }
  ]
}
```

这样前端或交易终端可以第一时间消费结构化信号，而不是再自己解析文本。

## 目标数据模型

### Evidence 层

- `raw_frames`：原始 WebSocket frame，按 payload hash 去重。
- `events`：标准化后的 Twitter event，按 logical dedup key 去重。
- `event_fts`：FTS5 全文检索索引，和 `events` 同事务写入。

### Entity 层

- `event_entities`：每条事件抽出的 CA、symbol、hashtag、mention、URL/domain、keyword。
- `token_resolution_status`：`resolved_ca`、`unresolved_symbol`、`non_token_entity`。
- `confidence`：确定性抽取为高置信；不写 LLM 猜测。

### Signal 层

- `account_token_alerts`：监控账号提 token / CA / cashtag 的提醒。
- `account_keyword_alerts`：监控账号提关键词的提醒。
- `token_windows`：token 窗口指标。
- `keyword_windows`：keyword 窗口指标。

## 详细实施计划

### Phase 0：锁定范围和删除原则

目标：先把工程边界钉死，避免实现过程中又保留兼容层。

改动：

- 确认当前版本不保留 LanceDB。
- 确认不保留 embedding runtime。
- 确认不保留 LLM enrichment runtime。
- 确认不做自动迁移；历史数据如果重要，只允许一次性离线 export/import。

验收：

```bash
rg -n "future-use|semantic projection|dual-write|compatibility adapter" docs README.md AGENTS.md CLAUDE.md
```

期望：没有把 LanceDB 当未来占位的表述。

### Phase 1：SQLite schema 和连接核心

目标：先证明本地 Python runtime 支持 WAL 和 FTS5，再继续改业务。

新增文件：

- `src/gmgn_twitter_intel/storage/sqlite_client.py`
- `src/gmgn_twitter_intel/storage/sqlite_schema.py`
- `tests/test_sqlite_schema.py`

实现内容：

- `connect_sqlite(path, read_only=False)`
- writable connection 设置：
  - `PRAGMA journal_mode=WAL`
  - `PRAGMA synchronous=NORMAL`
  - `PRAGMA foreign_keys=ON`
  - `PRAGMA busy_timeout=5000`
  - `PRAGMA temp_store=MEMORY`
- read-only connection 设置：
  - `PRAGMA query_only=ON`
  - `PRAGMA foreign_keys=ON`
  - `PRAGMA busy_timeout=5000`
- `transaction(conn)` context manager。
- migration 创建：
  - `schema_migrations`
  - `raw_frames`
  - `events`
  - `event_fts`
  - `event_entities`
  - `account_token_alerts`
  - `account_keyword_alerts`
  - `token_windows`
  - `keyword_windows`

测试：

```bash
uv run python -m pytest tests/test_sqlite_schema.py -q
```

验收：

- 空 DB 可以 bootstrap。
- FTS5 可以插入文本并 `MATCH` 查询。
- migration 可以重复执行且幂等。

### Phase 2：替换配置和运行路径

目标：从公共配置面移除 LanceDB，换成 SQLite。

修改文件：

- `src/gmgn_twitter_intel/settings.py`
- `src/gmgn_twitter_intel/runtime_paths.py`
- `tests/test_settings.py`
- `tests/test_project_structure.py`

实现内容：

- 新增 `SQLITE_PATH`。
- 默认路径改为 `~/.gmgn-twitter-intel/twitter_intel.sqlite3`。
- Docker 内路径为 `/data/twitter_intel.sqlite3`。
- 新增 `WATCH_KEYWORDS`。
- 移除：
  - `LANCEDB_PATH`
  - `EMBEDDING_DIM`
  - Lance thread env
  - LanceDB-specific settings
  - LLM runtime settings，如果只服务 enrichment。

测试：

```bash
uv run python -m pytest tests/test_settings.py tests/test_project_structure.py -q
```

验收：

- settings 不再暴露 LanceDB 配置。
- `WATCH_KEYWORDS=listing,airdrop,mainnet` 能解析成稳定 tuple。
- 默认路径和 Docker 路径一致。

### Phase 3：Entity extractor

目标：把实体抽取从 token-only 扩展为确定性 entity extraction。

新增文件：

- `src/gmgn_twitter_intel/pipeline/entity_extractor.py`
- `tests/test_entity_extractor.py`

可复用文件：

- `src/gmgn_twitter_intel/pipeline/tweet_text.py`
- `src/gmgn_twitter_intel/pipeline/token_extractor.py` 中已经可靠的 CA/cashtag 逻辑可迁移，不保留旧抽象名。

实现内容：

- EVM CA 正则。
- Solana CA 正则。
- cashtag 抽取并标准化为大写 symbol。
- hashtag 抽取。
- mention 抽取。
- URL 和 domain 抽取。
- configured keyword 匹配，大小写归一。
- 每个 entity 输出：
  - `entity_type`
  - `raw_value`
  - `normalized_value`
  - `chain`
  - `token_resolution_status`
  - `confidence`
  - `source`

测试：

```bash
uv run python -m pytest tests/test_entity_extractor.py -q
```

验收：

- 同一文本重复抽取结果稳定。
- CA 被标记为 resolved。
- cashtag 无 CA 时保持 unresolved。
- keyword 不误匹配普通词片段。

### Phase 4：Evidence repository

目标：把 raw frame、event、FTS row 放进同一个事务。

新增文件：

- `src/gmgn_twitter_intel/storage/evidence_repository.py`
- `tests/test_evidence_repository.py`

修改文件：

- `src/gmgn_twitter_intel/collector/service.py`

实现内容：

- `insert_raw_frame(frame)`：按 payload hash 幂等。
- `insert_event(event)`：按 `event_id` 和 `logical_dedup_key` 幂等。
- `insert_event_fts(event)`：和 event 同事务。
- `recent(limit, since_ms, watched_only)`。
- `search_fts(query, limit, watched_only)`。
- `counts(since_ms)`。

测试：

```bash
uv run python -m pytest tests/test_evidence_repository.py -q
```

验收：

- raw frame 重复写不会产生重复行。
- event 重复写不会产生重复行。
- event 和 FTS 写入要么一起成功，要么一起失败。
- recent/search 在 ingest 连接打开时仍可读。

### Phase 5：Entity repository

目标：实体成为一等数据，不再藏在 event JSON 里。

新增文件：

- `src/gmgn_twitter_intel/storage/entity_repository.py`
- `tests/test_entity_repository.py`

实现内容：

- `insert_event_entities(event_id, entities)`。
- `find_by_ca(ca, limit)`。
- `find_by_symbol(symbol, limit)`。
- `find_by_keyword(keyword, limit)`。
- `find_by_author(handle, since_ms)`。
- `entity_counts(since_ms, watched_only)`。

测试：

```bash
uv run python -m pytest tests/test_entity_repository.py -q
```

验收：

- 同一 event 同一 entity 幂等。
- CA/symbol/keyword 查询走索引。
- watched scope 查询不扫全表。

### Phase 6：Signal repository 和 signal builder

目标：把交易员真正关心的提醒和窗口指标物化。

新增文件：

- `src/gmgn_twitter_intel/storage/signal_repository.py`
- `src/gmgn_twitter_intel/pipeline/signal_builder.py`
- `tests/test_signal_builder.py`

实现内容：

- account token alert：
  - watched author 提到 CA / symbol。
  - 标记 `is_first_seen_global`。
  - 标记 `is_first_seen_by_author`。
- account keyword alert：
  - watched author 提到 configured keyword。
  - 同样标记首次出现。
- token windows：
  - `1m`
  - `5m`
  - `1h`
  - `24h`
  - `mention_count`
  - `watched_mention_count`
  - `unique_author_count`
  - `weighted_reach`
  - `market_mindshare`
  - `watched_mindshare`
  - `velocity`
  - `top_authors_json`
  - `top_events_json`
- keyword windows 同理。

测试：

```bash
uv run python -m pytest tests/test_signal_builder.py -q
```

验收：

- watched account 发出 token mention，当场生成 account token alert。
- watched account 发出 keyword mention，当场生成 account keyword alert。
- 窗口指标可从 evidence + entity 重建。
- 同一 event 重放不会重复制造 alert。

### Phase 7：重接 CollectorService

目标：写入链路变成 store-first，然后 publish。

修改文件：

- `src/gmgn_twitter_intel/collector/service.py`
- `src/gmgn_twitter_intel/api/app.py`
- `tests/test_collector_service.py`
- `tests/test_api_health.py`

实现顺序：

1. 收到 raw frame。
2. normalizer 生成 event。
3. evidence repository 写 raw frame + event + FTS。
4. entity extractor 抽实体。
5. entity repository 写实体。
6. signal builder 生成 alerts/windows。
7. signal repository 写 signal。
8. WebSocket hub publish enriched payload。

测试：

```bash
uv run python -m pytest tests/test_collector_service.py tests/test_api_health.py -q
```

验收：

- 任何 live publish 之前，event 已经落库。
- DB 写失败时不 publish 假 live event。
- `/readyz` 能检测 DB 写探针、collector stale、frame/event stale。

### Phase 8：WebSocket replay 和 live payload

目标：客户端第一时间拿到结构化 entity/signal，而不是自己解析文本。

修改文件：

- `src/gmgn_twitter_intel/api/ws.py`
- `tests/test_api_websocket.py`

实现内容：

- replay payload 包含：
  - `event`
  - `entities`
  - `alerts`
- live payload 同样包含三层。
- subscribe scope 保持 handle filtering。
- auth 协议不扩大。

测试：

```bash
uv run python -m pytest tests/test_api_websocket.py -q
```

验收：

- replay 和 live payload shape 一致。
- watched account 的 token/keyword mention 可以在 payload 内直接看到 alert。

### Phase 9：Search / token-flow / account-alert 服务

目标：查询服务围绕交易工作流，而不是围绕存储实现。

新增文件：

- `src/gmgn_twitter_intel/retrieval/token_flow_service.py`
- `src/gmgn_twitter_intel/retrieval/account_alert_service.py`
- `tests/test_token_flow_service.py`
- `tests/test_account_alert_service.py`

修改文件：

- `src/gmgn_twitter_intel/retrieval/search_service.py`
- `tests/test_search_service.py`

删除文件：

- `src/gmgn_twitter_intel/retrieval/ranking.py`

实现内容：

- search：
  - CA 查询走 `event_entities` exact lookup。
  - symbol 查询走 `event_entities` exact lookup。
  - handle 查询走 `events(author_handle, received_at_ms)`。
  - keyword/text 查询走 FTS5 BM25。
- token-flow：
  - 从 `token_windows` 读窗口指标。
  - 排序优先级：watched mention、velocity、mention count。
- account-alerts：
  - 查询 watched account 的 token/keyword alerts。
  - 支持 author filter 和 alert type filter。

测试：

```bash
uv run python -m pytest tests/test_search_service.py tests/test_token_flow_service.py tests/test_account_alert_service.py -q
```

验收：

- 不再有 hash embedding ranking。
- 查询结果都能返回 top evidence。
- 大多数交易查询不需要扫 `events.raw_json`。

### Phase 10：CLI 重建为交易员命令

目标：CLI 直接回答交易问题。

修改文件：

- `src/gmgn_twitter_intel/cli.py`
- `tests/test_cli.py`

保留或新增命令：

```bash
gmgn-twitter-intel recent --limit 20
gmgn-twitter-intel search "base stablecoin" --limit 20
gmgn-twitter-intel search --symbol PEPE --limit 20
gmgn-twitter-intel token-flow --window 5m --limit 20
gmgn-twitter-intel keyword-flow --window 1h --limit 20
gmgn-twitter-intel account-alerts --window 24h --limit 50
gmgn-twitter-intel ops rebuild-windows --window 5m
gmgn-twitter-intel config
```

删除命令：

- `embed`
- `enrich`
- LanceDB-specific `ops rebuild-indexes`
- LanceDB store path options
- 只为 LLM enrichment 服务的命令

测试：

```bash
uv run python -m pytest tests/test_cli.py -q
```

验收：

- CLI 输出稳定 JSON。
- 命令围绕 evidence/entity/signal。
- 没有 LanceDB 参数。

### Phase 11：删除 LanceDB / embedding / LLM runtime

目标：把不属于当前产品的东西从仓库里删干净。

删除文件：

- `src/gmgn_twitter_intel/storage/lancedb_client.py`
- `src/gmgn_twitter_intel/storage/lancedb_schema.py`
- `src/gmgn_twitter_intel/storage/runtime_bootstrap.py`
- `src/gmgn_twitter_intel/storage/tweet_repository.py`
- `src/gmgn_twitter_intel/storage/social_repository.py`
- `src/gmgn_twitter_intel/storage/llm_repository.py`
- `src/gmgn_twitter_intel/pipeline/embedding.py`
- `src/gmgn_twitter_intel/pipeline/llm_enrichment.py`
- `src/gmgn_twitter_intel/retrieval/ranking.py`

修改文件：

- `pyproject.toml`
- `uv.lock`
- `tests/test_project_structure.py`
- `README.md`
- `AGENTS.md`
- `CLAUDE.md`
- `compose.yaml`
- `Dockerfile`
- `Makefile`

移除依赖：

- `lancedb`
- `pyarrow`
- `litellm`
- `openai`，如果只被 LiteLLM 使用

验证：

```bash
uv sync
rg -n "lancedb|LanceDB|pyarrow|litellm|llm_enrichment|embedding|HashEmbedding|TweetRepository|SocialRepository|LlmRepository" src tests README.md AGENTS.md CLAUDE.md pyproject.toml compose.yaml Dockerfile Makefile
rg -n "LANCEDB_PATH|EMBEDDING_DIM|LANCE_|RAYON_|twitter_intel\\.lancedb|rebuild-indexes|semantic projection" src tests README.md AGENTS.md CLAUDE.md pyproject.toml compose.yaml Dockerfile Makefile
uv run python -m pytest tests/test_project_structure.py -q
```

验收：

- 除迁移计划文档外，产品代码和产品文档没有 LanceDB。
- 没有未来占位。
- 没有 dead imports。

### Phase 12：Docker、文档、运维

目标：运行方式也围绕 SQLite，而不是旧数据目录。

修改文件：

- `compose.yaml`
- `Dockerfile`
- `Makefile`
- `README.md`
- `AGENTS.md`
- `CLAUDE.md`

实现内容：

- Docker volume 挂载 `/data`。
- 默认 DB 为 `/data/twitter_intel.sqlite3`。
- healthcheck 调 `/readyz`。
- 删除 LanceDB / Lance thread env。
- 文档写清楚：
  - `MONITOR_HANDLES`
  - `WATCH_KEYWORDS`
  - `WS_TOKEN`
  - `SQLITE_PATH`
  - SQLite backup 命令
  - trader CLI 工作流

备份命令：

```bash
sqlite3 /data/twitter_intel.sqlite3 ".backup '/data/backups/twitter_intel-YYYYMMDD-HHMMSS.sqlite3'"
```

验证：

```bash
uv run gmgn-twitter-intel config
uv run python -m compileall src tests
```

验收：

- 文档和实际配置一致。
- 不推荐 raw `cp -a` 复制热数据库。

### Phase 13：全量验证和 Docker soak

目标：证明系统可以跑，不只是单测通过。

本地验证：

```bash
uv run python -m pytest -q
uv run ruff check .
uv run python -m compileall src tests
```

Docker 验证：

```bash
docker compose up -d --build app
curl -fsS http://127.0.0.1:8765/readyz
docker compose exec -T app gmgn-twitter-intel recent --limit 5
docker compose exec -T app gmgn-twitter-intel token-flow --window 5m --limit 10
docker compose exec -T app gmgn-twitter-intel account-alerts --window 24h --limit 10
docker compose exec -T app gmgn-twitter-intel search stablecoin --limit 5
```

Soak：

```bash
sleep 43200
curl -fsS http://127.0.0.1:8765/readyz
docker compose logs --tail=200 app
```

验收：

- 12 小时内无 DB write hang。
- `/readyz` 持续健康，除非上游真实 stale。
- event count 和 raw frame count 正常增长。
- token/entity/signal 查询不积压。
- 没有 LanceDB 相关错误、配置或日志。

## 验收标准

这次硬化完成的定义：

- LanceDB 从当前产品中消失：代码、依赖、配置、Docker、CLI、产品文档都不保留。
- SQLite WAL 存储 raw frames、events、entities、alerts、windows。
- FTS5 可以在 ingest 活跃时执行全文检索。
- 监控账号提到 CA / cashtag / keyword 时，live payload 直接带 `entities` 和 `alerts`。
- `token-flow` 能显示 token mindshare、watched mindshare、velocity、top evidence。
- `account-alerts` 能显示监控账号的 token/keyword 提醒。
- `/readyz` 能暴露 collector、DB、frame/event freshness、写入错误。
- `uv run pytest`、`ruff`、`compileall` 全部通过。
- Docker 12 小时 soak 无写入 hang、无锁死、无积压扩大。

## 风险和取舍

### SQLite one-writer 风险

SQLite WAL 支持多读单写。当前服务是单进程 collector + API，这正好匹配。不要多容器同时写同一个 DB。

### FTS5 不是语义检索

这是有意取舍。当前交易问题优先需要 exact/entity/full-text/window，不需要 semantic similarity。不要为了语义想象力保留当前没有用的依赖。

### 历史 LanceDB 数据

不做自动迁移。如果历史数据重要，可以在切换前做一次离线 export/import。应用 runtime 不承担迁移兼容逻辑。

### Token symbol 歧义

cashtag 没有 CA 时不强行 resolved。这会让部分 token 在早期显示为 unresolved，但能避免把错误 token 写成事实。

## 推荐执行顺序

最稳的顺序是：

1. 先做 SQLite schema/client。
2. 再做 settings/runtime path。
3. 再做 entity extractor。
4. 再做 evidence repository。
5. 再做 signal builder/repository。
6. 再接 collector 和 WebSocket。
7. 再重建 search/CLI。
8. 最后删除 LanceDB/embedding/LLM runtime。
9. 最后做 Docker 和 12 小时 soak。

不要先删 LanceDB 再补新存储。那样会制造一段系统不可运行的中间态。正确做法是：先让 SQLite 路径完整可测试，然后一次性切换并清理旧路径。
