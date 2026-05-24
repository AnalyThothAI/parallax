# Spec — OKX DEX WebSocket 长跑韧性与根因修复

**Status**: Draft
**Date**: 2026-05-24
**Owner**: Codex
**Related**:
- `docs/superpowers/plans/active/2026-05-11-okx-dex-ws-market-stream-and-radar-recovery-cn.md`
- OKX DEX WebSocket subscribe docs: `https://web3.okx.com/zh-hans/onchainos/dev-docs/market/websocket-subscribe`
- OKX DEX price-info docs: `https://web3.okx.com/zh-hans/onchainos/dev-docs/market/websocket-price-info-channel`

## Background

`market_tick_stream` 是 asset market 域的 Tier 1 行情流 worker。它从 token capture tier 取 hot `chain_token` 目标，调用 streaming provider 订阅 OKX DEX WS，然后把收到的行情写入 `market_ticks`，并把变化目标送入 Token Radar dirty queue。这个 worker 的 DB 写入边界在 `src/gmgn_twitter_intel/domains/asset_market/runtime/market_tick_stream_worker.py:112`，订阅和接收边界在 `src/gmgn_twitter_intel/domains/asset_market/runtime/market_tick_stream_worker.py:121` 和 `src/gmgn_twitter_intel/domains/asset_market/runtime/market_tick_stream_worker.py:125`。

OKX DEX WS client 当前负责连接、登录、订阅、接收 price-info 数据。连接使用 `websockets.connect(..., ping_interval=20, open_timeout=5, close_timeout=5)`，见 `src/gmgn_twitter_intel/integrations/okx/dex_ws_client.py:81` 到 `src/gmgn_twitter_intel/integrations/okx/dex_ws_client.py:87`。接收循环是直接 `await websocket.recv()` 后 `json.loads(str(raw_message))`，见 `src/gmgn_twitter_intel/integrations/okx/dex_ws_client.py:145` 到 `src/gmgn_twitter_intel/integrations/okx/dex_ws_client.py:160`。这里没有 OKX 文档要求的应用层字符串 `ping` / `pong` 处理，也没有 idle watchdog、`notice` 事件重连、或订阅 ack 错误分类。

2026-05-11 的既有恢复计划已经写明目标形态应是 `connect -> login -> subscribe -> ping loop -> yield price-info updates`，并要求每 25 秒发送纯文本 `"ping"`、期待 `"pong"`、在 close/timeout/notice/non-zero error 后重连，见 `docs/superpowers/plans/active/2026-05-11-okx-dex-ws-market-stream-and-radar-recovery-cn.md:371` 到 `docs/superpowers/plans/active/2026-05-11-okx-dex-ws-market-stream-and-radar-recovery-cn.md:375`。当前代码没有落完这个设计。

现有单测覆盖了签名、字段归一、订阅替换、recv 失败后可手动 `ensure_connected()`、连接 timeout bounded、close timeout bounded，见 `tests/unit/test_okx_dex_ws_client.py:158` 到 `tests/unit/test_okx_dex_ws_client.py:224`。但缺失这些关键长跑契约测试：应用层 `pong` 不应进入 JSON parser；idle 后必须发送文本 `ping`；`notice` 必须触发重连与重订阅；hung recv / hung close 不得导致 worker run_once 长时间卡住；OKX unavailable 时系统应降级到 poll lane 而不是让整体 readiness 失败。

运行证据显示，OKX WS 并非凭证、URL、channel、token 格式永久错误：在同一 app container、同一 operator config 下，登录返回 `code=0`，文本 `ping` 收到 `pong`，单 token `price-info` 能收到数据，约 49 个当前 hot 目标批量订阅能收到数百帧数据且无 subscribe error。线上日志同时显示 OKX WS 先成功进入 streaming，之后在 2026-05-23 23:31 至 23:38 多次从 `connecting` 变成 `disconnected`，并出现 `operation=connect error=timed out during opening handshake`。这说明外部链路是可用但不稳定，系统问题在于长连接协议和恢复生命周期不完整。

