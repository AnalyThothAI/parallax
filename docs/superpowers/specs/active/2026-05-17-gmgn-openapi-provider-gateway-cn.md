# Spec — GMGN OpenAPI Provider Gateway Hard Cut

**Status**: Implementing
**Date**: 2026-05-17
**Owner**: Codex / Qinghuan
**Related**: `docs/ARCHITECTURE.md`, `docs/WORKERS.md`, `src/gmgn_twitter_intel/integrations/gmgn/openapi_client.py`, `src/gmgn_twitter_intel/app/runtime/providers_wiring.py`, `src/gmgn_twitter_intel/domains/asset_market/runtime/asset_profile_refresh_worker.py`

## Background

Token Radar icon/profile 缺失的直接现象来自 `asset_profiles` 没有稳定写入 `gmgn_dex_profile` ready rows。进一步排查显示 GMGN `/v1/token/info` 可以返回 `logo/link/pool/stat/dev` 等完整 token profile，但当前出口会间歇或持续遇到 Cloudflare/WAF 403 HTML challenge。官方 `gmgn-cli@1.3.0` 在同一出口、同一 API key、IPv4 可用的情况下也返回 `HTTP 403 non-JSON`，说明根因不是 Python 少传字段，也不是单纯换一个 HTTP client 能解决。

现有修复已把 Cloudflare challenge 识别为 provider-level block，并阻止 `asset_profile_refresh` 把整批 token 写成 `asset_profiles.status='error'`。这只是止血。当前 GMGN 链路仍有两个架构问题：

1. rate limit、transport fingerprint、cooldown、retry、cache 分散在 raw client、provider adapter、worker 错误处理之间；
2. raw OpenAPI client 同时承担 HTTP、认证、解析、节流、缓存职责，边界不清，后续扩展 `security/pool/holders/traders/trending` 会继续复制逻辑。

## First Principles

1. **Provider gateway 是唯一上游治理点。** GMGN OpenAPI 的 route weight、cache、retry、cooldown、circuit breaker、transport fingerprint 全部归 gateway，worker 和 domain provider 不直接治理 HTTP。
2. **Raw client 不做业务治理。** `GmgnOpenApiClient` 只负责构造 GMGN auth query、发送请求、解析 envelope、把上游错误分类成 typed integration exceptions。
3. **Domain fact 不记录 provider outage。** Cloudflare challenge、429 cooldown、5xx 网络抖动是 provider 状态，不是 token 状态。它们不得写入 `asset_profiles` 的 token-level `missing/error`。
4. **Hard cut，不保留旧链路。** `GmgnDexMarketProvider` 只依赖 gateway，不再依赖 raw client；旧的 client 内部 throttle 不保留；旧的 provider-level block 字符串判断不散落到 worker。
5. **Kappa/CQRS 约束不变。** OpenAPI raw frames 是输入，不是事实。事实仍只能落到 PostgreSQL material tables；gateway 不写数据库，只控制外部 IO。

## Goals

- **G1 Unified GMGN route gateway.** 建立 `GmgnOpenApiGateway`，统一暴露 token info、kline，并为后续 security/pool/holders/traders/trending 留出 route registry。
- **G2 Weighted rate governance.** 按 GMGN 官方 route weight 约束请求：`token_info/security/pool/kline/trending` weight 1，`holders/traders` weight 5。单进程内使用 leaky-bucket 行为，禁止 worker 自己 sleep。
- **G3 Circuit breaker.** 遇到 Cloudflare challenge、429 banned、provider unavailable 时 open circuit。circuit open 期间立即抛 provider unavailable，不继续打源站。
- **G4 Retry only transient failures.** 只对网络抖动和 5xx transient error 做有限 retry + jitter；Cloudflare challenge、429 cooldown、bad token request 不 retry。
- **G5 Transport upgrade.** `curl-cffi` 依赖下限升级到当前锁定的现代版本，默认 browser impersonation 使用当前可用的现代 Chrome profile，IPv4 继续强制。
- **G6 No compatibility branch.** wiring 中删除 raw client 直连 provider 的旧路径；测试守住 provider 只能接 gateway。

## Non-goals

- 不实现绕过 Cloudflare 的浏览器自动化、代理池、登录态复制或 JS challenge 求解。
- 不改 GMGN anonymous public WebSocket collector。
- 不引入新的 DB 表、worker heartbeat 表或 provider health 持久化表。
- 不把 OKX DEX token search 伪装成 GMGN fallback；OKX profile source 是单独的数据源设计，后续另立 spec。
- 不把 `asset_profiles` 变成 provider outage 日志。

## Target Architecture

```text
GmgnDexMarketProvider
  └─ GmgnOpenApiGateway
       ├─ route registry: path, method, weight, cache policy
       ├─ weighted leaky bucket
       ├─ circuit breaker / cooldown
       ├─ transient retry
       └─ GmgnOpenApiClient
            ├─ curl_cffi IPv4 transport
            ├─ X-APIKEY + timestamp + client_id auth query
            ├─ JSON envelope parsing
            └─ typed integration exceptions

asset_profile_refresh_worker
  └─ catches DexProviderTemporarilyUnavailable
       ├─ reports provider_blocked
       └─ does not write asset_profiles error rows
```

The gateway lives in `integrations/gmgn` because it is upstream-provider infrastructure, not domain logic. The domain adapter in `app/runtime/providers_wiring.py` maps `GmgnOpenApiProviderUnavailableError` to `DexProviderTemporarilyUnavailable`, preserving the domain boundary.

