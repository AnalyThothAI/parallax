# Spec — Token Profile Image Mirror KISS Root Fix

**Status**: Approved for planning
**Date**: 2026-05-31
**Owner**: Codex / Qinghuan
**Related**: `docs/CONTRACTS.md`, `docs/WORKERS.md`, `src/parallax/domains/asset_market/ARCHITECTURE.md`, `docs/superpowers/specs/active/2026-05-17-gmgn-openapi-provider-gateway-cn.md`

## Background

Token Radar row 的图标不是 Token Radar scoring contract 的一部分。`AssetFlowService`
从 `token_radar_current_rows` 读取 current rows 后，再通过 profile read model
hydrate profile block；这发生在 `src/parallax/domains/token_intel/read_models/asset_flow_service.py:80`
和 `src/parallax/domains/token_intel/read_models/asset_flow_service.py:81`。

公开 profile 图标只来自 `token_profile_current.logo_url`。
`TokenProfileReadModel` 在 ready profile 中只暴露 `identity.logo_url`，见
`src/parallax/domains/asset_market/read_models/token_profile_read_model.py:36`
和 `src/parallax/domains/asset_market/read_models/token_profile_read_model.py:46`。
前端也只消费这个公开字段；没有字段时显示 fallback mark，见
`web/src/shared/model/tokenRadarCompactCase.ts:24` 和
`web/src/features/live/ui/TokenRadarTable.tsx:291`。

直接展示 GMGN、OKX、Binance 等 provider logo URL 不是当前产品契约，也不是可靠
方案。公开图片必须是 same-origin local mirror URL。`/api/token-images/{image_id}`
只服务 `token_image_assets.status='ready'` 且本地缓存文件存在的 row，见
`src/parallax/app/surfaces/api/routes_token_images.py:18`、
`src/parallax/app/surfaces/api/routes_token_images.py:24` 和
`src/parallax/app/surfaces/api/routes_token_images.py:28`。

当前 profile projection 已经尊重这个 hard cut：它只在 provider logo URL 对应 ready
local image row 时写 public `logo_url`；否则写 `logo_mirror_pending`，见
`src/parallax/domains/asset_market/services/token_profile_current_projection.py:392`
到 `src/parallax/domains/asset_market/services/token_profile_current_projection.py:403`。
`TokenProfileCurrentWorker` 会收集候选 provider logo URL，并只查询
`token_image_assets.ready_by_source_urls(...)`，见
`src/parallax/domains/asset_market/runtime/token_profile_current_worker.py:113`
到 `src/parallax/domains/asset_market/runtime/token_profile_current_worker.py:148`。

`TokenImageMirrorWorker` 的输入是 `token_image_source_dirty_targets`。队列为空时它
直接返回 `no_due_token_image_source_targets`，见
`src/parallax/domains/asset_market/runtime/token_image_mirror_worker.py:52`
到 `src/parallax/domains/asset_market/runtime/token_image_mirror_worker.py:65`。
而 `asset_profile_refresh` 当前成功写 profile source 后只 enqueue
`token_profile_current_dirty_targets`，没有在同一处显式 enqueue image source dirty
target；见 `src/parallax/domains/asset_market/runtime/asset_profile_refresh_worker.py:186`
到 `src/parallax/domains/asset_market/runtime/asset_profile_refresh_worker.py:217`。
这和 manifest 声明的 `asset_profile_refresh` 写
`token_image_source_dirty_targets` 不一致，见
`src/parallax/app/runtime/worker_manifest.py:207` 到
`src/parallax/app/runtime/worker_manifest.py:210`。

2026-05-31 的只读诊断显示：Token Radar 1h/all/all current rows 是 fresh 且
targetful；但 `token_image_assets` 为空、`token_image_source_dirty_targets` 为空，
同时多个 ready `token_profile_current` row 带 provider logo candidate 并标记
`logo_mirror_pending`。这说明“source URL 不能直接展示”不是根因；缺口应按
source admission → local mirror → profile re-projection 的 durable lifecycle 继续定位。

## Problem