## Problem

OKX WS 失败的根因不是“OKX 永久不可用”或“配置凭证错误”，而是当前 adapter 把一个需要应用层心跳、idle 检测、notice 重连、重订阅和降级隔离的长期连接，做成了一个短测能过的裸 `recv()` 生成器。连接在无数据、服务升级、网络抖动或本机高负载时会自然中断；中断后客户端没有足够的协议语义和状态机来可靠恢复，worker 还会把 provider failure 直接上抛，最终把实时行情 lane 变成系统级不健康信号。

## First Principles

PostgreSQL facts are truth; provider raw frames are inputs, not facts. OKX WS 只能写入 `market_ticks` 这类物化事实，不能成为 Token Radar 或 asset identity 的业务真相。这个边界由 `MarketTickStreamWorker._persist_ticks()` 维护：它只在 tick 插入成功后 enqueue dirty targets，见 `src/gmgn_twitter_intel/domains/asset_market/runtime/market_tick_stream_worker.py:155`。

Worker `run_once()` 是业务边界；外部 IO 不应让单次 run 长时间逃出 runtime supervision。`market_tick_stream` 已在订阅和 `__anext__()` 外层使用 `asyncio.wait_for`，见 `src/gmgn_twitter_intel/domains/asset_market/runtime/market_tick_stream_worker.py:121` 和 `src/gmgn_twitter_intel/domains/asset_market/runtime/market_tick_stream_worker.py:133`，但 provider 的 recv/close/reconnect 生命周期仍缺少更细的协议级边界。

Streaming lane 是加速路径，不是唯一真相路径。`market_tick_poll` 可以提供 Tier 2 行情事实；因此 OKX WS 不可用时，系统应进入 degraded/poll-backed 状态，而不是让整体服务失败。

## Goals

- G1. OKX adapter SHALL implement OKX application-level heartbeat: when no message arrives for less than 30 seconds, send plain text `ping`; expect plain text `pong`; missing `pong` triggers reconnect.
- G2. OKX adapter SHALL treat close, recv timeout, service `notice`, non-zero login error, and non-zero subscribe error as classified recoverable or terminal events, with structured last-error metadata.
- G3. Desired subscriptions SHALL survive reconnect: after reconnect, the adapter resubscribes the current target set exactly once per active connection and records desired/acked counts.
- G4. `market_tick_stream.run_once()` SHALL remain bounded under hung connect, hung recv, hung close, service notice, and provider unavailable scenarios.
- G5. OKX WS failure SHALL degrade the realtime lane without making the whole app unhealthy when poll lane and database are healthy.
- G6. Observability SHALL expose enough state to answer “why is OKX WS not producing data?” without secret values: state, last close/error category, last message time, last pong time, reconnect count, desired subscriptions, acked subscriptions, data frames, emitted ticks.
- G7. The fix SHALL reduce self-inflicted CPU pressure by preventing broken reconnect loops and avoiding duplicate subscription churn; it does not need to solve Token Radar/equity projection churn in the same change.

## Non-goals

- N1. Do not change OKX credentials, URL, or operator config schema unless implementation proves a missing knob is required.
- N2. Do not remove `market_tick_poll` or make WS the only market source.
- N3. Do not change Token Radar scoring, ranking windows, or projection schema in this spec.
- N4. Do not subscribe to all discovered tokens. Keep explicit caps and hot-target selection.
- N5. Do not print or persist API secrets in logs, status payloads, test fixtures, or generated docs.

## Target Architecture

`OkxDexWebSocketMarketProvider` becomes a small connection manager instead of a naked `recv()` generator. It owns:

- connection lifecycle: connect, login, subscribe, receive, heartbeat, reconnect, close
- desired subscription set: requested by worker, persisted in memory, replayed after reconnect
- application heartbeat: text `ping` / `pong`, independent from the WebSocket protocol ping
- message classifier: data, subscribe ack, unsubscribe ack, error, notice, pong, unknown
- bounded output queue: normalized `OkxDexPriceInfoUpdate` rows flow to the worker without exposing raw websocket receive behavior
- health snapshot: redacted, structured, suitable for `/api/status`

