# GMGN Twitter CLI

监听 GMGN 公共 Twitter 信号，按 Twitter handle 订阅，提供本地 WebSocket 推送和 LanceDB 回放。

## 核心概念

```text
GMGN 公共 WS
  -> 解析标准事件
  -> twitter_events   单事实表存所有可解析公共事件
  -> matched 标记     命中订阅 handle 后在同一行标记
  -> /ws 推送与 replay
```

- 用户只配置 `MONITOR_HANDLES`，不要配置 chain。
- `twitter_monitor_basic` 和 `twitter_monitor_token` 是上游公共频道，会一起监听。
- `twitter_events` 是 LanceDB 单事实表；当前 WebSocket replay 只读取已命中的事件。
- 原始事件 JSON 会保留在事实行里，清洗文本、URL、cashtag、hashtag、mention 和 token entity 会作为可检索字段落库。
- `token_resolution_status` 当前支持 `resolved`、`unresolved`、`invalid_candidate`、`no_token`。没有解析出 token 的推文仍会存入 `twitter_events`，但不会进入 token mindshare 分子。
- 这是 GMGN 匿名公共流过滤，不等于完整 Twitter firehose。

## 快速启动

```bash
uv sync
cp .env.example .env
```

编辑 `.env`：

```env
WS_TOKEN=replace-with-a-strong-token
MONITOR_HANDLES=toly,elonmusk,cz_binance
```

前台运行：

```bash
uv run gmgn-twitter-cli serve
```

macOS 后台运行：

```bash
uv run gmgn-twitter-cli service install --start
```

后台状态与日志：

```bash
uv run gmgn-twitter-cli service status
uv run gmgn-twitter-cli service logs --lines 80
uv run gmgn-twitter-cli service stop
```

## 常用配置

| 变量 | 说明 | 默认 |
|---|---|---|
| `WS_TOKEN` | 下游 WebSocket 鉴权 token | 必填 |
| `MONITOR_HANDLES` | 订阅的 Twitter handle，逗号分隔 | 空 |
| `API_HOST` | 本地 API 监听地址 | `0.0.0.0` |
| `API_PORT` | 本地 API 端口 | `8765` |
| `LANCEDB_PATH` | LanceDB 目录 | `~/.local/state/gmgn-twitter-cli/twitter_intel.lancedb` |
| `EMBEDDING_DIM` | LanceDB embedding 向量维度 | `1024` |
| `SENTIMENT_BACKEND` | mindshare sentiment 后端，默认关闭 | `none` |
| `LLM_MODEL` | `enrich` 命令使用的 LiteLLM 模型 | 空 |

上游默认：

```env
UPSTREAM_CHANNELS=twitter_monitor_basic,twitter_monitor_token
UPSTREAM_CHAINS=sol,eth,base,bsc
```

`UPSTREAM_CHAINS` 是 GMGN 上游覆盖参数，不是外部订阅概念。

## WebSocket 使用

连接：

```text
ws://127.0.0.1:8765/ws
```

第一条消息必须鉴权：

```json
{"type":"auth","token":"replace-with-a-strong-token"}
```

订阅并拉最近历史：

```json
{"type":"subscribe","handles":["toly","elonmusk"],"replay":100}
```

事件格式：

```json
{"type":"event","event":{"event_id":"...","source":{"channel":"twitter_monitor_basic"},"author":{"handle":"toly"},"content":{"text":"..."}}}
```

## 查询历史

查命中订阅的历史事件：

```bash
uv run gmgn-twitter-cli recent --limit 20
uv run gmgn-twitter-cli recent --handles toly,elonmusk --limit 20
uv run gmgn-twitter-cli recent --ca 0x6982508145454ce325ddbe47a25d4ec3d2311933 --chain eth --limit 20
uv run gmgn-twitter-cli recent --symbol PEPE --limit 20
uv run gmgn-twitter-cli recent --store ~/.local/state/gmgn-twitter-cli/twitter_intel.lancedb --limit 20
uv run gmgn-twitter-cli search "whale listing rumor" --limit 20
uv run gmgn-twitter-cli mindshare --ca 0x6982508145454ce325ddbe47a25d4ec3d2311933 --chain eth --window 1h
uv run gmgn-twitter-cli embed --limit 100
uv run gmgn-twitter-cli ops reprocess-entities --limit 1000
uv run gmgn-twitter-cli ops rebuild-indexes
```

LanceDB 默认目录是 `~/.local/state/gmgn-twitter-cli/twitter_intel.lancedb`，前台 CLI 和 macOS 后台服务读取同一个库。
`EMBEDDING_DIM` 是 LanceDB 固定向量列维度；修改维度需要新建或重建 LanceDB 目录。
`mindshare` 输出会带 `public_stream_coverage` quality flag，提醒它只代表 GMGN 匿名公共流覆盖，不是完整 Twitter firehose。

## 健康检查

```bash
curl http://127.0.0.1:8765/healthz
curl http://127.0.0.1:8765/readyz
```

`/readyz` 会返回采集计数、库内计数和 backlog，例如：

```json
{"collector":{"frames_received":100},"store_counts":{"twitter_events":80,"matched_twitter_events":3},"embedding_backlog":{"pending":10}}
```

## 开发命令

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
```
