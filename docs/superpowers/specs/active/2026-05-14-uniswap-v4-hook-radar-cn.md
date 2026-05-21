# Uniswap V4 Hook Radar — 独立链上发现维度 Spec

**Status**: Draft, awaiting review
**Date**: 2026-05-14
**Owner**: Claude with Qinghuan
**Scope**: 在 `gmgn-twitter-intel` 服务里新增一条独立的链上数据维度——Uniswap V4 hook 发现与排行榜。仅 ETH 主网。仅 pull-based（无实时告警）。无 Twitter 联动。本文是 spec，不含 alembic 完整 migration、文件级任务、PR 拆分（那些进 plan）。

**Related**:

- `docs/ARCHITECTURE.md`、`docs/CONTRACTS.md`、`docs/DESIGN_DISCIPLINE.md`、`docs/TESTING.md`
- `docs/superpowers/specs/active/2026-05-10-providers-and-enforcement-design-cn.md`（provider 抽象惯例）
- `docs/superpowers/specs/active/2026-05-12-gmgn-dex-market-provider-split-cn.md`（DEX 类 provider 拆分模式参考）
- `docs/superpowers/specs/active/2026-05-08-signal-lab-pulse-agent-hard-cut-cn.md`（pulse_candidates 现状 — 本 spec 明确**不复用**这张表）

---

## 一句话结论

新增独立的 **Hook Radar** 维度：周期拉取 HookRank 公开 subgraph 发现 ETH 主网上的 Uniswap V4 hook，结合 Etherscan 元数据做静态风险分级，落两张新表（`hook_addresses` + `hook_snapshots`），提供 `/api/hook-radar/*` REST，前端新增 `/hook-radar` 路由与 `HookRadarWorkbench`。**不复用 `pulse_candidates`**（TargetType invariant 不允许，pulse_status 词汇与 hook 语义错位）。**不接入 Twitter 信号**（与既有 Pulse 解耦）。**不做实时告警 / WebSocket 推送**（MVP 是发现 + 排行榜）。Provider 层抽象成 `HookRadarFeedProvider` Protocol，一期实现 `HookRankSubgraphFeedProvider`，二期可平滑替换为 Uniswap 官方 v4-subgraph 或 Envio fork 而不影响上游消费者。

## 1. 当前事实与约束

- Uniswap V4 主网 PoolManager 地址：`0x000000000004444c5dc75cb358380d2e3de08a90`
- HookRank 已建好 hook 维度 schema 的公开 subgraph：`https://api.studio.thegraph.com/query/83028/univ4/v300`（免费、无运维、与 hookrank.io 网页同源）
- Uniswap 官方 v4-subgraph 按 pool 维度建模，hook 维度聚合需自己写
- 项目既有 `UpstreamClientProtocol`（`src/gmgn_twitter_intel/domains/ingestion/providers.py:9-27`）只装载单一 GMGN WebSocket upstream，hook radar 不走 ingestion 通道——它不是事件流，是 pull discovery
- `pulse_candidates.target_type` 是 `Literal["Asset", "CexToken"]`（`domains/pulse_lab/interfaces.py:43`），`pulse_status` 是为 token 设计的 5 档 enum
- `asset_venues`、`asset_identity_evidence`、`price_feeds` 已有 `chain + address` 字段，但其语义是"该 asset 在该 venue 上的标识"——hook 不是 asset，硬塞会污染语义
- 既有 DEX provider 模式：`AssetMarketProviders`（frozen dataclass）+ `DexMarketStreamProvider`（Protocol）+ `OkxDexWebSocketMarketProviderAdapter`（实现）—— hook radar 沿用此模式
- 直接 psycopg3 + alembic 38 个 migration，最新 `20260514_0038`

## 2. 第一性原理

### 2.1 Hook 是独立维度，不是 Asset 子类

Hook 合约不是可交易资产；它是"协议级行为修饰器"。它没有 canonical_symbol、没有 price、没有 holder。把它塞进 `assets / pulse_candidates` 会逼着既有表加 nullable 字段或加 status 值，污染 token-centric invariant。独立表 + 独立路由是更干净的边界。

### 2.2 Pull discovery 不需要事件总线