`MarketTickStreamWorker` remains the owner of DB persistence. It asks the provider to replace targets and drains updates for one bounded stream cycle. Provider failures inside a cycle return a skipped/degraded `WorkerResult` with notes instead of crashing the full service when fallback market polling is configured and healthy.

Provider health is separated from app readiness. OKX WS states are IO states:

```text
disconnected -> connecting -> authenticating -> subscribed -> streaming
                 |              |                |             |
                 v              v                v             v
              failed_terminal / degraded_recoverable / circuit_open
```

`failed_terminal` is for auth/config errors that operator action must fix. `degraded_recoverable` is for network, idle timeout, close, notice, or upstream temporary errors. `circuit_open` is a cool-down state after repeated recoverable failures. Only terminal auth/config failure should be prominent as operator action; recoverable failures should keep poll lane alive.

## Conceptual Data Flow

```text
token_capture_tier
  -> market_tick_stream
  -> okx_ws_connection_manager
       -> connect/login/subscribe
       -> receive loop + application heartbeat
       -> reconnect + resubscribe
       -> bounded update queue
  -> market_ticks
  -> token_radar_dirty_targets
  -> token_radar_projection
```

The changed arrows are inside the OKX provider. `market_tick_stream` still writes facts and emits wake hints; it does not learn OKX protocol internals.

Fallback flow:

```text
okx_ws_connection_manager degraded/circuit_open
  -> market_tick_stream returns degraded/skipped notes
  -> market_tick_poll continues writing Tier 2 market_ticks
  -> /api/status shows realtime degraded, app ready if fallback facts are fresh enough
```

## Core Models

`OkxWsConnectionHealth`:

- `state`: connection state or degraded/circuit state.
- `last_state_change_at_ms`: monotonic state transition timestamp.
- `last_message_at_ms`: last raw inbound message time, including pong.
- `last_pong_at_ms`: last successful application-level pong.
- `last_error_category`: redacted enum such as `connect_timeout`, `login_error`, `subscribe_error`, `idle_timeout`, `notice_reconnect`, `closed`, `json_parse_error`.
- `last_error_code`: upstream code when present, never secrets.
- `reconnect_count`: count since process start.
- `desired_subscription_count`: current desired target count.
- `acked_subscription_count`: last known acked target count.
- `data_frame_count`: data frames since process start.
- `tick_count`: normalized updates yielded since process start.

`OkxWsFailurePolicy`:

- Recoverable: network close, opening handshake timeout, idle timeout, missing pong, service notice, transient parse/unknown frame after logging.
- Terminal until config change: missing credentials, login auth error, repeated explicit auth rejection.
- Circuit open: repeated recoverable failures above threshold in a rolling window; cool down before next reconnect.

## Interface Contracts

`/api/status`:

- Include `providers.okx_dex_ws` or equivalent provider health payload.
- Payload must be redacted and safe to show to an operator.
- Status semantics distinguish app readiness from OKX realtime health:
  - `ok=true` allowed when OKX WS is `degraded_recoverable` or `circuit_open` and poll lane is healthy.
  - `ok=false` reserved for DB unavailable, no viable market data path, or terminal required provider misconfiguration if the app is configured to require realtime.

Worker status:

- `market_tick_stream` notes include `provider_state`, `failure_category`, `stream_targets`, `ticks_inserted`, `degraded=true|false`.
- A recoverable provider failure in one cycle should be observable as skipped/degraded, not as an unbounded active task.

CLI config/status:

- `uv run gmgn-twitter-intel config` remains the source of truth for config paths.
- Diagnostics must report path/boolean/provider status only; no secret values.

## Acceptance Criteria