Token Radar row 有可交易 token、可用 profile source、甚至 provider logo candidate，
但公开 icon 长期为空。用户看到的是“所有 token 都没有 icon”，系统内部看到的是
`logo_mirror_pending` 但 image mirror 没有 durable work。这个状态会误导排障：
它看起来像远端 provider 图不可用，实际可能是 provider logo source 从未进入本地镜像队列。

## First Principles

1. **Provider URL 是 source，不是 public asset.** GMGN、OKX、Binance logo URL 可以
   作为下载源和 provenance，但前端/API 不直接展示它们。
2. **Local mirror 是唯一 public image surface.** public `logo_url` 要么是
   `/api/token-images/{image_id}`，要么是 `NULL`。
3. **Durable queue 才是 worker truth.** `token_image_mirror` 不扫描 profile 表找活；
   它只消费 `token_image_source_dirty_targets`，队列缺失就是 lifecycle 缺失。
4. **KISS：一个缺图 target 只有一个状态分类。** 不再用“pending”同时表达无源图、
   未入队、下载失败、unsupported、待 re-project。

## Goals

- **G1 Root-cause classification.** 每个缺图 Token Radar target 能被确定归入：
  `no_source_logo`、`source_not_admitted`、`mirror_pending`、`mirror_failed`、
  `mirror_unsupported`、`ready_not_projected`、`ready_projected`。
- **G2 Single source admission owner.** 对 Token Radar/profile 需要展示的 token，
  provider logo candidate 必须由一个明确 owner 写入
  `token_image_source_dirty_targets`；不要多处临时 SQL 扫描或前端 fallback。
- **G3 Local mirror loop closes.** 当 provider logo candidate 可下载并镜像成功后，
  `token_profile_current.logo_url` 最终投影为 same-origin `/api/token-images/{image_id}`。
- **G4 No fake pending.** 如果没有 provider logo candidate，或 source 已知
  unsupported，profile quality flags 必须表达真实状态，不再停留在不可执行的
  `logo_mirror_pending`。
- **G5 Backfill existing stuck rows.** 现有 ready profile 中带 source logo candidate
  但未 admitted 的 rows 可以通过一次 ops/backfill 入队，不需要重跑整个 Token Radar。

## Non-goals

- 不直接在前端或 API 展示 GMGN/OKX/Binance provider URL。
- 不恢复 `/api/token-image?url=...` 远端代理。
- 不把 token icon 放进 `factor_snapshot_json` 或 Token Radar scoring input。
- 不新增 DB 表；使用现有 `token_image_assets`、`token_image_source_dirty_targets`、
  `token_profile_current_dirty_targets`。
- 不用本 spec 解决 GMGN OpenAPI Cloudflare/WAF 问题；那是 provider profile source
  coverage 问题，不是 image mirror lifecycle。
- 不引入浏览器自动化、代理池、登录态复制、JS challenge 求解。
- 不做 symbol-only DEX logo matching。

## Target Architecture

缺图链路收敛为一个小闭环：

```text
persisted profile/evidence source
  -> select exact provider logo candidates
  -> admit missing non-terminal image sources
  -> token_image_source_dirty_targets
  -> token_image_mirror
  -> token_image_assets ready / unsupported / error
  -> token_profile_current_dirty_targets
  -> token_profile_current.logo_url = /api/token-images/{image_id} or NULL with reason
  -> /api/token-radar profile.identity.logo_url
  -> frontend img or fallback mark
```

Source admission 只做三件事：

- 从当前 profile projection 已经选择的 exact source candidates 提取 absolute HTTPS
  image URL；
- 跳过已有 terminal image source：`ready` 和 `unsupported` 不重复入队；
- 对没有 terminal row 的 source 写 durable dirty target，并保留 target identity、
  source provider、source kind、source watermark 和 bounded provenance。

推荐的 ownership 是 profile-current projection lane：它已经同时看见 GMGN OpenAPI、
Binance Web3、GMGN stream exact snapshot、OKX exact-address evidence、CEX profile
和 target identity。这样比在每个 upstream source writer 里复制 admission 逻辑更
KISS，也能覆盖 stream/evidence 这类不经过 `asset_profile_refresh` 的 logo source。