Hook radar 的输入是"主网上新增/活跃的 hook"，这是一个**世界状态**而非事件流。subgraph 拉取一次得到当前快照，比订阅 PoolManager.Initialize 事件再自己重建状态简单一个量级。不走 PG LISTEN/NOTIFY，不走 WebSocket 推，不走 ingestion 通道——只是一个周期 worker。

### 2.3 一期被一个第三方 schema 锁死是可接受的风险

HookRank 的 subgraph 把 hook 维度做完了；Uniswap 官方 subgraph 把这部分留给消费者自己聚合。MVP 阶段省 2-3 天的代价，换"如果 HookRank 项目停摆要切换 provider"的尾部风险。用 Protocol 隔离上游消费者，这个风险被钉死在一个 adapter 文件里。这是项目里 OKX/GMGN provider 已经验证过的形态，不是新引入的范式。

### 2.4 风险分级先静态，不要等时序

MVP 不做"TVL 突变""volume 突降"这类时序异常——那是 V2。静态元数据（verified / has_admin / uses_return_delta / immutable / hook_flags bitmap）在 hook 发现的同一刻就能算出 `risk_tier + risk_reasons`。这意味着即使 snapshot loop 失败，发现 loop 仍能交付完整的"新 hook + 风险分级"价值。两个 loop 解耦。

## 3. 目标

1. **发现 ETH 主网 Uniswap V4 hook**：周期拉 HookRank subgraph，把新发现的 hook 落 `hook_addresses` 表（UPSERT），全量历史也按需 lazy 回填。
2. **静态风险分级**：每个新 hook 在发现时通过 `HookContractInspector` 拉 Etherscan + 解析合约 metadata，落 `risk_tier`（low/medium/high/unknown）+ `risk_reasons`（JSON 数组）。规则集见 §6。
3. **周期 snapshot**：对已知 active hook 周期拉 24h 聚合（pool_count、tvl_usd、volume_24h_usd、fees_24h_usd、swap_count_24h、success_rate），落 `hook_snapshots`。
4. **HTTP API**：`/api/hook-radar/feed`（排序排行榜）+ `/api/hook-radar/hook/{hook_id}`（详情 + 近 7 天快照）。
5. **前端 Hook Workbench**：新增 `/hook-radar` 与 `/hook-radar/:hookId` 两条路由，与 `/signal-lab` 并列；CockpitTopbar / CockpitSideRail 加入口。
6. **Provider 可替换**：所有上游消费者只依赖 `HookRadarFeedProvider` Protocol，HookRank adapter 是其中一个实现。

## 4. 非目标

- **不复用 `pulse_candidates`**：见 §2.1 与现状 §1，硬约束。
- **不接 Twitter 信号**：用户在 brainstorming 阶段明确选了"独立 Hook 雷达维度"（非交叉验证）。
- **不实时告警**：无 WebSocket channel、无 Telegram push、无 Tenderly Alert 集成（V2）。
- **不多链**：仅 ETH 主网。`chain_id` 字段在 schema 里存在但 MVP 永远是 `'ethereum'`。多链是 V2。
- **不做时序异常检测**：TVL/volume 突变检测、failed tx 飙升检测都是 V2。
- **不接治理动作监控**：admin/upgrade/pause function call 监听是 V2 的 Tenderly 集成范畴。
- **不接 ingestion / event bus**：hook radar 是 pull-only，不入 GMGN ingestion 路径。
- **不做 dual-write 兼容层**：本 spec 是全新维度，没有"老路径"要兼容。
- **不做完整历史回填**：subgraph 一次拉到的就是当前世界状态；老快照按需 lazy fill（用户打开详情页时如果发现 < 7 天快照，触发一次补采）。

## 5. 目标架构

### 5.1 数据模型

新建两张表（独立于 `assets` / `pulse_candidates`）：