- AC1. WHEN a fake websocket produces no data for heartbeat interval THEN provider SHALL send plain text `ping` before 30 seconds and record `last_ping_at_ms`.
- AC2. WHEN a fake websocket responds with plain text `pong` THEN provider SHALL update `last_pong_at_ms` and SHALL NOT pass `pong` to `json.loads`.
- AC3. WHEN a fake websocket does not return `pong` within the configured pong timeout THEN provider SHALL close the old connection, classify `idle_timeout` or `missing_pong`, reconnect, and resubscribe desired targets.
- AC4. WHEN OKX sends `{"event":"notice","code":"64008",...}` THEN provider SHALL classify `notice_reconnect`, reconnect, and resubscribe without requiring process restart.
- AC5. WHEN login or subscribe returns a non-zero code THEN provider SHALL classify the upstream code and expose a redacted error category; auth failures SHALL be terminal, subscription validation failures SHALL be visible per target or per batch.
- AC6. WHEN connect, recv, or close hangs in tests THEN `market_tick_stream.run_once()` SHALL return or be cancellable within `stream_cycle_seconds + cleanup_timeout_seconds`, with no leaked active task.
- AC7. WHEN OKX WS is unavailable but `market_tick_poll` is healthy and recent THEN `/api/status` SHALL remain app-ready and mark OKX WS as degraded/circuit-open.
- AC8. WHEN running a live smoke with operator credentials THEN login + subscribe top N current hot targets + app-level ping/pong SHALL succeed without printing secrets.
- AC9. WHEN the provider reconnects after a data frame stream THEN duplicate subscriptions SHALL NOT grow unbounded and request rate SHALL remain under OKX request limits.
- AC10. WHEN `market_tick_stream.enabled=false` in runtime config THEN status SHALL clearly show realtime lane disabled by config, not failed by provider.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Reconnect loop increases CPU and upstream request rate | High | Circuit breaker, exponential backoff, reconnect counters, OKX request-limit-aware tests |
| `pong` or `notice` still hits JSON data path | High | Unit tests with exact plain text `pong` and notice frames |
| Resubscribe duplicates create upstream load | Medium | Desired set is canonical; acked counts tracked; tests assert one subscribe batch per reconnect |
| Degraded status hides real auth failures | Medium | Distinguish terminal auth/config errors from recoverable transport errors |
| Poll fallback overloads DB after WS failure | Medium | Keep configured poll batch/cadence caps; status shows fallback freshness rather than forcing catch-up |
| More health fields leak sensitive details | High | Health payload contains booleans, timestamps, enum categories, counts only |

## Evolution Path

After this fix, the next likely improvement is splitting OKX streaming into small shard connections when hot target count grows beyond one stable connection's comfort zone. The design should not foreclose sharding: desired subscription set and health snapshot should be per connection internally, with an aggregate provider-level status externally.

Separately, the current CPU problem has another root in projection churn: high-frequency market ticks dirty Token Radar targets and cause repeated read-model rewrites. This spec prevents a broken WS lane from amplifying load, but the projection churn fix should be a separate spec/plan focused on write suppression, freshness buckets, rank-history compaction, and duplicate no-op update avoidance.

## Alternatives Considered

- Disable `market_tick_stream` permanently. Rejected because it bypasses the broken lane and sacrifices Tier 1 realtime data; it is an operational safety switch, not a root fix.
- Only increase `open_timeout` from 5 seconds. Rejected because it may reduce opening-handshake false failures under load, but it does not implement OKX's required app heartbeat, notice reconnect, pong parsing, or degraded fallback semantics.
- Keep current provider and add more worker-level `wait_for`. Rejected because worker timeouts cannot correctly handle `pong`, `notice`, subscribe ack errors, or resubscribe state; protocol ownership belongs in the OKX adapter.
- Make OKX WS failure fatal to readiness. Rejected because the architecture has a poll lane and PostgreSQL facts; a realtime provider outage should degrade freshness, not take down all reads.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Implement OKX app-level heartbeat, reconnect/resubscribe, bounded provider lifecycle, redacted health, and degraded fallback semantics. |
| Ask first | Change runtime config defaults, increase subscription caps above current operator setting, or introduce multi-connection sharding. |
| Never | Print secrets, make provider frames business truth, rely on repository fixtures for live config, or claim WS fixed without unit + live smoke verification. |
