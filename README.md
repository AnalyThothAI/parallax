# GMGN Twitter Intel

监听 GMGN 匿名公共 Twitter WebSocket，把可解析推文写入本地 SQLite WAL 数据库，并在 evidence、entity、token signal、LLM enrichment、narrative signal 层上提供 `/ws` 实时推送、HTTP 健康检查和 JSON CLI 查询。

## 运行模型

- `make serve`：本地前台运行，适合开发和排查。
- `make docker-up`：Docker 运行，适合长期跑。
- 不提供 macOS LaunchAgent、systemd 或系统自启动命令。
- 外部程序只调用本服务的 `/ws`、`/readyz` 或 JSON CLI，不直接调用 GMGN 公共频道。

数据流：

```text
GMGN public WS
  -> normalize tweet
  -> SQLite WAL evidence
  -> deterministic entity extraction
  -> token signal windows
  -> enrichment jobs
  -> LLM watched-account enrichment
  -> narrative signal windows
  -> /ws live push + replay
  -> CLI search / token-flow / account-alerts / narrative-flow / account-narratives
```

## 快速开始

```bash
make sync
make init
make config
```

`make init` 会创建：

```text
~/.gmgn-twitter-intel/config.yaml
~/.gmgn-twitter-intel/logs/
```

编辑 `config.yaml` 中的 `handles`，如需启用 watched-account LLM enrichment，再配置 `llm.openai_api_key` 与 `llm.openai_model`。`ws_token` 是本服务的 Web/API 访问令牌；内置 cockpit 会从后端启动配置自动读取，不需要在页面里单独填写。

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

## 数据目录

本地前台和 Docker Compose 使用同一个宿主目录：

```text
~/.gmgn-twitter-intel/config.yaml
~/.gmgn-twitter-intel/twitter_intel.sqlite3
~/.gmgn-twitter-intel/logs/gmgn-twitter-intel.log
```

Docker Compose bind mount：

```text
宿主机: ~/.gmgn-twitter-intel
容器内: /root/.gmgn-twitter-intel
```

查询 Docker 内数据：

```bash
docker compose exec app gmgn-twitter-intel recent --limit 20
```

在线备份：

```bash
sqlite3 ~/.gmgn-twitter-intel/twitter_intel.sqlite3 ".backup '$HOME/.gmgn-twitter-intel/twitter_intel-YYYYMMDD-HHMMSS.sqlite3'"
```

不要用 raw `cp -a` 复制正在写入的热数据库。

## 配置

唯一配置源是 `~/.gmgn-twitter-intel/config.yaml`。服务不读取 `.env`、`SQLITE_PATH`、`MONITOR_HANDLES`、`WS_TOKEN` 等环境变量。

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
  sqlite_path: "twitter_intel.sqlite3"
llm:
  openai_api_key:
  openai_model:
  openai_base_url: "https://api.openai.com/v1"
  timeout_seconds: 20
  enrichment_poll_interval: 2
```

`storage.sqlite_path` 推荐保持相对路径，这样数据库固定落在 `~/.gmgn-twitter-intel` 下。内部 collector 参数在同一个 `config.yaml` 的 `upstream` 与 `collector` 段中维护。

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

推送 payload 包含三层：

```json
{
  "type": "event",
  "event": {"event_id": "...", "author": {"handle": "toly"}, "content": {"text": "..."}},
  "entities": [{"entity_type": "symbol", "normalized_value": "PEPE"}],
  "alerts": [{"alert_type": "account_token", "author_handle": "toly"}],
  "enrichment": null
}
```

内置 cockpit 会自动带鉴权；外部只读 HTTP API 调用需要 `Authorization: Bearer <ws_token>`，只有 `/api/bootstrap` 供同源前端启动使用：

```bash
TOKEN="replace-with-a-strong-token"
curl -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8765/api/status"
curl -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8765/api/recent?limit=20"
curl -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8765/api/search?q=%24PEPE&limit=20"
curl -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8765/api/token-flow?window=5m&limit=20"
curl -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8765/api/account-alerts?window=24h&limit=50"
curl -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8765/api/narrative-flow?window=1h&limit=20"
curl -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8765/api/account-narratives?window=24h&limit=50"
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
uv run gmgn-twitter-intel narrative-flow --window 1h --limit 20
uv run gmgn-twitter-intel account-narratives --window 24h --limit 50
uv run gmgn-twitter-intel enrichment-jobs --limit 50
uv run gmgn-twitter-intel ops rebuild-windows --window 5m
```

`search --symbol PEPE` 等价于查 `$PEPE`，但不会触发 shell 的 `$` 环境变量展开问题。

## 范围边界

- 所有可解析公共事件都会入库。
- `config.yaml` 的 `handles` 决定哪些事件触发 watched account 实时推送和默认 replay。
- CA、cashtag、hashtag、mention、URL/domain 都是确定性抽取。
- token signal 来自确定性 CA/cashtag；narrative signal 来自 watched-account LLM enrichment。
- LLM 输出必须绑定原文 evidence substring；不把模型猜测直接当事实。
- cashtag 没有 CA 时保持 unresolved symbol，不强行映射成某个 token。
- `coverage=public_stream` 代表 GMGN 匿名公共流覆盖，不是完整 Twitter firehose。