如果 implementation plan 选择别的 owner，必须证明它仍然覆盖上述所有 exact source
families，且不会让同一个 source URL 被多个 worker 重复入队。

## Conceptual Data Flow

Current behaviour:

```text
provider/evidence source with logo URL
  -> token_profile_current sees no ready local image
  -> writes logo_url NULL + logo_mirror_pending
  -> token_image_mirror sees empty dirty queue
  -> icon never appears
```

Target behaviour:

```text
provider/evidence source with logo URL
  -> token_profile_current classifies missing local image as source_not_admitted
  -> durable source admission writes token_image_source_dirty_targets
  -> token_image_mirror downloads to local cache
  -> mirror completion enqueues token_profile_current_dirty_targets
  -> token_profile_current projects /api/token-images/{image_id}
```

Unsupported source behaviour:

```text
provider/evidence source with unsupported/missing/default logo
  -> no image dirty target
  -> token_profile_current.logo_url NULL
  -> quality_flags explain source_without_logo / placeholder_logo / mirror_unsupported
```

## Core Models

### Image Source Candidate

Semantic fields:

- `target_type`, `target_id` — exact public target identity.
- `source_url` — absolute HTTPS provider image URL.
- `source_provider` — selected source family, such as `gmgn_stream_snapshot`,
  `okx_dex_evidence`, `binance_cex_profile`, `gmgn_dex_profile`, or
  `binance_web3_profile`.
- `source_kind` — where the URL came from, such as
  `token_profile_current.source_payload.i`, `asset_profiles.logo_url`,
  `asset_identity_evidence.raw_payload.tokenLogoUrl`, or
  `cex_token_profiles.logo_url`.
- `source_watermark_ms` — latest source observation driving admission.
- `raw_ref_json` — bounded provenance, never provider raw payload dumps.

### Image Lifecycle Status

For one target/source URL pair:

- `no_source_logo` — exact persisted source exists but has no usable logo URL.
- `source_not_admitted` — usable source URL exists, but no dirty/asset row exists.
- `mirror_pending` — dirty row or pending/error retry row exists.
- `mirror_failed` — `token_image_assets.status='error'` and retry is scheduled.
- `mirror_unsupported` — terminal unsupported media or disallowed source.
- `ready_not_projected` — local image is ready, but current profile still has NULL logo.
- `ready_projected` — current profile exposes `/api/token-images/{image_id}`.

Only `ready_projected` creates a public icon.

## Interface Contracts

### HTTP/API

- `/api/token-radar` continues to expose `profile.identity.logo_url` as `NULL` or
  `/api/token-images/{image_id}` only.
- `/api/token-radar` does not expose provider image URLs.
- `/api/token-images/{image_id}` remains the only public image route.

### CLI/Ops

- Existing `uv run parallax ops mirror-token-images` should become useful when
  source candidates exist: it consumes admitted dirty rows and writes local
  cache assets.
- A minimal backfill/repair command may be added in the plan if needed, but it
  must only enqueue `token_image_source_dirty_targets`; it must not download
  images inline, mutate Token Radar rows, or call profile providers.

### Workers

- `token_image_mirror` continues to own downloads and local file writes.
- `token_profile_current` continues to own public profile projection.
- Source admission may write only control-plane dirty targets; it must not write
  `token_image_assets` or local files.

## Acceptance Criteria

- **AC1.** WHEN a ready profile/evidence source has a usable absolute HTTPS logo
  candidate and no ready/unsupported/error/pending local image row exists, THEN
  system SHALL enqueue exactly one `token_image_source_dirty_targets` row for
  `(source_url_hash, target_type, target_id)`.
- **AC2.** WHEN a source URL already has `token_image_assets.status='ready'`,
  THEN system SHALL not enqueue a duplicate image dirty row and SHALL project
  `token_profile_current.logo_url` to `/api/token-images/{image_id}` after the
  profile target is rebuilt.
