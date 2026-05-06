# GMGN Twitter Intel

监听 GMGN 匿名公共 Twitter WebSocket，把可解析推文写入 PostgreSQL evidence store，并在 evidence、entity、token signal、social-event harness 层上提供 `/ws` 实时推送、HTTP 健康检查和 JSON CLI 查询。

## 运行模型

- `make serve`：本地前台运行，适合开发和排查。
- `make docker-up`：Docker 运行，适合长期跑。
- 不提供 macOS LaunchAgent、systemd 或系统自启动命令。
- 外部程序只调用本服务的 `/ws`、`/readyz` 或 JSON CLI，不直接调用 GMGN 公共频道。

数据流：

```text
GMGN public WS
  -> normalize tweet
  -> PostgreSQL evidence
  -> deterministic entity extraction
  -> token signal windows
  -> deterministic social heat / quality / propagation / tradeability / timing scores
  -> immutable token signal snapshots
  -> watched-account social-event extraction jobs
  -> strict social-event-v2 LLM extraction
  -> attention seeds
  -> event clusters
  -> immutable harness snapshots
  -> shadow decisions
  -> local-market settlement
  -> credit attribution
  -> report-only weights
  -> /ws live push + replay
  -> CLI search / token-flow / token-signal-snapshots / social-events / harness-snapshots / harness-credits
```

Harness 链路有一条硬边界：只有 `handles` 中的 watched accounts 会进入 LLM social-event-v2 抽取；全量 GMGN public stream 仍只作为确定性 token flow / market evidence 和 token signal scoring，不会被全量送进 LLM。

LLM 不做交易决策，只抽取结构化 social event。Harness 负责落库、快照、shadow decision、结算、信用分配和 report-only 权重。

## 快速开始

```bash
make sync
make init
make config
```

`make init` 会创建：

```text
~/.gmgn-twitter-intel/config.yaml
~/.gmgn-twitter-intel/postgres_password
~/.gmgn-twitter-intel/logs/
```

编辑 `config.yaml` 中的 `handles`，如需启用 watched-account social-event extraction，再配置 `llm.api_key` 与 `llm.model`。`ws_token` 是本服务的 Web/API 访问令牌；内置 cockpit 会从后端启动配置自动读取，不需要在页面里单独填写。

本地前台运行：

```bash
make serve
```

Docker 运行：

```bash
make docker-up
make docker-status
make docker-logs
make docker-down
```

FastAPI 会直接服务前端构建产物。Docker 镜像会在构建阶段自动执行前端构建，运行后访问 `http://127.0.0.1:8765/`。页面会先读取 `/api/bootstrap`，再自动带上 `config.yaml` 里的 `ws_token` 访问 `/api/*` 快照并连接 `/ws` 实时流，不需要输入 token。

本地后端检查：

```bash
make check
```

## 数据库

本地前台和 Docker Compose 共用宿主配置文件。Docker Compose 启动专用 PostgreSQL 容器，并通过 Alembic 在 `migrate` 服务里执行 schema migration；应用容器只在 migration 完成后启动。

```text
~/.gmgn-twitter-intel/config.yaml
~/.gmgn-twitter-intel/postgres_password
~/.gmgn-twitter-intel/logs/gmgn-twitter-intel.log
```

Docker Compose 挂载：

```text
宿主配置: ~/.gmgn-twitter-intel -> /root/.gmgn-twitter-intel
PostgreSQL 数据: gmgn-twitter-intel-postgres -> /var/lib/postgresql
```

查询 Docker 内数据：

```bash
docker compose exec app gmgn-twitter-intel recent --limit 20
```

手动执行 migration / health check：

```bash
docker compose run --rm migrate
docker compose exec app gmgn-twitter-intel db health
```

不要从宿主机直接读取或复制 Docker named volume 里的热数据库；Docker 模式下通过 `/api/*`、`/ws` 或 `docker compose exec app gmgn-twitter-intel ...` 查询。

