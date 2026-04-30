# GMGN Twitter CLI

监听 GMGN 匿名公共 Twitter WebSocket，按 Twitter handle 过滤命中事件，落库到 LanceDB，并提供 WebSocket 推送、历史查询、token 检索和 social mindshare 计算。

## 三层概念

| 层 | 是什么 | 谁使用 |
|---|---|---|
| 上游公共频道 | `twitter_monitor_basic`、`twitter_monitor_token`，由 collector 连接 GMGN 匿名公共流 | 本服务内部使用 |
| 本地监控配置 | `MONITOR_HANDLES`，决定哪些作者事件算命中、实时推送、默认 replay | 部署者配置 |
| 对外接口 | 本服务暴露的 `/ws`、`/healthz`、`/readyz`、JSON CLI | 其他程序调用 |

外部程序不调用 GMGN 公共频道，也不传 `UPSTREAM_CHANNELS`。外部程序只调用本服务的 `/ws` 或 CLI。

## 存储和处理范围

- 上游公共频道进入的是同一条存储链路：所有可解析公共事件都会写入 LanceDB `twitter_events`。
- 写入时统一做去重、文本清洗、URL/cashtag/hashtag/mention/CA 抽取、token entity 落库和 embedding 状态标记。
- `MONITOR_HANDLES` 不是另一套存储；它只是命中筛选。命中的事件会在同一行设置 `matched_at_ms`，并进入实时 `/ws` 推送和默认历史 replay。
- 没有解析出 token 的推文仍会保存、清洗、embedding、语义检索，但不会进入某个 token/CA 的 mindshare 分子。
- `coverage=public_stream` 只代表 GMGN 匿名公共流覆盖，不等于完整 Twitter firehose。

## 数据流

```text
GMGN public WS
  -> parse/normalize Twitter event
  -> LanceDB twitter_events                 all parseable public events
  -> clean text / entities / embedding flag same processing path
  -> handle match by MONITOR_HANDLES
      -> matched_at_ms > 0
      -> /ws live push + default replay
  -> search / mindshare / LLM enrich / ops
```

## 快速启动

```bash
uv sync
cp .env.example .env
```

`.env` 示例：

```env
WS_TOKEN=replace-with-a-strong-token
MONITOR_HANDLES=toly,traderpow,theunipcs,dotyyds1234,brc20niubi,jessepollak,cz_binance,heyibinance,elonmusk,cookerflips,himgajria,cryptodevinl,spidercrypto0x
```

确认 handles 被正确读取：

```bash
uv run gmgn-twitter-cli config
```

输出结构类似，实际 `handles` 会是你的完整列表：

```json
{"ok":true,"data":{"handles":["toly","traderpow"],"handle_count":2}}
```

前台运行：

```bash
uv run gmgn-twitter-cli serve
```

macOS 后台运行：

```bash
uv run gmgn-twitter-cli service install --start
uv run gmgn-twitter-cli service status
uv run gmgn-twitter-cli service logs --lines 80
uv run gmgn-twitter-cli service stop
```

## 配置

| 变量 | 说明 | 默认 |
|---|---|---|
| `WS_TOKEN` | 下游 WebSocket 鉴权 token | 必填 |
| `MONITOR_HANDLES` | 需要监控的 Twitter handle，逗号分隔 | 空 |
| `API_HOST` | 本地 API 监听地址 | `0.0.0.0` |
| `API_PORT` | 本地 API 端口 | `8765` |
| `REPLAY_LIMIT` | WebSocket 默认 replay 条数 | `100` |
| `LANCEDB_PATH` | LanceDB 目录 | `~/.local/state/gmgn-twitter-cli/twitter_intel.lancedb` |
| `EMBEDDING_DIM` | LanceDB 固定向量维度 | `1024` |
| `SENTIMENT_BACKEND` | mindshare sentiment 后端 | `none` |
| `LLM_MODEL` | `enrich` 使用的 LiteLLM 模型 | 空 |

内部 collector 参数：

```env
UPSTREAM_CHANNELS=twitter_monitor_basic,twitter_monitor_token
UPSTREAM_CHAINS=sol,eth,base,bsc
GMGN_WS_APP_VERSION=20260429-12894-ccec416
GMGN_WS_PROXY=
```

一般不需要改。`EMBEDDING_DIM` 会决定 LanceDB 向量列结构，修改维度需要新建或重建 LanceDB 目录。

## 其他程序怎么使用

推荐生产实时接入 `/ws`；CLI 适合脚本、排查、离线任务。

外部程序可调用的只有这些本服务接口：