```sql
CREATE TABLE hook_addresses (
    hook_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chain_id           TEXT NOT NULL,                  -- MVP 恒为 'ethereum'
    address            TEXT NOT NULL,                  -- checksummed hex (EIP-55)
    first_seen_at      TIMESTAMPTZ NOT NULL,           -- HookRank firstSeen 字段
    deployer           TEXT,                           -- 部署者地址
    contract_verified  BOOLEAN,                        -- Etherscan source verified
    is_immutable       BOOLEAN,                        -- EIP-1967 proxy detection 反义
    has_admin_fn       BOOLEAN,                        -- admin/upgrade/pause/setOwner 选择器存在
    uses_return_delta  BOOLEAN,                        -- beforeSwap/afterSwapReturnDelta flag
    hook_flags         JSONB NOT NULL DEFAULT '{}',    -- 14 个 V4 flag bitmap 解码后的命名 dict
    risk_tier          TEXT NOT NULL,                  -- 'low' | 'medium' | 'high' | 'unknown'
    risk_reasons       JSONB NOT NULL DEFAULT '[]',    -- ['unverified', 'has_pause', ...]
    metadata_json      JSONB NOT NULL DEFAULT '{}',    -- 余下 etherscan / sourcify 字段
    refreshed_at       TIMESTAMPTZ NOT NULL,
    UNIQUE (chain_id, address)
);

CREATE INDEX hook_addresses_first_seen_idx ON hook_addresses (first_seen_at DESC);
CREATE INDEX hook_addresses_risk_idx       ON hook_addresses (risk_tier);

CREATE TABLE hook_snapshots (
    snapshot_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hook_id            UUID NOT NULL REFERENCES hook_addresses(hook_id) ON DELETE CASCADE,
    captured_at        TIMESTAMPTZ NOT NULL,
    pool_count         INTEGER,
    tvl_usd            NUMERIC(38, 6),
    volume_24h_usd     NUMERIC(38, 6),
    fees_24h_usd       NUMERIC(38, 6),
    swap_count_24h     INTEGER,
    success_rate       NUMERIC(6, 4),                  -- 0.0–1.0
    raw_json           JSONB NOT NULL DEFAULT '{}'     -- subgraph 原始响应（debug 用）
);

CREATE INDEX hook_snapshots_hook_time_idx ON hook_snapshots (hook_id, captured_at DESC);
```

**FK 索引规范**：按既有 `feedback_hard_cut_style` 与 `project_fk_index_gap` 偏好，`hook_snapshots.hook_id` FK 自带 index（上面 `hook_snapshots_hook_time_idx` 复合索引前缀已覆盖）。

### 5.2 Domain 层（`src/gmgn_twitter_intel/domains/hook_radar/`）

```
domains/hook_radar/
  __init__.py
  interfaces.py            # 类型：HookFeedItem, HookSnapshotFeed, HookContractInspection,
                           #       HookAddress, HookSnapshot, HookFeedRow, HookDetail
  providers.py             # Protocol：HookRadarFeedProvider, HookContractInspector
  risk_rules.py            # 纯函数：score_risk(inspection, feed_flags) -> (tier, reasons)
  services/
    __init__.py
    hook_radar_service.py  # 用例编排：discover()、snapshot()、get_feed()、get_detail()
  runtime/
    __init__.py
    hook_radar_worker.py   # async loop：周期 discover + snapshot
  storage/
    __init__.py
    hook_address_store.py  # CRUD：upsert_hook_address(), list_active_addresses()
    hook_snapshot_store.py # CRUD：insert_snapshot(), recent_for_hook()
```

### 5.3 Provider 抽象

```python
# domains/hook_radar/providers.py
class HookRadarFeedProvider(Protocol):
    """上游 hook 发现 & 聚合数据源。一期 = HookRank subgraph。"""

    async def fetch_hooks(
        self, *, chain_id: str, since: datetime | None
    ) -> list[HookFeedItem]:
        """发现：返回 since 以来出现的 hook 列表（含 returnDelta flag、firstSeen 等）"""

    async def fetch_snapshots(
        self, *, chain_id: str, addresses: list[str]
    ) -> list[HookSnapshotFeed]:
        """快照：返回当前 24h 聚合指标"""

class HookContractInspector(Protocol):
    """从链上/Etherscan 拉合约元数据 —— 风险分级专用，独立于 feed。"""

    async def inspect(
        self, *, chain_id: str, address: str
    ) -> HookContractInspection:
        """返回 verified、has_admin_fn、is_immutable、selector list 等"""
```

