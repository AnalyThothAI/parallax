# GMGN Twitter CLI

监听 GMGN 公共 Twitter 信号，按 Twitter handle 订阅，提供本地 WebSocket 推送和 SQLite 回放。

## 核心概念

```text
GMGN 公共 WS
  -> 解析标准事件
  -> observed_events  先存所有可解析公共事件
  -> matched_events   再存命中订阅 handle 的事件
  -> /ws 推送与 replay
```

- 用户只配置 `MONITOR_HANDLES`，不要配置 chain。
- `twitter_monitor_basic` 和 `twitter_monitor_token` 是上游公共频道，会一起监听。
- `observed_events` 用来保留最近公共流，方便新增 handle 后回填。
- `matched_events` 用来给外部 WS replay 和 `recent` 查询。
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
| `OBSERVED_RETENTION_DAYS` | 公共流保留天数 | `7` |
| `MATCHED_RETENTION_DAYS` | 命中事件保留天数 | `180` |

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
```

SQLite 固定在 `~/.local/state/gmgn-twitter-cli/events.sqlite3`，前台 CLI 和 macOS 后台服务读取同一个库。

服务启动时会从 `observed_events` 回填当前 `MONITOR_HANDLES` 到 `matched_events`。因此新增 handle 后重启服务，可以补到最近 `OBSERVED_RETENTION_DAYS` 内的历史。

## 健康检查

```bash
curl http://127.0.0.1:8765/healthz
curl http://127.0.0.1:8765/readyz
```

`/readyz` 会返回采集计数和库内计数，例如：

```json
{"collector":{"frames_received":100},"store_counts":{"observed_events":80,"matched_events":3}}
```

## 开发命令

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
```