## 配置

唯一应用配置源是 `~/.gmgn-twitter-intel/config.yaml`。服务不读取 `.env`、`SQLITE_PATH`、`MONITOR_HANDLES`、`WS_TOKEN` 等环境变量。PostgreSQL 容器自身使用 Compose `environment` 初始化数据库名、用户和 password secret；应用仍只从 YAML 读取数据库连接。

核心字段：

```yaml
ws_token: "replace-with-a-strong-token"
handles:
  - toly
api:
  host: "0.0.0.0"
  port: 8765
  heartbeat_interval: 30
  replay_limit: 100
storage:
  postgres:
    dsn: "postgresql://gmgn_app:gmgn_app@postgres:5432/gmgn_twitter_intel"
    password_file: "postgres_password"
    pool_min_size: 1
    pool_max_size: 10
    connect_timeout_seconds: 5
llm:
  provider: "openai"
  api_key:
  model:
  base_url: "https://api.openai.com/v1"
  timeout_seconds: 20
  enrichment_poll_interval: 2
```

`storage.postgres.password_file` 相对 `~/.gmgn-twitter-intel` 解析；`make init` 会创建该 secret 文件。内部 collector 参数在同一个 `config.yaml` 的 `upstream` 与 `collector` 段中维护。

## 外部调用

健康检查：

```bash
curl http://127.0.0.1:8765/healthz
curl http://127.0.0.1:8765/readyz
```

WebSocket：

```text
ws://127.0.0.1:8765/ws
```

外部 WebSocket 客户端先发送 auth 消息：

```json
{"type":"auth","token":"replace-with-a-strong-token"}
```

订阅：

```json
{"type":"subscribe","handles":["toly"],"replay":20}
{"type":"subscribe","cas":[{"chain":"eth","ca":"0x6982508145454ce325ddbe47a25d4ec3d2311933"}],"replay":20}
{"type":"subscribe","symbols":["PEPE"],"replay":20}
```

推送 payload 使用同一个可回放读模型：

```json
{
  "type": "event",
  "event": {"event_id": "...", "author": {"handle": "toly"}, "content": {"text": "..."}},
  "entities": [{"entity_type": "symbol", "normalized_value": "PEPE"}],
  "alerts": [{"alert_type": "account_token", "author_handle": "toly"}],
  "token_attributions": [],
  "harness": null
}
```

内置 cockpit 会自动带鉴权；外部只读 HTTP API 调用需要 `Authorization: Bearer <ws_token>`，只有 `/api/bootstrap` 供同源前端启动使用：

```bash
TOKEN="replace-with-a-strong-token"
curl -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8765/api/status"
curl -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8765/api/recent?limit=20"
curl -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8765/api/search?q=%24PEPE&limit=20"
curl -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8765/api/token-flow?window=5m&limit=20"
curl -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8765/api/token-posts?token_id=token:eth:0x...&window=5m&limit=50"
curl -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8765/api/account-alerts?window=24h&limit=50"
curl -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8765/api/social-events?window=1h&limit=50"
curl -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8765/api/attention-seeds?window=1h&limit=50"
curl -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8765/api/harness-snapshots?horizon=6h&limit=50"
curl -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8765/api/harness-outcomes?horizon=6h&limit=50"
curl -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8765/api/harness-credits?horizon=6h&limit=80"
curl -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8765/api/harness-score-buckets?horizon=6h"
curl -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8765/api/harness-health"
curl -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8765/api/token-signal-snapshots?window=5m&limit=50"
curl -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8765/api/token-signal-outcomes?horizon=6h&limit=50"
curl -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8765/api/token-signal-evaluations?horizon=6h"
curl -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8765/api/enrichment-jobs?limit=50"
```

## CLI

所有查询命令输出 JSON，适合下游用 subprocess 调用。