实现（adapter）：

- `infrastructure/hook_radar/hookrank_subgraph_provider.py`：`HookRankSubgraphFeedProvider`
  - 用 httpx AsyncClient POST GraphQL
  - 把 HookRank 响应映射到 `HookFeedItem` / `HookSnapshotFeed`
  - 失败：raise `HookRadarUpstreamError`，由 service 层 catch + log，不让 worker 死
- `infrastructure/hook_radar/etherscan_inspector.py`：`EtherscanHookInspector`
  - Etherscan API: getsourcecode (verified flag + ABI)
  - bytecode + EIP-1967 storage slot 检测 immutable
  - 用 4byte 数据库匹配 admin/upgrade/pause/setOwner 选择器

Wiring：`app/runtime/providers_wiring.py` 加 `_hook_radar_factory()`，与 `_gmgn_upstream_factory()` 同形态。

### 5.4 Worker 调度

`HookRadarWorker`（仿 `PulseCandidateWorker` 但更简单——纯 pull，无 LISTEN/NOTIFY 唤醒）：

```
class HookRadarWorker:
    discovery_interval_seconds: int = 300    # 默认 5min
    snapshot_interval_seconds: int = 900     # 默认 15min

    async def discovery_loop():
        while not stopping:
            since = last_seen_at_or_none()
            feed_items = await feed_provider.fetch_hooks(chain_id='ethereum', since=since)
            for item in feed_items:
                inspection = await inspector.inspect(chain_id='ethereum', address=item.address)
                tier, reasons = risk_rules.score_risk(inspection, item.flags)
                await store.upsert_hook_address(...)
            await sleep(discovery_interval_seconds)

    async def snapshot_loop():
        while not stopping:
            addresses = await store.list_active_addresses(limit=200)  # 头部活跃 hook
            feeds = await feed_provider.fetch_snapshots(chain_id='ethereum', addresses=addresses)
            for feed in feeds:
                await snapshot_store.insert_snapshot(...)
            await sleep(snapshot_interval_seconds)
```

**"active hook" 定义**：在最近 24h 内任一 `hook_snapshots` 行的 `swap_count_24h > 0` 或 `tvl_usd > 0`；如果连一次 snapshot 都没有（刚发现的 hook），也算 active 一个周期以采集首个快照。`list_active_addresses(limit=200)` 按 latest `volume_24h_usd` 倒序取前 N，避免对历史长尾死 hook 重复拉取浪费配额。

启动注册：`app/runtime/app.py` 在 `PulseCandidateWorker` 启动旁加 `asyncio.create_task(worker.discovery_loop())` 与 `asyncio.create_task(worker.snapshot_loop())`，统一 lifecycle 与既有 worker 对齐（startup wait、shutdown 取消、异常 supervisor）。

### 5.5 HTTP API（`app/surfaces/api/http.py`）

```
GET /api/hook-radar/feed
    Query: sort=volume|tvl|newest（默认 volume）
           limit=int（默认 50，最大 200）
           risk_tier=low|medium|high|unknown（可选过滤）
    Response: list[HookFeedRow]
      {
        hook_id, chain_id, address, first_seen_at,
        risk_tier, risk_reasons,
        latest_snapshot: {
          captured_at, pool_count,
          tvl_usd, volume_24h_usd, fees_24h_usd,
          swap_count_24h, success_rate
        } | null
      }

GET /api/hook-radar/hook/{hook_id}
    Query: window_hours=int（默认 168 = 7 天，最大 720 = 30 天）
    Response: HookDetail
      {
        ...identity fields,
        etherscan_url,                       # 服务端拼好
        snapshots: [近 window_hours 内 hook_snapshots 倒序，最多 200 条]
      }
```

错误：标准 FastAPI 异常映射，沿用既有 error envelope。

**无 WebSocket channel**——`PublicWebSocketHub` 不接 hook-radar 主题，保持现有边界干净。

### 5.6 前端（`web/src/features/hook-radar/`）

新建 feature 目录，与 `signal-lab/` `live/` `cockpit/` 平级：