## Data Flow

```text
token_radar_projection_coverage ready rows
  + bounded recent event resolutions
        ↓
PendingAssetProfileQuery
        ↓
asset_profile_refresh_worker
        ↓
GmgnDexMarketProvider.token_profile()
        ↓
GmgnOpenApiGateway.token_info()
        ↓
GmgnOpenApiClient GET /v1/token/info
        ↓
DexTokenProfile
        ↓
asset_profiles ready row
        ↓
TokenProfileReadModel
        ↓
/api/token-radar and frontend icon/profile display
```

Provider outage path:

```text
Cloudflare HTML / 429 / provider unavailable
        ↓
GmgnOpenApiProviderUnavailableError
        ↓
Gateway opens circuit
        ↓
DexProviderTemporarilyUnavailable
        ↓
asset_profile_refresh result.provider_blocked = 1
        ↓
no asset_profiles mutation
```

## Interface Contracts

### `GmgnOpenApiClient`

- Owns only low-level OpenAPI mechanics: auth query, transport, JSON parsing, response mapping.
- Raises:
  - `GmgnOpenApiProviderUnavailableError` for Cloudflare challenge, 429/rate-limit cooldown, and provider unavailable envelopes.
  - `GmgnOpenApiTransientError` for retryable network/5xx failures.
  - `GmgnOpenApiError` for non-retryable OpenAPI errors.
- Does not own cache or rate limiting.

### `GmgnOpenApiGateway`

- Public sync methods:
  - `lookup_token_info(chain, address) -> GmgnTokenInfoLookup`
  - `token_kline(chain, address, resolution, limit, now_ms=None) -> list[GmgnTokenKlineCandle]`
- Applies per-route cache before consuming bucket tokens.
- Acquires route weight before calling raw client.
- Opens circuit on provider unavailable, using upstream reset/cooldown when available and a conservative default otherwise.
- Retries only transient errors.

### `GmgnDexMarketProvider`

- Depends on `GmgnOpenApiGateway`, not raw client.
- Maps provider outage to `DexProviderTemporarilyUnavailable`.
- Does not contain string checks for Cloudflare/rate-limit text.

## Acceptance Criteria

- **AC1.** WHEN `GmgnDexMarketProvider` is constructed, THEN it receives `GmgnOpenApiGateway` and no runtime code wires it directly to `GmgnOpenApiClient`.
- **AC2.** WHEN two token info calls hit the gateway cache, THEN only the first call consumes route weight and calls raw OpenAPI.
- **AC3.** WHEN `/v1/token/info` returns Cloudflare challenge, THEN gateway opens circuit and the next call fails immediately without raw HTTP.
- **AC4.** WHEN `/v1/token/info` returns 429 with `reset_at` or `X-RateLimit-Reset`, THEN gateway opens circuit until that time and does not retry during cooldown.
- **AC5.** WHEN raw client raises retryable transient error once and then succeeds, THEN gateway retries and returns the success.
- **AC6.** WHEN raw client raises Cloudflare/provider unavailable, THEN gateway does not retry.
- **AC7.** WHEN `asset_profile_refresh` sees provider unavailable, THEN it returns `provider_blocked=1`, `error=0`, and writes no `asset_profiles` status row.
- **AC8.** WHEN tests inspect raw client, THEN no client-level `min_request_interval_seconds` throttle remains.
- **AC9.** WHEN dependency metadata is checked, THEN `curl-cffi` lower bound is upgraded to the current modern version used in lockfile.

## Verification

- Unit tests for gateway cache, route weight, transient retry, circuit open, and provider-unavailable no-retry.
- Unit tests for provider wiring hard cut.
- Existing GMGN OpenAPI client parsing tests.
- Existing asset profile refresh provider-blocked tests.
- `ruff check` on modified files.
- Targeted `pytest` for GMGN, provider wiring, asset profile refresh, and pending profile query.
- Manual ops probe may return provider blocked in this environment; that is acceptable if it reports `error=0` and avoids token-level writes.

## Risks

| Risk | Severity | Mitigation |
|---|---:|---|
| Single-process limiter does not coordinate across multiple app processes. | Medium | Current local service runs one Python service. If multi-process deployment appears, add DB/Redis-backed provider gateway quota in a separate spec. |
| Circuit open hides quick upstream recovery. | Low | Keep default Cloudflare cooldown conservative but bounded; manual ops run can verify recovery. |
| Raw client tests relying on throttle/cache need rewrite. | Low | Deliberate hard cut; gateway owns those behaviours. |
| `curl-cffi` profile names change across versions. | Medium | Keep default profile configurable at gateway/client construction and covered by constructor tests. |
| Gateway grows into a business service. | Medium | Keep it provider-only. It returns integration models, never writes facts, never ranks tokens. |

## Boundaries

| Class | Behaviour |
|---|---|
| Always | Route all GMGN OpenAPI traffic through gateway; classify provider outage separately from token failure; keep writes in existing repositories/workers; prefer exact provider facts over frontend fallback. |
| Ask first | Adding provider health persistence, OKX DEX profile source, browser automation, proxy rotation, or multi-process distributed quota. |
| Never | Worker-local GMGN sleeps; UI fallback for missing icons; writing Cloudflare/429 as token `asset_profiles.error`; direct GMGN raw client usage from domain providers; retry loops against Cloudflare challenge. |