- **AC3.** WHEN a source URL already has terminal `unsupported`, THEN system
  SHALL not requeue it forever and SHALL expose `logo_url=NULL` with a
  non-pending quality reason.
- **AC4.** WHEN provider/evidence source has no usable logo URL, THEN system
  SHALL not enqueue image dirty work and SHALL classify the profile as
  `source_without_logo` or placeholder-specific reason.
- **AC5.** WHEN `token_image_mirror` successfully mirrors an admitted source,
  THEN it SHALL write a ready `token_image_assets` row and enqueue the exact
  target into `token_profile_current_dirty_targets`.
- **AC6.** WHEN the follow-up profile rebuild runs after AC5, THEN
  `/api/token-radar` SHALL return `profile.identity.logo_url` as a same-origin
  `/api/token-images/{image_id}` path for that target.
- **AC7.** WHEN `/api/token-radar` is inspected for any row, THEN no row SHALL
  expose GMGN, OKX, Binance, or other remote provider image URL as public
  `profile.identity.logo_url`.
- **AC8.** WHEN existing ready profiles contain source logo candidates but no
  image queue/assets rows, THEN the repair path SHALL enqueue mirror work
  without re-running Token Radar projection or provider profile refresh.
- **AC9.** WHEN diagnostics summarize icon readiness, THEN every missing icon
  SHALL fall into exactly one lifecycle status from this spec.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Requeue loop for unsupported images. | High | Source admission must skip terminal unsupported sources and profile projection must stop labelling them as executable pending work. |
| Duplicate admission from multiple workers. | Medium | Keep one source-admission owner; DB primary key remains `(source_url_hash, target_type, target_id)`. |
| Over-broad backfill downloads stale or irrelevant logos. | Medium | Backfill only enqueues current ready profile/evidence sources or bounded Token Radar/profile targets; mirror worker owns IO. |
| Provider image source disallows hotlinking or blocks browser display. | Low | This is expected; local mirror downloads and serves same-origin cache. |
| Remote media is SVG/HTML/unsupported. | Medium | Mirror marks unsupported; public profile remains NULL with non-pending quality flag. |
| Large provider raw payload leaks into queue rows. | Medium | `raw_ref_json` is bounded provenance only. |

## Evolution Path

After the KISS fix, a small ops diagnostic can report icon readiness by lifecycle
status for current Token Radar rows. Do not add that before the durable mirror
loop works. If multi-process or distributed provider-image download quotas become
necessary, add a separate provider media gateway spec; do not complicate the
current single-service queue contract.

## Alternatives Considered

- **Frontend remote fallback** — rejected because provider URLs may be blocked,
  non-displayable, or unstable, and the current contract explicitly requires
  same-origin `/api/token-images/{image_id}`.
- **API remote proxy revival** — rejected because `/api/token-image?url=...` was
  intentionally removed. It would reintroduce SSRF/cache/security concerns and
  bypass durable media state.
- **Have Token Radar projection write icons** — rejected because profile/icon is
  outside `factor_snapshot_json` and Token Radar should not own provider media.
- **Have every source writer enqueue images independently** — rejected as less
  KISS: GMGN OpenAPI, Binance Web3, GMGN stream evidence, OKX exact evidence,
  and CEX profile would each need duplicate source parsing and terminal checks.
- **Scan all provider profile tables inside token_image_mirror** — rejected
  because mirror worker's input contract is a durable dirty queue; broad scans
  hide missed admission and fight the Kappa/CQRS worker model.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Treat provider logo URLs as mirror source inputs; serve only local `/api/token-images/{image_id}` URLs; classify every missing icon into one lifecycle status; keep image download IO in `token_image_mirror`. |
| Ask first | Adding a new ops diagnostic surface, widening backfill beyond current ready profile/evidence rows, changing media allowlist, or adding provider media health persistence. |
| Never | Raw provider image URL fallback in frontend/API; inline image downloads from Token Radar/profile projection; new DB tables for this fix; symbol-only DEX logo matching; writing provider outage as token-level image failure. |