| 场景 | 调用什么 | 数据范围 |
|---|---|---|
| 实时消费 | `ws://127.0.0.1:8765/ws` | 已命中 `MONITOR_HANDLES` 的事件，再按客户端订阅条件过滤 |
| 服务健康和状态 | `GET /healthz`、`GET /readyz` | 服务状态、生效 handles、store 计数、backlog |
| 本地批处理查询 | `uv run gmgn-twitter-cli ...` | JSON 输出，适合其他程序用 subprocess 调用 |

当前 `/ws` 的 token 订阅是在 matched 事件集合里过滤。也就是说，`cas`/`symbols` 会返回命中 `MONITOR_HANDLES` 且包含该 token 的事件；它不是 GMGN 公共流全量 token 推送。

连接：

```text
ws://127.0.0.1:8765/ws
```

第一条消息必须鉴权：

```json
{"type":"auth","token":"replace-with-a-strong-token"}
```

按 handle 订阅：

```json
{"type":"subscribe","handles":["toly","elonmusk"],"replay":100}
```

按 CA 订阅：

```json
{"type":"subscribe","cas":[{"chain":"eth","ca":"0x6982508145454ce325ddbe47a25d4ec3d2311933"}],"replay":100}
```

按 symbol 订阅：

```json
{"type":"subscribe","symbols":["PEPE"],"replay":100}
```

`tokens` 是 `symbols` 的兼容别名：

```json
{"type":"subscribe","tokens":["PEPE"],"replay":100}
```

事件格式：

```json
{"type":"event","event":{"event_id":"...","source":{"coverage":"public_stream","channel":"twitter_monitor_basic"},"author":{"handle":"toly"},"content":{"text":"..."}}}
```

健康检查：

```bash
curl http://127.0.0.1:8765/healthz
curl http://127.0.0.1:8765/readyz
```

`/readyz` 会返回生效 handles、LanceDB 路径、采集计数、库内计数、entity backlog 和 embedding backlog。

## 各能力的数据范围

| 能力 | 范围 |
|---|---|
| 事件入库 | 所有可解析 GMGN 公共事件 |
| 清洗/实体抽取/embedding pending | 所有入库事件 |
| `/ws` live/replay | 命中 `MONITOR_HANDLES` 的事件；客户端 `handles`、`cas`、`symbols` 只是在这个集合上继续过滤 |
| `recent` | 命中 `MONITOR_HANDLES` 的历史事件 |
| `search` | 命中 `MONITOR_HANDLES` 的历史事件 |
| `mindshare` | 所有已入库且能解析到 resolved CA 的公共事件 |
| `enrich --unresolved` | 命中 `MONITOR_HANDLES` 且 unresolved 的事件 |

## CLI 能力

所有查询类命令都输出 JSON，方便其他程序调用。

```bash
# 查看脱敏后的生效配置
uv run gmgn-twitter-cli config

# 最近命中事件
uv run gmgn-twitter-cli recent --limit 20
uv run gmgn-twitter-cli recent --handles toly,elonmusk --limit 20

# 按 token 查询
uv run gmgn-twitter-cli recent --ca 0x6982508145454ce325ddbe47a25d4ec3d2311933 --chain eth --limit 20
uv run gmgn-twitter-cli recent --symbol PEPE --limit 20

# CA / symbol / handle / 文本混合检索
uv run gmgn-twitter-cli search "whale listing rumor" --limit 20
uv run gmgn-twitter-cli search "$PEPE" --limit 20
uv run gmgn-twitter-cli search "0x6982508145454ce325ddbe47a25d4ec3d2311933" --limit 20

# social mindshare
uv run gmgn-twitter-cli mindshare --ca 0x6982508145454ce325ddbe47a25d4ec3d2311933 --chain eth --window 1h
uv run gmgn-twitter-cli mindshare --symbol PEPE --window 24h

# 低成本后台处理
uv run gmgn-twitter-cli embed --limit 100
uv run gmgn-twitter-cli resolve-token --symbol PEPE

# LLM 富化，只对指定范围跑
uv run gmgn-twitter-cli enrich --unresolved --limit 20
uv run gmgn-twitter-cli enrich --ca 0x6982508145454ce325ddbe47a25d4ec3d2311933 --chain eth --limit 20

# 运维
uv run gmgn-twitter-cli ops reprocess-entities --limit 1000
uv run gmgn-twitter-cli ops rebuild-indexes
```

CLI 目前只新增 `config` 这个必要能力。其余能力先保持 KISS：实时消费走 `/ws`，历史和运维走 JSON CLI。等真实外部程序需要时，再加 `export ndjson`、`backfill` 或 `watch` 这类批处理/流式客户端命令。

## 开发

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
```