```bash
uv run gmgn-twitter-intel init
uv run gmgn-twitter-intel config
uv run gmgn-twitter-intel recent --limit 20
uv run gmgn-twitter-intel search --symbol PEPE --limit 20
uv run gmgn-twitter-intel search --ca 0x6982508145454ce325ddbe47a25d4ec3d2311933 --limit 20
uv run gmgn-twitter-intel search "base stablecoin" --limit 20
uv run gmgn-twitter-intel token-flow --window 5m --limit 20
uv run gmgn-twitter-intel account-alerts --window 24h --limit 50
uv run gmgn-twitter-intel social-events --window 1h --limit 50
uv run gmgn-twitter-intel attention-seeds --window 1h --limit 50
uv run gmgn-twitter-intel harness-snapshots --horizon 6h --limit 50
uv run gmgn-twitter-intel harness-outcomes --horizon 6h --limit 50
uv run gmgn-twitter-intel harness-credits --horizon 6h --limit 80
uv run gmgn-twitter-intel harness-weights --horizon 6h --limit 100
uv run gmgn-twitter-intel harness-score-buckets --horizon 6h
uv run gmgn-twitter-intel harness-health
uv run gmgn-twitter-intel token-signal-snapshots --window 5m --limit 50
uv run gmgn-twitter-intel token-signal-outcomes --horizon 6h --limit 50
uv run gmgn-twitter-intel token-signal-evaluations --horizon 6h
uv run gmgn-twitter-intel enrichment-jobs --limit 50
uv run gmgn-twitter-intel ops rebuild-attributions --symbol PEPE
uv run gmgn-twitter-intel ops backfill-harness-jobs --limit 1000
uv run gmgn-twitter-intel ops settle-harness --horizon 6h
uv run gmgn-twitter-intel ops attribute-harness-credits --horizon 6h
uv run gmgn-twitter-intel ops update-harness-weights
uv run gmgn-twitter-intel ops freeze-token-signals --window 5m --limit 200
uv run gmgn-twitter-intel ops settle-token-signals --horizon 6h --limit 500
```

`search --symbol PEPE` 等价于查 `$PEPE`，但不会触发 shell 的 `$` 环境变量展开问题。

## 范围边界

- 所有可解析公共事件都会入库。
- `config.yaml` 的 `handles` 决定哪些事件触发 watched account 实时推送和默认 replay。
- CA、cashtag、hashtag、mention、URL/domain 都是确定性抽取。
- token 社交热度来自确定性 CA/cashtag attribution、rolling windows、timeline features、market snapshot 和可解释评分模块；Harness signal 来自 watched-account social-event-v2 extraction 加确定性 scoring。
- V1 不接外部新闻源，不自动实盘，不自动推广配置；`harness_weights.status` 先保持 `report_only`。
- 旧 narrative API/CLI 产品入口已移除；历史 narrative rows 不会被解释成新的 harness event。已有 watched 原始事件可用 `ops backfill-harness-jobs` 重新进入 social-event-v2 抽取队列。
- `token-flow` 返回 `social_heat`、`discussion_quality`、`propagation`、`tradeability`、`timing`、`opportunity` 评分块，以及 `score_versions`、`data_health`、`posts_query`、`timeline_query`。
- `freeze-token-signals` 把当前 token-flow 排名冻结为不可变 snapshot，结算与评估只读取冻结时的 evidence、timeline、component payload、market snapshot id，避免回看偏差。
- `token-posts` 按 token attribution 返回全量帖子分页，包含 `post_quality`、`total_count`、`has_more` 和 `next_cursor`。
- `token-social-timeline` 返回 bucket、authors、posts 和传播 summary，用于查看单币社交传播路径。
- LLM 输出必须绑定原文 evidence substring；不把模型猜测直接当事实。
- cashtag 没有 CA 时保持 unresolved symbol，不强行映射成某个 token。
- `coverage=public_stream` 代表 GMGN 匿名公共流覆盖，不是完整 Twitter firehose。