```
web/src/features/hook-radar/
  api/
    useHookRadarFeedQuery.ts              # React Query, key: ['hook-radar', 'feed', {sort, riskTier}]
    useHookDetailQuery.ts                 # key: ['hook-radar', 'detail', hookId]
  model/
    hookRadarTypes.ts                     # TS 类型，从后端契约镜像
  ui/
    HookRadarPage.tsx                     # 路由容器
    HookRadarWorkbench.tsx                # 主视图：sort tabs + 排行榜表
    HookDetailRoutePage.tsx               # 详情页（对齐 PulseDetailRoutePage 结构）
    HookRiskBadge.tsx                     # low/medium/high/unknown 视觉
    HookSnapshotSparkline.tsx             # 近 7 天小折线
    hookRadar.css                         # 局部样式
  index.ts                                # barrel
```

`web/src/shared/query/queryKeys.ts` 加 `hookRadar` 命名空间。

路由（`AppRoutes.tsx`，紧邻 signal-lab）：

```tsx
<Route path="hook-radar" element={<HookRadarPage />} />
<Route path="hook-radar/:hookId" element={<HookDetailRoutePage />} />
```

导航入口：
- `CockpitTopbar.tsx` 顶部 nav 加 "Hook Radar"
- `CockpitSideRail.tsx` 侧边导航加同名条目
- `MobileRouteNav.tsx` 移动端顶级路由入口

视觉风格：跟现有 `SignalLabWorkbench` 一致（表格 + 行高 + 风险色 + 时间格式），不引入新 design tokens。

## 6. 风险分级规则（MVP）

仅基于**静态元数据 + 合约 flags**——即使 snapshot loop 失败，发现 loop 仍能交付完整分级。

| 维度 | 检测来源 | 触发条件 | 影响 |
|---|---|---|---|
| 合约未验证 | Etherscan getsourcecode | source code 为空 | +High |
| 升级能力 | bytecode 4byte 匹配 | 包含 `upgrade()` / `setOwner()` / `transferOwnership()` 选择器 | +High |
| 暂停能力 | bytecode 4byte 匹配 | 包含 `pause()` / `setPaused()` 选择器 | +High |
| 经济操纵能力 | HookRank feed flag | `beforeSwapReturnDelta` 或 `afterSwapReturnDelta` 为 true | +Medium |
| Proxy 可升级 | EIP-1967 storage slot | implementation slot 非空 | +Medium |
| Timelock / 多签缓解 | Etherscan owner 地址 | owner 是已知 timelock / GnosisSafe | -Medium |

聚合规则：
- 任一 +High → `risk_tier = 'high'`
- 否则 ≥ 2 个 +Medium → `risk_tier = 'high'`
- 1 个 +Medium → `risk_tier = 'medium'`
- 全部缓解 → `risk_tier = 'low'`
- inspector 拉不到数据 → `risk_tier = 'unknown'`

`risk_reasons` 是触发的维度名字符串数组（例：`["unverified", "has_pause", "uses_return_delta"]`），UI 直接展示原因徽章而不是数字分。

规则全部在 `risk_rules.py` 纯函数实现，阈值通过 config 注入（key：`hook_radar.risk.*`），方便 V2 调整。

## 7. 配置（`app/config/`）

新增 key（dotted notation 沿用既有惯例）：

```
hook_radar.enabled                       bool, 默认 true
hook_radar.discovery_interval_seconds    int,  默认 300
hook_radar.snapshot_interval_seconds     int,  默认 900
hook_radar.feed.provider                 str,  默认 'hookrank'
hook_radar.feed.hookrank.endpoint        str
hook_radar.inspector.etherscan_api_key   secret
hook_radar.snapshot.top_n_hooks          int,  默认 200
```

`hook_radar.inspector.etherscan_api_key` 走既有 secret loader 路径（`docs/SECURITY.md`）。

## 8. 测试矩阵（按 `docs/TESTING.md`）

