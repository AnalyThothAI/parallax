# GMGN Twitter Intel

监听 GMGN 匿名公共 Twitter WebSocket，把可解析推文写入 LanceDB，并提供本地 `/ws` 实时推送、HTTP 健康检查和 JSON CLI 查询。

## 运行模型

- `make serve`：本地前台运行，适合开发和排查。
- `make docker-up`：Docker 运行，适合长期跑。
- 不再提供 macOS LaunchAgent、systemd 或任何系统自启动命令。
- 外部程序只调用本服务的 `/ws`、`/readyz` 或 JSON CLI，不直接调用 GMGN 公共频道。

数据流：

```text
GMGN public WS
  -> normalize tweet
  -> LanceDB twitter_events
  -> text cleanup / entity extraction / embedding status
  -> MONITOR_HANDLES match
  -> /ws live push + replay
  -> CLI search / mindshare / ops
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

把当前 checkout 安装或更新成全局 CLI：

```bash
make install
gmgn-twitter-intel config
```

如果安装后 shell 找不到 `gmgn-twitter-intel`，先运行一次：

```bash
make tool-path
```

全局 CLI 会读取当前目录的 `.env`，也会读取默认运行目录：

```text
~/.gmgn-twitter-intel/.env
```

所以如果希望在任意目录直接运行 `gmgn-twitter-intel serve`，可以把运行配置放到 `~/.gmgn-twitter-intel/.env`。`config` 和本地查询命令可以在没有 `WS_TOKEN` 时运行；启动 `/ws` 服务仍需要配置 `WS_TOKEN`。

## 数据目录

本地前台默认使用：

```text
~/.gmgn-twitter-intel/twitter_intel.lancedb
```

Docker Compose 默认挂载：

```text
宿主机: ${GMGN_TWITTER_HOME:-$HOME/.gmgn-twitter-intel}
容器内: /data
LanceDB: /data/twitter_intel.lancedb
```

所以默认情况下，本地前台和 Docker 会读写同一个宿主机目录：

```text
$HOME/.gmgn-twitter-intel/twitter_intel.lancedb
```

想换目录：

```bash
make docker-up APP_HOME=/absolute/path/to/gmgn-twitter-intel
```

或者在普通 CLI 中设置：

```bash
LANCEDB_PATH=/absolute/path/to/twitter_intel.lancedb uv run gmgn-twitter-intel serve
```

`EMBEDDING_DIM` 会决定 LanceDB 向量列维度，已有库不建议改维度。

## 配置

| 变量 | 说明 | 默认 |
|---|---|---|
| `WS_TOKEN` | 下游 WebSocket 鉴权 token，启动 `/ws` 服务时必填 | 必填 |
| `MONITOR_HANDLES` | 需要实时命中的 Twitter handle，逗号分隔 | 空 |
| `API_HOST` | API 监听地址 | `0.0.0.0` |
| `API_PORT` | API 端口 | `8765` |
| `REPLAY_LIMIT` | WebSocket replay 默认条数 | `100` |
| `GMGN_TWITTER_HOME` | 运行数据根目录 | `~/.gmgn-twitter-intel` |
| `LANCEDB_PATH` | LanceDB 目录 | `~/.gmgn-twitter-intel/twitter_intel.lancedb` |
| `EMBEDDING_DIM` | LanceDB embedding 固定维度 | `1024` |
| `SENTIMENT_BACKEND` | mindshare sentiment 后端 | `none` |
| `LLM_MODEL` | `enrich` 使用的 LiteLLM 模型 | 空 |

内部 collector 参数一般不需要改：

```env
UPSTREAM_CHANNELS=twitter_monitor_basic,twitter_monitor_token
UPSTREAM_CHAINS=sol,eth,base,bsc
GMGN_WS_APP_VERSION=20260429-12894-ccec416
GMGN_WS_PROXY=
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

Python 客户端如果本机有代理环境变量，建议 `proxy=None`：

```python
import asyncio
import json
import websockets

async def main():
    async with websockets.connect("ws://127.0.0.1:8765/ws", proxy=None) as ws:
        await ws.send(json.dumps({"type": "auth", "token": "replace-with-a-strong-token"}))
        print(await ws.recv())
        await ws.send(json.dumps({"type": "subscribe", "symbols": ["PEPE"], "replay": 20}))
        async for message in ws:
            print(json.loads(message))

asyncio.run(main())
```

## CLI

所有查询命令输出 JSON，适合下游用 subprocess 调用。

开发时可以继续用 `uv run` 调用仓库内环境；如果已经执行过 `make install`，也可以直接用全局 `gmgn-twitter-intel` 命令。

```bash
uv run gmgn-twitter-intel config
uv run gmgn-twitter-intel recent --limit 20
uv run gmgn-twitter-intel search --symbol PEPE --limit 20
uv run gmgn-twitter-intel search --ca 0x6982508145454ce325ddbe47a25d4ec3d2311933 --limit 20
uv run gmgn-twitter-intel search "whale listing rumor" --limit 20
uv run gmgn-twitter-intel mindshare --symbol PEPE --window 24h
uv run gmgn-twitter-intel embed --limit 100
uv run gmgn-twitter-intel ops reclassify-processing --dry-run --limit 1000
uv run gmgn-twitter-intel ops reprocess-entities --limit 1000
uv run gmgn-twitter-intel ops rebuild-indexes
```

`search --symbol PEPE` 等价于查 `$PEPE`，但不会触发 shell 的 `$` 环境变量展开问题。只有手写 `"$PEPE"` 时，zsh/bash 会先把 `$PEPE` 当环境变量展开；普通文本、CA、`PEPE`、`--symbol PEPE` 都没有这个问题。

`search` 输出形态：

```json
{
  "ok": true,
  "data": {
    "query": {"kind": "symbol", "text": "$PEPE", "scope": "all", "symbol": "PEPE"},
    "result_count": 0,
    "items": [],
    "candidates": []
  },
  "error": null
}
```

有结果时 `items` 中每项包含：

```json
{"event": {"event_id": "...", "author": {"handle": "..."}, "content": {"text": "..."}}, "match_type": "exact_ca", "score": 100.0}
```

## 范围边界

- 所有可解析公共事件都会入库。
- `MONITOR_HANDLES` 只决定哪些事件进入实时 `/ws` 推送和默认 replay。
- `search` 默认查所有已入库公共事件；`--scope matched` 只查命中 `MONITOR_HANDLES` 的事件。
- `recent` 只返回命中 `MONITOR_HANDLES` 的历史事件。
- 没解析出 token 的推文仍会保存、清洗；只有命中监控 handle、或带有明确 crypto 语义信号的 tokenless 内容才进入 embedding 队列。
- `coverage=public_stream` 代表 GMGN 匿名公共流覆盖，不是完整 Twitter firehose。
