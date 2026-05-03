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
cp .env.example .env
make config
```

`.env` 至少配置：

```env
WS_TOKEN=replace-with-a-strong-token
MONITOR_HANDLES=toly,traderpow,theunipcs,dotyyds1234,brc20niubi,jessepollak,cz_binance,heyibinance,elonmusk,cookerflips,himgajria,cryptodevinl,spidercrypto0x
```

如需启用 watched-account LLM enrichment，再配置 `OPENAI_API_KEY` 与 `OPENAI_MODEL`。

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

完整检查：

```bash
make check
```

## 数据目录

本地前台默认使用：

```text
~/.gmgn-twitter-intel/twitter_intel.sqlite3
```

Docker Compose 默认使用 Docker named volume：

```text
volume: gmgn-twitter-intel_data
容器内: /data/twitter_intel.sqlite3
```

查询 Docker 内数据：

```bash
docker compose exec app gmgn-twitter-intel recent --limit 20
```

指定数据库路径：

```bash
SQLITE_PATH=/absolute/path/to/twitter_intel.sqlite3 uv run gmgn-twitter-intel recent --limit 20
```

在线备份：

```bash
sqlite3 /data/twitter_intel.sqlite3 ".backup '/data/backups/twitter_intel-YYYYMMDD-HHMMSS.sqlite3'"
```

不要用 raw `cp -a` 复制正在写入的热数据库。

## 配置

| 变量 | 说明 | 默认 |
|---|---|---|
| `WS_TOKEN` | 下游 WebSocket 鉴权 token，启动 `/ws` 服务时必填 | 必填 |
| `MONITOR_HANDLES` | 需要实时命中的 Twitter handle，逗号分隔 | 空 |
| `SQLITE_PATH` | SQLite 数据库文件 | `~/.gmgn-twitter-intel/twitter_intel.sqlite3` |
| `API_HOST` | API 监听地址 | `0.0.0.0` |
| `API_PORT` | API 端口 | `8765` |
| `REPLAY_LIMIT` | WebSocket replay 默认条数 | `100` |
| `GMGN_TWITTER_HOME` | 运行数据根目录 | `~/.gmgn-twitter-intel` |
| `OPENAI_API_KEY` | watched-account LLM enrichment API key；为空时只积压 enrichment job | 空 |
| `OPENAI_MODEL` | watched-account enrichment 使用的模型；与 API key 同时配置才会启动 worker | 空 |
| `OPENAI_BASE_URL` | OpenAI-compatible API base URL | `https://api.openai.com/v1` |
| `LLM_TIMEOUT_SECONDS` | 单条 enrichment 请求超时 | `20` |
| `ENRICHMENT_POLL_INTERVAL` | enrichment worker 空轮询间隔 | `2` |

内部 collector 参数一般不需要改：

```env
UPSTREAM_CHANNELS=twitter_monitor_basic,twitter_monitor_token
UPSTREAM_CHAINS=sol,eth,base,bsc
GMGN_WS_APP_VERSION=20260429-12894-ccec416
GMGN_WS_PROXY=
UPSTREAM_IDLE_TIMEOUT=90
COLLECTOR_STALE_TIMEOUT=180
```

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

第一条消息鉴权：

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

## CLI

所有查询命令输出 JSON，适合下游用 subprocess 调用。

```bash
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
- `MONITOR_HANDLES` 决定哪些事件触发 watched account 实时推送和默认 replay。
- CA、cashtag、hashtag、mention、URL/domain 都是确定性抽取。
- token signal 来自确定性 CA/cashtag；narrative signal 来自 watched-account LLM enrichment。
- LLM 输出必须绑定原文 evidence substring；不把模型猜测直接当事实。
- cashtag 没有 CA 时保持 unresolved symbol，不强行映射成某个 token。
- `coverage=public_stream` 代表 GMGN 匿名公共流覆盖，不是完整 Twitter firehose。