| 层 | 文件位置 | 测试内容 |
|---|---|---|
| 单元 | `tests/unit/domains/hook_radar/test_risk_rules.py` | 每条风险规则一个 case + 聚合逻辑（high override medium、unknown 兜底） |
| 单元 | `tests/unit/domains/hook_radar/test_hookrank_response_parsing.py` | HookRank GraphQL 响应 → `HookFeedItem` / `HookSnapshotFeed` 映射 |
| 单元 | `tests/unit/domains/hook_radar/test_etherscan_inspector.py` | selector 匹配 + EIP-1967 检测（用 fixture bytecode） |
| 集成 | `tests/integration/domains/hook_radar/test_worker_discovery.py` | 真实 PG（无 mock）+ stub feed/inspector → 一轮 discovery + snapshot 落表 |
| 集成 | `tests/integration/app/surfaces/api/test_hook_radar_api.py` | 真实 PG + seed + 调 `/api/hook-radar/feed` 与 `/hook/{id}` |
| 契约 | `tests/contract/hook_radar/test_feed_provider_contract.py` | HookRankSubgraphFeedProvider 实现 Protocol 所有方法 |
| 组件 | `web/tests/component/features/hook-radar/HookRadarWorkbench.test.tsx` | sort tab 切换、风险徽章渲染、空态 |
| 组件 | `web/tests/component/features/hook-radar/HookDetailRoutePage.test.tsx` | 详情渲染 + 路由参数解析 |
| E2E  | `web/tests/e2e/golden-paths/hook-radar.spec.ts` | 进 /hook-radar → 切排序 → 点详情 → 看风险原因 |

按 [[feedback_hard_cut_style]]：集成测试必须打真实 PG，不 mock。

## 9. 演化路径（V2 候选，明确不在本 spec 范围）

- 接 Tenderly Alerts：治理动作 / failed tx 飙升 → push 到 Telegram / 邮件
- 接 Uniswap 官方 v4-subgraph 或 fork Envio multichain indexer：换 adapter 不动 service
- 多链：Base、Unichain、Arbitrum、Optimism、Polygon —— provider 层加 chain_ids 维度
- TVL/Volume 异常检测算法：z-score / ratio 突变
- Hook 与 Twitter 信号交叉（反向链路）：链上异常事件回查谁在推 → 触发既有 notification 通道
- WebSocket 实时推送：新 hook + 高风险即时通知前端

## 10. 工时估算（粗）

| 项 | 工作日 |
|---|---|
| alembic migration + 数据模型 | 0.5 |
| HookRankSubgraphFeedProvider + EtherscanHookInspector + 契约测试 | 1.0 |
| risk_rules 纯函数 + 单元测试 | 0.5 |
| HookRadarWorker + 集成测试 | 1.0 |
| HTTP API + 集成测试 | 0.5 |
| 前端 Workbench + 详情页 + 导航入口 + 组件测试 | 1.5 |
| E2E + 文档（CONTRACTS / RELIABILITY 增补） | 0.5 |
| **合计** | **5.5** |

## 11. 验证 checklist（落地后）

- [ ] 单元 / 集成 / 组件 / E2E 全绿（按 `docs/TESTING.md` 命令）
- [ ] `uv run gmgn-twitter-intel --help` 包含 hook radar 相关命令（如有）
- [ ] HookRadarWorker 启动后 30min 内 `hook_addresses` 至少有 N > 50 行（HookRank 主网 hook 数量级）
- [ ] `risk_tier` 分布合理（不应全是 'unknown' —— inspector 起作用了）
- [ ] `/api/hook-radar/feed?sort=volume` 返回非空且按 volume_24h_usd 倒序
- [ ] 前端 `/hook-radar` 路由可访问，导航入口在 Topbar / SideRail / MobileRouteNav 三处都存在
- [ ] HookRank endpoint 不可用时 worker 不死（仅 log error + 下个周期重试）
- [ ] 无 ingestion / pulse_candidates / asset 表的写入（hook radar 完全独立）

## 12. 不变式（invariants）

- `hook_addresses.chain_id = 'ethereum'`（MVP 期间唯一允许值，约束在 service 层 ValueError 护栏，不在 DB CHECK —— 多链 V2 时只改 service）
- `hook_addresses.risk_tier ∈ {low, medium, high, unknown}`
- 同一 `(chain_id, address)` 在 `hook_addresses` 唯一
- 写 `hook_snapshots` 必须先有对应 `hook_addresses` 行（FK 保证）
- Hook Radar 不写 `assets / asset_venues / pulse_candidates / events / event_entities` 任一表
